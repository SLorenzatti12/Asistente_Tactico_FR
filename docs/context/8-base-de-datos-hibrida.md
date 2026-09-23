# Base de datos híbrida (SQLite local + Supabase en la nube)

Nico

## Por qué "híbrida" y no una migración completa a la nube

El stack definido en `7-stack-tecnologico.md` eligió SQLite explícitamente
por la premisa de **procesamiento 100% offline** en el estadio (sin
conectividad, sin servidor que instalar en la laptop del analista). Esa
decisión no cambia acá: **todo lo que pasa durante el partido sigue
funcionando exactamente igual, contra SQLite local, sin depender de
internet.**

Lo que se agrega es una **segunda capa, opcional y posterior**, para lo que
SQLite estructuralmente no puede resolver bien porque vive en el archivo de
una sola laptop:

- Que un coach revise el semáforo de un partido desde su casa, sin pedirle
  el archivo `.sqlite` al analista.
- Tener un historial de partidos/resultados consolidado del equipo, no uno
  por máquina.
- Gestión de usuarios/roles (quién es analista, quién es coach) más allá de
  "quien tenga la laptop".

Supabase no es un servidor que se instala localmente (lo que sí se
descartó en `7-stack-tecnologico.md`) — es una API HTTPS a la que solo se
llama cuando hay conexión, para *subir* lo que ya se generó offline. Ver
la entrada correspondiente en `decisiones.md`.

## Qué vive en cada lado

| Local — SQLite (`data/db/analizador.sqlite`) | Cloud — Supabase (Postgres + Storage) |
|---|---|
| `teams`, `match_team` (equipo/categoría asignado a cada partido — ver `src/db/team_repo.py`) | `clubs`, `users`, `teams`, `players` |
| `roster` (plantel por equipo, alta/baja desde la app — ver `src/db/roster_repo.py`) | `matches` (calendario/resultados), `match_videos`, `calibrations`, `tracking_outputs` (solo la ruta al parquet) |
| `match_videos` (ruta local del video de cada partido — ver `src/db/video_repo.py`) | Copias sincronizadas de `events` y `player_ratings`, para consulta remota |
| `events`, `event_types`, `semaforo` (tal cual las creó/evoluciona `tagging.py`) | Video subido a Supabase **Storage**, bucket privado `match-videos` |
| Tracking (`.parquet` en `data/outputs/`) y calibración (`data/calibracion/`) | — |

El plantel se carga **una sola vez por equipo**, no por partido — se
reutiliza en todos los partidos de ese equipo (ver
`app/components/roster_view.py` y `app/components/team_selector.py`, que
asigna qué equipo jugó cada partido). El tracking frame-a-frame nunca se
guarda como filas de SQL (`tracking_outputs.parquet_url` solo apunta al
archivo). El video **sí se sube entero**, pero como archivo a Supabase
Storage — nunca como bytes en una tabla; `match_videos.storage_url` en la
tabla cloud guarda el path del objeto dentro del bucket privado, no una
URL pública (el bucket no es público — ver "Cómo levantarlo"). Ver
`db/schema_cloud.sql` para el detalle de columnas.

## Sync: dirección y disparo

- **Una sola dirección:** local → nube. No hay sync inverso todavía (no se
  baja nada de Supabase a la SQLite local).
- **Manual, no automático:** se corre explícitamente con
  `python scripts/sync_to_cloud.py --all` (o pasando un partido puntual)
  cuando hay conexión — nunca como requisito para tagear o calificar en
  cancha.
- **Idempotente:** cada evento/calificación se sube una sola vez (columna
  `synced_at` en SQLite) y el upsert en Supabase usa `(match_id, local_id)`
  como clave, así correr el script dos veces no duplica filas.

## Piezas nuevas en el repo

```text
db/schema_cloud.sql          # DDL a pegar en el SQL Editor de Supabase
src/db/
  supabase_client.py         # conexión (lee SUPABASE_URL/KEY de .env o secrets.toml)
  local.py                   # lectura de SQLite + marcado de sincronizado
  team_repo.py                # equipos/categorías y qué equipo jugó cada partido
  roster_repo.py              # plantel por equipo (alta/baja)
  video_repo.py                # ruta local del video de cada partido
  sync.py                    # lógica de sync (roster, video, sync_match, sync_all)
app/components/
  team_selector.py            # UI: elegir/crear el equipo de un partido
  roster_view.py               # UI: alta/baja de jugadores del plantel
  video_registry.py            # UI: registrar la ruta local del video
scripts/sync_to_cloud.py     # CLI del punto anterior
.env.example                 # template de credenciales (nunca commitear .env real)
```

## Cómo levantarlo (una vez, por integrante que lo use)

1. Crear un proyecto gratis en [supabase.com](https://supabase.com).
2. Dashboard → SQL Editor → pegar y correr `db/schema_cloud.sql`.
3. Dashboard → Storage → New bucket → nombre `match-videos`, con
   **"Public bucket" desactivado** (el video de jugadores no debe quedar
   accesible sin permiso — ver la sección de privacidad en
   `docs/context/proyecto-analizador-tactico.md`). Solo hace falta
   crearlo una vez por proyecto de Supabase.
4. Dashboard → Settings → API → copiar `Project URL` y la key `anon public`.
5. `cp .env.example .env` y completar esos dos valores.
6. `pip install -r requirements.txt` (agrega `supabase` y `python-dotenv`).
7. Desde la app: crear al menos un equipo y asignarlo a un partido (panel
   "📁 Partido"), cargar su plantel (tab "🚦 Semáforo" → "Gestionar
   plantel"), y opcionalmente registrar la ruta del video ("🎥 Video del
   partido").
8. Probar: `python scripts/sync_to_cloud.py --all`.

## Pendiente / próximos pasos

- Botón "☁️ Sincronizar" dentro de la app (hoy es CLI a propósito: la
  subida de video puede tardar varios minutos según el tamaño del
  archivo y congelaría la interfaz si se disparara desde un botón de
  Streamlit).
- Generar signed URLs para reproducir el video subido (el bucket es
  privado — `match_videos.storage_url` guarda el path del objeto, no un
  link directo; falta la pantalla/función que pida un link temporal
  cuando alguien quiera verlo).
- Vincular `player_ratings.player_id` / `events.player_id` a la tabla real
  `players` en vez de `player_number` suelto (el plantel ya es una tabla
  real con id propio — `roster_repo.py` — falta que semáforo/eventos
  referencien ese id en vez de un número de camiseta suelto).
- Definir si Supabase Auth reemplaza la tabla `users` propia, si en algún
  momento se necesita login real en una vista compartida del equipo.
