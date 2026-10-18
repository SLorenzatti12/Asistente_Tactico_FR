# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

Contexto persistente del proyecto para Claude Code. Los archivos importados abajo se cargan automáticamente en cada sesión — mantenerlos actualizados a medida que cambian decisiones o arquitectura.

@docs/context/overview.md
@docs/context/arquitectura.md
@docs/context/decisiones.md
@docs/context/proyecto-analizador-tactico.md
@docs/context/0-validacion-de-problema.md
@docs/context/1-validacion-de-soluciones.md
@docs/context/1.1-analisis-de-entrevistas.md
@docs/context/2-sprint-0.md
@docs/context/3-setup-organizacional.md
@docs/context/4-mvp.md
@docs/context/5-riesgos-y-toma-de-decisiones.md
@docs/context/6-planificacion.md
@docs/context/7-stack-tecnologico.md
@docs/context/8-base-de-datos-hibrida.md

`README.md` describe el stack **inicial** (YOLOv8n + `ultralytics`, 2 clases, entry point `app.py`). Eso quedó obsoleto el 17/08/2026 — ver `decisiones.md`. Para arquitectura y stack actuales, la fuente de verdad es `arquitectura.md`, no el README.

## Setup y comandos

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Levantar el dashboard (entry point real, no app.py)
streamlit run app/main.py
```

No hay suite de tests, linter ni build configurados en el repo (sin `pytest`, sin `.flake8`/`pyproject.toml`, sin Makefile). Para verificar un cambio de UI sin depender del navegador, se puede usar `streamlit.testing.v1.AppTest` para correr `app/main.py` real y clickear widgets por `key` desde un script — ver cualquier sesión reciente que haya tocado `app/` para el patrón.

Para probar el dashboard sin un video/pipeline real, generar datos sintéticos:

```bash
python scripts/make_sample_parquet.py   # crea data/outputs/demo_field.parquet
```

Pipeline completo sobre un video real (offline, por etapas — ver "Flujo de datos" en `arquitectura.md`):

```bash
# 0. (opcional) bajar un partido de YouTube a data/videos/
python scripts/download_video.py "<url>" --start 00:05:00 --duration 00:10:00

# 1. Detección + tracking (requiere ROBOFLOW_API_KEY en el entorno)
export ROBOFLOW_API_KEY="..."
python src/detection/run_inference.py data/videos/<clip>.mp4

# 2. Homografía: calibrar (una vez por cámara/ángulo) y aplicar.
#    Las medidas de la cancha son por estadio (default 105×68): cargarlo una vez
#    y pasarlo al calibrar — quedan copiadas en la calibración y en el parquet.
python scripts/estadios.py alta "<estadio>" --largo <m> --ancho <m>
python src/homography/calibrate.py data/videos/<clip>.mp4 --estadio "<estadio>"
#    (o, con puntos medidos sobre la imagen en vez de clics:
#     --puntos-archivo data/calibracion/<clip>_puntos_f<N>.json)
python src/homography/calibrate.py data/videos/<clip>.mp4 --apply data/outputs/<clip>_coords.parquet

# Rehacer el video anotado (H.264, cajas en todos los frames) desde el parquet, sin el detector
python scripts/regenerar_video_anotado.py data/videos/<clip>.mp4 data/outputs/<clip>_coords.parquet

# Partido de dos tiempos: un video por tiempo, cada uno procesado por separado
# (su parquet, calibración, dirección de ataque y equipos). Si llegó un solo
# archivo con todo, cortarlo primero (no se detecta el entretiempo solo):
python scripts/cortar_video.py data/videos/<partido>.mp4 --en 47:30   # → <partido>_t1.mp4 / _t2.mp4
python scripts/partidos.py alta "<partido>" --t1 <video_t1> --t2 <video_t2> --estadio "<estadio>"
#    Calibración del 2° tiempo propagada desde la del 1° (avisa si la cámara se movió):
python src/homography/calibrate.py data/videos/<video_t2>.mp4 --desde-calibracion data/videos/<video_t1>.mp4
```

Sync manual a la nube (Supabase) — solo con internet, nunca requerido en cancha; ver `8-base-de-datos-hibrida.md` para el setup (proyecto Supabase, `db/schema_cloud.sql`, bucket privado `match-videos`, `.env` a partir de `.env.example`):

```bash
python scripts/sync_to_cloud.py --all
python scripts/sync_to_cloud.py <match_name>
```

## Arquitectura del dashboard (`app/`)

`app/main.py` es el único entry point real (Santi) y actúa de orquestador: mantiene `st.session_state`, resuelve qué partido está seleccionado (`match_selector()`, busca `*_field.parquet` en `data/outputs/` y agrupa los dos tiempos de un partido registrado en `partido_tiempos`, con un selector de tiempo) y monta en el layout las funciones que exponen los módulos de `app/components/` — cada componente es dueño de su propia lógica y estado, `main.py` no la duplica:

- `map_view.py` — mapa 2D (Plotly) + panel de métricas tácticas, a partir del DataFrame `frame, time_sec, track_id, class_name, field_x, field_y[, team]`.
- `video_sync.py` — reproductor de video custom (Custom Component v2) que expone `video.currentTime` a Python; reemplaza a `st.video()` porque ese no permite leer en qué segundo va la reproducción. Videos de hasta 200 MB: hardlink autogenerado en `app/static/` (gitignorado, no tocar a mano; ahí queda solo el del partido abierto). Más grandes: un servidor local con *range requests* que arranca solo con el dashboard (Streamlit no sirve estáticos de más de 200 MB, y desactiva todos si `app/static/` pasa 1 GB).
- `tagging.py` — botonera de tagueo one-click, eventos, y el tab de Semáforo post-partido. Dueño de `data/db/analizador.sqlite` (`init_db()`, tablas `events`/`event_types`/`semaforo`).
- `player_stats_view.py` — estadísticas individuales, sobre `src/analysis/player_stats.py`.
- `team_selector.py`, `roster_view.py`, `video_registry.py` — capa de base de datos híbrida (ver abajo).
- `theme.py` — única fuente de colores/tipografía; debe mantenerse sincronizado a mano con `.streamlit/config.toml` (Streamlit no permite leer ese `.toml` desde Python, así que la paleta vive duplicada en los dos lugares a propósito — ver comentarios en ambos archivos si hay que tocar un color).

## Pipeline de datos (`src/`)

Etapas independientes que se corren por CLI, no importadas por el dashboard en tiempo real (ver comandos arriba):

- `src/detection/run_inference.py` — modelo propio en Roboflow (RF-DETR Small, `player`/`goalkeeper`/`referee`/`ball`) vía paquete `inference`, tracking con `supervision.ByteTrack()`. Exporta video anotado + `*_coords.parquet`.
- `src/homography/calibrate.py` — calibración manual de 4 puntos por cámara; transforma píxeles a metros reales (origen (0,0) en la esquina superior izquierda: `field_x` 0–largo arco a arco, `field_y` 0–ancho lateral a lateral). Las medidas de la cancha salen del estadio (`--estadio`, default 105×68 reglamentaria), se copian al JSON de la calibración y viajan en el parquet como `df.attrs["medidas_cancha"]` — leerlas con `medidas_de_df()` de `src/homography/medidas_cancha.py`. Exporta `*_coords_field.parquet`, el formato que consume todo lo demás.
- `src/analysis/team_assignment.py` — infiere equipo (`home`/`away`) por color de camiseta (KMeans sobre el torso), con muestras por track y el pasto estimado del propio video; los tracks mayormente `goalkeeper` van por geometría.
- `src/analysis/tactical_patterns.py` — fases de bloque (avanza/repliega) y líneas por jugador. Sin detección de posesión confiable (recall bajo de la clase `ball`) — no confundir "fase" con ataque/defensa por posesión.
- `src/analysis/lados.py` — de qué lado juega cada equipo: frena `tactical_patterns` si un video tiene los dos tiempos juntos, y verifica que los equipos cambien de lado entre el 1° y el 2° tiempo.
- `src/analysis/player_stats.py` — estadísticas por `track_id` a partir del parquet en metros.

El `.parquet` es el contrato entre etapas: se mantiene estable entre versiones del modelo de detección para no romper el resto del pipeline.

## Base de datos híbrida (`src/db/`)

SQLite local (`data/db/analizador.sqlite`) es la única base durante el procesamiento/tagueo en cancha — 100% offline, sin excepciones. Supabase (Postgres + Storage) es una segunda capa opcional, alimentada por un sync manual y unidireccional (local → nube, nunca al revés) que se corre aparte cuando hay internet — nunca bloquea ni es requisito del flujo en cancha. Detalle completo, incluyendo el porqué, en `docs/context/8-base-de-datos-hibrida.md`.

Piezas locales (`src/db/`), cada una dueña de su propia tabla en el mismo archivo SQLite:

- `team_repo.py` — equipos/categorías (soporta más de un plantel, ej. Primera/Reserva) y qué equipo jugó cada partido (`match_team`).
- `estadio_repo.py` — estadios con las medidas de su cancha (`estadios`) y en cuál se jugó cada partido (`match_estadio`). Alta/listado/asignación con `scripts/estadios.py`; lo consume `calibrate.py --estadio`.
- `partido_repo.py` — agrupa los dos videos (uno por tiempo) de un partido (`partido_tiempos`). Alta con `scripts/partidos.py`, que copia equipo y estadio a los dos tiempos. Solo local por ahora.
- `roster_repo.py` — plantel de jugadores **por equipo**, cargado una sola vez y reutilizado en todos sus partidos (no por partido). Baja = `DELETE` físico, a propósito (no hay soft delete).
- `video_repo.py` — ruta local del video crudo de cada partido, y si ya se subió.
- `local.py` — helpers de solo-lectura sobre `events`/`semaforo` (tablas de `tagging.py`) para el sync.
- `sync.py` — orquesta el sync: plantel como mirror completo por equipo (upsert + borra en la nube lo que ya no está local), sube el video real a un bucket **privado** de Supabase Storage (`match-videos`), y sincroniza eventos/calificaciones. Todo vía `scripts/sync_to_cloud.py`, nunca desde un botón de Streamlit (subir un video de cientos de MB colgaría la interfaz síncrona de Streamlit).
- `supabase_client.py` — único punto de conexión (lee credenciales de `.env` / `secrets.toml` / env vars).

`db/schema_cloud.sql` es el DDL del lado Supabase — se pega a mano en el SQL Editor del proyecto, es idempotente (`create table if not exists`).
