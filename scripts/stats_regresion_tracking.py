"""
Estadísticas de regresión del tracking sobre un *_coords.parquet.

Calcula los números de la línea base documentada en docs/context/decisiones.md
con los MISMOS criterios de conteo, para que la comparación sea pareja:
  - IDs únicos: todas las clases MENOS `ball`.
  - Distribución de largo de tracks: solo `player` + `goalkeeper`.

Uso:
    python src/detection/run_inference.py data/videos/sportivo_min.mp4 --skip 1
    python scripts/stats_regresion_tracking.py data/outputs/sportivo_min_coords.parquet
"""

import sys

import pandas as pd

if len(sys.argv) != 2:
    sys.exit("Uso: python scripts/stats_regresion_tracking.py <ruta/al/_coords.parquet>")

df = pd.read_parquet(sys.argv[1])
largos = df[df["class_name"].isin(["player", "goalkeeper"])].groupby("track_id").size()

print(f"IDs únicos (sin ball): {df.loc[df['class_name'] != 'ball', 'track_id'].nunique()}")
print(f"Detecciones: {len(df)}  "
      + "  ".join(f"{c}={n}" for c, n in df["class_name"].value_counts().items()))
print(f"Tracks player+goalkeeper: >500={(largos > 500).sum()}  "
      f"100-500={((largos >= 100) & (largos <= 500)).sum()}  <100={(largos < 100).sum()}")
