"""
Analizador Táctico — Módulo de Inferencia (Roboflow)
======================================================
Corre el modelo custom entrenado en Roboflow (RF-DETR Small, 4 clases:
player/goalkeeper/referee/ball) + ByteTrack (vía supervision) sobre un
video de partido. Reproduce en Python la misma lógica que se validó en
el Workflow de Roboflow:
  - Filtro de confianza por clase
  - Resolución de superposición goalkeeper/player (se descarta el
    duplicado "player" cuando se superpone con un "goalkeeper")

Exporta:
  - Video anotado con bounding boxes, track IDs y clase (color por rol)
  - Archivo .parquet con coordenadas frame a frame

Requiere:
    pip install inference supervision opencv-python

Uso:
    export ROBOFLOW_API_KEY="tu-api-key"
    python src/detection/run_inference.py data/videos/partido_clip.mp4
    python src/detection/run_inference.py data/videos/partido_clip.mp4 --skip 1
"""

import argparse
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from tqdm import tqdm

# ── Rutas base ─────────────────────────────────────────────
ROOT    = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / "data" / "outputs"

# Cache persistente de pesos — evita que se pierdan al reiniciar la compu
os.environ.setdefault("MODEL_CACHE_DIR", str(ROOT / "models" / "roboflow_cache"))

# ── Configuración del modelo ────────────────────────────────
MODEL_ID = "santiago-lorenzatti/amateur-soccer-tactical-analysis-1-rfdetr-small-t1"

# Mismos umbrales validados en el Workflow de Roboflow
CONF_THRESHOLDS = {
    "ball":       0.20,
    "player":     0.40,
    "goalkeeper": 0.40,
    "referee":    0.60,
}
DEFAULT_CONF = 0.40  # fallback por si aparece alguna clase no mapeada

# Umbral de superposición para descartar el "player" duplicado sobre un "goalkeeper"
GOALKEEPER_OVERLAP_IOU = 0.50

CLASS_COLORS = {
    "player":     (60, 60, 220),    # rojo
    "goalkeeper": (30, 170, 250),   # naranja
    "referee":    (0, 210, 210),    # amarillo
    "ball":       (255, 255, 255),  # blanco
}


def _lazy_imports():
    """Importa inference/supervision recién acá, con mensaje claro si faltan instalar."""
    try:
        from inference import get_model
        import supervision as sv
    except ImportError:
        sys.exit(
            "[ERROR] Faltan dependencias. Instalá con:\n"
            "  pip install inference supervision opencv-python"
        )
    return get_model, sv


def _iou(box_a, box_b) -> float:
    """Intersection-over-Union entre dos bounding boxes [x1,y1,x2,y2]."""
    xa1, ya1, xa2, ya2 = box_a
    xb1, yb1, xb2, yb2 = box_b
    inter_x1, inter_y1 = max(xa1, xb1), max(ya1, yb1)
    inter_x2, inter_y2 = min(xa2, xb2), min(ya2, yb2)
    inter_w, inter_h = max(0, inter_x2 - inter_x1), max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    if inter_area == 0:
        return 0.0
    area_a = (xa2 - xa1) * (ya2 - ya1)
    area_b = (xb2 - xb1) * (yb2 - yb1)
    return inter_area / (area_a + area_b - inter_area)


def _filter_and_clean(boxes, confs, class_names) -> np.ndarray:
    """
    Aplica, en este orden:
      1. Filtro de confianza por clase (CONF_THRESHOLDS)
      2. Resolución de superposición: si un "player" se superpone con un
         "goalkeeper" con IoU >= GOALKEEPER_OVERLAP_IOU, se descarta el "player"

    Retorna un array booleano (keep_mask) del mismo largo que boxes.
    """
    n = len(boxes)
    keep = np.array([
        confs[i] >= CONF_THRESHOLDS.get(class_names[i], DEFAULT_CONF)
        for i in range(n)
    ])

    gk_idx = [i for i in range(n) if keep[i] and class_names[i] == "goalkeeper"]
    pl_idx = [i for i in range(n) if keep[i] and class_names[i] == "player"]

    for gi in gk_idx:
        for pi in pl_idx:
            if keep[pi] and _iou(boxes[gi], boxes[pi]) >= GOALKEEPER_OVERLAP_IOU:
                keep[pi] = False  # descarta el duplicado "player"

    return keep


def run(video_path: Path, frame_skip: int = 2, api_key: str = None) -> Path:
    get_model, sv = _lazy_imports()

    api_key = api_key or os.environ.get("ROBOFLOW_API_KEY")
    if not api_key:
        sys.exit(
            "[ERROR] Falta la API key de Roboflow.\n"
            "  export ROBOFLOW_API_KEY=\"tu-api-key\""
        )

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    stem = video_path.stem

    print(f"\n[1/4] Cargando modelo {MODEL_ID}...")
    print("       (primera vez: descarga y cachea los pesos localmente)")
    model = get_model(model_id=MODEL_ID, api_key=api_key)
    tracker = sv.ByteTrack()

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        sys.exit(f"[ERROR] No se pudo abrir el video: {video_path}")

    fps          = cap.get(cv2.CAP_PROP_FPS)
    width        = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    print(f"[2/4] Video abierto: {width}x{height} @ {fps:.1f} fps")
    print(f"       Procesando 1 de cada {frame_skip} frames\n")

    out_video_path  = OUTPUTS / f"{stem}_tracked.mp4"
    out_coords_path = OUTPUTS / f"{stem}_coords.parquet"

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_video_path), fourcc, fps, (width, height))

    records = []
    frame_idx = 0

    print("[3/4] Corriendo inferencia...")
    with tqdm(total=total_frames, desc="Frames", unit="fr", ncols=70) as pbar:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            frame_idx += 1
            pbar.update(1)

            if frame_idx % frame_skip != 0:
                writer.write(frame)
                continue

            # ── Detección ───────────────────────────────────
            results = model.infer(frame)[0]
            detections = sv.Detections.from_inference(results)

            class_names = [results.predictions[i].class_name for i in range(len(detections))] \
                if hasattr(results, "predictions") else list(detections.data.get("class_name", []))

            # Fallback si supervision ya trae class_name en .data
            if not class_names and "class_name" in detections.data:
                class_names = list(detections.data["class_name"])

            boxes = detections.xyxy
            confs = detections.confidence if detections.confidence is not None else np.ones(len(boxes))

            # ── Filtro de confianza + resolución de superposición ──
            if len(boxes) > 0:
                keep_mask = _filter_and_clean(boxes, confs, class_names)
                detections = detections[keep_mask]
                class_names = [c for c, k in zip(class_names, keep_mask) if k]

            # ── Tracking (ByteTrack, vía supervision) ──────
            detections = tracker.update_with_detections(detections)

            # ── Dibujar anotación ───────────────────────────
            annotated = frame.copy()
            for i in range(len(detections)):
                x1, y1, x2, y2 = detections.xyxy[i].astype(int)
                tid  = int(detections.tracker_id[i]) if detections.tracker_id is not None else -1
                name = class_names[i] if i < len(class_names) else "unknown"
                color = CLASS_COLORS.get(name, (200, 200, 200))
                label = f"{name} #{tid}" if tid != -1 else name
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                cv2.putText(annotated, label, (x1, max(y1 - 6, 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

                # ── Guardar coordenadas ─────────────────────
                records.append({
                    "frame":      frame_idx,
                    "time_sec":   round(frame_idx / fps, 2),
                    "track_id":   tid,
                    "class_name": name,
                    "x1": round(float(x1), 1), "y1": round(float(y1), 1),
                    "x2": round(float(x2), 1), "y2": round(float(y2), 1),
                    "cx": round((x1 + x2) / 2, 1),
                    "feet_y": round(float(y2), 1),  # punto de apoyo en el pasto
                    "conf": round(float(detections.confidence[i]), 3)
                             if detections.confidence is not None else None,
                })

            writer.write(annotated)

    cap.release()
    writer.release()

    print("\n[4/4] Exportando coordenadas...")
    df = pd.DataFrame(records)

    if df.empty:
        print("[ADVERTENCIA] No se detectaron objetos.")
    else:
        df.to_parquet(out_coords_path, index=False)
        _print_summary(df, out_video_path, out_coords_path)

    return out_coords_path


def _print_summary(df: pd.DataFrame, video_out: Path, coords_out: Path) -> None:
    tracked = df[(df["track_id"] != -1) & (df["class_name"] != "ball")]
    n_ids  = tracked["track_id"].nunique()
    n_dets = len(df)
    dur    = df["time_sec"].max()

    print("\n" + "═" * 50)
    print("  RESULTADO DEL PROCESAMIENTO")
    print("═" * 50)
    print(f"  IDs de tracking únicos (sin pelota) : {n_ids}")
    print(f"  Total de detecciones                : {n_dets:,}")
    print(f"  Duración procesada                  : {dur:.1f} seg")
    print("─" * 50)
    print("  Detecciones por clase:")
    for name, count in df["class_name"].value_counts().items():
        print(f"    {name:<12} {count:,}")
    print("─" * 50)
    print(f"  Video anotado → {video_out.name}")
    print(f"  Coordenadas   → {coords_out.name}")
    print("═" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analizador Táctico — Inferencia con modelo Roboflow (4 clases)",
    )
    parser.add_argument("video", type=str, help="Ruta al video .mp4")
    parser.add_argument("--skip", type=int, default=2, help="Procesar 1 de cada N frames")
    parser.add_argument("--api-key", type=str, default=None,
                         help="API key de Roboflow (o usar variable ROBOFLOW_API_KEY)")
    args = parser.parse_args()

    path = Path(args.video)
    if not path.exists():
        sys.exit(f"[ERROR] Archivo no encontrado: {path}")

    run(path, frame_skip=args.skip, api_key=args.api_key)
