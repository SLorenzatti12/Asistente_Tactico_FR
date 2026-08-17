"""
Analizador Táctico — Módulo de Homografía
==========================================
Convierte coordenadas de píxeles (frame de video) a metros reales
sobre la cancha, usando una calibración manual de 4 puntos.

Flujo:
    1. El usuario hace clic en 4 puntos conocidos de la cancha
       sobre el primer frame del video (ej: las 4 esquinas del área,
       o las 4 esquinas de la cancha si se ven completas)
    2. Se guarda la matriz de homografía en un .json (una vez por video/cámara)
    3. Cualquier coordenada en píxeles del .parquet de detecciones
       se puede transformar a metros usando esa matriz

Uso:
    # Paso 1: calibrar (una vez por video/ángulo de cámara)
    python src/homography/calibrate.py data/videos/partido.mp4

    # Paso 2: aplicar la calibración a las coordenadas ya detectadas
    python src/homography/calibrate.py data/videos/partido.mp4 --apply data/outputs/partido_coords.parquet
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT    = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / "data" / "outputs"

# ── Dimensiones estándar de cancha (metros) ────────────────
FIELD_LENGTH = 105.0
FIELD_WIDTH  = 68.0

# Puntos de referencia disponibles para calibrar — el usuario elige
# cuáles 4 puede ver claramente en su video (no siempre se ve la cancha entera)
REFERENCE_POINTS = {
    "esquina_sup_izq":      (0.0, 0.0),
    "esquina_sup_der":      (FIELD_LENGTH, 0.0),
    "esquina_inf_izq":      (0.0, FIELD_WIDTH),
    "esquina_inf_der":      (FIELD_LENGTH, FIELD_WIDTH),
    "penal_izq":            (11.0, FIELD_WIDTH / 2),
    "penal_der":            (FIELD_LENGTH - 11.0, FIELD_WIDTH / 2),
    "area_chica_sup_izq":   (0.0, FIELD_WIDTH / 2 - 9.16),
    "area_chica_inf_izq":   (0.0, FIELD_WIDTH / 2 + 9.16),
    "area_grande_sup_izq":  (0.0, FIELD_WIDTH / 2 - 20.16),
    "area_grande_inf_izq":  (0.0, FIELD_WIDTH / 2 + 20.16),
    "centro_cancha":        (FIELD_LENGTH / 2, FIELD_WIDTH / 2),
    "mitad_linea_sup":      (FIELD_LENGTH / 2, 0.0),
    "mitad_linea_inf":      (FIELD_LENGTH / 2, FIELD_WIDTH),
}

# Orden sugerido para calibración rápida (4 esquinas del área central,
# suelen verse bien incluso con cámara desde el fondo)
DEFAULT_ORDER = ["esquina_sup_izq", "esquina_sup_der", "esquina_inf_izq", "esquina_inf_der"]


class CalibrationUI:
    """Ventana interactiva para marcar puntos de referencia sobre un frame."""

    def __init__(self, frame: np.ndarray, point_names: list):
        self.frame       = frame
        self.display     = frame.copy()
        self.point_names = point_names
        self.clicks      = []  # lista de (x, y) en píxeles, en el mismo orden que point_names

    def _on_mouse(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(self.clicks) < len(self.point_names):
            self.clicks.append((x, y))
            self._redraw()

    def _redraw(self):
        self.display = self.frame.copy()
        for i, (px, py) in enumerate(self.clicks):
            cv2.circle(self.display, (px, py), 6, (0, 0, 255), -1)
            cv2.putText(self.display, str(i + 1), (px + 10, py - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        self._draw_hud()

    def _draw_hud(self):
        h, w = self.display.shape[:2]
        overlay = self.display.copy()
        cv2.rectangle(overlay, (0, 0), (w, 70), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.55, self.display, 0.45, 0, self.display)

        if len(self.clicks) < len(self.point_names):
            next_point = self.point_names[len(self.clicks)]
            msg = f"Clic en: {next_point.replace('_', ' ').upper()}  ({len(self.clicks)}/{len(self.point_names)})"
        else:
            msg = "Listo — presiona ENTER para confirmar, o R para reiniciar"

        cv2.putText(self.display, msg, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
        cv2.putText(self.display, "R: reiniciar   Q: cancelar", (15, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    def run(self):
        """Abre la ventana interactiva. Retorna los clics o None si se cancela."""
        window = "Calibracion - Analizador Tactico"
        cv2.namedWindow(window)
        cv2.setMouseCallback(window, self._on_mouse)
        self._redraw()

        while True:
            cv2.imshow(window, self.display)
            key = cv2.waitKey(20) & 0xFF

            if key == ord("q"):
                cv2.destroyAllWindows()
                return None
            elif key == ord("r"):
                self.clicks = []
                self._redraw()
            elif key == 13 and len(self.clicks) == len(self.point_names):  # ENTER
                cv2.destroyAllWindows()
                return self.clicks


def calibrate(video_path: Path, point_names: list = None) -> Path:
    """
    Abre el primer frame del video y pide clics en los puntos de referencia.
    Guarda la matriz de homografía resultante en un .json.
    """
    point_names = point_names or DEFAULT_ORDER

    cap = cv2.VideoCapture(str(video_path))
    ret, frame = cap.read()
    cap.release()
    if not ret:
        sys.exit(f"[ERROR] No se pudo leer el primer frame de: {video_path}")

    print(f"\nSe abrirá una ventana. Hacé clic, en orden, en estos {len(point_names)} puntos:")
    for i, name in enumerate(point_names, 1):
        print(f"  {i}. {name.replace('_', ' ')}")
    print("\nSi alguno de estos puntos no se ve en tu video, cancelá (Q) y volvé a")
    print("llamar a calibrate() pasando otra lista de puntos que sí se vean")
    print("(ver REFERENCE_POINTS en este archivo para las opciones disponibles).\n")
    input("Presioná ENTER para abrir la ventana...")

    ui = CalibrationUI(frame, point_names)
    pixel_points = ui.run()

    if pixel_points is None:
        sys.exit("[INFO] Calibración cancelada.")

    # Puntos reales correspondientes (en metros)
    real_points = [REFERENCE_POINTS[name] for name in point_names]

    # ── Calcular matriz de homografía ──────────────────────
    src = np.array(pixel_points, dtype=np.float32)
    dst = np.array(real_points, dtype=np.float32)
    H, status = cv2.findHomography(src, dst, method=0)  # 4 puntos exactos, sin RANSAC

    if H is None:
        sys.exit("[ERROR] No se pudo calcular la homografía. Revisá que los 4 puntos no sean colineales.")

    # ── Guardar calibración ─────────────────────────────────
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUTS / f"{video_path.stem}_homography.json"

    calibration = {
        "video": video_path.name,
        "point_names": point_names,
        "pixel_points": pixel_points,
        "real_points": real_points,
        "homography_matrix": H.tolist(),
    }
    with open(out_path, "w") as f:
        json.dump(calibration, f, indent=2)

    print(f"\n✅ Calibración guardada en: {out_path.name}")
    print("   Podés reusarla para todos los videos grabados desde la misma cámara/posición.")
    return out_path


def apply_homography(coords_path: Path, homography_path: Path) -> Path:
    """
    Aplica una calibración guardada a un .parquet de coordenadas en píxeles,
    agregando columnas field_x, field_y en metros reales.
    """
    with open(homography_path) as f:
        calib = json.load(f)
    H = np.array(calib["homography_matrix"], dtype=np.float64)

    df = pd.read_parquet(coords_path)

    # Usamos el punto "feet_y" (pies del jugador) en vez del centro del bbox,
    # porque es el punto que realmente toca el pasto — más preciso para homografía
    points = df[["cx", "feet_y"]].to_numpy(dtype=np.float32).reshape(-1, 1, 2)
    transformed = cv2.perspectiveTransform(points, H).reshape(-1, 2)

    df["field_x"] = transformed[:, 0].round(2)
    df["field_y"] = transformed[:, 1].round(2)

    # Filtrar posiciones fuera de la cancha (± 5m de margen por error de calibración)
    margin = 5.0
    in_bounds = (
        (df["field_x"] >= -margin) & (df["field_x"] <= FIELD_LENGTH + margin) &
        (df["field_y"] >= -margin) & (df["field_y"] <= FIELD_WIDTH + margin)
    )
    n_out = (~in_bounds).sum()
    if n_out > 0:
        pct = n_out / len(df) * 100
        print(f"[AVISO] {n_out} detecciones ({pct:.1f}%) cayeron fuera de la cancha.")
        if pct > 15:
            print("        Esto es alto — revisá la calibración, puede haber puntos mal marcados.")

    out_path = coords_path.parent / f"{coords_path.stem}_field.parquet"
    df.to_parquet(out_path, index=False)

    print(f"\n✅ Coordenadas de cancha exportadas: {out_path.name}")
    print(f"   Nuevas columnas: field_x, field_y (metros, origen en esquina sup-izquierda)")
    return out_path


# ── CLI ────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analizador Táctico — Calibración de homografía",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Calibrar un video nuevo (abre ventana interactiva)
  python src/homography/calibrate.py data/videos/partido.mp4

  # Aplicar una calibración ya hecha a las coordenadas detectadas
  python src/homography/calibrate.py data/videos/partido.mp4 --apply data/outputs/partido_coords.parquet
        """,
    )
    parser.add_argument("video", type=str, help="Ruta al video .mp4 (para calibrar) o de referencia")
    parser.add_argument("--apply", type=str, default=None,
                         help="Ruta a un .parquet de coordenadas — si se pasa, aplica la calibración "
                              "existente en vez de abrir la ventana de calibración")
    args = parser.parse_args()

    video_path = Path(args.video)
    if not video_path.exists():
        sys.exit(f"[ERROR] Video no encontrado: {video_path}")

    if args.apply:
        coords_path = Path(args.apply)
        if not coords_path.exists():
            sys.exit(f"[ERROR] Archivo de coordenadas no encontrado: {coords_path}")
        homography_path = OUTPUTS / f"{video_path.stem}_homography.json"
        if not homography_path.exists():
            sys.exit(f"[ERROR] No hay calibración guardada para este video.\n"
                      f"  Corré primero: python src/homography/calibrate.py {video_path}")
        apply_homography(coords_path, homography_path)
    else:
        calibrate(video_path)
