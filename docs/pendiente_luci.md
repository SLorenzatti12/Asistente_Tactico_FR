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
