"""
Video anotado: dibujo de cajas y escritura en H.264
=====================================================
Compartido por run_inference.py (video anotado al procesar) y
scripts/regenerar_video_anotado.py (rehacerlo desde un parquet ya
procesado, sin volver a correr el detector).

Dos decisiones (ver docs/context/decisiones.md, "Partidos completos de 90
minutos"):

- **H.264 con CRF 26**, vía ffmpeg (libx264). El mp4v de OpenCV pesaba 8
  veces más (825 MB contra 103 MB en los 27 min de sportivo_crop3; ~345 MB
  para 90 min) y Chrome no lo reproduce. CRF 26 es el valor más comprimido con el que los números de
  track se siguen leyendo; con CRF 30 se borronean.
- **Cajas en todos los frames.** Con `--skip N` solo 1 de cada N frames
  pasa por el detector; antes los otros se escribían sin anotar y las cajas
  parpadeaban. Ahora repiten las del último frame procesado (atraso máximo
  de N−1 frames, 80 ms con N=3).

Si ffmpeg no está instalado se cae a mp4v de OpenCV, con aviso: el
procesamiento no se frena por el video.
"""

import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np

CLASS_COLORS = {
    "player":     (60, 60, 220),    # rojo
    "goalkeeper": (30, 170, 250),   # naranja
    "referee":    (0, 210, 210),    # amarillo
    "ball":       (255, 255, 255),  # blanco
}

# Calidad del H.264: CRF más alto = más chico y más borroso. Comparado sobre 3
# min de sportivo_crop3 anotado: con CRF 26 los números de track se leen; con
# CRF 30 se borronean. Con CRF 26 y cajas en todos los frames, los 27 min de
# sportivo_crop3 pesan 103 MB (~345 MB un partido de 90 min).
VIDEO_CRF = 26
VIDEO_PRESET = "veryfast"   # ~25× tiempo real en esta Mac: no frena a la inferencia


def dibujar_cajas(frame: np.ndarray, cajas) -> np.ndarray:
    """
    Dibuja sobre `frame` (in place) y lo devuelve. `cajas` es una lista de
    (x1, y1, x2, y2, track_id, clase) en píxeles; track_id -1 = sin ID.
    """
    for x1, y1, x2, y2, tid, clase in cajas:
        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
        color = CLASS_COLORS.get(clase, (200, 200, 200))
        etiqueta = f"{clase} #{int(tid)}" if int(tid) != -1 else clase
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, etiqueta, (x1, max(y1 - 6, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    return frame


class EscritorVideo:
    """
    Escribe frames BGR a un .mp4 en H.264 (ffmpeg, libx264, CRF VIDEO_CRF)
    pasándolos por un pipe, o en mp4v con OpenCV si no hay ffmpeg.
    `movflags +faststart` deja el índice al principio del archivo: el
    navegador puede empezar a reproducir y adelantar sin bajarlo entero.
    """

    def __init__(self, ruta: Path, fps: float, ancho: int, alto: int):
        self.ruta = Path(ruta)
        self.ffmpeg = shutil.which("ffmpeg")
        self._proceso = None
        self._cv2 = None
        if self.ffmpeg:
            self.codec = f"H.264 (libx264, CRF {VIDEO_CRF})"
            self._proceso = subprocess.Popen(
                [self.ffmpeg, "-v", "error", "-y",
                 "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{ancho}x{alto}", "-r", f"{fps}",
                 "-i", "-",
                 "-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
                 "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(self.ruta)],
                stdin=subprocess.PIPE,
            )
        else:
            self.codec = "mp4v (OpenCV) — ffmpeg no encontrado"
            print("[AVISO] ffmpeg no está instalado: el video anotado sale en mp4v, que pesa ~5 veces "
                  "más y no se reproduce en Chrome. Instalalo con: brew install ffmpeg")
            self._cv2 = cv2.VideoWriter(str(self.ruta), cv2.VideoWriter_fourcc(*"mp4v"), fps, (ancho, alto))

    def escribir(self, frame: np.ndarray) -> None:
        if self._proceso is not None:
            self._proceso.stdin.write(np.ascontiguousarray(frame).tobytes())
        else:
            self._cv2.write(frame)

    def cerrar(self) -> None:
        if self._proceso is not None:
            self._proceso.stdin.close()
            if self._proceso.wait() != 0:
                raise RuntimeError(f"ffmpeg terminó con error al escribir {self.ruta}")
        else:
            self._cv2.release()
