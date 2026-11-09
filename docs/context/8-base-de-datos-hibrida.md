# Base de datos híbrida (SQLite local + Supabase en la nube)

Nico

## Estado

**Vinculado y verificado end-to-end (23/09/2026).** Hay un proyecto real
de Supabase creado, con `db/schema_cloud.sql` corrido y el bucket privado
`match-videos` creado. Se probó `python scripts/sync_to_cloud.py --all`
contra ese proyecto: un equipo y su plantel subieron correctamente a las
tablas `teams`/`players`. Las credenciales viven en `.env` (local,
gitignored, nunca en el repo).

**Seguridad de la nube: preparada, falta aplicarla (09/11/2026).** Hoy el
proyecto real sigue con RLS desactivada (cualquiera con la key pública
lee/escribe todo — ver "Seguridad de la nube" más abajo). `db/rls_cloud.sql`,
`scripts/verificar_rls.py` y el cliente privilegiado (`get_privileged_client`
en `supabase_client.py`, ya usado por `sync.py`) están escritos y probados
localmente (import, sintaxis), pero **todavía no se corrieron contra el
proyecto real** — eso son los 5 pasos de esa sección, pendientes de que
alguien con acceso al dashboard los ejecute.

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
| `estadios`, `match_estadio` (medidas de cancha por estadio y dónde se jugó cada partido — ver `src/db/estadio_repo.py`; todavía no se sincronizan) | |
| `partido_tiempos` (agrupa los dos videos/tiempos de un partido — ver `src/db/partido_repo.py`) | `match_halves` (mismo agrupamiento, referenciando las dos filas de `matches`) |
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
db/rls_cloud.sql              # activa RLS, sin políticas para anon/authenticated
src/db/
  supabase_client.py         # conexión: get_client() (anon) / get_privileged_client() (service_role)
  local.py                   # lectura de SQLite + marcado de sincronizado
  team_repo.py                # equipos/categorías y qué equipo jugó cada partido
  roster_repo.py              # plantel por equipo (alta/baja)
  video_repo.py                # ruta local del video de cada partido
  estadio_repo.py              # medidas de cancha por estadio y estadio de cada partido (solo local)
  partido_repo.py              # agrupa los dos tiempos de un partido (solo local)
  sync.py                    # lógica de sync (roster, partido_tiempos, video, sync_match, sync_all)
app/components/
  team_selector.py            # UI: elegir/crear el equipo de un partido (propaga a los dos tiempos)
  roster_view.py               # UI: alta/baja de jugadores del plantel
  video_registry.py            # UI: registrar la ruta local del video
scripts/sync_to_cloud.py     # CLI del punto anterior
scripts/estadios.py          # alta/listado de estadios y asignación a partidos
scripts/partidos.py           # alta/listado de partidos de dos tiempos
scripts/verificar_rls.py      # prueba anon bloqueada / service_role operativa
.env.example                 # template de credenciales (nunca commitear .env real)
```

## Diagrama rápido de `src/db/`

```
┌─────────────────────────────────────────────────────────────┐
│ src/db/  — capa de base de datos híbrida                     │
│                                                               │
│  supabase_client.py  → único punto de conexión (.env/secrets)│
│                                                               │
│  team_repo.py     → equipos/categorías + match_team          │
│  roster_repo.py   → plantel por equipo (alta/DELETE físico)  │
│  video_repo.py    → ruta local del video + flag "subido"     │
│  local.py         → solo-lectura de events/semaforo          │
│         │                                                     │
│         └──► sync.py → orquesta el sync completo:            │
│               - plantel: mirror por equipo (upsert + borra)  │
│               - video: sube a bucket privado Storage         │
│               - events/semaforo: upsert vía local.py          │
└──────────────────────────┬────────────────────────────────────┘
                            │ usa
┌───────────────────────────▼──────────────────────────────────┐
│ Puntos de entrada a la capa                                   │
│  scripts/sync_to_cloud.py       → CLI, dispara sync.py         │
│  db/schema_cloud.sql            → DDL espejo en Supabase        │
│  app/components/team_selector.py  → UI: elegir/crear equipo    │
│  app/components/roster_view.py    → UI: alta/baja plantel      │
│  app/components/video_registry.py → UI: registrar ruta video   │
└─────────────────────────────────────────────────────────────┘
```

Regla de dependencia: todo dentro de `src/db/` solo habla con SQLite
local; `sync.py` es el único que además habla con Supabase, y solo cuando
se corre `sync_to_cloud.py` a mano (nunca desde un botón de Streamlit ni
bloqueando el flujo en cancha).

## Cómo levantarlo (una vez, por integrante que lo use)

1. Crear un proyecto gratis en [supabase.com](https://supabase.com).
2. Dashboard → SQL Editor → pegar y correr `db/schema_cloud.sql`.
3. Dashboard → Storage → New bucket → nombre `match-videos`, con
   **"Public bucket" desactivado** (el video de jugadores no debe quedar
   accesible sin permiso — ver la sección de privacidad en
   `docs/context/proyecto-analizador-tactico.md`). Solo hace falta
   crearlo una vez por proyecto de Supabase.
4. Dashboard → Settings → API → copiar `Project URL` y la key pública
   (según la versión del dashboard aparece como `anon public` o como
   `publishable` — **nunca** la `service_role`/`secret`, esa tiene acceso
   total sin restricciones).
5. `cp .env.example .env` y completar esos dos valores.
6. `pip install -r requirements.txt` (agrega `supabase` y `python-dotenv`).
7. Desde la app: crear al menos un equipo y asignarlo a un partido (panel
   "📁 Partido"), cargar su plantel (tab "🚦 Semáforo" → "Gestionar
   plantel"), y opcionalmente registrar la ruta del video ("🎥 Video del
   partido").
8. Probar: `python scripts/sync_to_cloud.py --all`.

## Seguridad de la nube

**Problema (hoy, sin aplicar todavía):** `schema_cloud.sql` no activa RLS
en ninguna tabla. Postgres sin RLS no filtra nada: cualquiera que consiga
la key pública (`anon` — pensada para ser pública, no es un secreto, pero
sin RLS deja de ser inofensiva) puede leer y escribir las 12 tablas directo
contra la API REST de Supabase, sin pasar por la app ni por `sync.py`.

**Solución:** activar RLS en todas las tablas y no darle ninguna política
a `anon`/`authenticated` — con RLS activada y cero políticas, Postgres
niega todo acceso a esos roles por default (no hace falta escribir un
`DENY` explícito). El único código que escribe en la nube (`sync.py`) pasa
a usar la key `service_role`, que bypassea RLS por diseño de Supabase —
sigue funcionando exactamente igual. Ver `get_client()` / `get_privileged_client()`
en `src/db/supabase_client.py`.

**Por qué no hay políticas reales en vez de bloquear todo:** una política
con sentido necesita algo contra qué decidir (¿este usuario puede ver este
club? ¿este partido?), y eso requiere Auth con usuarios reales — que no
existe todavía (ver `decisiones.md`). Escribir una política permisiva sin
ese criterio sería simular seguridad que no es tal. Bloquear todo para
`anon` es correcto hoy porque **nada en la app corre contra Supabase con
la key pública** (se verificó: el único consumidor de `supabase_client.py`
es `sync.py`, que ahora usa `service_role`) — el día que se agregue una
vista de solo lectura para coaches (ver "Pendiente"), esa sí necesitará
política real con Auth.

**Los 5 pasos, en orden (solo quien tenga acceso al dashboard real):**

1. Agregar `SUPABASE_SERVICE_ROLE_KEY` a tu `.env` — Dashboard de Supabase
   → Settings → API → key `service_role` ("secret", **no** la
   `anon public`). Ver `.env.example`.
2. Probar el sync tal como está (`python scripts/sync_to_cloud.py --all`)
   — referencia de que todo funciona ANTES del cambio, para poder comparar.
3. Correr `db/rls_cloud.sql` en el SQL Editor del proyecto (Dashboard →
   SQL Editor → New query → pegar → Run). Es idempotente.
4. Correr `python scripts/verificar_rls.py` — confirma que la key pública
   quedó bloqueada y que la privilegiada sigue andando.
5. Volver a probar el sync (`python scripts/sync_to_cloud.py --all`) —
   tiene que dar el mismo resultado que en el paso 2.

Si el paso 5 falla pero el 2 funcionaba, algo de `rls_cloud.sql` quedó mal
— no seguir usando el proyecto con RLS a mitad de camino (ver `verificar_rls.py`
para qué tabla/key específica está fallando).

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
- **Aplicar "Seguridad de la nube" (arriba) contra el proyecto real** —
  los 5 pasos. Mientras no se corran, sigue siendo cierto que cualquiera
  con la key pública lee/escribe todo, sin pasar por la app.
- El día que haya Auth y una vista de solo lectura para coaches, escribir
  políticas RLS reales para `authenticated` (hoy `db/rls_cloud.sql`
  deliberadamente no le da ninguna, ver "Seguridad de la nube").
