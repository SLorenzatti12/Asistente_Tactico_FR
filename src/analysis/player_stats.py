"""
Analizador Táctico — Estadísticas individuales por jugador
==========================================================
Analiza las trayectorias de cada track_id a partir del .parquet con
coordenadas de cancha en metros (field_x, field_y) que genera
src/homography/calibrate.py.

Referencia de cancha: 105m (largo, eje x) x 68m (ancho, eje y),
origen (0,0) en la esquina superior izquierda.

Flujo típico:
    df    = cargar_coords("data/outputs/partido_clip2_coords_field.parquet")
    limpio = filter_noise(df)
    stats  = compute_player_stats(limpio)
    stats  = infer_formation_zones(stats)

Uso por consola:
    python src/analysis/player_stats.py data/outputs/partido_clip2_coords_field.parquet
    python src/analysis/player_stats.py <parquet> --min-frames 30 --max-speed 11 --top 15
    python src/analysis/player_stats.py <parquet> --guardar data/outputs/stats.csv

Advertencia sobre el tracking
-----------------------------
ByteTrack no garantiza identidad persistente durante todo el partido: un
mismo jugador puede aparecer bajo varios track_id (re-identificación
perdida tras una oclusión). Por eso las métricas son "por track", no
"por jugador", y la distancia total es un piso, no el recorrido real
del partido completo.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ── Dimensiones estándar de cancha (metros) ────────────────
FIELD_LENGTH = 105.0
FIELD_WIDTH  = 68.0

# Clases que representan personas del equipo (se excluyen árbitro y pelota).
CLASES_JUGADOR = ("player", "goalkeeper")

# Velocidad máxima plausible para un jugador amateur (m/s).
# ~12 m/s ≈ 43 km/h, por encima del récord humano: todo lo que la supere
# es un salto de la homografía o un cruce de identidades del tracker.
MAX_SPEED_MS = 12.0

# Mínimo de frames para considerar que un track_id es un jugador real
# y no un fragmento espurio de tracking.
MIN_FRAMES = 10

# Cuántos descartes seguidos por velocidad imposible tolera el filtro antes
# de asumir que el punto de anclaje era el outlier (y no los que le siguen).
# Sin esto, un único glitch al principio de un track invalidaría todo el resto.
_MAX_DESCARTES_SEGUIDOS = 3

# Ventana (en muestras) de la mediana móvil que se aplica a las POSICIONES antes
# de medir el recorrido. La homografía tiembla ~0.1 m por frame aun con el
# jugador quieto y, a 30 fps, ese temblor se acumula: sobre este clip infla la
# distancia total un ~15%. Con ventana 5 (≈0.17 s) la curva ya se estabiliza,
# sin recortar cambios de dirección reales. Poner 0 o 1 desactiva el suavizado.
_VENTANA_POSICION = 5

# Ventana (en muestras) de la mediana móvil que se aplica a las velocidades
# instantáneas antes de tomar el máximo. A 30 fps un pico de 1-2 frames es
# ruido de detección, no un sprint.
_VENTANA_SUAVIZADO = 5

# Columnas que devuelve compute_player_stats, en orden.
COLUMNAS_STATS = [
    "track_id",
    "class_name",
    "n_frames",
    "tiempo_en_cancha_seg",
    "distancia_total_m",
    "pos_promedio_x",
    "pos_promedio_y",
    "rango_x",
    "rango_y",
    "velocidad_max_ms",
    "velocidad_prom_ms",
]

ZONAS = ("defensa", "mediocampo", "ataque")


# ── Helpers internos ─────────────────────────────────────────
def _dt_mediano(df: pd.DataFrame) -> float:
    """
    Paso de tiempo típico entre frames consecutivos del video (segundos).
    Se usa para estimar el tiempo en cancha sin inflarlo con los huecos
    en los que el tracker perdió al jugador.
    """
    if df.empty or "time_sec" not in df.columns:
        return 0.0
    tiempos = np.sort(df["time_sec"].dropna().unique())
    if tiempos.size < 2:
        return 0.0
    dt = float(np.median(np.diff(tiempos)))
    return dt if dt > 0 else 0.0


def _solo_jugadores(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra jugadores de campo y arqueros; descarta árbitro y pelota."""
    if "class_name" not in df.columns:
        return df
    return df[df["class_name"].isin(CLASES_JUGADOR)]


def _preparar(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deja el DataFrame listo para analizar: sin filas sin coordenadas de cancha,
    sin detecciones duplicadas del mismo track en el mismo frame (se queda con
    la de mayor confianza) y ordenado por track y tiempo.
    """
    columnas_necesarias = {"track_id", "time_sec", "field_x", "field_y"}
    faltantes = columnas_necesarias - set(df.columns)
    if faltantes:
        raise ValueError(
            f"Al .parquet le faltan columnas requeridas: {sorted(faltantes)}. "
            "¿Aplicaste la homografía con src/homography/calibrate.py --apply?"
        )

    limpio = df.dropna(subset=["track_id", "time_sec", "field_x", "field_y"]).copy()
    limpio = limpio[np.isfinite(limpio["field_x"]) & np.isfinite(limpio["field_y"])]

    # Un mismo track no puede estar en dos lugares en el mismo frame.
    if "frame" in limpio.columns:
        if "conf" in limpio.columns:
            limpio = limpio.sort_values("conf", ascending=False)
        limpio = limpio.drop_duplicates(subset=["track_id", "frame"], keep="first")

    orden = ["track_id", "time_sec"]
    if "frame" in limpio.columns:
        orden = ["track_id", "frame", "time_sec"]
    return limpio.sort_values(orden).reset_index(drop=True)


def _suavizar_posiciones(xs: np.ndarray, ys: np.ndarray, ventana: int):
    """
    Mediana móvil centrada sobre la trayectoria, para sacarle el temblor de la
    homografía sin desplazar la posición (a diferencia de la media, la mediana
    no se deja arrastrar por un frame malo).
    """
    if ventana is None or ventana < 2 or xs.size < 2:
        return xs, ys
    suave = lambda v: (
        pd.Series(v).rolling(ventana, center=True, min_periods=1).median().to_numpy()
    )
    return suave(xs), suave(ys)


def _mascara_saltos_validos(
    xs: np.ndarray,
    ys: np.ndarray,
    ts: np.ndarray,
    max_speed_ms: float,
) -> np.ndarray:
    """
    Máscara booleana de las detecciones de UN track que son físicamente
    alcanzables desde la última posición aceptada.

    Recorre el track hacia adelante comparando siempre contra el último punto
    válido (no contra el anterior sin más): así un glitch aislado se descarta
    sin arrastrar consigo a los frames que le siguen. Si se acumulan
    _MAX_DESCARTES_SEGUIDOS rechazos, se asume que el outlier era el punto de
    anclaje y se re-ancla en la posición actual.
    """
    n = xs.size
    valida = np.ones(n, dtype=bool)
    if n < 2:
        return valida

    ancla = 0
    descartes = 0
    for i in range(1, n):
        dt = ts[i] - ts[ancla]
        if dt <= 0:            # mismo instante: no aporta información nueva
            valida[i] = False
            continue
        distancia = float(np.hypot(xs[i] - xs[ancla], ys[i] - ys[ancla]))
        if distancia / dt > max_speed_ms:
            descartes += 1
            if descartes >= _MAX_DESCARTES_SEGUIDOS:
                ancla = i          # el sospechoso era el ancla, no estos puntos
                descartes = 0
                continue
            valida[i] = False
        else:
            ancla = i
            descartes = 0
    return valida


# ── API pública ──────────────────────────────────────────────
def cargar_coords(ruta) -> pd.DataFrame:
    """Lee el .parquet de coordenadas de cancha (columnas field_x / field_y en metros)."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el archivo de coordenadas: {ruta}")
    return pd.read_parquet(ruta)


def filter_noise(
    df: pd.DataFrame,
    min_frames: int = MIN_FRAMES,
    max_speed_ms: float = MAX_SPEED_MS,
) -> pd.DataFrame:
    """
    Limpia el DataFrame de detecciones antes de calcular métricas.

    Descarta, en este orden:
      1. Filas sin coordenadas de cancha válidas y detecciones duplicadas.
      2. Saltos de posición que implicarían velocidades imposibles
         (> `max_speed_ms` m/s): glitches de homografía o cruces de identidad.
      3. track_ids que quedan con menos de `min_frames` detecciones, es decir
         fragmentos espurios del tracker.

    El filtro por cantidad de frames se aplica al final a propósito: un track
    puede caer por debajo del umbral recién después de sacarle los saltos.

    Args:
        df: DataFrame crudo del .parquet (todas las clases).
        min_frames: mínimo de detecciones para conservar un track_id.
        max_speed_ms: velocidad máxima plausible entre detecciones (m/s).

    Returns:
        DataFrame con las mismas columnas, solo con las filas conservadas.
        Si `df` viene vacío, devuelve `df` sin tocar.
    """
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()

    limpio = _preparar(df)
    if limpio.empty:
        return limpio

    partes = []
    for track_id, sub in limpio.groupby("track_id", sort=False):
        mascara = _mascara_saltos_validos(
            sub["field_x"].to_numpy(dtype=float),
            sub["field_y"].to_numpy(dtype=float),
            sub["time_sec"].to_numpy(dtype=float),
            max_speed_ms=max_speed_ms,
        )
        partes.append(sub[mascara])

    if not partes:
        return limpio.head(0)

    resultado = pd.concat(partes, ignore_index=True)

    # La pelota comparte track_id = -1 entre detecciones inconexas: no tiene
    # sentido exigirle continuidad, se la deja pasar tal cual.
    conteos = resultado.groupby("track_id")["time_sec"].transform("size")
    resultado = resultado[(conteos >= min_frames) | (resultado["track_id"] < 0)]

    orden = ["track_id", "frame"] if "frame" in resultado.columns else ["track_id", "time_sec"]
    return resultado.sort_values(orden).reset_index(drop=True)


def compute_player_stats(
    df: pd.DataFrame,
    ventana_suavizado: int = _VENTANA_POSICION,
) -> pd.DataFrame:
    """
    Calcula métricas de recorrido para cada track_id de jugador.

    Solo considera class_name en ("player", "goalkeeper"): árbitro y pelota
    quedan afuera. Conviene pasarle el DataFrame ya limpio con filter_noise();
    si se le pasa el crudo, un solo salto de homografía puede inflar la
    distancia total varios cientos de metros.

    Antes de medir se le pasa una mediana móvil a las trayectorias
    (`ventana_suavizado`, en frames) para no contar como recorrido el temblor
    de la homografía. Con 0 o 1 se usan las posiciones crudas, que dan una
    distancia sistemáticamente sobreestimada.

    Columnas devueltas (una fila por track_id):
        track_id             — identificador del track
        class_name           — clase predominante del track (player / goalkeeper)
        n_frames             — cantidad de detecciones
        tiempo_en_cancha_seg — segundos en los que aparece detectado
        distancia_total_m    — suma de distancias entre posiciones consecutivas
        pos_promedio_x/y     — posición media sobre la cancha (metros)
        rango_x/y            — amplitud de movimiento (max - min) por eje
        velocidad_max_ms     — velocidad máxima (m/s), suavizada con mediana móvil
        velocidad_prom_ms    — distancia total / tiempo en cancha (m/s)

    Casos borde:
        - DataFrame vacío o sin jugadores → DataFrame vacío con estas columnas.
        - Track con una sola detección → distancia, rangos y velocidades en 0.0.
        - Filas con NaN en field_x / field_y / time_sec → se ignoran.

    Args:
        df: detecciones con field_x / field_y en metros (idealmente ya filtradas).
        ventana_suavizado: ventana en frames de la mediana móvil sobre las
            posiciones. 0 o 1 desactiva el suavizado.
    """
    vacio = pd.DataFrame(columns=COLUMNAS_STATS)
    if df is None or df.empty:
        return vacio

    datos = _solo_jugadores(_preparar(df))
    if datos.empty:
        return vacio

    dt_video = _dt_mediano(datos)
    filas = []

    for track_id, sub in datos.groupby("track_id", sort=True):
        ts = sub["time_sec"].to_numpy(dtype=float)
        xs, ys = _suavizar_posiciones(
            sub["field_x"].to_numpy(dtype=float),
            sub["field_y"].to_numpy(dtype=float),
            ventana_suavizado,
        )
        n = xs.size

        # Clase predominante: un track puede oscilar entre player y goalkeeper
        # si el modelo duda en algunos frames.
        if "class_name" in sub.columns and not sub["class_name"].empty:
            clase = sub["class_name"].mode().iat[0]
        else:
            clase = "player"

        # Tiempo detectado: cantidad de frames x paso del video. Se cuenta el
        # tiempo VISTO, no el span primer-último frame, para no regalarle
        # segundos a los tracks que el tracker perdió por el medio.
        tiempo = n * dt_video if dt_video > 0 else 0.0

        if n < 2:
            filas.append({
                "track_id": int(track_id),
                "class_name": clase,
                "n_frames": n,
                "tiempo_en_cancha_seg": tiempo,
                "distancia_total_m": 0.0,
                "pos_promedio_x": float(xs[0]),
                "pos_promedio_y": float(ys[0]),
                "rango_x": 0.0,
                "rango_y": 0.0,
                "velocidad_max_ms": 0.0,
                "velocidad_prom_ms": 0.0,
            })
            continue

        pasos = np.hypot(np.diff(xs), np.diff(ys))     # metros entre detecciones
        distancia_total = float(pasos.sum())

        dts = np.diff(ts)
        validos = dts > 0
        if validos.any():
            velocidades = pasos[validos] / dts[validos]
            # Mediana móvil: mata los picos de 1-2 frames sin aplanar un sprint real.
            suavizada = (
                pd.Series(velocidades)
                .rolling(_VENTANA_SUAVIZADO, center=True, min_periods=1)
                .median()
            )
            velocidad_max = float(np.nanmax(suavizada.to_numpy()))
        else:
            velocidad_max = 0.0

        velocidad_prom = distancia_total / tiempo if tiempo > 0 else 0.0

        filas.append({
            "track_id": int(track_id),
            "class_name": clase,
            "n_frames": n,
            "tiempo_en_cancha_seg": tiempo,
            "distancia_total_m": distancia_total,
            "pos_promedio_x": float(np.mean(xs)),
            "pos_promedio_y": float(np.mean(ys)),
            "rango_x": float(xs.max() - xs.min()),
            "rango_y": float(ys.max() - ys.min()),
            "velocidad_max_ms": velocidad_max,
            "velocidad_prom_ms": velocidad_prom,
        })

    if not filas:
        return vacio

    stats = pd.DataFrame(filas, columns=COLUMNAS_STATS)
    return stats.sort_values("distancia_total_m", ascending=False).reset_index(drop=True)


def infer_formation_zones(
    stats_df: pd.DataFrame,
    largo_cancha: float = FIELD_LENGTH,
) -> pd.DataFrame:
    """
    Clasifica cada track en una zona de la cancha según su posición media en x.

    Criterio inicial por tercios del eje largo:
        [0, L/3)      → "defensa"
        [L/3, 2L/3)   → "mediocampo"
        [2L/3, L]     → "ataque"

    Limitaciones conocidas (a resolver cuando exista la columna `team`):
        - Asume que el equipo analizado ataca hacia x creciente. Para el equipo
          rival las etiquetas quedan espejadas, y en el segundo tiempo también.
        - Con las dos formaciones mezcladas la lectura es de ocupación de zona,
          no de puesto: la línea defensiva rival cae en "ataque".

    Args:
        stats_df: salida de compute_player_stats().
        largo_cancha: largo de la cancha en metros (para partir en tercios).

    Returns:
        Copia de stats_df con la columna `zona` agregada (categórica ordenada
        defensa < mediocampo < ataque). Las posiciones NaN quedan como NaN.
    """
    tipo_zona = pd.CategoricalDtype(categories=ZONAS, ordered=True)

    if stats_df is None or stats_df.empty:
        vacio = stats_df.copy() if stats_df is not None else pd.DataFrame(columns=COLUMNAS_STATS)
        vacio["zona"] = pd.Series(dtype=tipo_zona)
        return vacio

    if "pos_promedio_x" not in stats_df.columns:
        raise ValueError(
            "stats_df no tiene la columna 'pos_promedio_x'. "
            "Pasá la salida de compute_player_stats()."
        )

    resultado = stats_df.copy()
    tercio = largo_cancha / 3.0

    zona = pd.cut(
        resultado["pos_promedio_x"],
        bins=[-np.inf, tercio, 2 * tercio, np.inf],
        labels=list(ZONAS),
        right=False,          # el borde exacto del tercio cae en la zona de adelante
    )
    resultado["zona"] = zona.astype(tipo_zona)
    return resultado


# ── CLI ──────────────────────────────────────────────────────
def _formatear_tabla(stats: pd.DataFrame) -> str:
    """Arma la tabla legible para consola, con nombres cortos y 1-2 decimales."""
    if stats.empty:
        return "(sin jugadores para mostrar)"

    tabla = stats.copy()
    columnas = {
        "track_id": "ID",
        "class_name": "clase",
        "zona": "zona",
        "n_frames": "frames",
        "tiempo_en_cancha_seg": "tiempo_s",
        "distancia_total_m": "dist_m",
        "velocidad_max_ms": "v_max",
        "velocidad_prom_ms": "v_prom",
        "pos_promedio_x": "x_prom",
        "pos_promedio_y": "y_prom",
        "rango_x": "rango_x",
        "rango_y": "rango_y",
    }
    presentes = [c for c in columnas if c in tabla.columns]
    tabla = tabla[presentes].rename(columns=columnas)

    formatos = {
        "tiempo_s": "{:.1f}".format,
        "dist_m": "{:.1f}".format,
        "v_max": "{:.2f}".format,
        "v_prom": "{:.2f}".format,
        "x_prom": "{:.1f}".format,
        "y_prom": "{:.1f}".format,
        "rango_x": "{:.1f}".format,
        "rango_y": "{:.1f}".format,
    }
    return tabla.to_string(
        index=False,
        formatters={k: v for k, v in formatos.items() if k in tabla.columns},
    )


def _resumen(df_crudo: pd.DataFrame, df_limpio: pd.DataFrame, stats: pd.DataFrame) -> str:
    """Resumen del efecto del filtrado y totales del grupo."""
    tracks_crudos = _solo_jugadores(df_crudo)["track_id"].nunique() if not df_crudo.empty else 0
    lineas = [
        f"Detecciones: {len(df_crudo):,} crudas → {len(df_limpio):,} tras el filtro "
        f"({len(df_crudo) - len(df_limpio):,} descartadas)",
        f"Tracks de jugador: {tracks_crudos} crudos → {len(stats)} analizados",
    ]
    if not stats.empty:
        lineas.append(
            f"Distancia media por track: {stats['distancia_total_m'].mean():.1f} m  |  "
            f"pico de velocidad: {stats['velocidad_max_ms'].max():.2f} m/s "
            f"({stats['velocidad_max_ms'].max() * 3.6:.1f} km/h)"
        )
    if "zona" in stats.columns and not stats.empty:
        conteo = stats["zona"].value_counts().reindex(ZONAS, fill_value=0)
        lineas.append(
            "Reparto por zona: " + "  ".join(f"{z}={int(conteo[z])}" for z in ZONAS)
        )
    return "\n".join(lineas)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analizador Táctico — Estadísticas individuales por jugador",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python src/analysis/player_stats.py data/outputs/partido_clip2_coords_field.parquet

  python src/analysis/player_stats.py data/outputs/partido_clip2_coords_field.parquet \\
      --min-frames 30 --max-speed 11 --top 15

  python src/analysis/player_stats.py data/outputs/partido_clip2_coords_field.parquet \\
      --guardar data/outputs/partido_clip2_player_stats.csv
        """,
    )
    parser.add_argument("parquet", type=str,
                        help="Ruta al .parquet con coordenadas de cancha (field_x, field_y)")
    parser.add_argument("--min-frames", type=int, default=MIN_FRAMES,
                        help=f"Mínimo de detecciones para conservar un track (default: {MIN_FRAMES})")
    parser.add_argument("--max-speed", type=float, default=MAX_SPEED_MS,
                        help=f"Velocidad máxima plausible en m/s (default: {MAX_SPEED_MS})")
    parser.add_argument("--suavizado", type=int, default=_VENTANA_POSICION,
                        help="Ventana (frames) de la mediana móvil sobre las posiciones; "
                             f"0 o 1 la desactiva (default: {_VENTANA_POSICION})")
    parser.add_argument("--sin-filtro", action="store_true",
                        help="Calcula sobre los datos crudos, sin limpiar (para comparar)")
    parser.add_argument("--top", type=int, default=None,
                        help="Muestra solo los N tracks con más distancia recorrida")
    parser.add_argument("--guardar", type=str, default=None,
                        help="Ruta .csv donde guardar la tabla de estadísticas")
    args = parser.parse_args()

    ruta_parquet = Path(args.parquet)
    try:
        df_crudo = cargar_coords(ruta_parquet)
    except FileNotFoundError as e:
        sys.exit(f"[ERROR] {e}")

    if df_crudo.empty:
        sys.exit(f"[ERROR] El archivo no tiene detecciones: {ruta_parquet}")

    if args.sin_filtro:
        df_limpio = df_crudo
    else:
        try:
            df_limpio = filter_noise(df_crudo, min_frames=args.min_frames,
                                     max_speed_ms=args.max_speed)
        except ValueError as e:
            sys.exit(f"[ERROR] {e}")

    stats = infer_formation_zones(
        compute_player_stats(df_limpio, ventana_suavizado=args.suavizado)
    )

    print(f"\n📊 Estadísticas por jugador — {ruta_parquet.name}")
    print("=" * 78)
    print(_resumen(df_crudo, df_limpio, stats))
    print("=" * 78)

    tabla = stats.head(args.top) if args.top else stats
    print(_formatear_tabla(tabla))
    if args.top and len(stats) > args.top:
        print(f"... y {len(stats) - args.top} tracks más (sacá --top para verlos todos)")

    if args.guardar:
        destino = Path(args.guardar)
        destino.parent.mkdir(parents=True, exist_ok=True)
        stats.to_csv(destino, index=False)
        print(f"\n✅ Estadísticas guardadas en: {destino}")
