# Decisiones técnicas clave

Resumen de decisiones con motivo. Detalle completo en `docs/bitacora_2026-08-17.md`.

## Migración de modelo: 2 clases (Kaggle/YOLOv8) → 4 clases (Roboflow/RF-DETR)

**Por qué:** el primer modelo (YOLOv8s, dataset Kaggle) solo distinguía `football` y `player` — no separaba árbitros de jugadores, y un filtro geométrico posterior (descartar detecciones fuera de la cancha) no funcionó porque el árbitro se mueve dentro del campo igual que un jugador.

**Decisión:** migrar a dataset Roboflow `football-players-detection` (4 clases: `ball`, `player`, `referee`, `goalkeeper`) y entrenar en Roboflow Workflows (RF-DETR Small) en vez de Kaggle. Entrenamiento pasó de ~4h35 a <1h.

**Umbrales de confianza finales por clase:**

| Clase | Umbral | Motivo |
|---|---|---|
| `ball` | 0.20 | Recall bajo con pocos ejemplos de entrenamiento (327) y objeto de pocos píxeles — se prioriza recall sobre precisión |
| `player` | 0.40 | Default |
| `goalkeeper` | 0.40 | Default; superposición con `player` resuelta por regla de supresión (IoU ≥ 0.50 → se descarta `player`) |
| `referee` | 0.60 | Subido para reducir falsos positivos |

**Consecuencia en código:** `src/detection/run_inference.py` usa el paquete `inference` (no `ultralytics.YOLO`) y `supervision.ByteTrack()` en vez del `.track()` nativo de Ultralytics, porque el modelo de Roboflow no lo expone. La lógica de filtrado por clase y resolución de superposición se reimplementó en Python — no viene en los pesos descargados.

## Homografía: calibración fija por clic, no dinámica

**Por qué:** la calibración de 4 puntos al inicio del video solo es válida si la cámara no panea. Se comprobó con un video real: cámara "fija" pero con paneo continuo → 1.828 IDs de tracking únicos en 10 min (esperado 15–30); en un segmento sin paneo (27 s) bajó a 74 IDs.

**Decisión:** por ahora, requerir cámara verdaderamente fija (trípode, sin operador) al filmar los partidos reales. Homografía dinámica por frame (vía modelo de keypoints de cancha de Roboflow, `football-field-detection-f07vi/15`) queda como mejora futura, no integrada aún.

## Ángulo de cámara para pruebas: lateral (no detrás del arco)

**Por qué:** menor distorsión de perspectiva a lo largo de los 105 m de cancha — mismo criterio que usan Wyscout/InStat.

## Dependencia `streamlit-sortables` (drag-and-drop de tipos de evento)

**Por qué:** se necesitaba reordenar manualmente los botones de tagueo (`event_types`) con arrastrar-y-soltar. Streamlit no tiene un componente nativo para esto.

**Riesgo asumido a sabiendas:** investigado en GitHub/PyPI antes de instalar — último commit y release en enero de 2025 (casi 20 meses sin actividad a la fecha), y el propio autor lo marca `Development Status :: 3 - Alpha`. Es un componente custom con su propio bundle de JS, así que hay riesgo real de incompatibilidad con versiones nuevas de Streamlit que nadie parcheó. Se decidió probarlo igual (único candidato real para esta funcionalidad puntual) y pinearlo a una versión exacta (`==0.3.1`) en vez de un rango, para no arriesgar una actualización silenciosa de algo ya de por sí frágil.

**Si se rompe:** la alternativa de respaldo (sin dependencias) es reemplazar el drag-and-drop por botones ▲▼ de subir/bajar por fila.

## Base de datos híbrida: se agrega Supabase sin abandonar SQLite

**Contexto:** `7-stack-tecnologico.md` justificó SQLite descartando motores
cliente-servidor (Postgres/MySQL) por la premisa de procesamiento 100%
offline en el estadio. Esa decisión se mantiene sin cambios para todo lo
que ocurre durante el partido.

**Por qué se agrega igual:** SQLite es un archivo en una sola laptop — no
resuelve que un coach vea el semáforo desde su casa, ni un historial de
partidos consolidado del equipo, ni gestión de usuarios/roles. Nada de eso
es necesario en cancha, pero sí después.

**Decisión:** arquitectura híbrida. SQLite sigue siendo la única base
durante el procesamiento/tagueo offline, sin ningún cambio de flujo.
Supabase (Postgres gestionado) se agrega como segunda capa, alimentada por
un sync manual y unidireccional (local → nube) que se corre solo cuando hay
conexión — no es un servidor que se instale en la laptop del analista, es
una API a la que se llama después. Detalle completo en
`8-base-de-datos-hibrida.md`.

**Row Level Security (RLS): desactivada por ahora.** Al correr
`db/schema_cloud.sql` por primera vez (23/09/2026), Supabase avisa que las
tablas quedan sin RLS y ofrece activarla. Se eligió **no activarla**
todavía: el código (`src/db/sync.py`) usa una única key pública
("publishable"/anon) para todas las operaciones, y activar RLS sin
políticas escritas hace que Postgres bloquee todo por default —
rompería el sync entero sin ganar seguridad real (no hay con qué
distinguir usuarios todavía, no hay Auth). **Consecuencia:** cualquiera
con esa key pública puede leer/escribir las tablas directo contra la API
de Supabase, sin pasar por la app. Aceptable para esta etapa (proyecto de
facultad, un solo equipo, sin datos sensibles de terceros); revisar
cuando se agregue Auth — ver el pendiente correspondiente en
`8-base-de-datos-hibrida.md`.

## Infraestructura de repo

- El repo estuvo (y puede volver a estar) sincronizado con iCloud Drive, lo que corrompió archivos (0 bytes) durante merges/clonados. **Evitar arrastrar archivos con Finder**; usar terminal o el editor directamente. Recomendado sacar el repo local de iCloud Drive.
- `venv/` no debe trackearse en Git (se rompió el límite de 100 MB/archivo de GitHub una vez). Si reaparece, verificar `.gitignore` antes de commitear.
