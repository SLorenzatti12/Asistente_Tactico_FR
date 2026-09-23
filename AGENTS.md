# Analizador Táctico — Contexto del proyecto

Sistema de análisis táctico **post-partido** para fútbol amateur (Liga de San Francisco,
Córdoba, Argentina). Proyecto final universitario (UTN FRSF), entrega noviembre 2026.

Toma video de un partido filmado con cámara fija, detecta y trackea jugadores, convierte
posiciones a metros reales sobre la cancha, y muestra métricas tácticas en un dashboard.

---

## Idioma

**Todo el código, comentarios, docstrings y mensajes de consola van en español.**
Los nombres de librerías y términos técnicos establecidos (DataFrame, tracking, parquet)
se dejan como están.

---

## Pipeline

```
video .mp4
  → src/detection/run_inference.py     detección + tracking  → *_coords.parquet
  → src/analysis/team_assignment.py    equipo por color      → agrega columna `team`
  → src/homography/calibrate.py        píxeles → metros      → *_coords_field.parquet
  → app/main.py                        dashboard Streamlit
```

Módulos de análisis que consumen el parquet final:
- `src/analysis/player_stats.py` — stats por track (distancia, velocidad, rangos, zonas)
- `src/analysis/tactical_patterns.py` — fases de juego, líneas, patrones tácticos

---

## Estructura

```
src/detection/run_inference.py      Roboflow RF-DETR + ByteTrack (supervision)
src/homography/calibrate.py         calibración manual de 4 puntos + transformación
src/analysis/player_stats.py        estadísticas individuales por track
src/analysis/team_assignment.py     clustering de color de camiseta (KMeans)
src/analysis/tactical_patterns.py   fases, líneas y patrones tácticos
app/main.py                         estructura, tabs, selector de partido
app/theme.py                        paleta y estilos centralizados
app/components/map_view.py          mapa 2D Plotly + métricas de bloque
app/components/player_stats_view.py vista de stats por jugador
app/components/tagging.py           tagueo one-click + semáforo + SQLite
app/components/video_sync.py        componente CCv2 que sincroniza video y mapa
scripts/download_video.py           descarga de YouTube (yt-dlp)
scripts/train_kaggle.py             entrenamiento en Kaggle (no corre local)
docs/                               bitácoras, plan de testing, validación con clubes
```

---

## Formato de datos

El `.parquet` que consume todo el análisis tiene estas columnas:

| columna | descripción |
|---|---|
| `frame` | número de frame |
| `time_sec` | segundo del video |
| `track_id` | ID del track (ByteTrack). `-1` para la pelota |
| `class_name` | `player` / `goalkeeper` / `referee` / `ball` |
| `x1,y1,x2,y2`, `cx`, `feet_y` | bounding box en píxeles |
| `conf` | confianza de la detección |
| `field_x` | posición en metros sobre el eje largo (0–105) |
| `field_y` | posición en metros sobre el eje ancho (0–68) |
| `team` | `home` / `away` / NaN (solo en `player` y `goalkeeper`) |

Cancha de referencia: **105m × 68m**, origen (0,0) en esquina superior izquierda.

**No cambiar este formato sin revisar todos los consumidores** — `calibrate.py`,
los tres módulos de `src/analysis/`, y los componentes del dashboard dependen de él.

---

## Cómo correr

```bash
export ROBOFLOW_API_KEY="..."        # requerido por run_inference.py

python3 scripts/download_video.py "<url>" --start 00:00:00 --duration 00:00:45
python3 src/detection/run_inference.py data/videos/partido.mp4
python3 src/analysis/team_assignment.py data/videos/partido.mp4 data/outputs/partido_coords.parquet
python3 src/homography/calibrate.py data/videos/partido.mp4           # ventana interactiva
python3 src/homography/calibrate.py data/videos/partido.mp4 --apply data/outputs/partido_coords.parquet
python3 src/analysis/player_stats.py data/outputs/partido_coords_field.parquet
python3 src/analysis/tactical_patterns.py data/outputs/partido_coords_field.parquet

streamlit run app/main.py
```

`python` no existe en este entorno — usar siempre `python3`.

---

## Verificación

Para cambios en el dashboard, verificar con `streamlit.testing.v1.AppTest` que las
pestañas siguen corriendo sin excepciones. **AppTest no ejecuta JavaScript**, así que
todo lo que dependa del componente de video (`video_sync.py`) hay que verificarlo a ojo
en el navegador.

Para módulos de análisis: probar siempre contra los parquets reales en `data/outputs/`,
no solo con datos sintéticos. Varios bugs importantes de este proyecto solo aparecieron
al correr sobre datos de verdad.

---

## Limitaciones conocidas — NO intentar resolver sin leer esto

Estas no son tareas pendientes por olvido. Son decisiones tomadas con motivo documentado.

**El tracking fragmenta identidades.** Un mismo jugador puede aparecer bajo varios
`track_id` (ByteTrack pierde el track tras una oclusión y asigna uno nuevo). Además
**recicla IDs entre clases distintas**: el mismo número puede ser `player` en unos frames
y `referee` en otros. Por eso las métricas son "por track", no "por jugador", y la
distancia recorrida es un piso, no el total real. `tactical_patterns.py` detecta
candidatos a fusión pero **no fusiona automáticamente** — una fusión errónea contamina
dos jugadores en silencio; no fusionar deja el problema visible.

**La homografía asume cámara fija.** Si la cámara panea, la calibración de 4 puntos
deja de ser válida a los pocos segundos. Medido: un video con paneo dio 1.828 tracks
en 10 minutos; el mismo pipeline sobre un clip estable de 45s dio 68.

**La homografía tiembla ~0.1 m por frame** incluso con el jugador quieto. Sin suavizar,
la distancia recorrida queda sobreestimada ~15%. Por eso `player_stats.py` aplica una
mediana móvil sobre las trayectorias antes de medir.

**La pelota se detecta mal** (recall bajo, objeto de pocos píxeles, pocos ejemplos de
entrenamiento). Por eso `tactical_patterns.py` infiere las fases de juego por geometría
del bloque, **no por posesión**.

**El sistema mide posición, no intención.** Un jugador puede despegarse de su línea por
razones tácticamente correctas: desmarque para recibir, marca personal, basculación.
Validado con un DT mirando el video: los tres casos de mayor severidad eran falsos
positivos por esta razón. Por eso los umbrales de evidencia son altos y los patrones se
reportan como señales para revisar en video, **nunca como diagnósticos**.

**Los umbrales están calibrados contra datos reales**, con el número que los justifica
documentado en el comentario de cada constante. No cambiarlos sin medir el efecto sobre
los parquets de `data/outputs/`.

---

## Convenciones al trabajar acá

**Validar antes de afirmar.** Este proyecto tiene historia de conclusiones que parecían
correctas y no lo eran (la dirección de ataque "invertida" que no lo estaba, el
clustering contaminado por el color del pasto). Antes de reportar un hallazgo, verificarlo
contra los datos o el video, no contra la lógica del código.

**Preferir menos features sólidas que más features dudosas.** Ya se descartaron dos
patrones tácticos (`no_repliega`, `cobertura_banda`) porque los clips disponibles no
alcanzan para sostenerlos. Quedaron como esqueletos con `NotImplementedError` y la
explicación adentro.

**Documentar la calibración, no solo el número.** "El umbral es 50%" no es un argumento;
"subí de 25% a 50% porque con 25% marcaba un tercio del plantel" sí lo es.

**No tocar módulos ajenos sin avisar.** El proyecto es de tres personas con ramas
separadas (Santi, Nico, Luci). `map_view.py` y `player_stats_view.py` son de Nico;
`tagging.py` es de Luci.

---

## Git — precauciones específicas

Este repo tuvo que reescribirse con `git filter-repo` dos veces por archivos pesados
commiteados sin querer. **Antes de cualquier `git add .`, revisar `git status`.**

Nunca deben subirse: `venv/`, `models/roboflow_cache/`, `app/static/`, archivos `.mp4`,
`.parquet` ni `.pt`. Ya están en `.gitignore`, pero conviene confirmarlo.

Los videos y parquets de `data/` **no están en el repo** — se regeneran corriendo el
pipeline.

---

## Estado

Sprint 3 (dashboard) en curso. Funciona de punta a punta sobre clips reales.
Un club de la ciudad validó el sistema y se ofreció a aportar videos propios y a dejar
filmar en su cancha — eso desbloquea material más largo, que es lo que varios módulos
necesitan para dar resultados sólidos.
