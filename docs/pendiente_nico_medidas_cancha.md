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

### `app/components/map_view.py`
- `render_map(df, current_time)` → agregar un parámetro `medidas: dict | None = None` (None → `medidas_de_df(df)`, que cae en 105×68).
- `_draw_field_shapes` (181-187): perímetro `largo × ancho`, línea media en `largo/2`, círculo con `radio_circulo`. Si querés dibujar las áreas, las medidas ya vienen en el mismo dict. `_lineas_cancha()` de `src/homography/calibrate.py` arma todas las marcas como polilíneas en metros y te puede servir de referencia.
- Rango de los ejes (290-291): `[-2, largo + 2]` y `[-2, ancho + 2]`.
- Textos de ayuda de Amplitud/Profundidad (309-310): hoy dicen "68 m" y "105 m". Usar `ancho` y `largo`, o sacar el número.
- `render_metrics_panel`: las métricas de bloque (amplitud, profundidad, área) **no** necesitan cambios. Se calculan desde las coordenadas, que ya salen en metros reales si la calibración usó las medidas correctas.

### `app/components/player_stats_view.py`
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
