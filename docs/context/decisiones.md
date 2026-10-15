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

## Versiones fijadas de detección/tracking + línea base de regresión (13/10/2026)

**Qué cambió:** se actualizó `inference` 1.4.1 → 1.7.3 (arrastra `inference-sdk` 1.7.3, `inference-models` 0.39.1 y `supervision` 0.30.7). Quedan fijadas con versión exacta en `requirements.txt` para que los tres tengamos lo mismo.

**Efecto medido:** con la misma imagen, el detector nuevo devuelve cajas que difieren hasta ~1 px y confianzas hasta ~0.004 (cambio interno de `inference-models`). ByteTrack amplifica esas diferencias en los IDs. Se verificó que **ByteTrack en sí no cambió**: pasando las mismas detecciones por `supervision` 0.29.1 y 0.30.7, las asignaciones de ID son idénticas fila por fila. Se consideró ruido del tracker, no regresión.

**Línea base de regresión vigente** — `sportivo_min.mp4 --skip 1`, versiones de `requirements.txt`:

| Métrica | Valor |
|---|---|
| IDs únicos (todas las clases menos `ball`) | 133 |
| Detecciones | 30.593 (player 28.694 · goalkeeper 1.745 · referee 88 · ball 66) |
| Tracks `player`+`goalkeeper` >500 / 100-500 / <100 frames | 21 / 26 / 79 |

Línea base anterior (inference 1.4.1, para referencia): 130 IDs · 30.590 detecciones · 23 / 19 / 81.

**Cómo reproducirla** (los criterios de conteo importan — IDs sin `ball`, distribución solo sobre `player`+`goalkeeper`):
```
python src/detection/run_inference.py data/videos/sportivo_min.mp4 --skip 1
python scripts/stats_regresion_tracking.py data/outputs/sportivo_min_coords.parquet
```
Si los números cambian sin haber tocado versiones ni el modelo, algo cambió en el pipeline.

## Control de calidad de la homografía: superposición, no "% fuera de cancha" (13/10/2026)

**Qué se usaba antes:** una calibración se daba por buena si el `--apply` descartaba pocas detecciones por caer fuera de la cancha (p.ej. "4.8 %, dentro de tolerancia") y los puntos clickeados se veían bien ubicados.

**Por qué no alcanzaba:**
- El "% fuera de cancha" solo detecta errores **groseros**, los que sacan a los jugadores fuera de 105×68 m (+1.5 m de margen). Una calibración corrida o mal escalada varios metros *dentro* de la cancha lo pasa igual, porque los jugadores se mueven mayormente lejos de los bordes.
- Mirar los puntos clickeados no sirve: la homografía coincide con ellos **por construcción**. Lo mismo pasa con el error de reproyección de RANSAC sobre los puntos de ajuste (dio 0.2 m en una calibración que estaba 2–4.5 m corrida).

**Qué hay ahora:** `calibrate.py` corre un control al final de toda calibración (y a pedido con `--verificar`). Proyecta las líneas reglamentarias sobre el frame, mide la distancia a las líneas de cal reales **excluyendo las zonas a menos de 4 m de los puntos de ajuste**, guarda la imagen de superposición y da un veredicto `ok` / `revisar` / `no_verificable`. Detalle y límites en el docstring de `calibrate.py`.

**Qué encontró al estrenarlo:** las tres calibraciones manuales guardadas dan REVISAR, y en las tres la imagen lo confirma:

| Calibración | Puntos | Error mediano / p90 | Lo que se ve |
|---|---|---|---|
| `partido_clip2` | 4 esquinas de la cancha | 0.8 m / 3.9 m · 53 % sin línea cerca | Las esquinas **no se ven** en ese plano; se clickearon en los bordes de la imagen. La línea media proyectada cae ~170 px al costado de la real. **Pasaba el criterio viejo con el mismo 4.8 %** |
| `partido_clip` | línea media + área derecha | 1.5 m / 4.3 m · 49 % | Círculo proyectado mucho más chico que el real |
| `sportivo_test_crop` | línea media + área derecha | 2.1 m / 6.4 m · 53 % | `mitad_linea_inf` está sobre la banda cercana, que no se ve: se extrapoló |

**Consecuencia:** las coordenadas en metros de `partido_clip2`, que se usaron en `player_stats`, `team_assignment` y `tactical_patterns`, tenían errores de varios metros.

**Recalibración de `partido_clip2` (13/10/2026):** 9 puntos visibles (línea media con sus cruces del círculo, esquina sup. der., esquinas del área derecha y cruces del arco) sobre el frame 1320, el centro del tramo más largo con la cámara quieta. Control: **OK**, error mediano 0.21 m, p90 0.82 m, 0 % sin línea cerca. La anterior quedó en `partido_clip2_homography_calib_vieja.json` y el parquet anterior en `partido_clip2_coords_field_calib_vieja.parquet`.
- **Con paneo, la matriz fija vale solo en un tramo:** `--verificar` cada 0.5 s da OK únicamente entre 19.5 y 25 s (12 % del clip). En el resto, el error mediano es de 1–3 m. La calibración vieja no daba OK en ningún frame.
- **Lo que más cambió fueron las métricas de bloque.** La calibración vieja estiraba la cancha a lo largo y la comprimía a lo ancho: profundidad del bloque −30/−34 %, amplitud +13/+25 %, área −16/−23 %, con el mismo efecto en el tramo validado. Distancia media −8 %, velocidad máxima 11.8 → 10.0 m/s. Patrones detectados: 0 antes y 0 después.
- **Umbrales:** `PROPORCION_MIN_DESCONEXION` (0.70) sigue excluyendo los dos falsos positivos confirmados por el DT, aunque con menos margen (0.63 y 0.46). `UMBRAL_AVANCE_MS` (0.3) queda dentro del ruido del centroide con las coordenadas nuevas: genera "subidas" espurias en tramos quietos, que podrían habilitar `no_achica` con ruido. Con 0.45 queda solo la subida real. **No se cambió todavía:** con matriz fija y cámara que panea, parte de esa velocidad es movimiento de cámara, y el umbral se debería recalibrar recién con una homografía que siga el paneo.
- **Efecto colateral (resuelto):** al cambiar las filas conservadas, `team_assignment` invirtió las etiquetas `home`/`away`, aunque la asignación física era idéntica. Ver la sección siguiente.

## Etiquetas `home`/`away` estables en `team_assignment` (13/10/2026)

**Problema:** la etiqueta salía del número de cluster de KMeans, y ese orden depende de las muestras. Con distinta calibración (cambian las filas conservadas) o distinta cantidad de frames muestreados (20, 45), el mismo equipo pasaba de `home` a `away`. En el dashboard eso invierte local y visitante sin aviso.

**Decisión:** criterio fijo, **`home` = el equipo de camiseta más clara** (mayor luminancia del color del cluster). Es arbitrario y no tiene por qué coincidir con el local real, pero es el mismo en todas las corridas sobre el mismo video. Si las dos camisetas tienen luminancia parecida (diferencia < 20 en 0–255), queda `orden_etiquetas_confiable = False` en `.attrs["equipos_info"]` y el CLI lo avisa.

**Verificado sobre `partido_clip2`:** con la calibración vieja, con la nueva y con 20/30/45/60 frames muestreados, las etiquetas son las mismas, y dos corridas del CLI dan resultados idénticos track por track. La única diferencia es el track 33 con 60 frames, que cambia de *grupo* (no de etiqueta): es el track con identidad mezclada entre clases que ya se conocía.

**Límite:** con dos camisetas de luminancia parecida (por ejemplo, un rojo y un azul oscuros), el orden puede volver a ser frágil. Por eso se avisa en lugar de decidir en silencio.

## Mejora futura: propagar la calibración en video con paneo (no implementada)

**Contexto:** en `partido_clip2` (transmisión con paneo), una matriz única valida solo el 12 % del clip. El caso de uso real del club es cámara fija (Sportivo), donde una matriz alcanza, así que esto queda registrado y no se implementa por ahora.

**Idea:** calibrar a mano un solo frame (con control OK) y **propagar** esa calibración a cada frame registrando la imagen contra el frame calibrado, por ejemplo con ORB + RANSAC: `H_frame = H_calibrada · G(frame → frame_calibrado)`.

**Por qué funciona en teoría:** una cámara que solo **rota y hace zoom desde un punto fijo** (como una cámara de transmisión sobre un trípode o un cabezal) relaciona dos frames cualesquiera por una homografía *exacta*, para todos los puntos de la escena y no solo los del plano de la cancha, porque no hay paralaje sin traslación del centro óptico. Así que `G` se puede estimar con cualquier cosa con textura (tribuna, carteles, césped), sin depender de que se vean las líneas.

**Evidencia preliminar:** ya se estimó `G` con ORB contra el frame 1320 para elegir el frame de calibración. Hubo 300–500 inliers en la mayor parte del clip, y bajó a 36–65 en un paneo rápido (frames 720–840): esos tramos tendrían que marcarse como baja confianza.

**Cómo se validaría:** con el control por superposición en cada frame propagado (el mismo `control_calidad`), que el porcentaje del clip con OK suba desde el 12 % actual. Riesgos: acumulación de error si se encadenan frames en vez de registrar siempre contra la referencia; cortes de plano (ahí no existe `G`); y que la cámara no rote sobre un punto fijo (una cámara en carro o con operador que se desplaza tiene paralaje).

**La calibración automática por keypoints** (modelo `football-field-detection-f07vi/15`) tampoco pasa el control todavía: errores medianos de 1.2–3.6 m en transmisión y de 4.4 m en Sportivo. El modelo ubica sistemáticamente demasiado afuera los extremos laterales del círculo, y en cámara baja/nocturna no hay keypoints confiables en la mitad cercana.

**Regla que queda:** ninguna calibración se usa sin control OK **y** sin mirar la imagen. Los puntos a clickear tienen que **verse** en el frame; extrapolar marcas fuera de cuadro es la causa principal de las calibraciones malas que encontramos.

## Infraestructura de repo

- El repo estuvo (y puede volver a estar) sincronizado con iCloud Drive, lo que corrompió archivos (0 bytes) durante merges/clonados. **Evitar arrastrar archivos con Finder**; usar terminal o el editor directamente. Recomendado sacar el repo local de iCloud Drive.
- `venv/` no debe trackearse en Git (se rompió el límite de 100 MB/archivo de GitHub una vez). Si reaparece, verificar `.gitignore` antes de commitear.
