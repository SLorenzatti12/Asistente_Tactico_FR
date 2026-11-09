"""
Medidas de la cancha — única definición compartida
====================================================
Las canchas regionales no miden 105×68 ni respetan siempre las marcas
reglamentarias (en Sportivo, la banda cercana queda a ~39 m del eje en vez
de 34, y el área chica derecha parece medir ~6.2 m de profundidad). Por eso
las medidas son un dato del ESTADIO (tabla `estadios`, src/db/estadio_repo.py)
y viajan con cada calibración:

    estadios (SQLite) ──calibrate.py --estadio──▶ <video>_homography.json
                                                   "medidas_cancha" (copia)
                       ──calibrate.py --apply────▶ *_coords_field.parquet
                                                   .attrs["medidas_cancha"]

El JSON guarda una COPIA, no una referencia: si después se corrigen las
medidas del estadio, las coordenadas ya generadas siguen siendo coherentes
con la calibración que las produjo. Sin dato (JSON o parquet anteriores a
esto), se asume la cancha reglamentaria de 105×68.

Sistema de coordenadas: metros, origen (0,0) en la esquina superior
izquierda; x = largo (arco a arco), y = ancho (lateral a lateral).

Uso desde cualquier etapa posterior (dashboard, análisis):
    from src.homography.medidas_cancha import medidas_de_df
    df = pd.read_parquet(ruta)
    m = medidas_de_df(df)          # dict con "largo", "ancho", ...
"""

from __future__ import annotations

import math

# Claves de un dict de medidas (metros). "largo" y "ancho" son las de la
# cancha; el resto son las marcas, que casi siempre son las reglamentarias.
MEDIDAS_REGLAMENTARIAS = {
    "largo": 105.0,
    "ancho": 68.0,
    "area_grande_largo": 16.5,   # profundidad desde la línea de fondo
    "area_grande_ancho": 40.32,
    "area_chica_largo": 5.5,
    "area_chica_ancho": 18.32,
    "radio_circulo": 9.15,       # círculo central y medialuna del área
    "distancia_penal": 11.0,     # punto penal, desde la línea de fondo
}

# Ancho del arco entre postes (m). No es medida del estadio: los arcos son
# de fábrica y reglamentarios aunque la cancha no lo sea.
ANCHO_ARCO = 7.32

CLAVE_ATTRS = "medidas_cancha"   # clave en df.attrs y en el JSON de calibración


def completar_medidas(medidas: dict | None) -> dict:
    """
    Dict de medidas completo: lo que venga en `medidas` (claves conocidas,
    valores no nulos) y el resto reglamentario. Conserva "estadio" si viene.
    """
    resultado = dict(MEDIDAS_REGLAMENTARIAS)
    for clave, valor in (medidas or {}).items():
        if clave in MEDIDAS_REGLAMENTARIAS and valor is not None:
            resultado[clave] = float(valor)
    resultado["estadio"] = (medidas or {}).get("estadio")
    return resultado


def medidas_de_df(df) -> dict:
    """Medidas de la cancha guardadas en un DataFrame leído de *_coords_field.parquet
    (`df.attrs`). Sin dato → cancha reglamentaria de 105×68."""
    return completar_medidas(getattr(df, "attrs", {}).get(CLAVE_ATTRS))


def descripcion(medidas: dict) -> str:
    """Texto corto para consola: '100×70 m (Estadio X)'."""
    m = completar_medidas(medidas)
    nombre = f" ({m['estadio']})" if m.get("estadio") else " (reglamentaria, sin estadio asignado)"
    return f"{m['largo']:g}×{m['ancho']:g} m{nombre}"


def offset_medialuna(medidas: dict) -> float:
    """
    Distancia al eje (y) donde la medialuna del área corta la línea del
    frente del área: círculo de radio `radio_circulo` con centro en el punto
    penal → ± sqrt(r² − (area_grande_largo − distancia_penal)²). Con las
    medidas reglamentarias da 7.31 m.
    """
    m = completar_medidas(medidas)
    d = m["area_grande_largo"] - m["distancia_penal"]
    return math.sqrt(max(m["radio_circulo"] ** 2 - d ** 2, 0.0))
