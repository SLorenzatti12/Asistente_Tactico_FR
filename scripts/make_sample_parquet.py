"""
Generador de datos sintéticos — Asistente Táctico FR
======================================================
Crea un `demo_field.parquet` en data/outputs/ con el MISMO esquema que
producirá la homografía de Luci, para poder desarrollar map_view.py sin
esperar el pipeline real.

Esquema: frame, time_sec, track_id, class_name, team, field_x, field_y
  - Cancha 105 x 68 m, origen (0,0) esquina sup-izq.
  - 11 jugadores "home" (defienden arco izquierdo) + 11 "away" + 1 pelota.
  - team = "home" / "away" / None (la pelota va sin equipo).

Correr:  python scripts/make_sample_parquet.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

FIELD_LENGTH = 105  # eje x (arco a arco)
FIELD_WIDTH = 68    # eje y (lateral a lateral)

FPS = 10
DURATION_SEC = 20
N_FRAMES = FPS * DURATION_SEC

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "outputs" / "demo_field.parquet"

# Formación base 4-4-2 (GK, 4 def, 4 med, 2 del)
HOME = [(5, 34)] + [(20, y) for y in (12, 27, 41, 56)] \
       + [(40, y) for y in (12, 27, 41, 56)] + [(55, y) for y in (27, 41)]
AWAY = [(100, 34)] + [(85, y) for y in (12, 27, 41, 56)] \
       + [(65, y) for y in (12, 27, 41, 56)] + [(50, y) for y in (27, 41)]


def _clip_x(v):
    return float(np.clip(v, 1, FIELD_LENGTH - 1))


def _clip_y(v):
    return float(np.clip(v, 1, FIELD_WIDTH - 1))


def main():
    rng = np.random.default_rng(42)
    rows = []

    for f in range(N_FRAMES):
        t = f / FPS
        # Desplazamiento global del juego (ataque / repliegue del bloque)
        shift = 8 * np.sin(2 * np.pi * t / 12)

        for tid, (bx, by) in enumerate(HOME, start=1):
            x = bx + shift + rng.normal(0, 0.6) + 1.5 * np.sin(2 * np.pi * t / 7 + tid)
            y = by + rng.normal(0, 0.6) + 1.2 * np.sin(2 * np.pi * t / 9 + tid)
            rows.append((f, round(t, 3), tid, "player", "home", _clip_x(x), _clip_y(y)))

        for j, (bx, by) in enumerate(AWAY):
            tid = 100 + j  # ids separados para no chocar con los de home
            x = bx + shift + rng.normal(0, 0.6) + 1.5 * np.sin(2 * np.pi * t / 7 + j)
            y = by + rng.normal(0, 0.6) + 1.2 * np.sin(2 * np.pi * t / 9 + j)
            rows.append((f, round(t, 3), tid, "player", "away", _clip_x(x), _clip_y(y)))

        # Pelota (sin equipo)
        bx = 52 + 20 * np.sin(2 * np.pi * t / 12) + rng.normal(0, 1.5)
        by = 34 + 15 * np.sin(2 * np.pi * t / 8) + rng.normal(0, 1.5)
        rows.append((f, round(t, 3), 999, "ball", None, _clip_x(bx), _clip_y(by)))

    df = pd.DataFrame(
        rows,
        columns=["frame", "time_sec", "track_id", "class_name", "team", "field_x", "field_y"],
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(f"OK -> {OUT}  ({len(df)} filas, {N_FRAMES} frames, {DURATION_SEC}s @ {FPS}fps)")


if __name__ == "__main__":
    main()
