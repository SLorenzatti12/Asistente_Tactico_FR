"""
Tramos del video sin calibración válida — filtro para el análisis
==================================================================
`calibrate.py --apply` verifica si la cámara se movió respecto de su
calibración (verificar_estabilidad) y deja en el parquet, como metadata,
los tramos en que la matriz no vale:

    df.attrs["calibracion_tramos_no_validos"] = [{"desde": s, "hasta": s, "motivo": ...}, ...]

Ahí las coordenadas en metros están corridas (en sportivo_crop3, antes de
recalibrar, ~1.6 m de mediana y ~3 m en la banda lejana), así que las
métricas y los patrones NO se calculan sobre esas filas: player_stats y
tactical_patterns las sacan con filtrar_tramos_no_validos() al empezar.
Un parquet sin ese atributo (anterior a la verificación) pasa sin cambios.
"""

from __future__ import annotations

import pandas as pd

CLAVE_TRAMOS_NO_VALIDOS = "calibracion_tramos_no_validos"


def tramos_no_validos(df: pd.DataFrame) -> list[dict]:
    return list(getattr(df, "attrs", {}).get(CLAVE_TRAMOS_NO_VALIDOS) or [])


def mascara_tramos_validos(df: pd.DataFrame) -> pd.Series:
    """True en las filas cuyo time_sec cae fuera de todo tramo no válido."""
    valido = pd.Series(True, index=df.index)
    if "time_sec" not in df.columns:
        return valido
    for t in tramos_no_validos(df):
        valido &= ~((df["time_sec"] >= t["desde"]) & (df["time_sec"] < t["hasta"]))
    return valido


def filtrar_tramos_no_validos(df: pd.DataFrame) -> pd.DataFrame:
    """`df` sin las filas de tramos con calibración no válida (conserva attrs).
    Si no hay tramos marcados, devuelve el mismo objeto."""
    if df is None or not tramos_no_validos(df):
        return df
    filtrado = df[mascara_tramos_validos(df)]
    filtrado.attrs = dict(df.attrs)
    return filtrado
