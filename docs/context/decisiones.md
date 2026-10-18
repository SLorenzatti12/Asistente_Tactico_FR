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
