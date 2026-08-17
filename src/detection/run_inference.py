"""
Analizador Táctico — Módulo de Inferencia
==========================================
Corre YOLOv8 + ByteTrack sobre un video de partido y exporta:
  - Video anotado con bounding boxes, track IDs y clase (color por rol)
  - Archivo .parquet con coordenadas frame a frame

Soporta dos modelos:
  - yolov8n.pt genérico (COCO)         → detecta solo "persona"
  - modelo custom entrenado en fútbol  → detecta jugador/arquero/árbitro/pelota
    (ver scripts/train_kaggle.py para entrenarlo)

Uso:
    python src/detection/run_inference.py data/videos/partido.mp4
    python src/detection/run_inference.py data/videos/partido.mp4 --preview
    python src/detection/run_inference.py data/videos/partido.mp4 --skip 3
    python src/detection/run_inference.py data/videos/partido.mp4 --model models/football_yolo_v1.pt
"""

import argparse
import sys
from pathlib import Path

import cv2
import pandas as pd
from tqdm import tqdm
from ultralytics import YOLO

# ── Rutas base ─────────────────────────────────────────────
ROOT       = Path(__file__).resolve().parents[2]
OUTPUTS    = ROOT / "data" / "outputs"

# ── Configuración del modelo ───────────────────────────────
DEFAULT_MODEL   = "yolov8n.pt"   # Nano genérico: fallback si no hay modelo custom
CONF_THRESHOLD  = 0.40           # detecciones por debajo de esto se descartan

# Clases del modelo genérico COCO (fallback)
COCO_PERSON_CLASS = 0

# Clases del modelo custom entrenado en fútbol (ver train_kaggle.py)
# Confirmado tras el entrenamiento (ver log): names: {0: 'football', 1: 'player'}
# El dataset NO distingue arquero/árbitro — todo lo humano cae en "player".
FOOTBALL_CLASSES = {0: "football", 1: "player"}
FOOTBALL_TRACK_CLASSES = [1]         # trackeamos jugadores; la pelota se detecta pero no se trackea con ID
FOOTBALL_BALL_CLASS    = 0

# Colores por rol (BGR, para cv2) — usados solo si se dibuja anotación custom
CLASS_COLORS = {
    "player":     (60, 60, 220),   # rojo — todos los humanos (no distingue arquero/árbitro)
    "football":   (255, 255, 255), # blanco — la pelota
    "person":     (60, 60, 220),   # fallback modelo genérico
}


def _is_custom_model(model_path: str) -> bool:
    """Un modelo custom es cualquiera que no sea el nombre genérico de Ultralytics."""
    return not Path(model_path).name.startswith("yolov8") or "/" in model_path or "\\" in model_path


def run(video_path: Path, frame_skip: int = 2, show_preview: bool = False,
        model_path: str = DEFAULT_MODEL) -> Path:
    """
    Pipeline principal de inferencia.

    Parámetros
    ----------
    video_path   : ruta al archivo .mp4 del partido
    frame_skip   : procesar 1 de cada N frames (2 = mitad de frames, ~2x más rápido)
    show_preview : mostrar ventana en tiempo real (más lento, útil para debug)
    model_path   : ruta al .pt — genérico ("yolov8n.pt") o custom entrenado en fútbol

    Retorna
    -------
    Path al archivo .parquet con las coordenadas exportadas
    """
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    stem = video_path.stem
    custom = _is_custom_model(model_path)

    # ── 1. Cargar modelo ───────────────────────────────────
    print(f"\n[1/4] Cargando {model_path} {'(custom fútbol)' if custom else '(genérico COCO)'}...")
    model = YOLO(model_path)
    # yolov8n.pt se descarga automáticamente la primera vez (~6 MB) si no existe

    # Determinar qué clases trackear según el tipo de modelo
    if custom:
        track_classes = FOOTBALL_TRACK_CLASSES
        class_names   = FOOTBALL_CLASSES
    else:
        track_classes = [COCO_PERSON_CLASS]
        class_names   = {COCO_PERSON_CLASS: "person"}

    # ── 2. Abrir video ─────────────────────────────────────
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        sys.exit(f"[ERROR] No se pudo abrir el video: {video_path}")

    fps         = cap.get(cv2.CAP_PROP_FPS)
    width       = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_min = total_frames / fps / 60

    print(f"[2/4] Video abierto: {width}x{height} @ {fps:.1f} fps")
    print(f"       Duración: {duration_min:.1f} min — {total_frames} frames totales")
    print(f"       Procesando 1 de cada {frame_skip} frames (~{total_frames//frame_skip} inferencias)\n")

    # ── 3. Configurar writer de salida ────────────────────
    out_video_path  = OUTPUTS / f"{stem}_tracked.mp4"
    out_coords_path = OUTPUTS / f"{stem}_coords.parquet"

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_video_path), fourcc, fps, (width, height))

    # ── 4. Loop de inferencia ─────────────────────────────
    print("[3/4] Corriendo inferencia...")
    records   = []
    frame_idx = 0

    with tqdm(total=total_frames, desc="Frames", unit="fr", ncols=70) as pbar:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            frame_idx += 1
            pbar.update(1)

            # Frames salteados: escribir sin anotar para mantener duración del video
            if frame_idx % frame_skip != 0:
                writer.write(frame)
                continue

            # ── Detección + Tracking (ByteTrack) ──────────
            results = model.track(
                frame,
                persist=True,               # ByteTrack mantiene IDs entre llamadas
                tracker="bytetrack.yaml",   # bundled con Ultralytics
                classes=track_classes,      # personas (+ arquero/árbitro si es modelo custom)
                conf=CONF_THRESHOLD,
                verbose=False,
            )

            result = results[0]

            # ── Dibujar anotación ──────────────────────────
            if custom:
                # Dibujo manual con color por rol (más claro que el genérico de Ultralytics)
                annotated = frame.copy()
                if result.boxes is not None:
                    for box in result.boxes:
                        cls_id = int(box.cls[0])
                        name   = class_names.get(cls_id, "?")
                        color  = CLASS_COLORS.get(name, (200, 200, 200))
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                        tid = int(box.id[0]) if box.id is not None else -1
                        label = f"{name} #{tid}" if tid != -1 else name
                        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(annotated, label, (x1, max(y1 - 6, 10)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            else:
                annotated = result.plot()   # frame con bboxes + IDs (estilo default Ultralytics)

            # ── Extraer y guardar coordenadas ──────────────
            if result.boxes is not None and result.boxes.id is not None:
                boxes     = result.boxes.xyxy.cpu().numpy()
                track_ids = result.boxes.id.cpu().numpy().astype(int)
                confs     = result.boxes.conf.cpu().numpy()
                cls_ids   = result.boxes.cls.cpu().numpy().astype(int)

                for tid, (x1, y1, x2, y2), conf, cls_id in zip(track_ids, boxes, confs, cls_ids):
                    records.append({
                        "frame":      frame_idx,
                        "time_sec":   round(frame_idx / fps, 2),
                        "track_id":   int(tid),
                        "class_name": class_names.get(int(cls_id), "unknown"),
                        # Bounding box completo
                        "x1": round(float(x1), 1),
                        "y1": round(float(y1), 1),
                        "x2": round(float(x2), 1),
                        "y2": round(float(y2), 1),
                        # Centro del bbox (útil para homografía más adelante)
                        "cx": round((x1 + x2) / 2, 1),
                        # Pies del jugador = y2 (bottom del bbox)
                        # Usaremos este punto para proyectar en el mapa 2D
                        "feet_y": round(float(y2), 1),
                        "conf": round(float(conf), 3),
                    })

            # ── Pelota: se detecta pero no se trackea (sin ID persistente) ──
            if custom and result.boxes is not None:
                for box in result.boxes:
                    if int(box.cls[0]) == FOOTBALL_BALL_CLASS:
                        bx1, by1, bx2, by2 = box.xyxy[0].cpu().numpy()
                        records.append({
                            "frame": frame_idx, "time_sec": round(frame_idx / fps, 2),
                            "track_id": -1, "class_name": "ball",
                            "x1": round(float(bx1), 1), "y1": round(float(by1), 1),
                            "x2": round(float(bx2), 1), "y2": round(float(by2), 1),
                            "cx": round((bx1 + bx2) / 2, 1),
                            "feet_y": round(float(by2), 1),
                            "conf": round(float(box.conf[0]), 3),
                        })

            writer.write(annotated)

            if show_preview:
                cv2.imshow("Analizador Táctico — preview (Q para salir)", annotated)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    print("\n[INFO] Preview interrumpido por el usuario.")
                    break

    cap.release()
    writer.release()
    cv2.destroyAllWindows()

    # ── 5. Exportar coordenadas ────────────────────────────
    print("\n[4/4] Exportando coordenadas...")
    df = pd.DataFrame(records)

    if df.empty:
        print("[ADVERTENCIA] No se detectaron jugadores. Revisá la resolución o el conf_threshold.")
    else:
        df.to_parquet(out_coords_path, index=False)
        _print_summary(df, out_video_path, out_coords_path)

    return out_coords_path


def _print_summary(df: pd.DataFrame, video_out: Path, coords_out: Path) -> None:
    """Imprime resumen legible de los resultados."""
    # IDs de tracking reales (excluye la pelota, que se guarda con track_id=-1)
    tracked = df[df["track_id"] != -1]
    n_ids   = tracked["track_id"].nunique()
    n_dets  = len(df)
    dur_sec = df["time_sec"].max()

    print("\n" + "═" * 50)
    print("  RESULTADO DEL PROCESAMIENTO")
    print("═" * 50)
    print(f"  IDs de tracking únicos : {n_ids}")
    print(f"  Total de detecciones   : {n_dets:,}")
    print(f"  Duración procesada     : {dur_sec:.1f} seg")
    print(f"  Promedio det/frame     : {n_dets / df['frame'].nunique():.1f}")

    if "class_name" in df.columns and df["class_name"].nunique() > 1:
        print("─" * 50)
        print("  Detecciones por clase:")
        for name, count in df["class_name"].value_counts().items():
            print(f"    {name:<12} {count:,}")

    print("─" * 50)
    print(f"  Video anotado → {video_out.name}")
    print(f"  Coordenadas   → {coords_out.name}")
    print("═" * 50)

    if n_ids > 30:
        print(f"\n[AVISO] Se detectaron {n_ids} IDs — puede haber fragmentación.")
        print("  Causa probable: oclusiones o cambios de perspectiva.")
        print("  Ajuste: bajar conf a 0.35 o revisar la posición de cámara.")
    elif n_ids < 15:
        print(f"\n[AVISO] Solo {n_ids} IDs detectados — puede haber subdetección.")
        print("  Causa probable: resolución baja o jugadores muy pequeños en frame.")
        print("  Ajuste: bajar conf a 0.30, o si usás yolov8n genérico, migrar al modelo")
        print("  custom entrenado en fútbol (ver scripts/train_kaggle.py).")


# ── CLI ────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analizador Táctico — Inferencia YOLOv8 + ByteTrack",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python src/detection/run_inference.py data/videos/partido.mp4
  python src/detection/run_inference.py data/videos/partido.mp4 --skip 3
  python src/detection/run_inference.py data/videos/partido.mp4 --preview
  python src/detection/run_inference.py data/videos/partido.mp4 --model models/football_yolo_v1.pt
        """,
    )
    parser.add_argument("video",     type=str,            help="Ruta al video .mp4")
    parser.add_argument("--skip",    type=int, default=2, help="Procesar 1 de cada N frames (default: 2)")
    parser.add_argument("--preview", action="store_true", help="Mostrar preview en vivo (debug)")
    parser.add_argument("--model",   type=str, default=DEFAULT_MODEL,
                         help="Ruta al modelo .pt (default: yolov8n.pt genérico). "
                              "Usar el .pt de scripts/train_kaggle.py para detección multi-clase.")
    args = parser.parse_args()

    path = Path(args.video)
    if not path.exists():
        sys.exit(f"[ERROR] Archivo no encontrado: {path}")
    if path.suffix.lower() != ".mp4":
        print(f"[AVISO] La extensión es '{path.suffix}', se esperaba '.mp4'.")

    if args.model != DEFAULT_MODEL and not Path(args.model).exists():
        sys.exit(f"[ERROR] Modelo no encontrado: {args.model}\n"
                  f"  ¿Ya bajaste el best.pt de Kaggle y lo copiaste ahí?")

    run(path, frame_skip=args.skip, show_preview=args.preview, model_path=args.model)
