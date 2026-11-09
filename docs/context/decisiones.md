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
`8-base-de-datos-hibrida.md`. **Reemplazado el 27/10/2026:** RLS activada
y el sync pasa a la clave secreta; ver "Supabase: RLS activada y sync con
clave secreta (27/10/2026)" más abajo.

## Versiones fijadas de detección/tracking + línea base de regresión (13/10/2026)

**Qué cambió:** se actualizó `inference` 1.4.1 → 1.7.3 (arrastra `inference-sdk` 1.7.3, `inference-models` 0.39.1 y `supervision` 0.30.7). Quedan fijadas con versión exacta en `requirements.txt` para que los tres tengamos lo mismo.

**Efecto medido:** con la misma imagen, el detector nuevo devuelve cajas que difieren hasta ~1 px y confianzas hasta ~0.004 (cambio interno de `inference-models`). ByteTrack amplifica esas diferencias en los IDs. Se verificó que **ByteTrack en sí no cambió**: pasando las mismas detecciones por `supervision` 0.29.1 y 0.30.7, las asignaciones de ID son idénticas fila por fila. Se consideró ruido del tracker, no regresión.

**Línea base de regresión vigente (desde el 16/10/2026)** — `sportivo_min.mp4 --skip 1`, versiones de `requirements.txt`, con el arreglo del bug de clases de `run_inference.py`:

| Métrica | Valor |
|---|---|
| IDs únicos (todas las clases menos `ball`) | 131 |
| Detecciones | 30.593 (player 28.712 · goalkeeper 1.781 · referee 77 · ball 23) |
| Tracks `player`+`goalkeeper` >500 / 100-500 / <100 frames | 21 / 26 / 77 |

Líneas base anteriores, para referencia:
- **13/10/2026:** 133 IDs · player 28.694 · goalkeeper 1.745 · referee 88 · ball 66 · 21 / 26 / 79. **Reflejaba el bug de clases**: las mismas cajas y los mismos IDs, pero ~0.7% de las filas con la clase equivocada (43 jugadores contados como pelota). Por eso cambian los IDs sin pelota y los tracks cortos, aunque el tracking es idéntico. Ver "Bug de clases en `run_inference.py`".
- **inference 1.4.1:** 130 IDs · 30.590 detecciones · 23 / 19 / 81.

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

**Verificado sobre `partido_clip2`:** con la calibración vieja, con la nueva y con 20/30/45/60 frames muestreados, las etiquetas son las mismas, y dos corridas del CLI dan resultados idénticos track por track. La única diferencia es el track 33 con 60 frames, que cambia de *grupo* (no de etiqueta): es el track con identidad mezclada entre clases que ya se conocía (parte de esa mezcla era el bug de clases de `run_inference.py`, ver "Bug de clases en `run_inference.py`" más abajo).

**Límite:** con dos camisetas de luminancia parecida (por ejemplo, un rojo y un azul oscuros), el orden puede volver a ser frágil. Por eso se avisa en lugar de decidir en silencio.

## `team_assignment`: muestreo por track y pasto estimado del video (15/10/2026)

**Problema (`sportivo_crop3`, primer video nocturno con luz amarilla):**
- **Cobertura.** El video dura 26 min y tiene 2.819 tracks de jugador, con una mediana de 15 frames. Con 30 frames uniformes (uno cada ~55 s), solo 47 tracks recibían equipo por color.
- **Pasto.** El pasto nocturno tiene matiz 33–37, justo en el corte del filtro fijo (H ≥ 35). Además, en recortes de torso de ~5×10 px casi todo píxel mezcla camiseta y pasto. Solo se descartaba como pasto el 13% del recorte, y los dos colores de equipo salían verdosos. El filtro de sombra no tenía nada que ver: descartaba 0%.

**Decisión:**
- **Muestreo por track** (hasta 5 muestras repartidas en la vida de cada track, sobre una grilla de 1 frame cada 5, leídas en orden con `grab()`). El modo anterior queda como `--n-muestras N`.
- **Rango de pasto estimado del propio video:** fondo fuera de las detecciones, pico de matiz, y mediana ± 5 desvíos robustos (MAD) en matiz y en saturación mínima. El rango fijo queda como `--pasto-fijo` y como fallback.
- Se usan mediana y MAD, no percentiles, porque tribuna, carteles y pista entran en las colas de la distribución. Con percentiles, la saturación mínima caía a ~55 y el filtro "de pasto" se comía las camisetas blancas.

**Verificado** — coincidencia de cada track consigo mismo, sobre los mismos tracks con ≥3 muestras en todas las variantes:

| Video | Variante | Acuerdo medio | Tracks ≥90% en un solo cluster |
|---|---|---|---|
| `sportivo_crop3` (1.086 tracks) | pasto fijo | 0.851 | 50% |
| | pasto estimado | 0.899 | 65% |
| `partido_clip2` (31 tracks) | pasto fijo | 0.923 | 74% |
| | pasto estimado | 0.929 | 77% |

- En `sportivo_crop3`, las filas de jugador/arquero con equipo pasan de 70% a 93%.
- En `partido_clip2`, las etiquetas son idénticas a las anteriores salvo el track 33 (el de identidad mezclada ya conocido).
- Rangos estimados: `sportivo_crop3` H 26–46, S ≥ 78; `partido_clip2` H 31–51, S ≥ 66.
- Tiempo: ~20 s el video de 26 min.

**Límites:**
- Con el pasto más estricto, en `sportivo_crop3` quedan menos muestras válidas por recorte: 1.303 tracks con voto en vez de 1.606. Se prefiere voto más limpio a más votos.
- El azul de Crecer sigue mezclado con pasto en el color representativo: con jugadores de ~30 px, la mezcla de píxeles no se resuelve filtrando.
- **Arqueros (resuelto el 16/10/2026).** `_asignar_arqueros` asignaba por geometría (mitad de cancha) a todo track con alguna fila `goalkeeper`, aunque fuera casi siempre `player`. En `sportivo_crop3` eran 785 tracks que recibían equipo por posición y no por color.
  - Ahora es arquero solo el track con **más de la mitad** de sus filas `goalkeeper` (`PROPORCION_MIN_ARQUERO`). Esos tracks van por geometría y quedan **fuera** del clustering de color, porque su camiseta es un tercer color. El resto va por color.
  - En `sportivo_crop3` quedan 62 tracks arquero. De los otros 723: 475 reciben equipo por color y 248 quedan sin asignar por falta de muestras válidas, en vez de recibir uno por posición.
  - La consistencia del color no cambia (0.899 / 65% en `sportivo_crop3`, 0.940 / 80% en `partido_clip2`): el arreglo cambia de dónde sale la etiqueta, no el clustering.
  - **Verificado a ojo** sobre 40 de los 207 tracks de `sportivo_crop3` que cambiaron de etiqueta: ~29 quedan bien (blanco → `home`, azul → `away`), ~3 mal y ~8 son ambiguos (identidad mezclada, gente fuera de la cancha). Con la regla geométrica, alrededor de la mitad estaba mal.
  - En `partido_clip2` cambian 4 tracks: 2 se corrigen, 1 empeora (un blanco pasa a `away`, con un jugador rojo pegado en el recorte) y 1 es dudoso.

## Medidas de cancha por estadio (16/10/2026)

**Por qué:** las canchas regionales no miden 105×68 ni respetan siempre las marcas.
- En `sportivo_crop3`, el lado izquierdo, el círculo y la banda cercana cierran a 0.5 px solo con una cancha de ~79 m de ancho.
- El área chica derecha parece medir ~6.2 m de profundidad.
- Con 105×68 fijo en el código, ninguna combinación de puntos de ese video llega a OK, y el filtro "fuera de cancha" descarta jugadores reales cerca de la banda.

**Decisión:**
- Las medidas son un atributo del **estadio**, no del partido ni del equipo (un equipo juega de visitante en otras canchas; Primera y Reserva comparten estadio). Tablas `estadios` y `match_estadio` en `src/db/estadio_repo.py`; alta y asignación con `scripts/estadios.py`. Las marcas no cargadas valen las reglamentarias.
- `calibrate.py --estadio` **copia** las medidas al JSON de la calibración. Es una copia y no una referencia: si después se corrige el estadio, las coordenadas ya generadas siguen siendo coherentes con la calibración que las produjo. `--apply` avisa si el estadio asignado hoy no coincide.
- `--apply` filtra "fuera de cancha" con esas medidas y las deja en el parquet como `df.attrs["medidas_cancha"]`, que pandas conserva al leer y escribir. Sin columnas nuevas, así que el contrato del parquet no cambia. Se leen con `medidas_de_df()` (`src/homography/medidas_cancha.py`).
- Sin dato (JSON o parquet anteriores a esto) se asume 105×68: lo existente sigue funcionando igual. Verificado en `partido_clip2`: mismo control (OK 0.21/0.82 m) y coordenadas idénticas fila por fila.

**Pendiente:**
- Que el dashboard dibuje la cancha con las medidas del parquet (archivos de Nico, ver `docs/pendiente_nico_medidas_cancha.md`).
- Las medidas reales de Sportivo, que se piden al club.

## Calibración de `sportivo_crop3` desde puntos medidos y control que separa "no se ve" de "está corrida" (16/10/2026)

**Clics vs puntos medidos.** En la zona lejana de esta cámara baja, 1 px de alto equivale a ~0.3 m, y la ventana de calibración muestra la imagen reducida.
- Con clics la calibración salió con la línea media a 2.4 m y la banda cercana a 1.0 m.
- Además, el punto `area_chica_inf_der` se clickeó en la esquina del *frente* del área chica: (1752,144) en vez de (1871,141).
- **Decisión:** `calibrate.py --puntos-archivo <json>` calibra con puntos leídos de un archivo. El JSON de la calibración guarda `origen_puntos` (`clics_manuales` o el origen declarado en el archivo, p.ej. `ajuste_de_lineas`, con el método de cada punto). Sirve también para el futuro modo semiautomático.
- La calibración vigente usa `data/calibracion/sportivo_crop3_puntos_f4500.json`: 9 puntos medidos al sub-píxel sobre el frame 4500. La de clics quedó en `sportivo_crop3_homography_clics.json`.

**Medidas de Sportivo:**
- 102×75 m, dato del club. El ancho de 75 m lo confirma la banda cercana, que no entra en el ajuste: queda a 0.11–0.19 m.
- **El área grande derecha está pintada más chica que la reglamentaria:** ~15.0 m de profundidad y ~38.7 m de ancho. La izquierda da reglamentaria.
- Por eso la calibración no usa los puntos de esa área. El control la muestra 1.5 m corrida, que es la diferencia de la pintura y no un error de la calibración.
- Desde la imagen esto se confunde en parte con el largo: un largo de ~104.5 m explicaría casi lo mismo. Conviene medir con cinta la profundidad del área derecha.

**Control de calidad: por qué cambió.** Antes buscaba la línea real más cercana en un radio fijo de 40 px. En la zona lejana eso son ~13 m: medía la banda lejana (tapada por los carteles) contra la base de los carteles con 7–12 m de "error", y las líneas tenues del lado izquierdo sumaban al "% sin línea cerca".

**Cómo busca ahora:**
- La línea real se busca como una cresta sobre la perpendicular a cada muestra proyectada, a ±4 m *en la cancha*.
- La cresta tiene que estar sobre pasto de ambos lados y ser menos saturada que su entorno.
- Una marca con la línea encontrada en menos del 30% de sus muestras queda **no verificada**: se informa y se dibuja en gris, pero no entra en el veredicto.
- Hacen falta al menos 3 líneas verificadas para dar OK.

**El riesgo y cómo se cubre:**
- *Riesgo:* una marca proyectada a más de 4 m de la real tampoco "se encuentra", y quedaría como "no verificada" en vez de fallar. La primera versión daba OK a tres calibraciones que sabemos malas.
- *Cubierto así:* si cerca no hay nada, se busca en una banda ancha (±15 m) una línea **casi paralela** (±35°: una calibración mala también rota las líneas; con los clics, la línea media proyectada quedaba girada ~20°).
- Si esas muestras lejanas forman una línea continua (su distancia cambia suave entre muestras vecinas), la marca se ve pero está **corrida**, y el control falla.

**Verificado sobre todas las calibraciones guardadas** (veredicto esperado = obtenido en las 7):

| Calibración | Control viejo | Control nuevo | Por qué |
|---|---|---|---|
| `sportivo_crop3` (archivo, 9 pts) | revisar | **ok** (0.19 m; 4 líneas verificadas, 6 no se ven) | |
| `sportivo_crop3` clics | revisar | **revisar** | banda cercana corrida 7.4 m, línea media 2.0 m |
| `sportivo_crop3` calib vieja | revisar | **revisar** | banda cercana corrida 4.4 m |
| `partido_clip2` | ok | **ok** (0.25 m; 7 líneas verificadas) | |
| `partido_clip2` calib vieja | revisar | **revisar** | áreas corridas 5–14 m |
| `partido_clip` | revisar | **revisar** | bandas corridas 6–9 m |
| `sportivo_test_crop` | revisar | **revisar** | banda lejana corrida 10 m, error mediano 1.14 m |

**Límite que queda:**
- Lo que no se ve no se verifica. En `sportivo_crop3` el lado izquierdo queda sin verificar porque sus líneas son demasiado tenues para el detector. Ahí la evidencia es el ajuste de líneas a mano (0.10–0.17 m) y la imagen.
- La regla sigue siendo control OK **y** mirar la imagen.

## Primer partido completo con calibración validada: ajustes posteriores (16/10/2026)

**Arqueros fuera de los patrones.** En `sportivo_crop3`, `tactical_patterns` reportó "no achica" sobre el arquero de Crecer: 562 de sus 886 filas eran `goalkeeper` y 311 `player` (confusiones del detector), y esas filas entraban en la línea defensiva. `asignar_lineas` ahora excluye los tracks mayormente `goalkeeper`, con el mismo criterio que `team_assignment` (`tracks_arquero`). Queda 1 patrón en el partido, el del track 626.

**`velocidad_max` solo en tracks de ≥5 s** (`MIN_DURACION_VMAX_SEG`). Los más cortos dan NaN, no 0. Un track de 1.4 s en la banda lejana reportaba 54 km/h.
- **Limitación conocida, no se ataca por ahora:** en tracks largos siguen apareciendo máximos de 10–12 m/s (36–43 km/h), poco creíbles en fútbol amateur. Es ruido de profundidad en la banda lejana: con cámara baja, 1 px de alto ahí son ~0.3 m, y un temblor de la caja de 2–3 px entre frames parece un pique. La duración mínima no lo resuelve. Hasta resolverlo, la velocidad máxima de jugadores lejos de la cámara es orientativa.

**`lost_track_buffer` de ByteTrack: probado, queda en 30.**
- **Cómo se midió:** detector corrido una sola vez sobre `sportivo_min.mp4 --skip 1`, re-trackeado offline con cada configuración. Con la configuración actual reproduce exacta la línea base de ese momento (133 IDs, 21/26/79, todavía con el bug de clases; la tabla es con ese código).
- **Cómo se calcula el buffer:** `max_time_lost = int(frame_rate/30 × lost_track_buffer)`, y cuenta frames *procesados* (con `--skip 3`, cada frame procesado son 3 del video).

| Buffer efectivo | IDs | Tracks >500 / 100–500 / <100 |
|---|---|---|
| 30 frames (actual) | 133 | 21 / 26 / 79 |
| 75 (`lost_track_buffer=90`, `frame_rate=25`) | 124 | 21 / 26 / 72 |
| 90 | 123 | 21 / 26 / 72 |
| 125 | 122 | 21 / 26 / 71 |

- Solo se unen tracks cortos; los largos no aumentan.
- Las 18 reconexiones del buffer de 90, revisadas a ojo, son casi todas jugadores de blanco quietos en un amontonamiento, con saltos de 0–17 px. No se ven uniones entre equipos distintos, pero entre jugadores iguales apiñados la identidad no se puede confirmar a ojo.
- Procesar con `--skip 3` tampoco fragmenta más en este video: 104 IDs y 25 tracks de más de 20 s, contra 131 y 22 con skip 1.
- La fragmentación de `sportivo_crop3` (~105 tracks/min) es la misma que la de `sportivo_min`: viene de oclusiones, salidas de cuadro y detecciones perdidas, no del buffer.
- **Conclusión:** la fragmentación viene de oclusiones (amontonamientos, pelota parada) y de jugadores que salen y vuelven a entrar al cuadro. Para resolverla hace falta reconocer al jugador por su apariencia al reaparecer (re-identificación), no esperar más tiempo con el mismo ID. Queda fuera del alcance del MVP. Mientras tanto las métricas son "por track", y `tactical_patterns` solo señala candidatos a fusión sin fusionarlos.
- `sv.ByteTrack` está deprecado desde supervision 0.28 y se elimina en 0.31: no actualizar sin reemplazarlo.

**Bug de clases en `run_inference.py` (corregido el 16/10/2026):**
- **Qué pasaba:** la lista `class_names` se armaba antes del tracking, pero `update_with_detections` devuelve solo las detecciones que logra asociar. Cuando descartaba alguna, los nombres quedaban desalineados con las cajas: 0.7% de las filas en `sportivo_min`.
- **Arreglo:** la clase se lee de `detections.data["class_name"]` después del tracking.
- **Efecto en `sportivo_min`:** los tracks con más de una clase bajan de 44 a 14, y las filas "pelota" de 66 a 23 (43 eran jugadores).
- **Lo que llamábamos "ByteTrack recicla IDs entre clases" era en buena parte esto.** ByteTrack nunca reutiliza un número. Lo que queda es real pero menor: el detector etiqueta distinto a la misma persona según el frame (sobre todo arquero/jugador), y en una oclusión un track puede saltar a otra persona.
- La línea base de regresión cambió por esto (ver "Versiones fijadas…" arriba). Los parquets generados antes de esta fecha (`partido_clip2`, `partido_clip`, etc.) siguen teniendo el bug hasta que se reprocesen.

## Validación de `tactical_patterns` contra video (casos revisados)

Cada caso que alguien revisa contra el video queda acá: es la única evidencia que tenemos de si los patrones dicen algo útil. Los umbrales se recalibran con varios casos, no con uno.

| Video | Track / patrón | Lo que dijo el sistema | Lectura humana | Consecuencia |
|---|---|---|---|---|
| `partido_clip2` (Mundial 2026, Noruega–Francia, cámara de transmisión) | track 8: jugador que se abre hacia la línea para recibir — `desconectado` | severidad **1.00**, desviación sostenida (proporción 0.58) | **falso positivo** (DT): se despega por un motivo tácticamente correcto | `PROPORCION_MIN_DESCONEXION` = 0.70 |
| ídem | track 17: jugador que hace marca personal (seguía al track 4) — `desconectado` | severidad **1.00**, desviación sostenida (proporción 0.59) | **falso positivo** (DT): ídem | ídem |
| ídem | track 21/74 (la misma persona en dos tracks: 21 → 74, se solapan 0.30 s a 13 cm) — `no_achica` | con los umbrales de entonces (bastaban 2 subidas en el clip): track 21, severidad **1.00**, déficit en **1 de 4** subidas, valor técnico 17.8; su continuación, track 74, severidad 0.54, **1 de 1**, valor técnico 4.3. Evidencia de los dos: 0:30.2–0:40.1 | **falso positivo** (revisado contra el video): seguía la basculación normal del equipo, no era una falla del jugador | `MIN_FASES_ATAQUE` de 2 a 4 y `PROPORCION_MIN_NO_ACHICA` = 0.5 estricto (hacen falta al menos 3 de 4 subidas). Además fue el caso que calibró `MAX_SOLAPAMIENTO_FUSION_SEG` para los candidatos a fusión |
| `sportivo_crop3` (Sportivo–Crecer, cámara fija nocturna, calibración validada) | track 626 (home), banda cercana cerca de la mitad de cancha — `desconectado` | severidad **1.00** ("tendencia marcada"), 81% del tiempo en cancha, evidencia 4:48.7–5:24.7 | **desvío real pero leve, aceptable** (revisado por Santi, 16/10/2026) | ninguna todavía (ver abajo) |
| ídem | track 2374 (home, delantero) — `desconectado` | 81% del tiempo en cancha, evidencia 21:06,8–21:45,7 | **falso positivo** (Santi, 09/11/2026): el partido estaba detenido mientras el arquero rival buscaba la pelota fuera de la cancha | marca "Posible juego detenido" (ver la sección de ese nombre) |

**Patrón en los casos revisados: la severidad máxima no predice nada.** Los 4 casos revisados con severidad 1.00 (tracks 8, 17 y 21 de `partido_clip2`; 626 de `sportivo_crop3`) resultaron 3 falsos positivos y 1 desvío leve. Ninguno fue una "tendencia marcada" como dice el texto que ve el DT.

**Lo que muestra el caso de Sportivo:**
- Es el primer acierto en la dirección del patrón: el desvío existe.
- Pero la **severidad sobrestima**: el sistema dice "tendencia marcada" con severidad máxima, y la lectura humana es leve.
- La severidad satura en 1.0 con duplicar la distancia típica de la línea (`UMBRAL_SEVERIDAD_MAX_DESCONEXION`). Para un jugador de banda, en una línea que se estira a lo ancho, eso puede ser poco.
- **Con un solo caso no se recalibra.** Queda como evidencia para cuando haya más casos revisados con lectura humana de la intensidad, no solo de si es real o falso.

**Caso 626 → 587: el módulo de patrones es sensible a cambios en el tracking.** El arreglo del bug de clases no tocó al jugador (mismas cajas, mismo video), pero cambió la línea que el sistema le asigna, y el caso desapareció. Con el reproceso, el mismo jugador pasa a ser el track 587:
- Empieza 16 s antes (4:32.3–5:24.7) y tiene 430 filas en vez de 307.
- Su línea mayoritaria pasó de **ataque** a **mediocampo**.
- Contra la referencia de mediocampo se despega 1.30 veces (antes 2.11 contra la de ataque), por debajo del umbral de 1.50, así que ya no se reporta.
- En su lugar aparece otro caso, el track 2374 (home, `desconectado`, 21:07.0–21:45.7), todavía sin revisar contra el video.
- **Lectura:** el patrón depende de en qué línea queda clasificado el jugador, y eso cambia con detalles del tracking (dónde empieza el track, qué filas cuentan como `player`). Un cambio de infraestructura que no tiene nada que ver con lo que hizo el jugador apaga o prende un caso.

**Decisión: los patrones se presentan como señal experimental, no como diagnóstico (16/10/2026).** Por las dos evidencias de arriba: la severidad máxima no predijo nada en 4 de 4 casos revisados, y el mismo jugador entra o sale del reporte según detalles del tracking.
- Cada caso se muestra como **"Momento para revisar"**, con sus tramos de video. El texto describe qué se midió y las dos lecturas posibles, sin calificar la intensidad: se sacaron "tendencia leve/moderada/marcada".
- La severidad **solo ordena la lista** y aparece en la fila técnica (consola y pestaña). La pestaña ya no tiene etiquetas ni filtro por severidad, y la lista se titula "Momentos para revisar (N)".
- Esto no cambia qué se detecta (umbrales iguales), solo cómo se le presenta al DT.

**Para reproducir el caso 626 original:** la numeración de tracks corresponde al procesamiento anterior al arreglo del bug de clases. Usar `sportivo_crop3_coords_field_bug_clase.parquet` y `sportivo_crop3_tracked_bug_clase.mp4` en `data/outputs/`. En el reproceso los números de track cambian.

## Partidos completos de 90 minutos: perfilado, alternativas y decisión (18/10/2026)

**Perfilado sobre `sportivo_crop3`** (26.8 min, `--skip 3`), extrapolado ×3.36 a 90 min:

| Etapa | 27 min (medido) | 90 min (estimado) |
|---|---|---|
| `run_inference` | 23.2 min · 894 MB residente (1.38 GB pico) · parquet 3 MB · video anotado 825 MB | ~78 min · ~1.2 GB · video ~2.8 GB |
| `--apply` / `team_assignment` / `player_stats` / `tactical_patterns` | 1.3 s / 21 s / 2.3 s / 23 s (272–531 MB) | ~4 s / ~70 s / ~8 s / ~85 s |
| Dashboard: abrir el partido la primera vez | 23.5 s (683 MB) | ~85 s |
| Dashboard: cada actualización del mapa sincronizado | 16 ms | 21 ms (medido con 90 min simulados) |

- **El video anotado no carga en el dashboard:** Streamlit devuelve 404 a los archivos estáticos de más de 200 MB, y `app/static/` estaba en ~1.02 GB. Si la carpeta pasa 1 GiB, Streamlit desactiva **todos** los estáticos al arrancar.
- **La inferencia ya usa la GPU** (CoreML, formato MLProgram, CPU+GPU). Tarda 82 ms por frame, contra 268 ms solo en CPU. Es el 85% del tiempo: leer el video es el 4% y escribirlo el 8%. Lotes de frames y el Neural Engine no la aceleran (86–88 ms). Dos procesos a la vez rinden +17% en total.
- **El anotado pesa 5 veces el original solo por el códec:** el anotado es mp4v (4.3 Mbps) y el original recortado es H.264 (0.86 Mbps, 165 MB). Además las cajas parpadean: con `--skip 3` solo se dibujaban en uno de cada tres frames.
- Encontrar el frame del mapa tarda 1–3 ms de los 21 ms de cada actualización: hoy no es cuello de botella.

**Alternativas evaluadas** (mejora medida cuando dice "medido"; el resto, estimado):

| Opción | Mejora | Esfuerzo / riesgo | Decisión |
|---|---|---|---|
| a. Usar la GPU | ya la usa (medido) | — | — |
| b. Hilos para leer/inferir/escribir | ≤15% (techo: la inferencia) | medio / bajo-medio | **descartada** |
| c. Subir `--skip` a 5 | −35% de tiempo | muy bajo / cambia distancias y velocidades ~8–12% y obliga a rehacer líneas base (amplitud, profundidad y patrones casi iguales, medido con skip 6) | **descartada** |
| d. RF-DETR Nano | ~1.5× según cifras de Roboflow, sin medir; peor con objetos chicos | alto / alto (reentrenar y revalidar umbrales) | después de noviembre |
| e. Procesar solo tiempo de juego | 5–14% | medio / medio | no se hace |
| f. Proceso nocturno que se pueda retomar | no acelera; quita el riesgo de perder 78 min | medio / bajo | **sí** (paso 4) |
| s. Los dos tiempos en paralelo | +17% (medido) | bajo / bajo | solo si hace falta |
| g. Video anotado en H.264, CRF 26 | 2.8 GB → ~630 MB (medido sobre 3 min); los números de track se leen | bajo / bajo | **sí** (paso 1) |
| r. Repetir las cajas del último frame procesado en los intermedios | saca el parpadeo; atraso ≤80 ms | muy bajo / bajo | **sí** (paso 1) |
| i. Servidor local con *range requests* | cualquier tamaño, con adelantar/retroceder; los videos grandes salen de `app/static/` | bajo-medio / medio | **sí** (paso 1) |
| h. Cajas dibujadas en el navegador sobre el original | sin video anotado (~550 MB por partido) | alto / medio-alto | después de noviembre |
| j. Video en segmentos (HLS) | ninguna sobre la opción i para un archivo local | medio-alto / medio | **descartada** |
| k. Clips de jugadas tagueadas | complementa, no muestra el partido completo; toca `tagging.py` (Luci) | medio / bajo | después de noviembre (Sprint 4) |
| l. Precalcular estadísticas y patrones al procesar | 85 s → ~2 s al abrir | bajo-medio / bajo | **sí** (paso 3, patrones primero; estadísticas anotadas para Nico) |
| p. Guardar en disco el caché de Streamlit | instantáneo después de reiniciar | muy bajo / bajo | **sí** (paso 3) |
| m. Bajar la frecuencia de posiciones del mapa | casi nula (21 ms por actualización) | bajo / cambia métricas | **descartada** |
| n. Índice por frame en el mapa | 3 → 0.07 ms dentro de 21 ms | bajo / bajo, toca `map_view.py` (Nico) | baja prioridad, anotada para Nico |

**Resultado del paso 1 (video), 18/10/2026:**
- **H.264 con CRF 26 y cajas en todos los frames** (`src/detection/video_anotado.py`, usado por `run_inference.py`).
  - `sportivo_crop3`: 825 MB → **103 MB**, un partido de 90 min ~345 MB. Es mejor que lo estimado, porque sin el parpadeo el video comprime mucho mejor.
  - Sin costo de tiempo: `sportivo_min --skip 1` tardó 159 s, contra 157 s antes.
  - Parquet y línea base sin cambios (131 IDs, 21/26/77).
- **`scripts/regenerar_video_anotado.py`** rehace el video anotado desde el parquet, sin el detector: 129 s para los 27 min de `sportivo_crop3`. Da frames idénticos a los de `run_inference.py`: 0 diferencias en 1.500 frames, con skip 1 y con skip 3. El video anterior queda como `*_tracked_anterior.mp4`.
- **`video_sync.py`:**
  - Hasta 200 MB, el video sigue por los estáticos de Streamlit, y en `app/static/videos/` queda solo el del partido abierto (lejos del corte de 1 GB).
  - Más grande, lo sirve un servidor local (Starlette + uvicorn, que vienen con Streamlit) en un puerto libre. Arranca solo con el dashboard y responde *range requests*: 206 con el tramo pedido, verificado con pedidos reales. Solo sirve videos registrados por la app.

**Orden decidido:**
1. Video (g + r + i), reencodeando `sportivo_crop3` sin reprocesar.
2. Entretiempo y verificación automática de la calibración, antes de procesar el segundo tiempo.
3. Dashboard (l + p).
4. Robustez: retomar procesos cortados (f) y aviso de espacio en disco.

## Verificación automática de la calibración a lo largo del video (18/10/2026)

**Hallazgo:** la cámara "fija" de `sportivo_crop3` se movió, y la calibración vigente no vale en el **27% del video**.
- **0:00–0:10:** la cámara todavía se estaba acomodando (apunta a la tribuna). Ahí hay ~1.200 detecciones que no son del partido.
- **0:10–19:40:** deriva lenta, de 0 a ~2 px. El error de posición llega a ~0.8 m de mediana (1.3 m en la banda lejana): vale.
- **19:40.6–19:44.6:** mueven la cámara (pico de 9.5 m de error).
- **Desde las 19:45 hasta el final:** queda corrida ~10 px. Error de posición típico **1.6 m** de mediana y **3 m en la banda lejana**.
- **Consecuencia:** las coordenadas, métricas y patrones de los últimos ~7 minutos están corridas. El caso de patrones del track 2374 (21:07–21:46) cae en ese tramo.

**El control por superposición no alcanzaba para detectarlo.** En este video nocturno verifica pocas líneas y su veredicto depende de cuáles se ven en cada momento: dio REVISAR entre los minutos 10 y 18.5 (por la línea de fondo derecha, de pintura irregular) y OK después del movimiento, con la mediana empeorando apenas de 0.2 a 0.4–0.5 m.

**Qué hay ahora:** `verificar_estabilidad()` en `calibrate.py`.
- **Cómo mide:** registra cada momento del video contra el frame calibrado (ORB + RANSAC, sobre todo lo que tiene textura) y traduce ese corrimiento a error de posición en metros sobre una grilla de la cancha cada 3 m.
- **Criterio "vale":** el mismo del control de calidad (mediana ≤ 1.0 m y p90 ≤ 2.0 m). "Sin comparar" cuando hay menos de 30 coincidencias: cámara apuntando a otro lado, o corte.
- **Muestreo:** cada 30 s, con al menos 60 muestras por video, más el frame calibrado. Donde dos muestras difieren, mira segundo a segundo, y une los tramos separados por un solo segundo.
- **Dónde corre:**
  - al final de cada calibración;
  - con `--verificar` sin `--frame`;
  - antes de `--apply`, que **avisa y no descarta**: los tramos quedan en `df.attrs["calibracion_tramos_no_validos"]`, en segundos.
- **Caché:** el resultado se guarda en `<video>_estabilidad_camara.json`, sin modificar la calibración. Vale mientras no cambien el video, la matriz ni el método.
- **Tiempo:** 11 s para 27 min; ~35 s estimados para 90 min.

**Verificado:**

| Video | Resultado | Contraste |
|---|---|---|
| `sportivo_crop3` | vale en el 73%: no vale 0:00–0:10 ni 19:40.6–26:49 | barrido manual cada 30 s y cálculo de error en metros |
| `partido_clip2` | vale en el 12%: solo 20.3–25.5 s | el control por superposición cada 0.5 s había dado OK solo entre 19.5 y 25 s |

- `--apply` con la verificación da coordenadas idénticas a las vigentes en los dos videos: solo agrega el atributo con los tramos.

**Decisión y resultado: calibración por tramos (18/10/2026).**
- **El JSON de calibración admite `tramos`** (desde, hasta, matriz, frame de referencia, origen y control) **y `excluir`** (rangos descartados). Sin esas claves, todo sigue como antes.
- **`calibrate.py --propagar-tramo DESDE`** agrega un tramo con la matriz base corregida por el corrimiento medido entre el frame calibrado y el centro del tramo: `H_tramo = H_base · G⁻¹`, con G de ORB + RANSAC. Corre el control de calidad y guarda la imagen.
- **`--excluir DESDE HASTA --motivo ...`** descarta un rango. Las dos opciones respaldan antes la calibración (`*_homography_respaldo_<fecha>.json`).
- **La verificación de cámara** compara cada momento contra la referencia de su propio tramo.
- **`--apply`** usa la matriz de cada tramo y descarta las detecciones de los rangos excluidos.
- **`player_stats` (`filter_noise`) y `tactical_patterns` (fases, líneas, candidatos a fusión) excluyen las filas de tramos que siguen sin calibración válida** (`src/homography/tramos_validos.py`), no solo las anotan. Verificado: da idéntico a recortar el parquet a mano.

**Aplicado a `sportivo_crop3`:**
- Excluidos 0:00–0:10 (cámara acomodándose) y 19:40.6–19:45.6 (mientras la movían): 1.682 detecciones.
- Tramo propagado desde 19:45.6, con referencia en el frame 34922 (23:17), 915 coincidencias de registro.
  - Control: **OK**, error mediano 0.22 m, igual que la base. En ese mismo frame, la matriz sin corregir daba REVISAR.
  - Imagen revisada: la línea media y el círculo calzan.
- Verificación de cámara: válida en todo el video, fuera de los rangos excluidos.
- Las posiciones del tramo corregido se movieron 1.3 m de mediana (p90 2.9 m; 2 m en la banda lejana). El tramo base no cambió. Con la corrección, ninguna detección cae fuera de la cancha (antes eran 54).
- **El patrón del track 2374 (21:06.8–21:45.7) sigue apareciendo,** casi igual: valor técnico 3.66 contra 3.69. El jugador está cerca del eje, en el borde del área izquierda (x≈19, y≈34), donde el corrimiento pesaba menos. No era un efecto de la cámara movida.
- El parquet con una sola matriz quedó en `sportivo_crop3_coords_field_una_matriz.parquet`.

**Ojo con `partido_clip2`:** si se vuelve a correr `--apply`, el análisis queda limitado a 20.3–25.5 s, porque es el único tramo con calibración válida (la cámara panea). Es lo correcto, pero cambia sus estadísticas y patrones. El parquet vigente no se tocó.

## Entretiempo: un video por tiempo (18/10/2026)

**Decisión:** la unidad de procesamiento sigue siendo **un video = un tiempo**. Cada tiempo tiene su parquet, su calibración, su verificación de cámara, su dirección de ataque y su asignación de equipos. La dirección de ataque **nunca se asume igual** para los dos tiempos.
- **Tabla `partido_tiempos`** (`src/db/partido_repo.py`): agrupa los dos videos en un partido (`match_name` → `partido`, `tiempo`). Las tablas existentes (`match_team`, `match_estadio`, `events`, `semaforo`…) no cambian: siguen identificando por video.
- **Alta:** con `scripts/partidos.py alta`, que además copia el equipo y el estadio a los dos tiempos.
- **Dashboard:** selector de partido y, debajo, uno de tiempo. Los videos sueltos se ven como antes.
- **No se detecta el entretiempo automáticamente** (decisión de Santi). Filmamos un archivo por tiempo. Si llega uno solo con todo, `scripts/cortar_video.py --en <minuto>` lo corta donde se indique, y el control de cambio de lado frena si alguien procesa los dos tiempos juntos.

**Señal de lado** (`src/analysis/lados.py`): en cada ventana, la mediana de `field_x` de los jugadores de campo de cada equipo (por color, que es confiable). Cada equipo se para, en conjunto, más cerca de su propio arco, así que el signo de home − away dice el lado.
- Dentro de un tiempo el signo no cambia: 100% de las ventanas de 2 min en `sportivo_crop3` (27 min) y de 5 s en `partido_clip2`, siempre a 4 m o más del cero.
- En un video simulado con los dos tiempos (`sportivo_crop3` + una copia espejada), el signo se invierte justo en el cambio.
- Ventanas de ≤120 s, al menos 10 por video; una ventana con |dif| < 2 m no cuenta. Un cambio tiene que sostenerse al menos 2 ventanas seguidas de cada lado.

**Controles que usan esa señal:**
- **Cambio de lado dentro de un video:** `tactical_patterns` no calcula (`CambioDeLadoError`), y `team_assignment` no asigna arqueros por geometría. Los dos explican que hay que cortar el video.
- **Inversión entre tiempos:** si el otro tiempo ya está procesado, cada equipo tiene que haber cambiado de lado. Si no, o las etiquetas home/away se cruzaron entre tiempos, o algo salió mal (equipos o calibración). En ese caso **no se calculan patrones del 2° tiempo**: el CLI corta y la pestaña muestra el error. En el 1° tiempo solo avisa.

**Colores del 1° tiempo como referencia para el 2°** (`team_assignment`): el orden home/away sale de la luminancia de la camiseta, y en el 2° tiempo la luz puede cambiar (por ejemplo, de tarde a noche). Por eso, si el 1° tiempo ya está procesado, cada cluster del 2° se empareja con el color más parecido del 1° (distancia ΔE en CIELAB).
- Umbral **ΔE 12**: entre corridas sobre el mismo video, el color de un equipo varía 1–6; entre los dos equipos de un partido, la distancia es 29–54.
- **Si el emparejamiento se aleja más que el umbral, avisa y no fuerza** (decisión de Santi): queda el orden por luminancia y `equipos_info["referencia_colores"]["usada"] = False`. Se desactiva con `--sin-referencia`.
- Probado con colores iguales, invertidos y lejanos: respeta, corrige y avisa, respectivamente.

**Calibración del 2° tiempo propagada desde el 1°** (`calibrate.py --desde-calibracion <video_t1>`): registra el frame calibrado del 1° tiempo contra el centro del 2° (ORB + RANSAC, el mismo método de la verificación de cámara), propaga la matriz y los puntos, y corre el control de calidad y la verificación de cámara.
- Además informa si la cámara se movió entre los dos videos (en el entretiempo alguien puede tocar el trípode).
- **Probado** cortando `sportivo_crop3` en 13:00 como si fueran dos tiempos. El "2° tiempo" contiene el movimiento de cámara de 19:40:
  - 934 coincidencias de registro; el control dio **OK** (0.25 m mediano).
  - Detectó que la cámara se movió: usar la matriz sin corregir daría 1.54 m de error mediano (2.87 m en la banda lejana).
  - La verificación marcó como no válido 0:00–6:40.4, que en el original es 13:00–19:40.4, el movimiento ya documentado. En ese video de prueba, el frame central queda después del movimiento.
- **Regla:** igual que para el 1° tiempo, control OK **y** mirar la imagen.

**Corte sin reencodear y cantidad de frames.** `cortar_video.py` corta por defecto con *stream copy*: tarda segundos y no pierde calidad.
- El 2° tiempo arranca en el segundo pedido: OpenCV leyó el primer frame en 780.01 s para un corte en 780.0 s.
- Pero el contenedor arrastra los frames desde el keyframe anterior, y `CAP_PROP_FRAME_COUNT` cuenta 96 de más (20.818 contra 20.723 legibles).
- La verificación de cámara muestreaba esos frames inexistentes y reportaba un tramo "momentáneo" falso al final del video. Ahora se cuenta el último frame legible (`_cantidad_frames`). En los videos sin cortar el resultado no cambia.
- La barra de progreso de `run_inference` puede terminar antes del 100% en un video cortado: es solo visual.
- Con `--exacto` reencodea (CRF 18) y corta en el segundo pedido.

**Queda para otros:**
- **Luci:** el semáforo, por partido y no por video (`docs/pendiente_luci.md`).
- **Nico:** el sync de `partido_tiempos` a Supabase, y que `team_selector` asigne el equipo a los dos tiempos (`docs/pendiente_nico_medidas_cancha.md`).

## Mapa 2D: parpadeo al actualizarse y medidas de la cancha (19/10/2026)

**Causa del parpadeo (verificada en el código instalado y en el navegador):** en Streamlit 1.60, `st.plotly_chart` arma el id del elemento con la **figura entera** (`plotly_spec`), aunque se le pase `key` (`key_as_main_identity=False`). El frontend usa ese id como `key` de React. Entonces, cada actualización del mapa (unas 4 por segundo con el video) **desmonta el gráfico y lo vuelve a montar desde cero**: un `<div>` vacío y Plotly dibujando recién en un `useEffect`. Si el navegador pinta antes de que Plotly termine, queda un cuadro sin mapa.

**Qué no funciona en esta versión (probado):**
- `key` fijo y `uirevision`: el gráfico se reemplazó 50 veces en 50 actualizaciones.
- Forzar un id fijo (parche sobre `compute_and_register_element_id`): deja de volver a montarse, pero el frontend se queda con la figura del primer dibujo (`getElementState(id, "figure")`) y **los puntos no se mueven**.
- Pasar el mapa a Vega-Lite (`st.vega_lite_chart`): con o sin `key`, los puntos no se actualizaban en el fragmento.
- La alternativa que sí lo resuelve es un componente propio del navegador que mueva los puntos sin redibujar. Santi la descartó para esta demo.

**Lo que se hizo (`map_view.py`, con el OK de Nico):**
- Sin barra de herramientas de Plotly: con el mouse sobre el mapa aparecía y desaparecía en cada actualización.
- Alto (420 px) y rangos de ejes fijos (`fixedrange`), con la cancha como shapes del layout.
- Contenedor `mapa_2d` pintado del verde de la cancha: si un cuadro queda sin dibujar, se ve verde y no el fondo oscuro.
- En el panel del navegador de la Mac de desarrollo (Chromium), cuadro a cuadro: ningún cuadro sin cancha ni sin puntos, alto constante. **El gráfico se sigue volviendo a montar en cada actualización**: no se pudo medir si en el navegador y la máquina de la demo eso se nota.

**Medidas:** el mapa y las ayudas de las métricas usan `medidas_de_df(df)`: 102×75 en `sportivo_crop3` y 105×68 en `partido_clip2` (sin dato). Se dibujan perímetro, línea media, círculo y áreas grande y chica. El mapa de posiciones de `player_stats_view.py` sigue en 105×68 (pendiente de Nico).

## Migración visual al mockup de Antigravity (22/10/2026)

**Alcance (decisión de Santi):** se migra solo el aspecto del mockup (`mockup/`) al sistema actual: mismas vistas, datos y funciones. Quedan afuera la identidad de jugadores sobre los tracks, los dorsales, las formaciones y las severidades. El análisis de factibilidad pieza por pieza está en el artifact "Factibilidad del mockup Mesa Táctica": 28 de 30 piezas se logran sin dejar Streamlit.

**Decisiones:**
- **Solo modo oscuro**, como el mockup. Se sacó el switch claro/oscuro de `main.py`.
- **Navegación con un selector en el encabezado** en vez de `st.tabs`. Solo se calcula y dibuja la vista elegida: con pestañas se calculaban las cuatro en cada recarga.
- **Fuentes del sistema** en `config.toml`: Inter se descargaba de Google Fonts y sin internet no carga.
- **Estilos atados a clases propias** (`.at-*`) o a contenedores con key (`.st-key-*`), no a `data-testid` internos de Streamlit.

**Hecho (archivos de Santi):**
- **Encabezado:** marca, píldora del partido (tiempo y medidas de la cancha), selector de vista, y el partido y el equipo dentro de un popover.
- **Mesa táctica:** modo de visor (dividido / solo cancha / solo video), encabezados de panel y tarjetas con borde para métricas y tagueo.
- **Patrones:** banda superior y tarjetas en grilla de dos columnas.
- **El video sigue a los saltos.** Antes, un salto desde Patrones o desde el historial de tags movía el slider y la cancha pero no el video, y al darle play el video volvía a pisar el tiempo. Ahora `render_video_sincronizado(..., salto={"id", "t"})` lleva el video a ese segundo; el componente aplica cada id una sola vez. Se usa en cuatro casos:
  - los saltos (además cambian la vista a Mesa táctica);
  - mover el slider a mano;
  - volver a mostrar el video (otra vista, otro modo del visor, otro partido), para que retome donde está la cancha.
- **Verificado:**
  - AppTest sin excepciones sobre `sportivo_crop3` y `partido_clip2`, en las cuatro vistas y los tres modos del visor;
  - en el navegador, el clic en la evidencia 21:06 del track 2374 lleva a la Mesa táctica con el video en 1266.83 s.

**Atajos de teclado y tagueo junto al video (22/10/2026, pedido del club):**
- **Atajos:** los escucha el componente de video, en toda la página, mientras el video está visible:
  - <kbd>Espacio</kbd> reproduce y pausa; <kbd>←</kbd>/<kbd>→</kbd> mueven ±1 s, y con <kbd>Shift</kbd> ±5 s;
  - <kbd>1</kbd>–<kbd>9</kbd> taguean con el botón N de la botonera del equipo activo;
  - <kbd>L</kbd> y <kbd>V</kbd> cambian el tagueo a Local o Visitante.
- **Los tags por teclado usan las mismas funciones que los botones** de `tagging.py` (`get_event_types_for_team`, `save_event`, `TAG_TIME_BUFFER_SEC`), sin tocar el archivo de Luci. Se guarda el tiempo del video al apretar la tecla, menos el colchón.
- **No se disparan** mientras se escribe en un campo de texto ni con <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>/<kbd>Alt</kbd>. Si un botón o el slider tenía el foco, se lo sacan, para que <kbd>Espacio</kbd> no lo apriete.
- **Se usan números y no letras por tipo** (como P/S/T en el mockup) porque los tipos de evento son configurables. Debajo del slider, una leyenda muestra qué número corresponde a cada botón.
- **Disposición de la Mesa táctica (dos filas):**
  - **Arriba:** el video ancho, con la barra de tiempo y los atajos debajo, y el tagueo a su derecha.
  - **Abajo:** cancha y métricas. En "Solo cancha", la cancha sube al lugar del video.
- **Por qué el video va ancho:** la cámara es panorámica. `sportivo_crop3` mide 1920 × 460, y en una columna de ~300 px el video quedaba de ~70 px de alto. Ahora, en una pantalla de 1440 × 900, mide 922 × 221 px.
- **Gráficos e historial de eventos van en desplegables cerrados** (en `tagging.py`, con el OK de Luci). A la vista quedan solo los botones de tagueo.
- **Cerrada, la tarjeta de tagueo mide como la columna del video**: termina en 666 px en una pantalla de 1440 × 900, y la cancha y las métricas asoman arriba del borde. Por eso ya no tiene alto fijo; al abrir un desplegable, crece.
- **El modo del visor quedó fuera del fragmento**, porque cambia la disposición. Cambiarlo redibuja la página entera.
- **"Solo cancha" también reproduce.** El video no se ve, pero sigue montado en modo mini: un botón de reproducir/pausar y el tiempo, arriba de la barra. Es el video el que hace avanzar el tiempo de la cancha. Antes, en ese modo, no había forma de ponerla a correr. Los atajos andan igual.
  - El video oculto es de 1 px, no `display:none`, para que el navegador no deje de decodificarlo.
  - Al cambiar entre "completo" y "mini" el componente se vuelve a montar y retoma donde está la cancha (`_video_lugar`).
  - Verificado en el navegador: en "Solo cancha", reproducir avanza la cancha (5:02 → 5:05); al volver a "Dividido", el video sigue en 5:05.
- En la columna de métricas, los números van más chicos, con un estilo limitado al contenedor `panel_metricas`.
- **Verificado en el navegador** con teclas reales sobre `sportivo_crop3`:
  - espacio y flechas mueven el video lo esperado;
  - a 0:30, <kbd>2</kbd> guardó "Salida" Local en 0:20, <kbd>V</kbd> cambió a Visitante y <kbd>1</kbd> guardó "Presión" Visitante en 0:20;
  - los eventos de prueba se borraron después.

**Vista Jugadores con el aspecto del mockup (22/10/2026, con el OK de Nico):**
- **Qué tiene** (`player_stats_view.py`):
  - barra de filtros: equipo, zona con conteo, búsqueda por número de track, y los parámetros de análisis en un popover;
  - cuatro tarjetas de totales: distancia total, tracks, velocidad máxima (orientativa) y tiempo promedio en cancha;
  - tabla ordenable con barras de distancia y selección de fila;
  - ficha lateral del track elegido: mini cancha con posición promedio y elipse de dispersión, sus números y "Ver en la Mesa táctica";
  - **"Ver en la Mesa táctica" lleva al medio del track** (en un grupo, al medio de su track más largo), no a su primer segundo. Caso que lo motivó (23/10/2026): el track 1078 de `sportivo_crop3` sigue a un jugador de Crecer de 539,0 a 540,4 s, y en un cruce pasa a uno de Sportivo hasta 560,7 s. El voto por color lo marca Local, que es correcto para la mayor parte del track, pero el botón llevaba al comienzo y mostraba al de Crecer. Ahora lleva a 549,9 s (suelto) o a 739,8 s (grupo 1078 → 1146 → 1282).
  - Pendiente, a medir antes de decidir: partir un track en dos cuando el color de la camiseta cambia dentro de él (cambia la asignación de equipos, que alimenta estadísticas y patrones);
  - el mapa de posiciones de todos los tracks, en un desplegable.
- **Solo datos reales** (decisión de Santi): una fila por track, sin dorsales, nombres, sprints, rangos de velocidad ni valoración del DT.
- **El equipo de cada track** es el más frecuente en sus filas; **el inicio**, su primer `time_sec`.
- **La zona ahora usa el largo de la cancha del estadio** (`infer_formation_zones(largo_cancha=...)`, pendiente de la nota de Nico). En `sportivo_crop3` (102 m) puede cambiar la zona de tracks cerca del límite de cada tercio, comparado con antes (105 m).
- **Límite conocido:** la zona sigue saliendo de los tercios de la cancha, sin la dirección de ataque de cada equipo. Para el equipo que ataca hacia la izquierda, "defensa" y "ataque" quedan invertidos.

**Agrupar "posiblemente el mismo jugador" y filtrar por duración (22/10/2026):**
- **Por qué:** la tabla mostraba 1.591 filas en `sportivo_crop3`. La causa es la fragmentación del tracking (~105 tracks por minuto, la mayoría de pocos segundos).
- **Agrupar** usa los pares de `detectar_candidatos_fusion()`, sin cambiar sus criterios, con una regla nueva (`agrupar_candidatos_fusion()`, en `tactical_patterns.py`): se encadena A → B solo si A tiene un único candidato siguiente y B un único previo. Si hay varias continuaciones posibles, no se elige ninguna.
- **Comparación medida en `sportivo_crop3`** (decisión de Santi: regla A):

| Regla | Filas | Grupo más grande |
|---|---|---|
| Sin agrupar | 1.591 | — |
| A: sin ambigüedad (**elegida**) | 1.394 | 6 tracks |
| B: mejor candidato mutuo | 1.062 | 11 tracks |

- **Filtro de duración** (decisión de Santi: por defecto ≥30 s). Filas con la regla A:

| Mostrar | Filas |
|---|---|
| Todos | 1.394 |
| ≥15 s | 580 |
| ≥30 s | 348 |
| ≥1 min | 124 |

- **En `partido_clip2`** se agrupan 2 pares. Uno es el 21 → 74, ya confirmado contra el video como la misma persona.
- **Se muestra como "posible", no como fusión:** en la tabla, "#1078 (+2)"; en la ficha, "posiblemente el mismo jugador (no confirmado)" con la cadena de tracks. El interruptor "Agrupar posibles mismos jugadores" vuelve a mostrar un track por fila. Los datos y los patrones no se tocan: es solo cómo se agrupan las filas en la vista Jugadores.
- **Cómo se calcula cada fila de un grupo:**
  - suma de distancia y de tiempo en cancha;
  - velocidad promedio ponderada por tiempo; velocidad máxima, la mayor;
  - posición ponderada por frames;
  - rango de movimiento aproximado con la envolvente de los rangos de sus tracks.

**Pendiente:**
- **Nico:**
  - paleta del mockup en `theme.py` (hoy conviven dos paletas: la de `theme.py` pinta los gráficos y las tarjetas de métricas);
  - cancha estilo mockup, interruptores de envolvente y centroides, tarjetas de métricas.
- **Luci:** botonera de tagueo y semáforo.
- **Santi, después de la demo:** barra de transporte propia y marcas de eventos en la línea de tiempo, dentro del componente de video.

## Login local y roles (26/10/2026)

**Decisión (Santi):**
- **El login es local:** los usuarios viven en la SQLite de la laptop y funciona sin internet, como todo lo de la cancha. El login de la nube (Supabase Auth y RLS) queda para cuando haya una vista para ver desde casa.
- **Roles:** los cuatro de `db/schema_cloud.sql`.
- **Alta:** el primer admin se crea por consola (`scripts/usuarios.py`) y el resto, desde la app.

**Por qué no `st.login`:** el login de Streamlit usa un proveedor externo (Google, etc.) por internet. En la cancha no anda.

**Cómo está hecho:**
- **`src/db/usuarios_repo.py`:** tabla `usuarios`.
  - Las contraseñas se guardan como hash scrypt con sal por usuario (`hashlib`, sin dependencias nuevas), nunca en claro; mínimo 8 caracteres.
  - Siempre queda al menos un admin activo, y los usuarios se desactivan, no se borran.
  - La matriz de permisos es `PERMISOS`.
- **`app/components/sesion.py`:**
  - pantalla de ingreso y menú del usuario (cambiar contraseña, "Usuarios" para el admin, salir);
  - el usuario se relee de la base en cada corrida, así que desactivarlo o cambiarle el rol aplica en la próxima interacción;
  - la sesión es por pestaña del navegador: al recargar la página hay que volver a ingresar.
- **`app/components/usuarios_view.py`:** alta, cambio de rol, contraseña nueva y activar o desactivar. Un admin no puede desactivarse ni cambiarse el rol a sí mismo.

| Rol | Puede |
|---|---|
| Administrador | todo, incluida la administración de usuarios |
| Analista | taguear (botones y atajos), gestionar el partido (equipo, video) y el plantel, tipos de evento |
| Cuerpo técnico | ver todo y calificar el semáforo |
| Solo lectura | ver; no carga ni modifica nada |

**Qué se controla hoy (en `main.py`):**
- vistas según el rol;
- columna de tagueo y atajos de tagueo solo para quien taguea; para el resto, el video usa todo el ancho;
- equipo y video del partido solo para quien gestiona el partido.

**Límites:**
- **Es control de la pantalla, no de los datos:** quien tenga acceso a los archivos de la laptop puede leer la base y los parquets.
- **Los usuarios y sus hashes no se sincronizan a Supabase.**
- ~~Faltan modos de solo lectura en archivos de Luci y Nico~~ **Resuelto el 27/10/2026:** ver "Roles en tagueo, Semáforo y plantel; autor de cada evento y calificación".

**Verificado (AppTest sobre una copia de la base, con un usuario de cada rol):**
- clave incorrecta rechazada;
- vistas, botones de tagueo y configuración del partido según la tabla;
- alta de usuario y "Salir";
- un usuario desactivado con la sesión abierta queda afuera en la próxima interacción.

También se probó en el navegador (pantalla de ingreso, menú del usuario y vista Usuarios) con un usuario temporal, que después se borró.

## Seguridad: checklist de la Clase 21 (27/10/2026)

**Contexto:** la Clase 21 del Seminario pide pasar una checklist mínima de seguridad sobre el sistema real (base de la sección 5.2 del informe). Se revisó el repo y se corrigió lo que dependía de archivos de Santi o compartidos.

**Ya estaba bien (revisado):**
- **Sin claves en el repo:** `.env` y `.streamlit/secrets.toml` están en `.gitignore`. Se buscó en todo el historial y no aparece ninguno, ni claves de Supabase.
- **Consultas parametrizadas:** los únicos SQL armados con texto usan nombres de tabla o columna de listas fijas del código, nunca un dato del usuario.

**Qué se agregó:**
- **Bloqueo por intentos fallidos** (`usuarios_repo.verificar`).
  - Con 5 ingresos fallidos seguidos con el mismo nombre de usuario, ese nombre queda bloqueado hasta que el más viejo cumple 15 minutos.
  - Se cuenta por el nombre escrito, exista o no, así que el mensaje de bloqueo no revela qué usuarios existen.
  - Un ingreso correcto, o una contraseña nueva puesta por el admin o por consola, reinicia la cuenta.
  - Bloqueado, no se mira la contraseña.
- **Cierre de sesión por inactividad** (`sesion.py`).
  - Se cierra a los 30 minutos sin usar el dashboard. El video reproduciéndose cuenta como uso.
  - Un fragmento que corre cada 60 s (`vigilar_inactividad`) vuelve a la pantalla de ingreso, para que una laptop desatendida no quede con el partido a la vista.
- **Registro de accesos y acciones críticas** (`src/db/registro_repo.py`, tabla `registro`).
  - Registra ingresos (también los fallidos y los bloqueados), salidas, sesiones vencidas, altas, cambios de rol, activaciones, contraseñas cambiadas y respaldos, con quién lo hizo (`actor`: el usuario, `consola` o `sistema`).
  - Nunca guarda contraseñas ni hashes.
  - El admin lo ve en la vista Usuarios ("Registro de accesos y cambios"); por consola, con `scripts/usuarios.py registro`.
  - Las primeras filas de la base real son de la prueba en el navegador del 27/10 (usuario temporal `prueba_ui`, ya borrado). No se editaron: un registro de auditoría no se toca.
- **Respaldo** (`src/db/respaldo.py`, `scripts/respaldo.py`).
  - **Qué guarda:** una carpeta con la base (copia con la API de backup de SQLite, consistente aunque el dashboard esté abierto), los JSON de calibración, los parquets de coordenadas y un manifiesto con el SHA-256 de cada archivo y las filas de cada tabla. Los videos quedan afuera.
  - **Automático:** al ingresar, si el último tiene más de 24 h. Se conservan los últimos 14, en `data/respaldos/` (gitignorado).
  - **Otro disco:** con `--destino` o con la variable de entorno `ANALIZADOR_DIR_RESPALDOS`.
  - **Restaurar:** primero verifica el respaldo (SHA-256, `integrity_check`, filas) y hace otro del estado actual, para poder deshacer.
- **Errores sin datos internos:** `client.showErrorDetails = "none"` en `config.toml`. El navegador muestra un mensaje genérico y el detalle va a la terminal. Para desarrollar: `STREAMLIT_CLIENT_SHOW_ERROR_DETAILS=full`.
- **El dashboard escucha solo en esta laptop:** `server.address = "localhost"`.
  - Antes escuchaba en todas las interfaces: cualquiera en el mismo wifi podía abrir el dashboard y pedirle videos al servidor de `video_sync.py` (que usa la misma dirección).
  - Para usarlo desde una tablet en la red local: `--server.address 0.0.0.0`.
- **Dependencias fijadas:** todas con `==`, a las versiones probadas juntas con Python 3.12.
  - Se sacaron `ultralytics` (el modelo YOLOv8 inicial, ya no se importa) y `pyyaml`.
  - Se agregó `numpy`, que se importa directo y no estaba declarado.
  - En un entorno limpio, `pip install --dry-run -r requirements.txt` resuelve 244 paquetes sin conflictos.

**Verificado:**
- **Pruebas sobre una copia de la base, 24 de 24:**
  - bloqueo a los 5 fallidos aunque después llegue la clave buena;
  - el bloqueo también aplica a un usuario que no existe, y se levanta pasada la ventana o con una contraseña nueva;
  - comprobar la contraseña actual no cuenta como ingreso;
  - el registro no contiene contraseñas ni hashes;
  - restauración real: base con usuarios y eventos borrados y una calibración pisada vuelven al estado del respaldo;
  - un respaldo alterado no se restaura;
  - poda.
- **AppTest:** bloqueo desde la pantalla de ingreso, respaldo automático al ingresar, cierre a los 31 min de inactividad (a los 29 sigue adentro), "Salir" registrado y registro visible para el admin. El de roles y los recorridos generales dan igual que antes.
- **En el navegador:**
  - el servidor escucha solo en `127.0.0.1`: desde la IP de la red, conexión rechazada;
  - el video de `sportivo_crop3` carga;
  - con el video reproduciéndose, después de una pasada del vigilante, avanzó 76.9 s en 76.9 s reales, sin pausarse ni volver a montarse.

**Visto de paso, sin relación con esto:** `partido_clip` y `partido_clip2` siguen con el video anotado en el códec viejo (`mpeg4`), que Chromium no reproduce. Se arregla con `scripts/regenerar_video_anotado.py`, como ya se hizo con `sportivo_crop3`.

**Falta (archivos de Luci y Nico, o decisiones pendientes):** ~~modos de solo lectura, autor de eventos y calificaciones, RLS en Supabase~~ — hechos el 27/10/2026, ver las dos secciones siguientes.

## Roles en tagueo, Semáforo y plantel; autor de cada evento y calificación (27/10/2026)

**Quién lo hizo:** Santi, con el OK de Luci y de Nico (están con otros proyectos). Toca archivos de los dos: `tagging.py` (Luci) y `roster_view.py` (Nico). Cada archivo lo dice en su docstring.

**Qué cambió:**
- **Semáforo para todos los roles** (`PERMISO_VISTA` pasa a `ver_semaforo`).
  - Quien no califica (analista, solo lectura) lo ve en solo lectura.
  - Cada jugador muestra su última calificación, quién la puso y cuándo, también para quien califica (era el "TODO" de la pestaña).
  - Cada clic sigue agregando una fila (queda el historial), y ahora avisa y refresca.
- **Plantel:** con `gestionar_plantel` (admin, analista) se edita. Sin ese permiso (cuerpo técnico, solo lectura) se ve la lista sin alta ni baja.
  - `roster_view.py` vuelve a chequear el permiso adentro, por si otra pantalla lo embebe sin pasar `solo_lectura`.
- **Panel de eventos en solo lectura** (`render_tagging_panel(solo_lectura=True)`) para quien no taguea: los gráficos y el historial, con el clic para ir al momento, sin botonera, sin ⚙️ de tipos y sin editar ni borrar.
  - **Cambio de disposición:** el cuerpo técnico y solo lectura vuelven a tener la columna derecha en la Mesa táctica, con "Eventos del partido". El video ya no ocupa todo el ancho para ellos (decisión del 26/10 revertida, porque ahora esa columna les sirve).
- **Autor:** columnas nuevas `events.created_by` y `semaforo.created_by`, con el usuario del login local. Las agrega `tagging.init_db()` (migración aditiva) y las completan los botones, los atajos de teclado (`main.py`) y el Semáforo.
  - Las filas anteriores quedan en NULL ("sin dato").
  - En el historial, el autor aparece al pasar el mouse sobre cada evento.
  - **No se sincronizan:** en la nube, `created_by`/`rated_by` son uuid de `users`, y los usuarios locales no se suben.
- **Registro de accesos:** editar un evento (antes → después), borrarlo (con quién lo había tagueado) y cada alta o baja del plantel (son datos personales).

**Verificado:**
- **AppTest sobre una copia aislada del proyecto** (para no escribir eventos de prueba en la base real), con un usuario por rol:

| Rol | Mesa: botonera / ⚙️ / editar y borrar | Historial (ir al momento) | Semáforo: calificar | Plantel |
|---|---|---|---|---|
| Admin | sí / sí / sí | sí | sí | edita |
| Analista | sí / sí / sí | sí | no (solo lectura) | edita |
| Cuerpo técnico | no / no / no | sí | sí | solo lectura |
| Solo lectura | no / no / no | sí | no (solo lectura) | solo lectura |

- **Autoría:** un tag del analista guarda `created_by = t_analista`; una calificación del cuerpo técnico, `t_cuerpo`; el lector la ve como "🟢 destacado · por t_cuerpo · …". Alta y baja de un jugador quedan en el registro con el admin como actor.
- **En el navegador (misma copia):** editar un evento queda registrado como "#80: Presión · Local · 00:00 → Presión · Local · 00:02"; borrarlo, con "tagueado por t_admin". Editar y borrar se probaron ahí porque AppTest no simula la segunda corrida dentro de un `@st.dialog`.
- Los AppTest de siempre (roles, seguridad, recorrido general, grupos, historial) sin excepciones.

**Límite que queda:** ~~el Semáforo sigue identificando al jugador por dorsal~~ — resuelto el mismo día con el rediseño del Semáforo (sección siguiente).

## Criterios propios del club para los patrones: revisión del cuerpo técnico y prueba de criterios (27/10/2026)

**Pedido (Santi):** los patrones son lo que más le interesa al club, y tiene que poder establecer sus propios criterios.

**Enfoque acordado:**
- Separar **lo que el sistema mide** (posiciones, líneas, fases: ingeniería, no lo decide el club) de **lo que el club considera un problema** (umbrales, a quién aplica, excepciones).
- Antes de dejar que el club cambie un criterio, juntar evidencia de él mismo. Sin eso, un criterio "propio" es un número inventado con otro nombre.
- **Orden:**
  1. **Calificación de cada momento por el cuerpo técnico** (hecho).
  2. **Vista previa de criterios** (hecho).
  3. **Criterios guardados por equipo**, en unidades de cancha, con versión (pendiente).
  4. **Excepciones por línea o zona** (pendiente). Por jugador no se puede: el tracking no sabe quién es cada uno.
  5. **Patrones nuevos a partir de una ficha** que completa el club (`docs/ficha_criterio_patron.md`).

**Qué se hizo:**
- **Umbrales como parámetros** (`tactical_patterns.py`): los seis umbrales que deciden qué cuenta como patrón pasan a `CRITERIOS_POR_DEFECTO`. Son los de desconectado, no achica y la velocidad de avance del bloque.
  - `detectar_fases(umbral_avance_ms=…)` y `detectar_patrones(criterios=…)` aceptan otros valores, y el resultado deja anotados en `.attrs["criterios"]` los que usó.
  - **Los valores por defecto no cambiaron.** Verificado contra la versión anterior: mismos patrones, fases y "no evaluados", fila por fila, en `sportivo_crop3` (1 momento) y `partido_clip2` (0).
- **Revisión de cada momento** (`src/db/revision_patrones_repo.py`, tabla `patrones_revision`):
  - "👍 Útil", "✅ Correcto tácticamente" o "🚫 No se ve en el video", y un comentario.
  - Solo agrega filas: vale la última y queda el historial.
  - Cada revisión guarda el valor medido, la severidad, el segundo del primer tramo y los criterios con que apareció el momento. Así sigue siendo interpretable si cambia un criterio o se reprocesa el video, que renumera los tracks.
  - **Permiso nuevo `revisar_patrones`:** admin, analista y cuerpo técnico. El lector ve la calificación sin poder cambiarla.
  - Arriba de las tarjetas, "Revisados N de M" por veredicto.
  - "Lo que dijo el cuerpo técnico", el acumulado de todos los partidos por patrón con el % útil y los comentarios, es la evidencia para el informe y para justificar un cambio de criterio.
- **"Probar otros criterios (no cambia nada)":** las seis perillas en unidades de cancha, con el valor vigente y una ayuda.
  - Recalcula el partido abierto (~20 s en `sportivo_crop3`, cacheado) y compara con lo actual: cuántos momentos aparecerían, cuántos son nuevos, cuáles dejarían de aparecer y qué había dicho el cuerpo técnico de cada uno.
  - Los nuevos se pueden calificar ahí mismo, guardando el criterio de prueba con que aparecieron.
  - No guarda criterios ni cambia lo que ven los demás.

**Verificado:**
- **AppTest sobre una copia aislada:**
  - el DT califica "correcto tácticamente" con comentario, y queda guardado con su usuario y el criterio vigente;
  - el resumen pasa a 1 de 1, y el lector lo ve sin control;
  - **con criterios más permisivos** (30% más despegado que su línea, 50% del tiempo, 2 m de déficit), `sportivo_crop3` pasaría de **1 a 16 momentos**: 15 nuevos, 0 desaparecen. Uno nuevo calificado queda con `umbral_desconexion = 0.3`;
  - lo que ven los demás sigue en 1 momento.
- **En el navegador:** la tarjeta con la calificación y el comentario, y el panel de perillas.
- Los AppTest de siempre, sin excepciones.

**Primeras calificaciones (Santi, 27–28/10/2026, `sportivo_crop3`):** 15 momentos de `desconectado`, todos con criterios de prueba (30% más despegado, 50% del tiempo, 2 m). Quedaron 4 útiles, 9 correctos tácticamente y 2 que no se ven. El momento vigente (track 2374) quedó sin calificar.
- **"Cuánto más despegado" no separa:** mediana 1.8× en los útiles y 1.9× en los correctos. Es lo mismo que ya mostraba la severidad.
- **"Qué parte del tiempo" sí separa.** Solo moviendo esa perilla:

| Proporción mínima | Momentos | Útil / correcto / no se ve / sin calificar |
|---|---|---|
| 50% | 9 | 3 / 4 / 1 / 1 |
| 55% | 8 | 3 / 3 / 1 / 1 |
| 60% | 4 | 2 / 0 / 1 / 1 |
| 65% | 2 | 1 / 0 / 0 / 1 |
| 70% (vigente) | 1 | 0 / 0 / 0 / 1 |

  **No se cambia todavía:** son 15 casos de un partido, calificados por Santi y no por el DT. La regla es recalibrar con varios casos.
- **4 de los 6 momentos no útiles no son un problema de criterio:**
  - 2 pelotas paradas, que coinciden con tags "Pelota parada";
  - 1 equipo mal asignado (track 2643);
  - 1 arquero que el detector vio como arquero solo en el 18% de los cuadros (track 2774), así que el filtro de arqueros (más de la mitad) no lo sacó.

**Excepción por pelota parada (28/10/2026): probada, no ayuda con estos datos.**
- **Qué es:** criterio `ventana_pelota_parada_seg` (por defecto 0, no excluye nada) y parámetro `pelotas_paradas` de `detectar_patrones`.
  - Saca de líneas y fases los segundos que siguen a cada tag "Pelota parada" del analista, y los descuenta del tiempo en cancha.
  - **Usa los tags, no la detección de pelota,** que tiene recall bajo.
  - Es una perilla más en "Probar otros criterios".
- **Con la ventana en 0,** el resultado es idéntico al anterior en los dos partidos.
- **Efecto con los criterios de prueba,** frente a las calificaciones:
  - con 15 s salen los dos de pelota parada (674, 774), pero también el **140, que era útil**;
  - con 30 s sale además el **742, útil**. En esa misma pelota parada el 774 era "correcto" y el 742 "útil";
  - la proporción de útiles baja: 27% sin excepción, 25% con 15 s, 20% con 30 s.
- **Por qué no sirve:**
  - **Saca de más.** Sacar tiempo cambia el denominador de todos los jugadores que estaban en cancha en ese momento, no solo de los que estaban en la jugada.
  - **Agrega momentos.** Con los criterios vigentes más 30 s aparece el 638.
  - **Una pelota parada no hace "correcto" todo lo que pasa en ella.**
- **Queda la perilla para probar con más partidos,** pero no se recomienda activarla. La alternativa propuesta es no excluir nada y avisar en la tarjeta cuando un momento coincide con una pelota parada tagueada, para que lo juzgue el DT.

**Uso esperado:**
1. El club revisa y califica los momentos de varios partidos.
2. Con "Probar otros criterios" se mira qué umbral separa lo "útil" de lo "correcto tácticamente".
3. Recién con esa evidencia se propone cambiar un criterio, mostrando antes el efecto (la regla de siempre).

## Semáforo por partido: plantel del club, minutos y valoración de DT, ayudante y coordinador (27/10/2026)

**Pedido (Santi):** el semáforo no identifica a nadie. El club carga su plantilla y el cuerpo técnico registra minutos y rendimiento. Cada jugador tiene apellido, nombre, minutos jugados y la valoración de tres personas: DT, ayudante de campo y coordinador. Y una vista para crear el plantel.

**Decisiones (Santi):**
- Cada columna de valoración es de una **función del usuario** (no de un rol). La asigna el admin, y cada uno completa solo la suya.
- La escala sigue siendo 🔴🟡🟢.
- La nube se deja para después (ver abajo).

**Quién lo hizo:** Santi, con el OK de Luci (el semáforo era de `tagging.py`) y de Nico (`roster_repo`, `roster_view`).

**Cómo quedó:**
- **Vista "Semáforo"**, con dos subvistas: "Planilla del partido" y "Plantel".
  - No se agregó un quinto botón al encabezado, que ya se desbordó una vez con cinco.
  - Archivo `app/components/semaforo_view.py`.
- **Planilla del partido:** una fila por jugador del plantel (por su id, no por dorsal), con los minutos y tres semáforos.
  - **Quién edita qué:**
    - **Minutos:** cualquiera con permiso de calificar (cuerpo técnico, admin).
    - **Valoración:** solo la columna de la propia función.
    - **Columnas ajenas:** se ven como etiquetas de color, con quién y cuándo al pasar el mouse.
    - **Sin permiso** (analista, solo lectura): todo en solo lectura.
  - **Guardado:** cada cambio se guarda al momento.
  - **Datos:** `src/db/semaforo_repo.py`, tablas `semaforo_minutos` y `semaforo_valoraciones`.
    - Solo agregan filas: vale la última, y queda el historial, visible en "Historial de cambios".
    - Cada fila guarda el nombre del jugador en ese momento, para que el historial se lea aunque después se le dé de baja.
  - **El callback de valoración vuelve a chequear la función en el servidor.**
- **Por partido, no por video:** los dos tiempos de un partido (`partido_tiempos`) comparten la planilla (`clave_partido`). Resuelve el pendiente de Luci del 18/10/2026.
- **Plantel** (`roster_view.render_plantel`):
  - elegir o crear el equipo;
  - la plantilla como planilla editable (apellido, nombre, dorsal opcional), con agregar, corregir y sacar filas y "Guardar cambios";
  - importar desde un CSV (apellido, nombre[, dorsal]; coma o punto y coma; agrega sin borrar y saltea los que ya están).
  - Solo lo editan admin y analista. Cada alta, corrección y baja queda en el registro, igual que crear un equipo.
- **`roster`:** columnas nuevas `apellido` y `nombre`. Migración aditiva: las filas anteriores se parten por la última palabra.
  - `full_name` se sigue llenando ("Nombre Apellido"), porque lo sube el sync.
  - Ahora se ordena por apellido.
- **Usuarios:** columna `funcion` (`dt`, `ayudante`, `coordinador` o vacía), independiente del rol.
  - Se asigna en la vista Usuarios (alta y edición), y el cambio queda registrado.
  - Por consola: `scripts/usuarios.py crear … --funcion dt`.
  - `usuarios.py demo` crea `dt_demo`, `ayudante_demo` y `coordinador_demo`.
- **Lo que salió de `tagging.py`:** la pestaña vieja (`render_semaforo_tab`, `save_semaforo`, `load_roster`).
  - La tabla vieja `semaforo` (una fila por dorsal) se sigue creando porque el sync la lee, pero ya no se escribe.
  - Sus filas (7, de prueba) no se migraron: estaban por dorsal y el plantel real está vacío.

**Verificado:**
- **Lógica, sobre una copia de la base (19 de 19):**
  - migración del plantel (idempotente);
  - detección de altas, correcciones y bajas;
  - filas vacías ignoradas; apellido obligatorio; dorsal 0–99;
  - CSV con punto y coma y dorsal opcional; CSV sin apellido da error claro;
  - un partido para los dos tiempos;
  - vale la última carga y el historial no se pisa;
  - rechaza minutos fuera de 0–130, funciones y valoraciones desconocidas;
  - cambio de función registrado.
- **AppTest con 7 usuarios** (admin, analista, DT, ayudante, coordinador, cuerpo técnico sin función, lector):

| Usuario | Minutos | Columna editable | Plantel |
|---|---|---|---|
| Admin (sin función) | edita | ninguna (se le explica que falta la función) | edita |
| Analista | solo lectura | ninguna | edita |
| DT / Ayudante / Coordinador | edita | solo la suya | solo lectura |
| Cuerpo técnico sin función | edita | ninguna | solo lectura |
| Lector | solo lectura | ninguna | solo lectura |

- **Cargas:** las del DT y del ayudante quedan con su usuario. Lo que se carga desde el 1° tiempo se ve igual desde el 2°. Alta y cambio de función desde la vista Usuarios.
- **En el navegador, sobre una copia aislada:**
  - la planilla con 11 jugadores;
  - un clic en la columna propia guarda y actualiza el contador;
  - corregir un nombre en el plantel y guardar queda registrado ("Pirulo #- → Cristian Pirulo #-").

**Pendiente:**
- **Sync a la nube** de `semaforo_minutos`, `semaforo_valoraciones` y de `apellido`/`nombre`. Hay que cambiar el esquema de la nube (minutos y valoraciones por `players.id` y por función), y conviene hacerlo después de que Nico aplique la seguridad de la nube. Mientras tanto, el sync sigue subiendo la tabla vieja `semaforo`, que ya no recibe filas nuevas.
- **Excel directo (.xlsx):** necesita `openpyxl`, que no está instalado. Hoy se importa como CSV ("Guardar como → CSV").

## Supabase: RLS activada y sync con clave secreta (27/10/2026)

**Quién lo hizo:** Santi, con el OK de Nico. Reemplaza la decisión del 23/09/2026 ("RLS desactivada por ahora", más arriba).

**El problema:** con RLS desactivada, cualquiera con la clave pública del proyecto podía leer y escribir todas las tablas directo contra la API: plantel con nombres reales, semáforo, eventos, la tabla `users` con emails. Era el riesgo R2 de la matriz de la sección 5.2.

**Decisión:**
- **RLS activada en las 11 tablas, sin políticas para `anon` ni `authenticated`:** con la clave pública no se lee ni se escribe ninguna fila.
- **Defensa en profundidad:** además se le sacan a `anon` todos los permisos de tabla, también para las tablas futuras.
- **Storage:** el bucket `match-videos` queda privado y se borran las políticas que le daban acceso a `anon` o `public` sobre ese bucket.
- **El sync usa la clave secreta** (`SUPABASE_SECRET_KEY`, rol `service_role`, que saltea RLS).
  - Va solo en el `.env` de la máquina que sincroniza. No se lee de `st.secrets`, así que la app de Streamlit nunca la tiene.
  - `get_client()` rechaza la clave pública puesta como secreta (por prefijo `sb_publishable_`/`sb_secret_` o por el rol del JWT de las claves viejas).
- **Por qué clave secreta y no Supabase Auth:** Auth necesita crear cuentas en la nube y escribir políticas por club y rol, y hoy no hay ninguna pantalla en la nube que lo use. El sync es un script local, el caso de uso típico de la clave secreta.
  - **Contracara:** quien tenga la laptop que sincroniza tiene la clave con acceso total a la nube. Por eso conviene el cifrado de disco (riesgo R7) y tener la clave solo en esa máquina.
  - Cuando haya una vista en la nube (el DT mirando el semáforo desde la casa), van Supabase Auth y políticas para `authenticated`.

**Piezas:**
- `db/rls_cloud.sql`: idempotente; al final muestra una tabla de control (`rls = t`, `anon_puede = f`).
- `db/schema_cloud.sql`: ahora avisa que después hay que correr el de RLS.
- `src/db/supabase_client.py`: `get_client()` (secreta) y `get_client_publico()` (solo para verificar).
- `scripts/verificar_rls.py`: contra el proyecto real, comprueba que la clave pública no lee, no inserta, no lista ni sube videos, y que la secreta lee todo. Si algo se pudo escribir con la pública, lo borra con la secreta y lo informa como FALLA.

**Verificado:**
- **En un PostgreSQL 14 local que imita a Supabase:** roles `anon`, `authenticated` y `service_role` (con `bypassrls`), los permisos por defecto de Supabase, y un esquema `storage` con políticas abiertas a `anon` y `public` sobre el bucket.
  - **Antes:** la clave pública leía y llegó a insertar un club.
  - **Después:** `anon` recibe "permission denied" en las 11 tablas y "violates row-level security" al subir un video, y lista 0 objetos. `service_role` lee, escribe y sube.
  - El bucket quedó privado; se borraron las dos políticas abiertas y la de otro bucket quedó intacta.
  - Correrlo dos veces da lo mismo.
- **`verificar_rls.py` con dos nubes simuladas:** con RLS, 25 de 25 controles OK; sin RLS, detecta las 4 fallas y no deja restos.

**No verificado:** nada de esto se corrió contra el proyecto real de Supabase. Las credenciales no están en esta máquina (están en la de Nico), y aplicarlo es un cambio en la nube que tiene que hacer quien tenga acceso al dashboard. Los pasos están en `8-base-de-datos-hibrida.md` ("Seguridad de la nube"). **Hasta que se apliquen, el riesgo R2 sigue abierto.**

## 2° tiempo de Sportivo – Crecer: primer partido con los dos tiempos (28/10/2026)

**El video:** `IMG_8977.MOV` (Descargas de Santi). Santi confirmó que es el **2° tiempo**, aunque los horarios de grabación dicen lo contrario:

| Archivo | Inicio de grabación | Duración | Cuadros/s |
|---|---|---|---|
| `IMG_8977.MOV` | 24/09 22:08:38 | 27:43 | 29,97 |
| `SportivoVsCrecer.MOV` (origen de `sportivo_crop3`) | 24/09 23:09:00 | 26:49 | 25 |

El de 25 cuadros/s con horario redondo parece un archivo exportado (los iPhone graban a 29,97). Si algún día aparece evidencia en contra (reloj, marcador), los dos tiempos se intercambian con `scripts/partidos.py alta`.

**Procesado igual que el 1° tiempo:**
- **Recorte:** la misma franja de cancha que `sportivo_crop3`, `crop=1920:460:0:620`, medida con coincidencia exacta (1.000) contra el MOV del 1° tiempo. Queda en `data/videos/sportivo_t2.mp4` (H.264, 406 MB); el original queda en Descargas, sin tocar.
- **Detección:** `run_inference --skip 3`, 3.000 tracks en 27,8 min (el 1° tiempo tuvo 2.871 en 26,8 min). Video anotado en H.264, 118 MB.
- **Calibración:** propagada desde el 1° tiempo (`--desde-calibracion`), con 749 coincidencias de registro.
  - La cámara **se movió** entre tiempos: sin corregir habría 10 m de error de posición.
  - Se excluyen 0:00–0:13 (cámara acomodándose; 2.222 detecciones). La verificación de cámara da válida en el resto.
- **Equipos:** con los colores del 1° tiempo como referencia (diferencia 4,5–4,6, umbral 12), las etiquetas home/away quedan iguales a las del 1°. 803 tracks home, 645 away, 1.380 sin asignar (fragmentos cortos). El parquet sin equipos quedó en `sportivo_t2_coords_field_sin_equipos.parquet`.
- **Partido registrado:** "Sportivo vs Crecer" (`sportivo_crop3` = 1°, `sportivo_t2` = 2°), con equipo y estadio asignados a los dos.
- **Control entre tiempos:** OK, los equipos cambiaron de lado. Ningún video tiene los dos tiempos juntos.

**Excepción a la regla de calibración (control OK y mirar la imagen):** el control dio **REVISAR** y la calibración se usa igual, con esta evidencia.
- **El veredicto sale de una sola línea.** Mediana 0,32 m, p90 2,77 m. Calzan la línea media (0,32 m), el círculo (0,21 m) y el área grande derecha (1,05 m). Lo que falla es la **línea de fondo derecha, a 6,18 m**.
- **Los 9 puntos de calibración propagados caen sobre las marcas reales** del 2° tiempo, a 1–3 px. Revisado ampliado ×8: postes de los dos arcos, medialuna y área chica izquierdas, cruce de la línea media y área chica derecha. Es la misma precisión de la medición a mano del 1° tiempo.
- **Los errores de esa línea están todos en el tramo del córner lejano,** pegado a la base de los carteles. Ahí el control encuentra una línea "casi paralela" a varios metros, que muy probablemente es el borde de los carteles.
  - En el 1° tiempo esa línea casi no se encontraba (6–26% de las muestras), así que quedaba "no verificada" y no pesaba.
  - El córner lejano proyectado cae donde el pasto toca la base de los carteles, a 2–3 px.
- **Prueba independiente con los arqueros:** el 10% de detecciones de arquero más cercano a la línea de fondo derecha está a 3,2 m, contra 3,5 m en el 1° tiempo validado. Con la línea corrida 6 m daría ~9 m.
- **Ninguna detección cae afuera de la cancha de 102 × 75** (con margen de 1,5 m), igual que en el 1° tiempo.
- **Límite:** sin banderín visible, la posición a lo largo del córner lejano no se puede confirmar con la imagen. La evidencia es el conjunto de arriba.
- **Por qué el error de esa línea no puede ser de la calibración:** una homografía transforma rectas en rectas. Los dos postes del arco derecho están sobre la línea de fondo y la calibración los ubica a 1–2 px. Entonces la línea de fondo proyectada coincide con la real en toda su extensión, y lo único que no queda fijado así es la posición *a lo largo* de la línea, que el control no mide. Lo que el control encuentra a 5–6 m es otra cosa: el borde de los carteles, o la pintura irregular de esa línea ya vista en el 1° tiempo.

**Recalibración independiente, por precaución (28/10/2026, pedido de Santi):**
- **Qué se hizo:** una calibración con puntos medidos sobre el propio cuadro 24877 del 2° tiempo, en `data/calibracion/sportivo_t2_puntos_f24877.json`.
  - Son 6 puntos: bases de los cuatro postes y punta de la medialuna izquierda, ampliados ×8, y los cruces del círculo con la línea media (recta al sub-píxel con residuo 0,22 px y elipse ajustada).
  - Se omitieron el frente del área chica izquierda y la esquina del área chica derecha: en ese cuadro son demasiado tenues para medirlos sin extrapolar.
- **Control:** también **REVISAR, por la misma línea de fondo derecha** (5,25 m). Dos calibraciones por caminos distintos fallan en el mismo lugar.
- **Las dos coinciden:** diferencia entre ellas sobre la cancha visible, cada 3 m, de mediana 0,67 m, p90 1,51 m y máximo 1,87 m; en la banda lejana 1,32 m de mediana. Está dentro de la tolerancia que el proyecto usa para decir que una calibración "vale" (mediana ≤ 1 m, p90 ≤ 2 m), y el arco derecho no se separa del resto.
- **Ninguna gana con claridad:**
  - la medida calza un poco mejor la línea media (0,21 m contra 0,32), pero sus puntos no cierran del todo (la medialuna queda con 1,1 m de residuo, ruido de lectura sobre marcas borrosas);
  - la propagada sale de los 9 puntos sub-píxel del 1° tiempo.
- **Decisión: queda la propagada** (con la que están el parquet, los equipos y los patrones).
  - La medida se guarda como segunda opinión en `sportivo_t2_homography_medida.json` (y su imagen de control).
  - Los respaldos de antes de recalibrar quedaron en `*_propagada_20261028_195116.*`.
  - Verificado después de restaurar: el parquet vigente es idéntico al respaldo (coordenadas y equipos) y la cámara es estable fuera de 0:00–0:13.

**Patrones del 2° tiempo:**

| | Criterios vigentes | 60% del tiempo | Prueba (30% · 50% · 2 m) |
|---|---|---|---|
| 1° tiempo | 1 | 4 | 16 |
| 2° tiempo | 3: `desconectado` #82 (0:43) y **`no_achica` #696 (5:31) y #1394 (12:02)** | 9 | 24 |

- Son los **primeros "no achica" con datos reales**. En el 1° tiempo no hubo 4 subidas evaluables por jugador.
- Calificados el 28/10/2026 (ver abajo). **Esta tabla es de antes de corregir `no_achica` y de filtrar arqueros (30/10/2026):** con los criterios vigentes ahora son 2 momentos en el 1° tiempo (`desconectado` #2374 y `no_achica` #931) y 1 en el 2° (`desconectado` #82).

**Verificado en el dashboard (AppTest):** el partido aparece agrupado con sus dos tiempos, y las cuatro vistas abren sin errores en el 2° tiempo. Patrones muestra los 3 momentos y "los equipos cambiaron de lado". El Semáforo usa una sola planilla para el partido.

**Calificaciones del 2° tiempo (Santi, 28/10/2026):** los 24 momentos, con los mismos criterios de prueba que el 1° (30% más despegado, 50% del tiempo, 2 m). Quedaron 6 útiles, 16 correctos tácticamente y 2 que no se ven.
- **"Qué parte del tiempo" no se sostiene.** En el 1° tiempo parecía separar, y en el 2° no. Solo moviendo esa perilla, `desconectado` (útil / correcto / no se ve / sin calificar):

| Proporción mínima | 1° tiempo | 2° tiempo | Partido |
|---|---|---|---|
| 50% | 3 / 4 / 1 / 1 | 4 / 10 / 0 / 0 | 7 / 14 / 1 / 1 |
| 55% | 3 / 3 / 1 / 1 | 4 / 7 / 0 / 0 | 7 / 10 / 1 / 1 |
| 60% | 2 / 0 / 1 / 1 | 3 / 4 / 0 / 0 | 5 / 4 / 1 / 1 |
| 65% | 1 / 0 / 0 / 1 | 1 / 2 / 0 / 0 | 2 / 2 / 0 / 1 |
| 70% (vigente) | 0 / 0 / 0 / 1 | 1 / 0 / 0 / 0 | 1 / 0 / 0 / 1 |

  **No se propone bajar la proporción:** el 60% que parecía limpio con un tiempo mezcla útiles y correctos con los dos.
- **El motivo más repetido es el juego detenido:** 8 de los 16 `desconectado` no útiles (lateral, tiro libre, barrera, pelota afuera, antes de reanudar). En este tiempo hay 1 solo tag, así que la excepción por tags de pelota parada no podría sacarlos.
- **Hipótesis a medir con otro partido: el ritmo del juego.** Ritmo: mediana de la velocidad de todos los jugadores en cada segundo, suavizada 5 s, en los tramos del momento y relativa a la mediana de ese tiempo.
  - Ordena mejor que la proporción: un útil queda por encima de un no útil el 80% de las veces, contra 65% (1° tiempo 82% y 70%; 2° tiempo 80% y 60%; `desconectado`, 36 momentos).
  - Con ritmo ≥ 1,15 veces el normal quedan 7 momentos: 6 útiles y 1 correcto, de los 39 calificados y 10 útiles en total.
  - **No detecta el juego detenido:** los momentos comentados así tienen el mismo ritmo que el resto de los correctos (2,32 y 2,36 m/s). Lo que muestra es que los útiles pasan cuando el juego va rápido.
  - **Límites:** el 1,15 se eligió mirando estos mismos datos, y es un solo partido calificado por Santi, no por el DT. No se implementa.

**Error de medición en `no_achica` (encontrado por el comentario de Santi sobre el #1394, "no se encuentra"; corregido el 30/10/2026, con su OK):**
- **Qué pasaba:** el desplazamiento del jugador se mide en la parte de la subida en que su track existe, y el de sus compañeros en toda la subida. Un track que aparece al final queda "atrás" porque se midió menos tiempo, no porque haya corrido menos.
- **Además, los tramos de evidencia eran la subida del equipo, no la vida del track.** Por eso el salto podía llevar a un momento en que el jugador todavía no estaba.
- **#1394:** el primer tramo era 12:02,5–12:14,2 y el track recién aparece en 12:13: 1 s medido contra 11,7 s de sus compañeros. Le pasaba con 10,7 de los 17,3 s de su evidencia. Revisado en el video anotado: a las 12:08 no está, y a las 12:24 y 12:34 se ve con su número.
- **#696:** el primer tramo era 5:31,2–5:37,7 y el track aparece en 5:34,6.
- **Corrección (`_detectar_no_achica`):** el jugador y sus compañeros se miden sobre el mismo intervalo, el del track dentro de la subida, y ese intervalo es el tramo de evidencia. Un compañero entra en la comparación solo si cubre al menos el 80% de ese intervalo (`MIN_COBERTURA_PAR_EN_FASE`). Los umbrales y criterios no cambiaron.
- **Efecto** (verificado con el código ya corregido, igual a lo medido antes en un script aparte):

| Tiempo y criterios | Hoy | Sobre el mismo intervalo |
|---|---|---|
| 1° · vigentes | ninguno | #931 (sin calificar) |
| 1° · prueba | ninguno | #931 (sin calificar) |
| 2° · vigentes | #696 correcto, #1394 no se ve | #2158 (sin calificar) |
| 2° · prueba | #696, #1394, #816 útil | #816 útil, #2158 (sin calificar) |

  Salen los dos que no servían y queda el útil, pero son pocos casos. Las calificaciones de #696 y #1394 quedan guardadas, aunque esos momentos ya no aparezcan.
- **Los dos momentos nuevos, todavía sin calificar:**
  - **#931** (1° tiempo, desde 7:28): 58,6 s, todas las filas como jugador, 3 de 5 subidas, 4,9 m.
  - **#2158** (2° tiempo, desde 20:59): 3 de 4 subidas, 7,0 m. Es un arquero: ya no se muestra (ver abajo).
- **Calificación de los dos (Santi, 30/10/2026):**
  - **#931, correcto.** Es el delantero local: lejos de la jugada, pero en una posición correcta. Santi aclara que a veces, en esa misma situación, sí es un error. Un momento tiene varios tramos y se califica entero, así que esa mezcla no queda registrada.
  - **#2158, no se ve: es el arquero**, de azul oscuro. El 40% de sus filas son `goalkeeper`, y el filtro de arqueros pide más de la mitad.
- **El arquero de azul oscuro es de Sportivo (Santi, 30/10/2026), así que el lado que asigna el sistema está bien y el que falla es el color.** Su camiseta se parece a la de Crecer, y el color manda en los tracks con menos de la mitad de filas `goalkeeper`.
  - **Tracks de 30 s o más, cerca del arco de Sportivo, con 10–50% de filas de arquero y marcados visitantes:** 7 en el 2° tiempo (uno de 296 s) y 5 en el 1°. No se revisaron uno por uno.
  - **Sigue sin corregir:** esas filas cuentan para el equipo equivocado en la vista Jugadores y en las líneas de referencia de los patrones.
  - **Efecto medido (31/10/2026, sin aplicar, a la espera de decisión de Santi).** Regla probada: más de 20% de filas `goalkeeper` y esas filas a no más de 20 m de la posición habitual del track. Ese track recibe equipo por lado y sale de las líneas y del bloque. La asignación real, sin cambios, reproduce los parquets vigentes fila por fila.
    - **Tracks:** cambian de equipo 16 en el 1° tiempo y 22 en el 2°. De los 15 de 30 s o más, en las imágenes 14 son el arquero de azul oscuro y en 1 no se llega a ver. El corte de posición deja afuera al #2520, un jugador de blanco cuyo track salta al otro arquero; con 10% entraría además el #1452, otro track mezclado.
    - **Corregir solo el equipo empeora:** el arquero pasa a la línea y al bloque del local (profundidad del local en el 2° tiempo, de 32,6 a 35,8 m).
    - **Bloque, con la regla completa (mediana):** 1° tiempo, área del local de 786 a 754 m² y del visitante de 485 a 478 m²; 2° tiempo, local igual y visitante de 513 a 494 m².
    - **Patrones, criterios vigentes:** 1° tiempo de 2 a 1 momentos (sale #931); 2° tiempo de 1 a 5 (entran #1054, #1822, #1545, #2123, sin calificar).
    - **Patrones, criterios de prueba:** de 38 a 47 momentos. Salen 5 correctos (#931, #2329, #958, #1576, #1716) y 1 útil (#1547), y entran 15 sin calificar. Las fases cambian en 5% y 11,3% de las filas, porque el arquero entra en el centro del bloque de su equipo real.
    - **Límites:** los cortes de 20% y 20 m salen de mirar este partido. Aplicado de verdad, el reclustering puede mover algún track más. Otra vez, los momentos cambian bastante con un ajuste chico de los datos.
- **Qué hacer con los arqueros:**
  - **Bajar `PROPORCION_MIN_ARQUERO` no sirve:** ese corte también define quién entra en las líneas de referencia. Al 15% saca a #2158, pero con los criterios vigentes aparecen #1054 y #1822, y con los de prueba se pierde el #1547, que era útil. Al 10% se pierde además el #2903.
  - **Aplicado (30/10/2026, decisión de Santi): no se reporta el momento si el track tiene más de 10% de filas `goalkeeper`** (`PROPORCION_MAX_ARQUERO_EN_MOMENTO`), sin tocar las líneas. De los 40 momentos con criterios de prueba, saca solo a #2158 y #2774, los dos arqueros; el siguiente tiene 2%. Los demás momentos dan idéntico fila por fila, en los cuatro videos con equipos. Lo que sale queda dicho en "Patrones no evaluados".
- **Por línea** (`desconectado`, criterios de prueba; útil / correcto / no se ve): ataque 7 / 11 / 2, defensa 1 / 8 / 0, mediocampo 1 / 5 / 1. El patrón sirve más en los delanteros, pero ahí también se mezcla más: sin saber dónde está la pelota, el sistema no distingue si un delantero lejos está mal ubicado o bien.
- **Calificación por tramo (30/10/2026, decisión de Santi):** por lo que mostró el #931, cada tramo de un momento se puede calificar aparte.
  - **En la tarjeta:** junto al botón de cada tramo, 👍 ✅ 🚫. Es opcional y no reemplaza la calificación del momento ni su comentario. También está en los momentos nuevos de "Probar otros criterios". Se califican los tramos que muestra la tarjeta: los primeros 6.
  - **Datos:** tabla `patrones_revision_tramos`, que solo agrega filas: vale la última y queda el historial. Guarda el comienzo y el fin del tramo, el criterio con que apareció y quién calificó. Solo local, no se sincroniza.
  - **Acumulado:** "Lo que dijo el cuerpo técnico" suma una tabla "Por tramo". Quien no puede revisar ve la calificación sin poder cambiarla.
  - **Límite:** el tramo se identifica por su comienzo. Si otro criterio o un reproceso lo corre, cuenta como otro tramo.
  - **Verificado:** con AppTest sobre una copia de la base, calificar, corregir y sacar la calificación, que el momento no cambie, recuperarla en otra sesión, el lector sin controles y los momentos nuevos de la prueba. En el navegador, sobre otra copia, la tarjeta y un clic que guarda el tramo con su usuario; la base real no se tocó.
- **Verificado:**
  - en los cuatro videos con equipos, con los dos juegos de criterios, `desconectado` y los "no evaluados" dan igual que antes; lo único que cambia es el orden entre empates de severidad;
  - toda la evidencia de `no_achica` cae dentro de la vida de su track;
  - AppTest: la vista Patrones abre sin errores en los dos tiempos, con 2 momentos en cada uno;
  - en el video anotado, #2158 y #931 se ven con su número en su primer tramo.
- **Tiempo:** ~1,5 s más por tiempo del partido (de 21,8 a 23 s y de 29 a 30,8 s).

## "Volver a Patrones" desde la Mesa táctica (02/11/2026, pedido de Santi)

**Qué hace:** después de saltar a un tramo desde una tarjeta de Patrones, la Mesa táctica muestra el botón "Volver a Patrones", junto al modo del visor. Lleva a la misma tarjeta y deja la vista como estaba.
- **Qué restaura:** el filtro de equipo, las perillas y el desplegable "Probar otros criterios". Streamlit descarta el estado de los widgets que dejan de dibujarse, así que `_ir_a` anota esos valores al saltar (`_regreso_a_patrones`).
- **Cuándo aparece:** solo si el partido o tiempo abierto es el del salto. Un salto desde otra vista no lo pisa.
- **De paso:** todo salto ahora sube al comienzo de la página. Antes la Mesa táctica quedaba en la posición de la otra vista, con el video y este botón fuera de la pantalla.

**Verificado:** AppTest sobre una copia aislada, desde una tarjeta común y desde una de la prueba, con otro tiempo abierto. En el navegador, sobre otra copia: al saltar, el botón queda visible arriba, con el video en el segundo pedido; al volver a una tarjeta de la prueba, queda en el mismo lugar de la pantalla (138 px antes y después), con el desplegable abierto y las perillas en 30 y 50.

**Límite:** al volver, la lleva a la tarjeta, no al píxel exacto: la tarjeta queda centrada si antes estaba en otra posición.

## Procedencia de las salidas del pipeline (09/11/2026)

**Por qué:** surgió de un peritaje simulado. Para defender un resultado hay que poder demostrar de qué video salió y con qué código, y volver a producirlo igual.

**Qué se registra** (`src/utils/procedencia.py`): cada parquet guarda en su esquema, bajo la clave `analizador` (JSON), el script, los parámetros, el commit (y si había cambios sin commitear en archivos versionados), las versiones de las librerías y la fecha UTC. Además, guarda la procedencia de su entrada bajo `origen`, con el SHA-256 de ese archivo. Así la cadena llega hasta el SHA-256 del video original.
- **`run_inference.py`:** el SHA-256 del video, calculado antes de procesar, el modelo, los umbrales por clase, el IoU de supresión arquero/jugador y el skip.
- **`calibrate.py --apply`:** el SHA-256 de la calibración y, si existe, del archivo de puntos (o de qué video se propagó), el estadio y sus medidas, los tramos, los rangos excluidos y los tramos sin calibración válida.
- **`team_assignment.py`:** el SHA-256 del video de los colores y el otro tiempo usado como referencia.
- **`player_stats.py --guardar <x>.parquet`** y **`tactical_patterns.py`**, que ahora guardan su salida en parquet (`<entrada>_patrones.parquet` por defecto; `--guardar no` para no guardar). El CSV no puede llevar procedencia.
- **Ver la cadena:** `scripts/ver_procedencia.py <parquet>`; con `--verificar` recalcula los SHA-256 de lo que sigue en disco, y con `--json` muestra todo.

**No cambia ningún dato:** la metadata de pandas (`pandas` y `PANDAS_ATTRS`) se conserva, y `df.attrs` vuelve igual. Un parquet anterior no tiene la clave: `leer_meta` devuelve `None` y el visor lo avisa.

**Verificado sobre `sportivo_min --skip 1`** (calibración propagada desde `sportivo_crop3`, control OK 0,24 m):
- Línea base intacta: 131 IDs, tracks 21/26/77, y el parquet de detecciones idéntico fila por fila al de la corrida anterior.
- `ver_procedencia.py --verificar` sobre los patrones muestra las cinco etapas hasta el video (`fc22d600…527c`), con los hashes coincidiendo.
- `leer_meta` sobre `sportivo_crop3` y `partido_clip2` da `None`, y se leen igual.
- El SHA-256 de un video de 173 MB da lo mismo dos veces, y lo mismo que leerlo de una sola vez.

**Límites:**
- **Solo registra, no impide:** cualquiera puede reescribir un parquet. La prueba de integridad es recalcular los hashes, y el más fuerte es el del video original.
- **`team_assignment` reescribe su entrada:** el hash de esa entrada es el de la versión anterior del mismo archivo, que ya no existe. El visor lo aclara.
- **Los parquets existentes no tienen procedencia** hasta que se reprocesen.

## Posible juego detenido (09/11/2026)

**Por qué:** el sistema no sabe si la pelota está en juego, y la clase `ball` tiene recall bajo. El track 2374 (`desconectado`, 21:07–21:45 en `sportivo_crop3`) era un falso positivo: el juego estaba detenido. En las calificaciones del partido, el juego detenido explicaba 8 de los 16 `desconectado` no útiles del 2° tiempo.

**Heurística** (`src/analysis/estado_juego.py`): velocidad colectiva.
- Para cada jugador de campo (clase `player`, sin árbitros ni arqueros), el desplazamiento en el último segundo, con los tiempos reales de los cuadros. Por cuadro, la **mediana** entre jugadores, suavizada con una mediana móvil de 2 s.
- Es "posible juego detenido" si esa curva queda bajo el umbral durante al menos la duración mínima. Cuadros con menos de 4 jugadores medidos no cuentan.
- Cada video (un tiempo) se calcula por separado, y los tramos sin calibración válida quedan afuera.
- **Parámetros** (`PARAMETROS_POR_DEFECTO`, configurables y por CLI): umbral 1,4 m/s, duración mínima 15 s, suavizado 2 s, desplazamiento en 1 s, y un momento queda marcado si al menos el 50% de sus tramos cae en juego detenido.
- **Salida:** `python3 src/analysis/estado_juego.py <clip>_coords_field.parquet` → `<clip>_estado_juego.parquet` (inicio, fin, duración, velocidad mediana), con procedencia y los parámetros usados.
- **Cruce con los patrones:** `detectar_patrones` agrega `fraccion_juego_detenido` y `posible_juego_detenido`. **No saca momentos ni cambia la severidad.** La vista muestra "⏸ Posible juego detenido" con la ayuda "El movimiento general bajó; revisá en el video si la pelota estaba en juego", y un filtro para ocultarlos, apagado por defecto.

**Desvío de lo pedido: desplazamiento en 1 s, no entre cuadros consecutivos.** Con `--skip 3` los cuadros están a 0,12 s, y el temblor de 1–2 px de la caja en la banda lejana (~0,3 m por píxel) ya da 2–5 m/s. Entre cuadros, el tramo detenido del 2374 queda en 1,6–2,4 m/s, lo mismo que el partido (mediana 2,2), y ningún umbral cumple los dos casos. En 1 s ese ruido pesa diez veces menos. Perfiles en `docs/perfiles_juego_detenido.png`.

**Calibración** (grilla de umbrales de 0,9 a 1,4 m/s y duraciones de 5, 10 y 15 s, contra los dos casos y las calificaciones de los dos tiempos):
- **Track 2374:** marcado el 96% de su tramo (intervalo 21:08,0–21:45,4).
- **Basculación de los tracks 21/74 (`partido_clip2`, 0:30–0:41, juego en curso):** no se marca. La curva baja de 1,4 m/s solo ~1,5 s, alrededor de 0:35. Es un caso débil: otra cámara (transmisión que panea) y fuera del tramo con calibración válida.
- **Contra las calificaciones,** con criterios de prueba: marcados 7 de los 12 momentos comentados como juego detenido, 0 de los 9 útiles y 2 de los 16 correctos sin ese comentario. 1,3 m/s con 10 s marcaba uno útil.
- **Cuánto del partido marca:** 36% del 1° tiempo (12 intervalos) y 27% del 2° (18). Es plausible, porque en un partido la pelota está detenida buena parte del tiempo. Los intervalos están en los `*_estado_juego.parquet`.

**Resultado:**
- **Criterios vigentes:** marcado 1 de 2 momentos en el 1° tiempo (el #2374) y 0 de 1 en el 2° (#82, útil).
- **Criterios de prueba:** 5 de 16 en el 1° tiempo y 6 de 22 en el 2°.
- **Las demás columnas no cambian:** idénticas fila por fila en los cinco videos con equipos, con los dos juegos de criterios, y los "no evaluados" también.
- **AppTest:** la etiqueta aparece en el #2374 y no en el #931; el filtro deja 1 momento; en "Probar otros criterios", 5 líneas marcadas. Sin las columnas (resultado anterior), la vista funciona igual, sin etiqueta.

**Límites:**
- **Una pausa larga con trote** (jugadores que se reacomodan rápido en un córner) puede no detectarse.
- **Un tramo de juego muy lento** (toque atrás, equipo esperando) puede marcarse. Es un aviso, no un diagnóstico, y por eso no saca nada.
- **El umbral es absoluto** y se eligió mirando este partido: la mediana del 2° tiempo (1,45 m/s) es más alta que la del 1° (1,31). Hay que revisarlo con otro partido o con otra cámara.
- **El #958** quedó marcado (87%) aunque Santi lo calificó "basculación normal": el juego venía lento.

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
