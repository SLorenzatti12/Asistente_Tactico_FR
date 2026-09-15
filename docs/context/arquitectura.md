# Arquitectura y stack técnico

## Stack

- **Lenguaje:** Python 3.10+
- **Detección:** modelo propio en Roboflow (RF-DETR Small, 4 clases: `player`/`goalkeeper`/`referee`/`ball`), vía paquete `inference` — no `ultralytics.YOLO` (ver `decisiones.md`)
- **Tracking:** `supervision.ByteTrack()`
- **Visión & geometría:** OpenCV (homografía)
- **Interfaz:** Streamlit
- **Base de datos:** SQLite (serverless)
- **Procesamiento de video:** FFmpeg / MoviePy

> Nota: `README.md` describe un stack basado en YOLOv8n + `ultralytics`. Eso corresponde al modelo inicial (2 clases), reemplazado durante la sesión del 17/08/2026 — ver `decisiones.md`. Este archivo refleja el pipeline **actual**.

## Estructura real de carpetas

```
Asistente_Tactico_FR/
├── app/
│   ├── main.py                   # Dashboard Streamlit (mapa 2D, métricas, tagueo, semáforo)
│   └── components/
│       ├── map_view.py           # Mapa 2D Plotly + panel de métricas tácticas
│       └── tagging.py            # Botonera de etiquetado / export de clips
├── src/
│   ├── detection/
│   │   └── run_inference.py      # Inferencia (Roboflow RF-DETR) + tracking (ByteTrack)
│   └── homography/
│       └── calibrate.py          # Calibración de homografía (puntos de referencia manuales)
├── scripts/
│   ├── download_video.py
│   └── make_sample_parquet.py
├── docs/                         # Bitácoras, notas de reunión y este contexto
├── data/                         # Videos, assets, calibraciones (mayormente ignorado en Git)
└── db/                           # Esquema y datos SQLite
```

## Flujo de datos (pipeline)

```
video (.mp4)
   → src/detection/run_inference.py   (RF-DETR Small + ByteTrack)
   → *_coords.parquet                 (player/goalkeeper/referee/ball + track_id)
   → src/homography/calibrate.py      (homografía manual, 4 puntos)
   → *_coords_field.parquet           (coordenadas en metros reales)
   → app/main.py                      (dashboard Streamlit)
```

Formato de intercambio entre etapas: `.parquet` con columnas `frame`, `time_sec`, `track_id`, `class_name`, coordenadas. Se mantiene estable entre versiones del modelo de detección para no romper etapas downstream.
