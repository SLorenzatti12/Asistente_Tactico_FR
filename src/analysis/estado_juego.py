"""
Analizador Táctico — Posible juego detenido
=============================================
Santi (09/11/2026). El sistema no sabe si la pelota está en juego: la clase
`ball` tiene recall bajo y no sirve como señal. Este módulo marca los tramos en
que el movimiento general bajó tanto que el juego probablemente estaba detenido
(lateral, tiro libre, pelota afuera), para avisarlo en los "Momentos para
revisar". Caso que lo motivó: el track 2374 de sportivo_crop3 ("desconectado",
21:07–21:45) era un falso positivo, porque el partido estaba detenido mientras
el arquero rival buscaba la pelota fuera de la cancha.

Señal: la velocidad colectiva. Para cada jugador de campo (clase `player`; sin
árbitros ni arqueros), la velocidad de cada fila es su desplazamiento en el
último INTERVALO_VELOCIDAD_SEG, con los tiempos reales de los cuadros (respeta
el skip). Por cuadro se toma la MEDIANA entre jugadores, robusta a los tracks
erráticos, y se suaviza con una mediana móvil de VENTANA_SUAVIZADO_SEG. Un
tramo es "posible juego detenido" si esa curva queda bajo UMBRAL_MS durante al
menos DURACION_MIN_SEG.

Por qué el desplazamiento en 1 s y no entre cuadros consecutivos: con --skip 3
los cuadros están a 0.12 s, y el temblor de 1–2 px de la caja en la banda
lejana (~0.3 m por píxel) ya da 2–5 m/s "de velocidad". Con la velocidad entre
cuadros, el tramo detenido del track 2374 queda en 1.6–2.4 m/s, lo mismo que el
partido (mediana 2.2), y no hay umbral que lo separe. En 1 s ese ruido pesa
diez veces menos (ver decisiones.md, "Posible juego detenido").

Un video = un tiempo (ver lados.py): cada tiempo se calcula por separado, y los
tramos sin calibración válida (cámara movida) no cuentan.

Uso:
    python3 src/analysis/estado_juego.py data/outputs/<clip>_coords_field.parquet
    → data/outputs/<clip>_estado_juego.parquet, con su procedencia
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from src.homography.tramos_validos import filtrar_tramos_no_validos  # noqa: E402

# Calibrados el 09/11/2026 sobre Sportivo–Crecer (ver decisiones.md): el tramo
# del track 2374 queda marcado (96%), la basculación de los tracks 21/74 de
# partido_clip2 (juego en curso) no, y de los momentos calificados quedan
# marcados 7 de los 12 comentados como juego detenido y 0 de los 9 útiles.
PARAMETROS_POR_DEFECTO = {
    "umbral_ms": 1.4,                # velocidad colectiva (mediana suavizada) por debajo de la cual el juego parece detenido
    "duracion_min_seg": 15.0,        # cuánto tiene que durar para contar
    "ventana_suavizado_seg": 2.0,    # mediana móvil sobre la curva, absorbe el temblor de la homografía
    "intervalo_velocidad_seg": 1.0,  # desplazamiento de cada jugador en este intervalo (ver docstring)
    "min_jugadores": 4,              # cuadros con menos jugadores medidos no cuentan
    "fraccion_min_momento": 0.5,     # un momento queda marcado si al menos esta parte de sus tramos cae en juego detenido
}
_MAX_HUECO_SEG = 1.0                 # un hueco mayor (sin datos, o tramo excluido) corta el intervalo


def parametros_completos(parametros: dict | None = None) -> dict:
    p = dict(PARAMETROS_POR_DEFECTO)
    p.update(parametros or {})
    return p


def velocidad_colectiva(df: pd.DataFrame, parametros: dict | None = None) -> pd.DataFrame:
    """Curva de velocidad colectiva: una fila por cuadro con time_sec, la
    mediana entre jugadores (m/s), la misma suavizada y cuántos jugadores entraron."""
    p = parametros_completos(parametros)
    columnas = ["time_sec", "mediana", "mediana_suavizada", "n_jugadores"]
    validos = filtrar_tramos_no_validos(df)
    jugadores = validos[validos["class_name"] == "player"]
    jugadores = jugadores.dropna(subset=["field_x", "field_y"]).sort_values(["track_id", "time_sec"])
    if jugadores.empty:
        return pd.DataFrame(columns=columnas)

    intervalo = p["intervalo_velocidad_seg"]
    t = jugadores["time_sec"].to_numpy()
    x = jugadores["field_x"].to_numpy()
    y = jugadores["field_y"].to_numpy()
    tracks = jugadores["track_id"].to_numpy()
    velocidad = np.full(len(t), np.nan)
    limites = np.flatnonzero(np.r_[True, tracks[1:] != tracks[:-1], True])
    for ini, fin in zip(limites[:-1], limites[1:]):
        tt = t[ini:fin]
        # La fila de hace ~intervalo segundos del mismo track (con los tiempos
        # reales de los cuadros, sin suponer un skip).
        j = np.searchsorted(tt, tt - intervalo)
        dt = tt - tt[j]
        valido = (dt >= 0.7 * intervalo) & (dt <= 1.5 * intervalo)
        dist = np.hypot(x[ini:fin] - x[ini:fin][j], y[ini:fin] - y[ini:fin][j])
        velocidad[ini:fin] = np.where(valido, dist / np.where(dt > 0, dt, np.nan), np.nan)

    por_cuadro = (pd.DataFrame({"frame": jugadores["frame"].to_numpy(), "time_sec": t, "v": velocidad})
                  .groupby("frame").agg(time_sec=("time_sec", "first"), mediana=("v", "median"),
                                        n_jugadores=("v", "count")))
    por_cuadro = por_cuadro[por_cuadro["n_jugadores"] >= p["min_jugadores"]].sort_values("time_sec")
    if por_cuadro.empty:
        return pd.DataFrame(columns=columnas)
    serie = pd.Series(por_cuadro["mediana"].to_numpy(), index=pd.to_timedelta(por_cuadro["time_sec"], unit="s"))
    ventana = f"{int(round(p['ventana_suavizado_seg'] * 1000))}ms"
    por_cuadro["mediana_suavizada"] = serie.rolling(ventana, center=True, min_periods=3).median().to_numpy()
    return por_cuadro.reset_index(drop=True)[columnas]


def detectar_juego_detenido(df: pd.DataFrame, parametros: dict | None = None,
                            curva: pd.DataFrame | None = None) -> pd.DataFrame:
    """Intervalos de posible juego detenido: inicio, fin y duración (s), y la
    velocidad colectiva mediana dentro del intervalo (m/s)."""
    p = parametros_completos(parametros)
    columnas = ["inicio", "fin", "duracion", "velocidad_mediana"]
    curva = velocidad_colectiva(df, p) if curva is None else curva
    if curva.empty:
        return pd.DataFrame(columns=columnas)
    t = curva["time_sec"].to_numpy()
    v = curva["mediana_suavizada"].to_numpy()
    bajo = v < p["umbral_ms"]          # NaN cuenta como "no bajo"
    filas, i = [], 0
    while i < len(t):
        if not bajo[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(t) and bajo[j + 1] and t[j + 1] - t[j] <= _MAX_HUECO_SEG:
            j += 1
        if t[j] - t[i] >= p["duracion_min_seg"]:
            filas.append({"inicio": float(t[i]), "fin": float(t[j]), "duracion": float(t[j] - t[i]),
                          "velocidad_mediana": float(np.median(v[i:j + 1]))})
        i = j + 1
    return pd.DataFrame(filas, columns=columnas)


def fraccion_en_intervalos(tramos, intervalos: pd.DataFrame) -> float:
    """Qué parte de la duración de `tramos` [(ini, fin), ...] cae dentro de los intervalos."""
    total = sum(fin - ini for ini, fin in tramos)
    if total <= 0 or intervalos.empty:
        return 0.0
    solapado = sum(max(0.0, min(fin, b) - max(ini, a))
                   for ini, fin in tramos for a, b in zip(intervalos["inicio"], intervalos["fin"]))
    return float(min(1.0, solapado / total))


def marcar_momentos(patrones: pd.DataFrame, intervalos: pd.DataFrame,
                    fraccion_min: float = PARAMETROS_POR_DEFECTO["fraccion_min_momento"]) -> pd.DataFrame:
    """Agrega `fraccion_juego_detenido` y `posible_juego_detenido` a cada
    momento. Solo marca: no saca momentos ni toca la severidad."""
    patrones = patrones.copy()
    fracciones = [fraccion_en_intervalos(ev, intervalos) for ev in patrones["evidencia_seg"]] if len(patrones) else []
    patrones["fraccion_juego_detenido"] = pd.Series(fracciones, index=patrones.index, dtype=float).round(2)
    patrones["posible_juego_detenido"] = patrones["fraccion_juego_detenido"] >= fraccion_min
    return patrones


def _formato(seg: float) -> str:
    return f"{int(seg // 60)}:{seg % 60:04.1f}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analizador Táctico — Posible juego detenido")
    parser.add_argument("parquet", type=str, help="Ruta al *_coords_field.parquet")
    for clave, valor in PARAMETROS_POR_DEFECTO.items():
        if clave != "fraccion_min_momento":
            parser.add_argument(f"--{clave.replace('_', '-')}", type=type(valor), default=valor)
    parser.add_argument("--out", type=str, default=None,
                        help="Ruta de salida (default: <clip>_estado_juego.parquet junto a la entrada)")
    args = parser.parse_args()

    ruta = Path(args.parquet)
    if not ruta.exists():
        sys.exit(f"[ERROR] Parquet no encontrado: {ruta}")
    df = pd.read_parquet(ruta)
    parametros = {k: getattr(args, k) for k in PARAMETROS_POR_DEFECTO if k != "fraccion_min_momento"}
    curva = velocidad_colectiva(df, parametros)
    intervalos = detectar_juego_detenido(df, parametros, curva)

    clip = ruta.stem.replace("_coords_field", "").replace("_coords", "")
    destino = Path(args.out) if args.out else ruta.with_name(f"{clip}_estado_juego.parquet")
    from src.utils.procedencia import escribir_parquet_con_meta, meta_base, meta_de_entrada
    meta = meta_base(__file__, parametros_completos(parametros))
    try:
        from src.db import partido_repo
        meta["partido"] = partido_repo.get_tiempo(clip)
    except Exception:  # sin base o sin partido registrado: es un video suelto
        meta["partido"] = None
    meta["curva"] = {"cuadros": len(curva), "mediana_ms": float(curva["mediana_suavizada"].median())
                     if len(curva) else None}
    meta["origen"] = meta_de_entrada(ruta)
    escribir_parquet_con_meta(intervalos, destino, meta)

    duracion = (curva["time_sec"].max() - curva["time_sec"].min()) if len(curva) else 0
    print(f"\n⏸  Posible juego detenido — {ruta.name}")
    print(f"Velocidad colectiva mediana del video: {meta['curva']['mediana_ms']:.2f} m/s · umbral "
          f"{parametros['umbral_ms']} m/s durante ≥{parametros['duracion_min_seg']:g} s")
    print(f"{len(intervalos)} intervalos, {intervalos['duracion'].sum():.0f} s "
          f"({100 * intervalos['duracion'].sum() / duracion:.0f}% del video medido)" if duracion else "sin datos")
    for _, f in intervalos.iterrows():
        print(f"  {_formato(f['inicio'])} – {_formato(f['fin'])}  ({f['duracion']:.0f} s, "
              f"{f['velocidad_mediana']:.2f} m/s)")
    print(f"\n✅ Guardado en: {destino}")
