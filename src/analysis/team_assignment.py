"""
Analizador Táctico — Asignación automática de equipo por color de camiseta
=============================================================================
El pipeline (run_inference.py + calibrate.py) detecta y trackea jugadores
pero no sabe de qué equipo es cada uno. Este módulo lo infiere del color
de la camiseta: toma unas pocas muestras de la vida de cada track de
jugador, extrae el color de torso (descartando el pasto con un rango de
color medido en el propio video), agrupa esos colores en 2 clusters
(KMeans) y le asigna a cada track_id el equipo por voto mayoritario de sus
muestras.

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
entrada: un mismo track_id puede tener filas de clases distintas. Hasta
el 16/10/2026 gran parte de eso era un bug de run_inference.py (nombres
de clase desalineados con las cajas tras el tracking, ~0.7% de las
filas); lo que queda es real: el detector etiqueta distinto a la misma
persona según el frame, y en una oclusión el track puede saltar a otra
persona (ByteTrack no distingue clases). Por eso acá `team` se calcula
fila por fila restringido a class_name en ("player", "goalkeeper") —
nunca "por track_id en general" — para que una fila de árbitro/pelota
no herede por error el equipo de un jugador del mismo track.

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

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from src.analysis.lados import detectar_cambio_de_lado, mensaje_cambio_de_lado  # noqa: E402

# ── Segundo tiempo: colores del primero como referencia ──────
# Cada tiempo decide "home = camiseta más clara" por su cuenta; con dos
# camisetas de luminancia parecida eso podría invertirse entre tiempos. El
# segundo tiempo usa como referencia los colores de equipo del primero
# (colores_cluster_rgb de su parquet): cada cluster toma la etiqueta del color
# de referencia más parecido. Distancia de color: ΔE en CIELAB (diferencia
# percibida). Medido: entre las dos mitades de un mismo tiempo, la misma
# camiseta varía ΔE 1–6 (sportivo_crop3, partido_clip2); local contra
# visitante se separan ΔE 29–54. Si el color más parecido queda a más de
# UMBRAL_DELTA_E_REFERENCIA (p.ej. pasar de luz natural a reflectores), NO se
# fuerza: se avisa y se usa la regla de luminancia de este tiempo.
UMBRAL_DELTA_E_REFERENCIA = 12.0   # el doble de la mayor variación natural, < mitad de la menor separación

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
# Esos valores fijos son el FALLBACK. Por defecto el rango de pasto se estima
# del propio video (ver _estimar_pasto): con luz de estadio amarilla, de
# noche, el pasto de sportivo_crop3 tiene matiz 33-37 — justo en el corte de
# H_PASTO_MIN=35 — y en los recortes de torso (jugadores de ~30 px) casi
# todo píxel es una mezcla camiseta/pasto con matiz ~30 que pasaba el filtro
# fijo: solo se descartaba el 13% del recorte como pasto.
N_FRAMES_PASTO = 20       # frames muestreados para estimar el color del pasto
VENTANA_H_PASTO = 15      # candidatos a pasto: matiz a ± esto del pico dominante del fondo
K_MAD_PASTO = 5.0         # rango de pasto = mediana ± K desvíos robustos (MAD × 1.4826)
MIN_SEMIANCHO_H_PASTO = 3 # semiancho mínimo del rango de matiz (pasto muy parejo → MAD ~0)
MARGEN_H_PASTO = 2        # margen extra de matiz a cada lado

MIN_PIXELES_TORSO = 15  # mínimo de píxeles válidos en el recorte para confiar en la mediana

# ── Muestreo y votación ─────────────────────────────────────
# Muestreo por track (default): hasta MUESTRAS_POR_TRACK frames de la vida de
# cada track de jugador, repartidos a lo largo de ella. El muestreo anterior
# (N_MUESTRAS_DEFAULT frames uniformes en todo el video) deja casi todos los
# tracks sin asignar en un video largo con tracks cortos: en sportivo_crop3
# (26 min, 2.819 tracks de mediana 15 frames) solo 57 tracks juntaban las 2
# muestras mínimas. Se conserva como modo alternativo (n_muestras=...).
MUESTRAS_POR_TRACK = 5
PASO_GRILLA_MUESTREO = 5      # los frames de muestra se eligen sobre una grilla de 1 cada 5,
#                               así los tracks que conviven comparten frames y se decodifican menos
SALTO_MAX_SECUENCIAL = 120    # hasta este salto se avanza con grab() en vez de reposicionar el video
N_MUESTRAS_DEFAULT = 30       # modo alternativo: frames a muestrear a lo largo del video
MIN_MUESTRAS_TRACK = 2        # mínimo de muestras válidas por track para confiar en el voto

# Un track es "arquero" (equipo por geometría, fuera del clustering de color)
# solo si MÁS de esta fracción de sus filas de persona son `goalkeeper`. El
# detector confunde seguido jugador y arquero en detecciones sueltas: con la
# regla anterior (cualquier fila goalkeeper) en sportivo_crop3 había 785
# tracks "arquero", 708 de ellos casi siempre `player`, que recibían equipo
# por la mitad de cancha en la que estaban y no por su camiseta.
PROPORCION_MIN_ARQUERO = 0.5

# Diferencia mínima de luminancia (0-255) entre los dos colores de equipo
# para que el orden "home = más clara" sea confiable (ver
# _asignar_por_clustering). Por debajo de esto se avisa: con dos camisetas
# igual de claras/oscuras, el ruido de muestreo puede invertir el orden.
MIN_DIF_LUMINANCIA = 20


# ── Color de torso ───────────────────────────────────────────
def extraer_color_torso(frame: np.ndarray, bbox: tuple[float, float, float, float],
                        pasto: dict | None = None) -> tuple[int, int, int] | None:
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
        pasto: rango de pasto {"h_min", "h_max", "s_min"} estimado del video
            (ver _estimar_pasto). None → rango fijo H_PASTO_MIN/MAX, S_PASTO_MIN.

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
    if pasto is None:
        es_pasto = (h >= H_PASTO_MIN) & (h <= H_PASTO_MAX) & (s > S_PASTO_MIN)
    else:
        es_pasto = (h >= pasto["h_min"]) & (h <= pasto["h_max"]) & (s >= pasto["s_min"])
    valido = ~es_sombra & ~es_gris & ~es_pasto

    if int(valido.sum()) < MIN_PIXELES_TORSO:
        return None

    pixeles_bgr = recorte[valido]                 # Nx3, en BGR (formato nativo de OpenCV)
    b, g, r = np.median(pixeles_bgr, axis=0)       # mediana por canal — robusta a outliers
    return (int(round(r)), int(round(g)), int(round(b)))


# ── Color del pasto, estimado del propio video ───────────────
def _estimar_pasto(cap: cv2.VideoCapture, df: pd.DataFrame,
                   n_frames: int = N_FRAMES_PASTO) -> dict | None:
    """
    Rango HSV del pasto de ESTE video, medido sobre el fondo de la cancha.

    En `n_frames` frames repartidos por el video se toman los píxeles fuera
    de toda detección (bboxes agrandados, para no tocar jugadores ni sombras
    pegadas), con algo de color y de brillo. El pasto es la gran mayoría de
    ese fondo, así que el pico del histograma de matiz es el pasto; los
    candidatos son los píxeles a ±VENTANA_H_PASTO de ese pico. El rango
    final es mediana ± K_MAD_PASTO desvíos robustos (MAD), en matiz (más
    MARGEN_H_PASTO) y en saturación (solo la cota inferior, con piso
    S_PASTO_MIN). Mediana y MAD, y no percentiles de las colas, porque el
    fondo también tiene tribuna, carteles y pista con matiz parecido: en
    sportivo_crop3 son ~10% de los candidatos y bajaban el p5 de saturación
    de ~120 a ~55, con lo que el "pasto" pasaba a comerse las camisetas
    blancas.

    La saturación mínima es la que protege a las camisetas: el blanco bajo
    luz amarilla tiene un matiz parecido al del pasto nocturno (~25-30), pero
    mucha menos saturación.

    Returns:
        {"h_min", "h_max", "s_min", "h_pico", "n_pixeles"}, o None si no hay
        fondo suficiente o el pico no cae en un matiz verde/amarillento
        plausible (20-95) — en ese caso el llamador usa el rango fijo.
    """
    frames = _muestrear_frames(df, n_frames)
    hs, ss = [], []
    for frame_num in frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, float(frame_num - 1))
        ok, imagen = cap.read()
        if not ok or imagen is None:
            continue
        alto, ancho = imagen.shape[:2]
        fondo = np.ones((alto, ancho), dtype=bool)
        for fila in df[df["frame"] == frame_num].itertuples(index=False):
            x1, x2 = sorted((fila.x1, fila.x2))
            y1, y2 = sorted((fila.y1, fila.y2))
            m = 0.3 * (y2 - y1)
            fondo[max(int(y1 - m), 0):int(y2 + m) + 1, max(int(x1 - m), 0):int(x2 + m) + 1] = False
        hsv = cv2.cvtColor(imagen, cv2.COLOR_BGR2HSV)[::4, ::4]  # submuestreo: sobra con 1 de cada 16
        fondo = fondo[::4, ::4] & (hsv[..., 1] > 40) & (hsv[..., 2] > 40)
        hs.append(hsv[..., 0][fondo])
        ss.append(hsv[..., 1][fondo])
    if not hs:
        return None
    h = np.concatenate(hs).astype(int)
    s = np.concatenate(ss).astype(int)
    if h.size < 1000:
        return None

    hist = np.convolve(np.bincount(h, minlength=180), np.ones(5) / 5, mode="same")
    h_pico = int(np.argmax(hist))
    if not 20 <= h_pico <= 95:
        return None
    candidatos = np.abs(h - h_pico) <= VENTANA_H_PASTO
    h_c, s_c = h[candidatos], s[candidatos]
    h_med, s_med = np.median(h_c), np.median(s_c)
    h_desvio = 1.4826 * np.median(np.abs(h_c - h_med))
    s_desvio = 1.4826 * np.median(np.abs(s_c - s_med))
    semiancho_h = max(K_MAD_PASTO * h_desvio, MIN_SEMIANCHO_H_PASTO) + MARGEN_H_PASTO
    return {
        "h_min": int(np.floor(h_med - semiancho_h)),
        "h_max": int(np.ceil(h_med + semiancho_h)),
        "s_min": max(int(round(s_med - K_MAD_PASTO * s_desvio)), S_PASTO_MIN),
        "h_pico": h_pico,
        "n_pixeles": int(h_c.size),
    }


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


def _muestrear_por_track(df: pd.DataFrame, muestras_por_track: int,
                         paso: int = PASO_GRILLA_MUESTREO) -> pd.DataFrame:
    """
    Detecciones de `player` a muestrear: hasta `muestras_por_track` por
    track, repartidas a lo largo de su vida.

    Los frames se eligen sobre una grilla común (frame múltiplo de `paso`)
    para que los tracks que conviven en pantalla compartan frames — hay que
    decodificar menos. Un track tan corto que no toca la grilla aporta su
    frame central.
    """
    jugadores = df[df["class_name"] == "player"].drop_duplicates(["track_id", "frame"])
    elegidas = []
    for _, sub in jugadores.groupby("track_id"):
        sub = sub.sort_values("frame")
        en_grilla = sub[sub["frame"] % paso == 0]
        if en_grilla.empty:
            elegidas.append(sub.iloc[[len(sub) // 2]])
            continue
        n = min(muestras_por_track, len(en_grilla))
        indices = np.unique(np.linspace(0, len(en_grilla) - 1, n).round().astype(int))
        elegidas.append(en_grilla.iloc[indices])
    if not elegidas:
        return jugadores.iloc[0:0]
    return pd.concat(elegidas)


def _leer_frames(cap: cv2.VideoCapture, frames: list[int]):
    """
    Genera (frame, imagen) para los `frames` pedidos (1-based, como el
    parquet), en orden. Avanza con grab() mientras el salto sea corto
    —reposicionar el video obliga a decodificar desde el keyframe anterior
    y con miles de frames cercanos es mucho más lento— y reposiciona solo
    en los saltos largos.
    """
    posicion = None  # próximo índice 0-based que devolvería cap.read()
    for frame_num in sorted(set(int(f) for f in frames)):
        destino = frame_num - 1  # el parquet es 1-based, OpenCV 0-based
        if posicion is None or destino < posicion or destino - posicion > SALTO_MAX_SECUENCIAL:
            cap.set(cv2.CAP_PROP_POS_FRAMES, float(destino))
        else:
            while posicion < destino:
                if not cap.grab():
                    return
                posicion += 1
        ok, imagen = cap.read()
        posicion = destino + 1
        if ok and imagen is not None:
            yield frame_num, imagen


def _recolectar_muestras_color(cap: cv2.VideoCapture, detecciones: pd.DataFrame,
                                pasto: dict | None = None) -> pd.DataFrame:
    """
    Extrae el color de torso de cada detección de `detecciones` (filas de
    `player` ya elegidas por _muestrear_por_track o por frames uniformes).
    Los arqueros quedan afuera a propósito — ver _asignar_arqueros(), que
    los resuelve por geometría en vez de por color.
    """
    filas = []
    por_frame = dict(tuple(detecciones.groupby("frame")))
    for frame_num, imagen in _leer_frames(cap, list(por_frame)):
        for fila in por_frame[frame_num].itertuples(index=False):
            color = extraer_color_torso(imagen, (fila.x1, fila.y1, fila.x2, fila.y2), pasto)
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

    Etiquetas estables: KMeans numera los clusters en un orden que depende
    de las muestras (cambiando la calibración o cuántos frames se muestrean,
    el mismo equipo pasaba de "home" a "away"). Por eso la etiqueta no sale
    del número de cluster sino de un criterio fijo: **"home" es el equipo de
    camiseta más clara** (mayor luminancia). Es arbitrario — no tiene por
    qué coincidir con el local real — pero es el mismo en todas las corridas
    sobre el mismo video. Si las dos camisetas tienen luminancia parecida
    (< MIN_DIF_LUMINANCIA), el orden queda marcado como no confiable.

    Returns:
        (equipo_por_track, centros_cluster, orden_confiable) — el dict mapea
        track_id -> "home"/"away"; centros_cluster es un array 2x3 con el RGB
        de cada equipo, en orden [home, away] (para verificar a ojo que separó
        bien); orden_confiable es False si las luminancias están muy cerca.
    """
    if len(muestras) < 2:
        return {}, np.empty((0, 3)), True

    colores = muestras[["r", "g", "b"]].to_numpy(dtype=float)
    kmeans = KMeans(n_clusters=2, n_init=10, random_state=42).fit(colores)
    centros = kmeans.cluster_centers_
    luminancia = centros @ np.array([0.299, 0.587, 0.114])     # luma (Rec. 601)
    cluster_home = int(np.argmax(luminancia))
    orden_confiable = bool(abs(luminancia[0] - luminancia[1]) >= MIN_DIF_LUMINANCIA)
    etiqueta = {cluster_home: "home", 1 - cluster_home: "away"}
    muestras = muestras.assign(cluster=kmeans.labels_)

    equipo_por_track: dict[int, str] = {}
    for track_id, sub in muestras.groupby("track_id"):
        if len(sub) < min_muestras_track:
            continue
        conteo = sub["cluster"].value_counts()
        if len(conteo) > 1 and conteo.iloc[0] == conteo.iloc[1]:
            continue  # empate 50/50 entre los dos clusters — no hay mayoría clara
        cluster_ganador = int(conteo.idxmax())
        equipo_por_track[int(track_id)] = etiqueta[cluster_ganador]

    return equipo_por_track, centros[[cluster_home, 1 - cluster_home]], orden_confiable


def _a_lab(rgb) -> np.ndarray:
    return cv2.cvtColor(np.uint8([[list(rgb)]]), cv2.COLOR_RGB2LAB)[0, 0].astype(float) * [100 / 255, 1, 1] - [0, 128, 128]


def _delta_e(a, b) -> float:
    return float(np.linalg.norm(_a_lab(a) - _a_lab(b)))


def _aplicar_referencia(equipo_por_track: dict, centros: np.ndarray, referencia: list) -> tuple:
    """
    Etiqueta los dos clusters de este tiempo según los colores de referencia
    [home, away] del otro tiempo (emparejamiento de menor ΔE). Si el par
    elegido queda a más de UMBRAL_DELTA_E_REFERENCIA, no toca nada.
    Devuelve (equipo_por_track, centros [home, away], info).
    """
    directo = [_delta_e(centros[0], referencia[0]), _delta_e(centros[1], referencia[1])]
    cruzado = [_delta_e(centros[0], referencia[1]), _delta_e(centros[1], referencia[0])]
    invertir = max(cruzado) < max(directo)
    delta = cruzado if invertir else directo
    info = {"referencia_rgb": [tuple(int(v) for v in c) for c in referencia],
            "delta_e": [round(d, 1) for d in delta], "umbral": UMBRAL_DELTA_E_REFERENCIA}
    if max(delta) > UMBRAL_DELTA_E_REFERENCIA:
        info.update(usada=False, motivo=(
            f"los colores de este tiempo se alejan de los del otro (ΔE {max(delta):.0f} > "
            f"{UMBRAL_DELTA_E_REFERENCIA:g}; ¿cambió la luz?): no se fuerza la asignación, se usa la regla "
            f"de luminancia de este tiempo. Verificá a ojo que local y visitante coincidan con el otro tiempo"))
        return equipo_por_track, centros, info
    info.update(usada=True, invertida=bool(invertir), motivo=(
        "etiquetas tomadas del otro tiempo" + (" (invertidas respecto de la regla de luminancia)" if invertir else "")))
    if invertir:
        cambio = {"home": "away", "away": "home"}
        equipo_por_track = {t: cambio[e] for t, e in equipo_por_track.items()}
        centros = centros[[1, 0]]
    return equipo_por_track, centros, info


def colores_de_referencia(match_name: str, outputs_dir: Path | None = None) -> tuple[list | None, str | None]:
    """(colores [home, away] del otro tiempo del partido, nombre de ese video) si `match_name`
    es el 2° tiempo de un partido registrado y el 1° ya tiene equipos asignados; si no, (None, None)."""
    from src.db import partido_repo
    partido_repo.init_partidos_table()
    propio, otro = partido_repo.get_tiempo(match_name), partido_repo.otro_tiempo(match_name)
    if propio is None or otro is None or propio["tiempo"] != 2:
        return None, None
    ruta = (outputs_dir or _ROOT / "data" / "outputs") / f"{otro['match_name']}_coords_field.parquet"
    if not ruta.exists():
        return None, None
    colores = pd.read_parquet(ruta, columns=["frame"]).attrs.get("equipos_info", {}).get("colores_cluster_rgb")
    return (colores, otro["match_name"]) if colores and len(colores) == 2 else (None, None)


def tracks_arquero(df: pd.DataFrame) -> set[int]:
    """Tracks cuyas filas de persona son mayormente `goalkeeper` (más de
    PROPORCION_MIN_ARQUERO). El resto de los tracks con alguna fila
    goalkeeper se tratan como jugadores de campo: equipo por color."""
    personas = df[df["class_name"].isin(("player", "goalkeeper"))]
    if personas.empty:
        return set()
    fraccion = (personas["class_name"] == "goalkeeper").groupby(personas["track_id"]).mean()
    return {int(t) for t in fraccion.index[fraccion > PROPORCION_MIN_ARQUERO]}


def _asignar_arqueros(df: pd.DataFrame, equipo_por_track: dict[int, str],
                      ids_arquero: set[int] | None = None) -> dict[int, str]:
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

    Solo se aplica a `ids_arquero` (default: tracks_arquero(df), los
    mayormente goalkeeper); su posición se promedia sobre sus filas
    goalkeeper.
    """
    equipo_por_track = dict(equipo_por_track)  # no mutar el dict del caller
    if ids_arquero is None:
        ids_arquero = tracks_arquero(df)
    if "field_x" not in df.columns or not equipo_por_track:
        return equipo_por_track

    jugadores = df[df["track_id"].isin(set(equipo_por_track) - ids_arquero)].copy()
    if jugadores.empty:
        return equipo_por_track

    jugadores["team"] = jugadores["track_id"].map(equipo_por_track)
    x_prom_por_equipo = jugadores.groupby("team")["field_x"].mean()
    if len(x_prom_por_equipo) < 2:
        return equipo_por_track  # un solo equipo con jugadores clasificados — no hay con qué comparar

    equipo_ataca_x105 = x_prom_por_equipo.idxmin()  # field_x promedio más bajo → defiende cerca de x=0
    equipo_ataca_x0 = x_prom_por_equipo.idxmax()
    punto_medio = (x_prom_por_equipo.min() + x_prom_por_equipo.max()) / 2

    arqueros = df[(df["class_name"] == "goalkeeper") & df["track_id"].isin(ids_arquero)]
    for track_id, sub in arqueros.groupby("track_id"):
        x_prom = sub["field_x"].mean()
        if pd.isna(x_prom):
            continue
        equipo_por_track[int(track_id)] = equipo_ataca_x105 if x_prom < punto_medio else equipo_ataca_x0

    return equipo_por_track


# ── API pública ──────────────────────────────────────────────
def asignar_equipos(video_path, df: pd.DataFrame,
                     n_muestras: int | None = None,
                     min_muestras_track: int = MIN_MUESTRAS_TRACK,
                     muestras_por_track: int = MUESTRAS_POR_TRACK,
                     pasto_adaptativo: bool = True,
                     colores_referencia: list | None = None) -> pd.DataFrame:
    """
    Asigna equipo ("home" / "away") a cada track_id de jugador o arquero,
    a partir del color de camiseta muestreado del video.

    - `player`: color de torso muestreado en hasta `muestras_por_track`
      frames de la vida de cada track (o, con `n_muestras`, en ese número de
      frames uniformes de todo el video) + KMeans(2) + voto mayoritario por
      track (ver _asignar_por_clustering). El pasto se descarta con un rango
      de color estimado del propio video (ver _estimar_pasto).
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
        n_muestras: None (default) → muestreo por track. Un número → modo
            anterior: ese número de frames uniformes en todo el video.
        min_muestras_track: mínimo de muestras válidas por track para
            confiar en su voto mayoritario.
        muestras_por_track: tope de muestras por track (muestreo por track).
        pasto_adaptativo: False → rango de pasto fijo (H_PASTO_MIN/MAX,
            S_PASTO_MIN) en vez de estimarlo del video.

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
        pasto = _estimar_pasto(cap, resultado) if pasto_adaptativo else None
        if n_muestras is None:
            detecciones = _muestrear_por_track(resultado, muestras_por_track)
        else:
            frames_muestreados = _muestrear_frames(resultado, n_muestras)
            detecciones = resultado[(resultado["class_name"] == "player")
                                    & resultado["frame"].isin(frames_muestreados)]
        # Los arqueros quedan fuera del clustering aunque tengan filas
        # `player`: su camiseta es un tercer color y ensuciaría los 2 clusters.
        ids_arquero = tracks_arquero(resultado)
        detecciones = detecciones[~detecciones["track_id"].isin(ids_arquero)]
        muestras = _recolectar_muestras_color(cap, detecciones, pasto)
    finally:
        cap.release()

    equipo_por_track, centros_cluster, orden_confiable = _asignar_por_clustering(muestras, min_muestras_track)
    referencia_info = None
    if colores_referencia is not None and len(centros_cluster) == 2:
        equipo_por_track, centros_cluster, referencia_info = _aplicar_referencia(
            equipo_por_track, centros_cluster, colores_referencia)
    n_por_color = len(equipo_por_track)

    # Si los equipos cambian de lado a mitad del video (los dos tiempos en un
    # solo archivo), la geometría de los arqueros no vale: no se asignan.
    cambio = None
    if "field_x" in resultado.columns:
        provisorio = resultado.assign(team=resultado["track_id"].map(equipo_por_track))
        cambio = detectar_cambio_de_lado(provisorio)
    if cambio is None:
        equipo_por_track = _asignar_arqueros(resultado, equipo_por_track, ids_arquero)

    # OJO: un track_id no es siempre la misma clase a lo largo del video
    # (el detector etiqueta distinto a la misma persona según el frame, y en
    # una oclusión el track puede saltar a otra persona — ver el docstring
    # del módulo; hasta el 16/10/2026 se sumaba además un bug de
    # run_inference.py). Si se mapeara por track_id sobre TODO el DataFrame,
    # esas filas de árbitro/pelota heredarían por error el equipo del
    # jugador del mismo track — se restringe el mapeo a filas de persona
    # (player/goalkeeper) a propósito.
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
        "n_por_color": n_por_color,
        "n_arqueros_por_geometria": len(set(equipo_por_track) & ids_arquero),
        "colores_cluster_rgb": [tuple(int(round(c)) for c in centro) for centro in centros_cluster],
        "orden_etiquetas_confiable": orden_confiable,
        # None si se usó el rango fijo (pasto_adaptativo=False o no se pudo estimar)
        "pasto_hsv": pasto,
        # Segundo tiempo: si se usaron los colores del primero ({"usada", "delta_e", ...}) o None
        "referencia_colores": referencia_info,
        # Si los equipos cambian de lado dentro del video: aviso (arqueros sin asignar) o None
        "cambio_de_lado": mensaje_cambio_de_lado(cambio) if cambio else None,
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
    parser.add_argument("--muestras-por-track", type=int, default=MUESTRAS_POR_TRACK,
                        help=f"Tope de muestras de color por track (default: {MUESTRAS_POR_TRACK})")
    parser.add_argument("--n-muestras", type=int, default=None,
                        help="Modo anterior: muestrear este número de frames uniformes en todo el "
                             f"video en vez de muestrear por track (antes era el default, con {N_MUESTRAS_DEFAULT})")
    parser.add_argument("--sin-referencia", action="store_true",
                        help="En un 2° tiempo, no usar los colores del 1° como referencia")
    parser.add_argument("--pasto-fijo", action="store_true",
                        help=f"Usar el rango de pasto fijo (H {H_PASTO_MIN}-{H_PASTO_MAX}, S>{S_PASTO_MIN}) "
                             "en vez de estimarlo del video")
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
        referencia, video_referencia = (None, None) if args.sin_referencia else colores_de_referencia(
            parquet_path.stem.replace("_coords_field", "").replace("_coords", ""), parquet_path.parent)
        if referencia:
            print(f"2° tiempo: se usan como referencia los colores de equipo de {video_referencia}: "
                  f"home rgb{tuple(referencia[0])}, away rgb{tuple(referencia[1])}")
        resultado = asignar_equipos(args.video, df_entrada, n_muestras=args.n_muestras,
                                     min_muestras_track=args.min_muestras_track,
                                     muestras_por_track=args.muestras_por_track,
                                     pasto_adaptativo=not args.pasto_fijo,
                                     colores_referencia=referencia)
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        sys.exit(f"[ERROR] {e}")

    destino = Path(args.out) if args.out else parquet_path
    resultado.to_parquet(destino, index=False)

    info = resultado.attrs.get("equipos_info", {})
    print(f"\n✅ Columna `team` guardada en: {destino.name}")
    print(f"   🔵 home:         {info.get('n_home', 0)} tracks")
    print(f"   🔴 away:         {info.get('n_away', 0)} tracks")
    print(f"   ⚪ sin asignar:  {info.get('n_sin_asignar', 0)} tracks")
    print(f"   Por color: {info.get('n_por_color', 0)} tracks  |  arqueros por geometría: "
          f"{info.get('n_arqueros_por_geometria', 0)} tracks")
    print(f"   Muestras de color válidas usadas: {info.get('n_muestras_validas', 0)}")
    pasto = info.get("pasto_hsv")
    if pasto:
        print(f"   Pasto estimado del video (HSV de OpenCV): H {pasto['h_min']}-{pasto['h_max']}, "
              f"S ≥ {pasto['s_min']} (pico de matiz {pasto['h_pico']})")
    else:
        print(f"   Pasto: rango fijo H {H_PASTO_MIN}-{H_PASTO_MAX}, S > {S_PASTO_MIN}")

    colores = info.get("colores_cluster_rgb", [])
    if colores:
        print("   Color representativo de cada equipo (RGB) — home = camiseta más clara:")
        for i, c in enumerate(colores):
            print(f"     {('home', 'away')[i]}: rgb{c}")
        ref = info.get("referencia_colores")
        if ref is not None:
            icono = "✅" if ref["usada"] else "⚠️ "
            print(f"   {icono} Referencia del otro tiempo (ΔE {ref['delta_e']}): {ref['motivo']}")
        if not info.get("orden_etiquetas_confiable", True) and not (ref and ref["usada"]):
            print(f"   ⚠️  Las dos camisetas tienen luminancia parecida (< {MIN_DIF_LUMINANCIA}): "
                  f"las etiquetas home/away podrían invertirse entre corridas. Verificá con los colores.")
    else:
        print("   ⚠️ No se pudo calcular el clustering (¿muy pocas muestras válidas?).")
    if info.get("cambio_de_lado"):
        print(f"   ⚠️  {info['cambio_de_lado']} Los arqueros quedaron sin asignar.")
