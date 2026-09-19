"""
Analizador Táctico — Asignación automática de equipo por color de camiseta
=============================================================================
El pipeline (run_inference.py + calibrate.py) detecta y trackea jugadores
pero no sabe de qué equipo es cada uno. Este módulo lo infiere del color
de la camiseta: muestrea frames del video, extrae el color de torso de
cada jugador detectado, agrupa esos colores en 2 clusters (KMeans) y le
asigna a cada track_id el equipo por voto mayoritario de sus muestras.

Flujo:
    df = pd.read_parquet("data/outputs/partido_clip2_coords_field.parquet")
    df_con_equipo = asignar_equipos("data/videos/partido_clip2.mp4", df)
    df_con_equipo.to_parquet(..., index=False)

La columna `team` resultante ("home" / "away" / NaN) es exactamente la que
espera app/components/map_view.py para colorear por equipo en vez de por
track_id individual.

LIMITACIONES CONOCIDAS
-----------------------
Esto se rompe si los dos equipos usan colores parecidos entre sí (dos
camisetas oscuras, por ejemplo), o muy parecidos al del árbitro/arquero
rival, porque el clustering deja de separar bien las dos nubes de color.
También se rompe con una camiseta VERDE: se descarta como si fuera pasto
(ver H_PASTO_MIN/MAX más abajo). Son limitaciones aceptadas de este enfoque
puramente visual — el fallback en esos casos es asignación manual (una
columna `team` cargada a mano).

Aparte, y esto no es una limitación del método sino del tracking de
entrada: en este dataset ByteTrack a veces reasigna un mismo track_id
numérico a objetos de OTRA clase más adelante en el video (un jugador
pierde el track y ese número reaparece después en un árbitro o la
pelota). Por eso acá `team` se calcula fila por fila restringido a
class_name en ("player", "goalkeeper") — nunca "por track_id en
general" — para que una fila de árbitro/pelota no herede por error el
equipo de un jugador que alguna vez compartió ese mismo número.

Uso por consola:
    python src/analysis/team_assignment.py data/videos/partido_clip2.mp4 \\
        data/outputs/partido_clip2_coords_field.parquet
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

# ── Filtro de píxeles válidos para color de camiseta (HSV, rangos de OpenCV:
# H 0-179, S/V 0-255) ─────────────────────────────────────────────────────
V_MIN_SOMBRA = 35     # por debajo: sombra/negro — no aporta info de color
S_MIN_GRIS = 25       # por debajo: casi sin color (gris, blanco lavado, pasto pisado)
V_MAX_GRIS = 200      # ... salvo que además sea MUY brillante: eso es tela
#                        blanca real (hay equipos que juegan de blanco — el
#                        propio clip de prueba, Noruega vs Francia, es blanco
#                        vs rojo), no pasto apagado ni una línea de cal.

# Pasto de fondo colándose en el recorte: con bboxes chicos (jugador a 15-40px
# de alto en un plano general) el margen del bbox alrededor del jugador real
# alcanza para que algunas filas del "tercio superior" sean cancha, no
# camiseta — y el pasto (verde vívido) NO es gris/desaturado, así que el
# filtro de arriba no lo descarta solo. Se lo descarta aparte, por matiz:
# H 35-95 (verde, rango de OpenCV 0-179) con saturación media/alta.
# Contrapartida: un equipo de camiseta VERDE se pierde con este filtro —
# limitación aceptada, misma familia que la de "colores parecidos" del
# docstring del módulo.
H_PASTO_MIN, H_PASTO_MAX = 35, 95
S_PASTO_MIN = 60

MIN_PIXELES_TORSO = 15  # mínimo de píxeles válidos en el recorte para confiar en la mediana

# ── Muestreo y votación ─────────────────────────────────────
N_MUESTRAS_DEFAULT = 30       # frames a muestrear a lo largo del video
MIN_MUESTRAS_TRACK = 2        # mínimo de muestras válidas por track para confiar en el voto


# ── Color de torso ───────────────────────────────────────────
def extraer_color_torso(frame: np.ndarray, bbox: tuple[float, float, float, float]) -> tuple[int, int, int] | None:
    """
    Color dominante de la camiseta de un jugador, a partir de su bounding box.

    Se recorta el tercio superior (altura) y la mitad central (ancho) del
    bbox: ahí es más probable encontrar tela de la camiseta y no pasto de
    fondo, pantalón/piernas, ni el margen que suele quedar entre el borde
    del bbox y el jugador real.

    El filtro de píxeles válidos (sombras, gris/pasto pisado, pasto vívido de
    fondo) se calcula en HSV — más robusto que RGB a cambios de iluminación,
    porque separa el color (H/S) del brillo (V). Ese último filtro importa
    más de lo que parece: con jugadores chicos en cámara (plano general, bbox
    de ~15-40px de alto) el recorte del tercio superior casi siempre incluye
    algo de cancha de fondo, y el pasto es verde SATURADO — el filtro de
    "gris/desaturado" no lo agarra, hace falta descartarlo aparte por matiz
    (H 35-95). El color final, en cambio, se mide sobre el RGB original de
    esos mismos píxeles: la mediana de un canal circular como el matiz (Hue)
    no está bien definida cuando el color cae cerca del corte 0°/360° — y el
    rojo, justo el caso de prueba de este pipeline, cae ahí mismo.

    Args:
        frame: imagen BGR (la que devuelve cv2.VideoCapture.read()).
        bbox: (x1, y1, x2, y2) en píxeles — mismo sistema que x1..y2 del parquet.

    Returns:
        (r, g, b) del color dominante, o None si el bbox es inválido, cae
        fuera del frame, o no quedan suficientes píxeles válidos tras filtrar.
    """
    if frame is None or frame.size == 0:
        return None

    alto_frame, ancho_frame = frame.shape[:2]
    x1, x2 = sorted((float(bbox[0]), float(bbox[2])))
    y1, y2 = sorted((float(bbox[1]), float(bbox[3])))

    # Recorte a los límites del frame — un bbox del detector puede asomarse
    # apenas afuera del cuadro en los bordes de la imagen.
    x1, x2 = np.clip([x1, x2], 0, ancho_frame)
    y1, y2 = np.clip([y1, y2], 0, alto_frame)
    ancho, alto = x2 - x1, y2 - y1
    if ancho < 4 or alto < 4:
        return None

    torso_y1 = int(round(y1))
    torso_y2 = int(round(y1 + alto / 3))
    torso_x1 = int(round(x1 + ancho * 0.25))
    torso_x2 = int(round(x1 + ancho * 0.75))
    recorte = frame[torso_y1:torso_y2, torso_x1:torso_x2]
    if recorte.size == 0:
        return None

    hsv = cv2.cvtColor(recorte, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    es_sombra = v <= V_MIN_SOMBRA
    es_gris = (s < S_MIN_GRIS) & (v < V_MAX_GRIS)
    es_pasto = (h >= H_PASTO_MIN) & (h <= H_PASTO_MAX) & (s > S_PASTO_MIN)
    valido = ~es_sombra & ~es_gris & ~es_pasto

    if int(valido.sum()) < MIN_PIXELES_TORSO:
        return None

    pixeles_bgr = recorte[valido]                 # Nx3, en BGR (formato nativo de OpenCV)
    b, g, r = np.median(pixeles_bgr, axis=0)       # mediana por canal — robusta a outliers
    return (int(round(r)), int(round(g)), int(round(b)))


# ── Muestreo de frames ───────────────────────────────────────
def _muestrear_frames(df: pd.DataFrame, n_muestras: int) -> list[int]:
    """
    `n_muestras` números de frame distribuidos uniformemente a lo largo del
    video —no consecutivos—, elegidos entre los frames que efectivamente
    tienen alguna detección de `player` (así no se "gasta" una muestra en un
    frame vacío).
    """
    disponibles = np.sort(df.loc[df["class_name"] == "player", "frame"].unique())
    if disponibles.size == 0:
        return []
    n = min(n_muestras, disponibles.size)
    indices = np.linspace(0, disponibles.size - 1, n).round().astype(int)
    return sorted({int(f) for f in disponibles[indices]})


def _recolectar_muestras_color(cap: cv2.VideoCapture, df: pd.DataFrame,
                                frames: list[int]) -> pd.DataFrame:
    """
    Recorre los frames muestreados y extrae el color de torso de cada
    jugador de campo (`player`) detectado ahí. Los arqueros quedan afuera
    a propósito — ver _asignar_arqueros(), que los resuelve por geometría
    en vez de por color.
    """
    filas = []
    detecciones = df[(df["class_name"] == "player") & df["frame"].isin(frames)]

    for frame_num, sub in detecciones.groupby("frame"):
        # El campo "frame" del parquet es 1-based (run_inference.py cuenta
        # frame_idx antes de guardar), OpenCV es 0-based: se resta 1 al buscar.
        cap.set(cv2.CAP_PROP_POS_FRAMES, float(frame_num - 1))
        ok, imagen = cap.read()
        if not ok or imagen is None:
            continue
        for fila in sub.itertuples(index=False):
            color = extraer_color_torso(imagen, (fila.x1, fila.y1, fila.x2, fila.y2))
            if color is not None:
                filas.append({"track_id": int(fila.track_id),
                              "r": color[0], "g": color[1], "b": color[2]})

    return pd.DataFrame(filas, columns=["track_id", "r", "g", "b"])


# ── Clustering y voto mayoritario ─────────────────────────────
def _asignar_por_clustering(muestras: pd.DataFrame,
                             min_muestras_track: int) -> tuple[dict[int, str], np.ndarray]:
    """
    KMeans(2) sobre los colores de torso muestreados, y voto mayoritario por
    track_id: a cada jugador se lo asigna al cluster que más veces "ganó"
    entre todas sus muestras válidas, no a partir de una sola detección
    (que puede estar mal por oclusión, desenfoque o sombra).

    Tracks con menos de `min_muestras_track` muestras válidas, o con empate
    exacto entre los dos clusters, quedan sin asignar (None) — mejor no
    asignar que forzar una asignación dudosa.

    Returns:
        (equipo_por_track, centros_cluster) — el dict mapea track_id -> "home"/
        "away"; centros_cluster es un array 2x3 con el RGB de cada cluster
        (para poder mostrarlo y verificar a ojo que separó bien).
    """
    if len(muestras) < 2:
        return {}, np.empty((0, 3))

    colores = muestras[["r", "g", "b"]].to_numpy(dtype=float)
    kmeans = KMeans(n_clusters=2, n_init=10, random_state=42).fit(colores)
    muestras = muestras.assign(cluster=kmeans.labels_)

    equipo_por_track: dict[int, str] = {}
    for track_id, sub in muestras.groupby("track_id"):
        if len(sub) < min_muestras_track:
            continue
        conteo = sub["cluster"].value_counts()
        if len(conteo) > 1 and conteo.iloc[0] == conteo.iloc[1]:
            continue  # empate 50/50 entre los dos clusters — no hay mayoría clara
        cluster_ganador = int(conteo.idxmax())
        equipo_por_track[int(track_id)] = "home" if cluster_ganador == 0 else "away"

    return equipo_por_track, kmeans.cluster_centers_


def _asignar_arqueros(df: pd.DataFrame, equipo_por_track: dict[int, str]) -> dict[int, str]:
    """
    A los arqueros no se los mete en el clustering de color: su camiseta
    suele ser de un tercer color, distinto al de ambos equipos, y mezclarlos
    solo ensuciaría los 2 clusters. Se los asigna por geometría: el arquero
    que en promedio aparece más cerca de x=0 defiende ese arco — y por lo
    tanto pertenece al equipo que ataca hacia x=105, es decir, el equipo
    cuyos jugadores de campo (ya clasificados por color) tienen en promedio
    el field_x más bajo.

    Asume que el clip no cruza un entretiempo (no hay cambio de lado dentro
    del mismo video) — con un partido completo de los dos tiempos en un
    solo archivo esta heurística geométrica ya no vale, habría que partir
    el análisis por mitad.
    """
    equipo_por_track = dict(equipo_por_track)  # no mutar el dict del caller
    if "field_x" not in df.columns or not equipo_por_track:
        return equipo_por_track

    jugadores = df[df["track_id"].isin(equipo_por_track)].copy()
    if jugadores.empty:
        return equipo_por_track

    jugadores["team"] = jugadores["track_id"].map(equipo_por_track)
    x_prom_por_equipo = jugadores.groupby("team")["field_x"].mean()
    if len(x_prom_por_equipo) < 2:
        return equipo_por_track  # un solo equipo con jugadores clasificados — no hay con qué comparar

    equipo_ataca_x105 = x_prom_por_equipo.idxmin()  # field_x promedio más bajo → defiende cerca de x=0
    equipo_ataca_x0 = x_prom_por_equipo.idxmax()
    punto_medio = (x_prom_por_equipo.min() + x_prom_por_equipo.max()) / 2

    arqueros = df[df["class_name"] == "goalkeeper"]
    for track_id, sub in arqueros.groupby("track_id"):
        x_prom = sub["field_x"].mean()
        if pd.isna(x_prom):
            continue
        equipo_por_track[int(track_id)] = equipo_ataca_x105 if x_prom < punto_medio else equipo_ataca_x0

    return equipo_por_track


# ── API pública ──────────────────────────────────────────────
def asignar_equipos(video_path, df: pd.DataFrame,
                     n_muestras: int = N_MUESTRAS_DEFAULT,
                     min_muestras_track: int = MIN_MUESTRAS_TRACK) -> pd.DataFrame:
    """
    Asigna equipo ("home" / "away") a cada track_id de jugador o arquero,
    a partir del color de camiseta muestreado del video.

    - `player`: color de torso muestreado en `n_muestras` frames + KMeans(2)
      + voto mayoritario por track (ver _asignar_por_clustering).
    - `goalkeeper`: por geometría, no por color — ver _asignar_arqueros().
    - `referee` / `ball`: quedan siempre con team = NaN.
    - Tracks con muy pocas muestras válidas (< min_muestras_track), o cuyas
      muestras empatan entre los dos clusters, quedan también en NaN antes
      que forzar una asignación dudosa.

    LIMITACIONES CONOCIDAS: si los dos equipos usan colores de camiseta
    parecidos entre sí, el clustering no los separa bien; y una camiseta
    verde se descarta como si fuera pasto (ver extraer_color_torso). En
    ambos casos la asignación sale mal — son limitaciones aceptadas de este
    enfoque por color; el fallback es cargar `team` a mano.

    Args:
        video_path: ruta al video del partido (el mismo que generó el .parquet).
        df: DataFrame de detecciones — necesita frame, track_id, class_name,
            x1, y1, x2, y2 (y field_x si están los arqueros, para geometría).
        n_muestras: frames a muestrear a lo largo del video.
        min_muestras_track: mínimo de muestras válidas por track para
            confiar en su voto mayoritario.

    Returns:
        Copia de `df` con una columna `team` nueva ("home" / "away" / NaN).
        Además, deja metadata en `.attrs["equipos_info"]` (conteo por equipo,
        muestras válidas usadas, y los 2 colores RGB de cada cluster) — la
        usa el CLI de este mismo módulo para el resumen por consola.

    Raises:
        FileNotFoundError: si `video_path` no existe.
        RuntimeError: si el video existe pero OpenCV no lo puede abrir.
        ValueError: si a `df` le faltan columnas requeridas.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"No existe el video: {video_path}")

    columnas_necesarias = {"frame", "track_id", "class_name", "x1", "y1", "x2", "y2"}
    faltantes = columnas_necesarias - set(df.columns)
    if faltantes:
        raise ValueError(f"Al DataFrame le faltan columnas requeridas: {sorted(faltantes)}")

    resultado = df.copy()
    if resultado.empty:
        resultado["team"] = pd.Series(dtype=object)
        resultado.attrs["equipos_info"] = {
            "n_home": 0, "n_away": 0, "n_sin_asignar": 0,
            "n_muestras_validas": 0, "colores_cluster_rgb": [],
        }
        return resultado

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el video (¿códec no soportado?): {video_path}")

    try:
        frames_muestreados = _muestrear_frames(resultado, n_muestras)
        muestras = _recolectar_muestras_color(cap, resultado, frames_muestreados)
    finally:
        cap.release()

    equipo_por_track, centros_cluster = _asignar_por_clustering(muestras, min_muestras_track)
    equipo_por_track = _asignar_arqueros(resultado, equipo_por_track)

    # OJO: ByteTrack no garantiza que un track_id sea siempre la misma clase
    # a lo largo del video — en este dataset hay track_id que aparecen como
    # "player" en algunos frames y como "referee"/"ball" en otros (identidad
    # reasignada tras perder el track). Si se mapeara por track_id sobre TODO
    # el DataFrame, esas filas de árbitro/pelota heredarían por error el
    # equipo del jugador que alguna vez compartió ese mismo número — se
    # restringe el mapeo a filas de persona (player/goalkeeper) a propósito.
    es_persona = resultado["class_name"].isin(("player", "goalkeeper"))
    resultado["team"] = pd.Series(pd.NA, index=resultado.index, dtype=object)
    resultado.loc[es_persona, "team"] = resultado.loc[es_persona, "track_id"].map(equipo_por_track)

    n_home = sum(1 for v in equipo_por_track.values() if v == "home")
    n_away = sum(1 for v in equipo_por_track.values() if v == "away")
    tracks_de_persona = resultado.loc[
        resultado["class_name"].isin(("player", "goalkeeper")), "track_id"
    ].nunique()

    resultado.attrs["equipos_info"] = {
        "n_home": n_home,
        "n_away": n_away,
        "n_sin_asignar": tracks_de_persona - (n_home + n_away),
        "n_muestras_validas": len(muestras),
        "colores_cluster_rgb": [tuple(int(round(c)) for c in centro) for centro in centros_cluster],
    }
    return resultado


# ── CLI ──────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analizador Táctico — Asignación automática de equipo por color de camiseta",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplo:
  python src/analysis/team_assignment.py data/videos/partido_clip2.mp4 \\
      data/outputs/partido_clip2_coords_field.parquet
        """,
    )
    parser.add_argument("video", type=str, help="Ruta al video del partido")
    parser.add_argument("parquet", type=str,
                        help="Ruta al .parquet de coordenadas — se sobreescribe con la columna `team` agregada")
    parser.add_argument("--n-muestras", type=int, default=N_MUESTRAS_DEFAULT,
                        help=f"Frames a muestrear a lo largo del video (default: {N_MUESTRAS_DEFAULT})")
    parser.add_argument("--min-muestras-track", type=int, default=MIN_MUESTRAS_TRACK,
                        help=f"Mínimo de muestras válidas para confiar en el voto de un track (default: {MIN_MUESTRAS_TRACK})")
    parser.add_argument("--out", type=str, default=None,
                        help="Ruta de salida del .parquet; por defecto sobreescribe el de entrada")
    args = parser.parse_args()

    parquet_path = Path(args.parquet)
    if not parquet_path.exists():
        sys.exit(f"[ERROR] Parquet no encontrado: {parquet_path}")

    df_entrada = pd.read_parquet(parquet_path)

    try:
        resultado = asignar_equipos(args.video, df_entrada, n_muestras=args.n_muestras,
                                     min_muestras_track=args.min_muestras_track)
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        sys.exit(f"[ERROR] {e}")

    destino = Path(args.out) if args.out else parquet_path
    resultado.to_parquet(destino, index=False)

    info = resultado.attrs.get("equipos_info", {})
    print(f"\n✅ Columna `team` guardada en: {destino.name}")
    print(f"   🔵 home:         {info.get('n_home', 0)} tracks")
    print(f"   🔴 away:         {info.get('n_away', 0)} tracks")
    print(f"   ⚪ sin asignar:  {info.get('n_sin_asignar', 0)} tracks")
    print(f"   Muestras de color válidas usadas: {info.get('n_muestras_validas', 0)}")

    colores = info.get("colores_cluster_rgb", [])
    if colores:
        print("   Colores representativos de cada cluster (RGB):")
        for i, c in enumerate(colores):
            print(f"     cluster {i}: rgb{c}")
    else:
        print("   ⚠️ No se pudo calcular el clustering (¿muy pocas muestras válidas?).")
