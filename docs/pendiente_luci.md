# Pendientes para Luci (`app/components/tagging.py`)

Anotados por Santi. `tagging.py` es tuyo: no se tocó.

## Semáforo por partido, no por video (18/10/2026)

**Por qué.** Desde ahora cada tiempo es un video propio, con su `match_name` (por ejemplo `sportivo_crecer_t1` y `sportivo_crecer_t2`). La tabla `partido_tiempos` (`src/db/partido_repo.py`) los agrupa en un partido. El dashboard muestra un selector de partido y, debajo, uno de tiempo.

**Qué pasa hoy.** `render_semaforo_tab(match_name)` recibe el video del tiempo elegido, así que la calificación queda guardada en uno solo de los dos tiempos. Un jugador se califica una vez por partido.

**Propuesta.**
- La clave del semáforo pasa a ser el partido cuando el video pertenece a uno: `partido_repo.get_tiempo(match_name)` devuelve `{"partido", "tiempo"}`, o `None` si es un video suelto.
  - Lo más simple sin cambiar la tabla: guardar con el `match_name` del primer tiempo (`partido_repo.tiempos_de(partido)[0]["match_name"]`) y leer igual, elija el tiempo que elija.
  - O agregar una columna `partido` a `semaforo`.
- Los **eventos** (`events`) siguen por video: su tiempo es relativo al video de cada tiempo, y así está bien.
- Si cambia la tabla `semaforo`, avisarle a Nico: `src/db/local.py` y `src/db/sync.py` la leen para el sync.

## `use_container_width` deprecado

Streamlit lo avisa en cada corrida y lo va a sacar. Hay que cambiarlo por `width="stretch"`: en `tagging.py` aparece en las líneas 516, 554, 575, 578, 589, 592, 616, 623, 638 y 642.

## Migración visual al mockup (22/10/2026)

Santi pasó su parte (`main.py`, `config.toml`, `tactical_patterns_view.py`, `video_sync.py`). Ver decisiones.md, "Migración visual al mockup".

- **El modo claro se sacó.** `session_state["theme_mode"]` ya no existe. `tagging.py` lo lee con `"dark"` por defecto, así que no se rompió nada, pero la rama `"light"` de `_CHART_STYLE` (línea ~377) quedó sin uso y se puede borrar.
- **Ya no hay pestañas: hay un selector de vista arriba**, y solo se dibuja la vista elegida. `_request_seek()` sigue funcionando igual. Ahora, además, cualquier salto (`_pending_seek_time`) lleva a la Mesa táctica y **mueve también el video**: antes movía solo el slider y la cancha.
- **El tagueo ya va dentro de una tarjeta con borde** (`st.container(key="panel_tagueo")`, en `main.py`). Para que se vea como el mockup (análisis, etapa 4):
  - botonera en grilla de 2 columnas con `st.button(icon=…)`;
  - selector de equipo con `st.segmented_control`;
  - historial como lista compacta.
- **Semáforo (etapa 5):** fila de contadores (destacados / regulares / bajos) con `st.metric`, y grilla de tarjetas por jugador del plantel con los tres estados como botones. Opcionales: notas por jugador e informe para copiar a WhatsApp.
- **Atajos de teclado (22/10/2026):** <kbd>1</kbd>–<kbd>9</kbd> taguean con el botón N de tu botonera, en el orden en que se ven (de izquierda a derecha y de arriba hacia abajo), y <kbd>L</kbd>/<kbd>V</kbd> cambian `tag_team`. Usan tus funciones (`get_event_types_for_team`, `save_event`) desde `main.py`; tu archivo no se tocó. Sugerencia: mostrar el número en cada botón (por ejemplo "1 · Presión"), como las teclas del mockup. Hoy está en una leyenda debajo del slider.
