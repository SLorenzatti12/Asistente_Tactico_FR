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

## Historial de eventos como desplegable (pedido de Santi, 22/10/2026) — **hecho, con tu OK**

Aplicado en `tagging.py`: el historial va en `st.expander("Historial de eventos (N)")` cerrado, y se sacó el título "Editar eventos" de `_render_events_cards`. Lo de abajo queda como referencia.

En la Mesa táctica, la tarjeta de tagueo va al lado del video, con alto fijo. Santi quiere que se vean solo los botones y el gráfico, y que el historial de eventos quede en un desplegable cerrado. El cambio va en `render_tagging_panel()`, al final:

```python
        st.divider()
        _render_events_cards(events_df)
```

por:

```python
        with st.expander(f"Historial de eventos ({len(events_df)})", expanded=False):
            _render_events_cards(events_df)
```

Si `_render_events_cards` ya pone su propio título ("Editar eventos"), se puede sacar, porque el desplegable ya lo nombra.

## Roles y permisos (26/10/2026)

El dashboard tiene login local y cuatro roles (ver decisiones.md, "Login local y roles"). Desde `main.py` ya se controla qué vistas ve cada rol y quién ve la tarjeta de tagueo. Para que el control quede completo hace falta un modo de solo lectura en `tagging.py`. Con `from components.sesion import puede`:

- **Tarjeta de tagueo:** hoy solo la ven admin y analista. Para que cuerpo técnico y solo lectura vean el gráfico y el historial sin poder modificar, haría falta que `render_tagging_panel()` acepte algo como `solo_lectura=not puede("taguear")`. En ese modo no se muestran los botones de tagueo, el ⚙️ de tipos ni el editar y borrar de cada evento.
- **Semáforo:** hoy lo ven solo admin y cuerpo técnico (`calificar_semaforo`). Para que analista y solo lectura lo vean sin calificar, `render_semaforo_tab()` necesita desactivar los botones de calificación cuando `not puede("calificar_semaforo")`, y mostrar "Gestionar plantel" solo si `puede("gestionar_plantel")`.

### Hecho por Santi con tu OK (27/10/2026)

Todo lo de arriba quedó hecho en `tagging.py` (ver decisiones.md, "Roles en tagueo, Semáforo y plantel; autor de cada evento y calificación"):
- `render_tagging_panel(solo_lectura=...)`: en solo lectura, gráficos e historial (con ir al momento), sin botonera, ⚙️, editar ni borrar.
- `render_semaforo_tab(match_name, puede_calificar=..., puede_gestionar_plantel=...)`: en solo lectura muestra la última calificación de cada jugador.
  - También para quien califica: era el TODO "mostrar resumen de calificaciones", y ahora muestra la última, con quién y cuándo.
  - Cada clic ahora avisa y refresca.
- **Columnas nuevas** `events.created_by` y `semaforo.created_by` (migración aditiva en `init_db()`). `save_event(..., usuario=None)` y `save_semaforo(..., usuario=None)` las reciben. Las filas viejas quedan en NULL.
- **Registro de accesos:** editar o borrar un evento queda registrado, con antes y después (`_describir_evento`).
- `registro_repo` se importa como `src.db.registro_repo` (no `db.`), para que sea el mismo módulo que usa `sesion.py`.

Para revisar cuando vuelvas: el semáforo sigue identificando por dorsal (dos sin dorsal comparten la última calificación). Ya estaba así antes.
