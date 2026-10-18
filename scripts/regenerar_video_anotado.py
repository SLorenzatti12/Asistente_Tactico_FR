"""
Regenera el video anotado (*_tracked.mp4) de un partido YA procesado, a
partir del video original y de su *_coords.parquet — sin volver a correr
el detector (23 min en 27 min de partido contra ~3 min de esto).

Dibuja lo mismo que run_inference.py (mismas cajas, colores y etiquetas,
ver src/detection/video_anotado.py): en H.264 y con las cajas repetidas en
los frames que el --skip salteó, así no parpadean. Sirve para pasar al
formato nuevo los videos generados antes del 18/10/2026 (mp4v, con cajas
solo en 1 de cada N frames).

Usar el *_coords.parquet (píxeles, todas las detecciones), no el
*_coords_field.parquet: ese ya no tiene las detecciones fuera de cancha.

Uso:
    python3 scripts/regenerar_video_anotado.py data/videos/sportivo_crop3.mp4 \\
        data/outputs/sportivo_crop3_coords.parquet

El video anterior, si existe, se respalda como *_tracked_anterior.mp4.
"""

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "detection"))
from video_anotado import EscritorVideo, dibujar_cajas  # noqa: E402

OUTPUTS = ROOT / "data" / "outputs"


def inferir_skip(frames: np.ndarray) -> int:
    """El --skip con que se procesó: el salto más común entre frames con detecciones."""
    saltos = np.diff(np.unique(frames))
    return int(pd.Series(saltos).mode().iat[0]) if len(saltos) else 1


def regenerar(video: Path, coords: Path, salida: Path) -> Path:
    df = pd.read_parquet(coords)
    skip = inferir_skip(df["frame"].to_numpy())
    cajas_por_frame = {
        int(f): list(zip(g.x1, g.y1, g.x2, g.y2, g.track_id, g.class_name))
        for f, g in df.groupby("frame")
    }

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        sys.exit(f"[ERROR] No se pudo abrir el video: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    ancho, alto = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if salida.exists():
        respaldo = salida.with_name(salida.stem + "_anterior.mp4")
        salida.rename(respaldo)
        print(f"Video anterior respaldado como {respaldo.name}")

    escritor = EscritorVideo(salida, fps, ancho, alto)
    print(f"{video.name}: {ancho}x{alto} @ {fps:.2f} fps · procesado con --skip {skip} · {escritor.codec}")
    ultimas = []
    idx = 0
    t0 = time.time()
    with tqdm(total=total, desc="Frames", unit="fr", ncols=70) as barra:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            idx += 1                      # mismo conteo 1-based que run_inference.py
            if idx % skip == 0:           # frame procesado: sus cajas (o ninguna)
                ultimas = cajas_por_frame.get(idx, [])
            escritor.escribir(dibujar_cajas(frame, ultimas))
            barra.update(1)
    cap.release()
    escritor.cerrar()
    print(f"\n✅ {salida.name}: {salida.stat().st_size / 1048576:.0f} MB en {time.time() - t0:.0f} s")
    return salida


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Regenera el video anotado desde el parquet, sin el detector",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("video", help="Video original (el mismo que se procesó con run_inference.py)")
    ap.add_argument("coords", help="*_coords.parquet de ese video")
    ap.add_argument("--salida", default=None, help="Default: data/outputs/<video>_tracked.mp4")
    a = ap.parse_args()
    video = Path(a.video)
    regenerar(video, Path(a.coords), Path(a.salida) if a.salida else OUTPUTS / f"{video.stem}_tracked.mp4")
