# Pendiente para Nico: dibujar la cancha con sus medidas reales

**Contexto.** Las canchas regionales no miden 105×68. En Sportivo, la banda cercana aparece a ~39 m del eje en vez de 34. Por eso las medidas pasan a ser un dato del estadio:

- `scripts/estadios.py` carga las medidas en la tabla `estadios` de la SQLite local.
- `calibrate.py --estadio` las copia al JSON de la calibración.
- `--apply` las deja como **metadata** del `*_coords_field.parquet`, en `df.attrs["medidas_cancha"]`. No hay columnas nuevas, así que el contrato del parquet no cambia.

Un parquet anterior a esto no trae metadata y equivale a 105×68.

El back ya está hecho. Del lado de la app falta que el mapa lea las medidas en vez de usar las constantes de `theme.py`. Yo no toqué tus archivos (`theme.py`, `map_view.py`, `player_stats_view.py`) ni `main.py`.

## Cómo leer las medidas

```python
from src.homography.medidas_cancha import medidas_de_df   # app/ ya agrega la raíz a sys.path

df = pd.read_parquet(ruta)
m = medidas_de_df(df)
# {"largo": 105.0, "ancho": 68.0, "area_grande_largo": 16.5, "area_grande_ancho": 40.32,
#  "area_chica_largo": 5.5, "area_chica_ancho": 18.32, "radio_circulo": 9.15,
#  "distancia_penal": 11.0, "estadio": "Sportivo Belgrano" | None}
```

`df.attrs` se pierde fácil: en muchas operaciones de pandas y como parte de la clave de `st.cache_data`. Conviene **leer las medidas una sola vez, apenas se carga el parquet**, y pasarlas explícitas a cada componente. No conviene releerlas de un DataFrame ya filtrado.

## Qué cambiar

### `app/main.py` (línea ~530, donde se lee el parquet)
Calcular `medidas = medidas_de_df(df)` después del `pd.read_parquet` y pasárselas a `render_map`, `render_metrics_panel` y `render_player_stats`. (`main.py` es de Santi; lo coordinan entre ustedes.)

### `app/theme.py` (43-44)
`FIELD_LENGTH` / `FIELD_WIDTH` pueden quedar, pero solo como valor por defecto si no llegan medidas. Lo mejor es que importen de `MEDIDAS_REGLAMENTARIAS`, para no tener dos fuentes de verdad.

### `app/components/map_view.py` — **hecho el 19/10/2026** (Santi, con tu OK, para la demo)
`render_map` y `render_metrics_panel` leen las medidas del parquet con `medidas_de_df(df)`. `render_map` acepta además `medidas=` opcional. `main.py` no necesitó cambios. Se dibujan perímetro, línea media, círculo y áreas grande y chica de los dos lados, con rangos de ejes `[-2, largo + 2]` × `[-2, ancho + 2]`. Las ayudas de Amplitud y Profundidad usan el ancho y el largo reales. `_draw_field_shapes(fig)` sin medidas sigue dibujando 105×68, para que `player_stats_view.py` no se rompa. También se sacó la barra de herramientas de Plotly del mapa (ver decisiones.md, "Mapa 2D: parpadeo…"). Lo que sigue abajo de esta sección queda como referencia de lo que se hizo.

- `render_map(df, current_time)` → agregar un parámetro `medidas: dict | None = None` (None → `medidas_de_df(df)`, que cae en 105×68).
- `_draw_field_shapes` (181-187): perímetro `largo × ancho`, línea media en `largo/2`, círculo con `radio_circulo`. Si querés dibujar las áreas, las medidas ya vienen en el mismo dict. `_lineas_cancha()` de `src/homography/calibrate.py` arma todas las marcas como polilíneas en metros y te puede servir de referencia.
- Rango de los ejes (290-291): `[-2, largo + 2]` y `[-2, ancho + 2]`.
- Textos de ayuda de Amplitud/Profundidad (309-310): hoy dicen "68 m" y "105 m". Usar `ancho` y `largo`, o sacar el número.
- `render_metrics_panel`: las métricas de bloque (amplitud, profundidad, área) **no** necesitan cambios. Se calculan desde las coordenadas, que ya salen en metros reales si la calibración usó las medidas correctas.

### `app/components/player_stats_view.py` — **hecho el 22/10/2026** (Santi, con tu OK): la vista se rehízo con el aspecto del mockup y usa `medidas_de_df(df)` para los mapas y para `infer_formation_zones(largo_cancha=...)`. `largo_cancha` es parámetro de `_calcular_stats`, así entra en la clave del caché.
- Rango de los ejes del mapa de posiciones (241-242): igual que en `map_view`.
- `_calcular_stats` (64-77): `infer_formation_zones` reparte en tercios del largo. Hay que pasarle `largo_cancha=medidas["largo"]`, y **agregar `largo_cancha` como parámetro de `_calcular_stats`**. `st.cache_data` arma la clave con los argumentos, no con `df.attrs`: si no, dos partidos con el mismo contenido pero distinta cancha compartirían el cálculo. El CLI de `src/analysis/player_stats.py` ya lo hace así.

### Opcional (no bloquea)
- **Elegir estadio desde la app:** un selector como `team_selector.py`, usando `src/db/estadio_repo.py` (`list_estadios`, `get_match_estadio`, `set_match_estadio`). Hoy se hace por consola: `python scripts/estadios.py asignar <partido> <estadio>`.
  - Ojo: asignar el estadio desde la app no recalcula nada. Las coordenadas cambian recién al recalibrar y volver a correr `--apply`. `--apply` ya avisa si el estadio asignado no coincide con la calibración.
- **Sync a Supabase:** `estadios` y `match_estadio` hoy son solo locales. Si hacen falta en la nube, seguirían el patrón de `teams` / `match_team` en `src/db/sync.py` y `db/schema_cloud.sql`.

## Otros pendientes (18/10/2026)

- **Tramos sin calibración válida en el mapa.** `--apply` ahora deja en el parquet `df.attrs["calibracion_tramos_no_validos"]`: tramos (en segundos) donde la cámara se movió y los metros están corridos. `player_stats` y `tactical_patterns` ya los excluyen.
  - **Qué falta:** que el mapa (`map_view.py`) no dibuje esas posiciones, o que avise ("sin calibración válida en este momento").
  - **Cómo:** con `mascara_tramos_validos(df)` de `src/homography/tramos_validos.py`.
  - Hoy ningún partido tiene tramos marcados (sportivo_crop3 se recalibró por tramos), así que no es urgente.
- **`use_container_width` está deprecado** (Streamlit lo avisa en cada corrida). Hay que cambiarlo por `width="stretch"` en `roster_view.py:44` y `team_selector.py:50`.
- **Índice por frame en el mapa** (baja prioridad, opción n del análisis de videos largos en decisiones.md): `_frame_at_time` recorre todo el DataFrame en cada actualización. Indexar los frames una vez (ordenarlos y buscarlos con `searchsorted`) lo baja de 3 ms a 0.07 ms con 90 minutos. Hoy no se nota, porque cada actualización tarda 21 ms en total.

## Partidos de dos tiempos (18/10/2026)

Cada tiempo se filma, procesa y analiza como un video propio, con su `match_name`. Se agrega una tabla local que los agrupa en un partido: `partido_tiempos` (`match_name` PK → `partido`, `tiempo` 1|2), en `src/db/partido_repo.py`. El alta se hace con `python3 scripts/partidos.py alta "<partido>" --t1 <video> --t2 <video>`, que además copia el equipo (`match_team`) y el estadio (`match_estadio`) a los dos tiempos.

- **Sync a Supabase.** Hoy `partido_tiempos` es solo local. Para que en la nube un partido sea uno y no dos, hace falta:
  - agregarla a `db/schema_cloud.sql`;
  - sincronizarla en `src/db/sync.py`, con el mismo patrón que `match_team`;
  - decidir si `matches` en la nube pasa a ser por partido, con sus dos videos colgando, o si sigue por video con una columna `partido`/`tiempo`. Los eventos y el tracking siguen siendo por video: sus tiempos son relativos a cada video.
- **`team_selector.py`.** Hoy asigna el equipo a un solo video. Si se cambia desde la app para un tiempo, el otro queda con el anterior. Lo ideal es que, si el video pertenece a un partido (`partido_repo.get_tiempo(match_name)`), asigne a los dos (`partido_repo.tiempos_de(partido)`).

## Migración visual al mockup (22/10/2026)

Santi pasó su parte (`main.py`, `config.toml`, `tactical_patterns_view.py`, `video_sync.py`). Ver decisiones.md, "Migración visual al mockup". Lo que falta en tus archivos:

- **`theme.py`: la paleta quedó desfasada** (lo más importante). Sigue con fondo `#0e1117` y acento ámbar `#b45309`, y `config.toml` usa la del mockup. Los gráficos Plotly y las tarjetas de métricas salen de `theme.py`, así que hoy conviven dos paletas. Valores del mockup (`mockup/styles.css`):
  - fondo `#0a0b0d`;
  - superficies `#121519` / `#181c22`;
  - bordes `#242a35`;
  - texto `#f0f3f6` / `#9aa4b2`;
  - acento lima `#c3ff00`.

  `FONT_FAMILY` debería pasar a la pila del sistema que ahora usa `config.toml`: Inter se bajaba de Google Fonts y sin internet no carga.
- **`map_view.py`, cancha estilo mockup:**
  - césped oscuro a franjas (`#163622` / `#1a3f28`);
  - medialunas, puntos de penal y arcos de esquina;
  - flechas de dirección de ataque.

  `main.py` ya le pasa `medidas=` a `render_map` y dibuja el encabezado "Cancha cenital L × W m" arriba del mapa.
- **`map_view.py`, interruptores de envolvente y centroides:** dos parámetros nuevos en `render_map` (por ejemplo `mostrar_bloques=True`, `mostrar_centroides=True`). Los interruptores los pongo yo en `main.py`.
- **`map_view.py`, tarjetas de métricas:** el panel ya va dentro de una tarjeta con borde (`st.container(key="panel_metricas")`). Falta, por equipo, el encabezado en su color y las barras con `st.progress`.
- **`player_stats_view.py` (etapa 6) — hecho el 22/10/2026 con tu OK** (ver decisiones.md):
  - filtros por equipo y línea en píldoras;
  - tarjetas de totales;
  - `st.dataframe` con `column_config` (barras);
  - ficha lateral al seleccionar una fila.

## Roles y permisos (26/10/2026)

El dashboard tiene login local y cuatro roles (ver decisiones.md, "Login local y roles"). `main.py` ya muestra `render_team_selector` y `render_video_registry` solo a quien puede gestionar el partido (admin y analista). Lo que queda en tus archivos:

- **`roster_view.py`:** el alta y la baja del plantel deberían quedar solo para `puede("gestionar_plantel")` (`from components.sesion import puede`). Hoy se abre desde el Semáforo, que ve el cuerpo técnico.
- **Sync (`src/db/sync.py`):** la tabla local `usuarios` (con los hashes de las contraseñas) **no** se tiene que subir a Supabase. Si algún día se agrega login en la nube, va con Supabase Auth y la tabla `users` de `db/schema_cloud.sql`.

### Hecho por Santi con tu OK (27/10/2026)

- **`roster_view.py`:** `render_roster_manager(team_id, solo_lectura=False)`.
  - Sin `gestionar_plantel` (o con `solo_lectura=True`), muestra la lista sin alta ni baja. El permiso se vuelve a chequear adentro.
  - Cada alta y baja queda en el registro de accesos.
- **Supabase (RLS):** el SQL y el código están listos y probados contra un Postgres local que imita a Supabase. **Falta aplicarlo en el proyecto real, que es tuyo.** Los pasos, en orden, están en `docs/context/8-base-de-datos-hibrida.md` → "Seguridad de la nube":
  1. cargar `SUPABASE_SECRET_KEY` en tu `.env`;
  2. probar el sync;
  3. correr `db/rls_cloud.sql` en el SQL Editor;
  4. `python3 scripts/verificar_rls.py`;
  5. volver a probar el sync.
  - `get_client()` ahora usa la clave secreta y rechaza la pública.
  - `sync.py` no cambió.
  - Los usuarios locales siguen sin subirse.

### Plantel con apellido y nombre, y semáforo nuevo (27/10/2026, Santi con tu OK)

- **`roster_repo`:** columnas `apellido` y `nombre` (migración aditiva; las filas viejas se parten por la última palabra).
  - `add_player(team_id, apellido, nombre, dorsal)` y `update_player(...)` cambiaron de firma.
  - `full_name` se sigue llenando, así que **el sync del plantel no cambia**.
  - Se sacó `list_players` (solo lo usaba el semáforo viejo).
- **`roster_view`:** ahora es `render_plantel` (vista Semáforo → Plantel). Tiene elegir o crear equipo, la plantilla como planilla editable (`st.data_editor`), importar CSV y el registro de cada cambio.
- **Pendiente para la nube**, cuando apliques la seguridad: subir `semaforo_minutos` y `semaforo_valoraciones`. Son minutos y valoraciones por `players.id` y por función, y reemplazan a `player_ratings` por dorsal. También subir `apellido` y `nombre` a `players`. No se hizo ahora (decisión de Santi).
