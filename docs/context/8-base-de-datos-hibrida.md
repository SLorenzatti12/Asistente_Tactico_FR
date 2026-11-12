# Base de datos híbrida (SQLite local + Supabase en la nube)

Nico

## Estado

**Vinculado y verificado end-to-end (23/09/2026).** Hay un proyecto real
de Supabase creado, con `db/schema_cloud.sql` corrido y el bucket privado
`match-videos` creado. Se probó `python scripts/sync_to_cloud.py --all`
contra ese proyecto: un equipo y su plantel subieron correctamente a las
tablas `teams`/`players`. Las credenciales viven en `.env` (local,
gitignored, nunca en el repo).

**Seguridad de la nube: preparada, falta aplicarla.** El proyecto real sigue
con RLS desactivada (la decisión del 23/09/2026, ver `decisiones.md`): cualquiera
con la clave pública lee y escribe todo. `db/rls_cloud.sql`,
`scripts/verificar_rls.py` y el cliente con la clave secreta
(`supabase_client.py`) están escritos y probados en un Postgres local que
imita a Supabase, pero **todavía no se corrieron contra el proyecto real**.
Son los pasos de "Seguridad de la nube", más abajo, y los tiene que hacer
alguien con acceso al dashboard (hoy Nico). La preparación la hicieron Santi
(27/10/2026) y Nico (09/11/2026) en paralelo; se unió en el merge del
09/11/2026.

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
| `events`, `event_types`, `semaforo` (tal cual las creó/evoluciona `tagging.py`; `semaforo` ya no se escribe desde el 27/10/2026). Desde el 12/11/2026, `events.inicio_sec`/`fin_sec` (clip de cada tag) y la tabla `paradas` (botón "Juego detenido"): **todavía no se sincronizan** | Video subido a Supabase **Storage**, bucket privado `match-videos` |
| `semaforo_minutos`, `semaforo_valoraciones` (planilla por partido: minutos y valoración de DT, ayudante y coordinador por jugador del plantel — ver `src/db/semaforo_repo.py`; **todavía no se sincronizan**) | — (pendiente: reemplazar `player_ratings` por dorsal) |
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
  supabase_client.py         # conexión: get_client() = get_privileged_client() (clave secreta) / get_client_publico() (pública, solo para verificar)
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
scripts/verificar_rls.py      # comprueba que la clave pública no accede y la secreta sí
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
│               - partidos de dos tiempos → match_halves       │
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
2b. Dashboard → SQL Editor → pegar y correr `db/rls_cloud.sql` (RLS: la
   clave pública queda sin acceso).
4. Dashboard → Settings → API Keys → copiar `Project URL`, la clave
   **secreta** (`secret` / `service_role`: la usa el sync) y la pública
   (`publishable` / `anon`: solo para `scripts/verificar_rls.py`). La
   secreta tiene acceso total: va **solo** en el `.env` de la máquina que
   sincroniza (actualizado el 27/10/2026; antes decía "nunca la
   service_role", cuando el sync usaba la pública sin RLS).
5. `cp .env.example .env` y completar `SUPABASE_URL`,
   `SUPABASE_SECRET_KEY` y `SUPABASE_KEY`.
6. `pip install -r requirements.txt` (agrega `supabase` y `python-dotenv`).
7. Desde la app: crear al menos un equipo y asignarlo a un partido (panel
   "📁 Partido"), cargar su plantel (tab "🚦 Semáforo" → "Gestionar
   plantel"), y opcionalmente registrar la ruta del video ("🎥 Video del
   partido").
8. Probar: `python scripts/sync_to_cloud.py --all` y
   `python3 scripts/verificar_rls.py`.

## Seguridad de la nube

**Problema (mientras no se aplique):** `schema_cloud.sql` no activa RLS en
ninguna tabla. Postgres sin RLS no filtra nada: cualquiera que consiga la
clave pública (`anon` / publishable, pensada para ser pública) puede leer y
escribir las 12 tablas directo contra la API REST de Supabase, sin pasar por
la app ni por `sync.py`: plantel con nombres reales, eventos, la tabla
`users` con emails. Es el riesgo R2 de la sección 5.2 del informe.

**Solución:** activar RLS en todas las tablas y no darle ninguna política a
`anon` ni a `authenticated`. Con RLS activada y cero políticas, Postgres
niega todo acceso a esos roles. El sync pasa a usar la clave **secreta**,
que saltea RLS por diseño de Supabase y sigue funcionando igual. Detalle y
por qué en `decisiones.md` ("Supabase: RLS activada y sync con clave
secreta").

**Qué hace `db/rls_cloud.sql`:**
- Activa RLS en **todas las tablas del esquema `public`**, no en una lista
  fija: incluye `match_halves` y cualquier tabla que se agregue después.
- Le saca a `anon` todos los permisos de tabla, también los de las tablas
  futuras (defensa en profundidad: si alguien desactiva RLS por error, la
  clave pública sigue sin acceso).
- Deja privado el bucket `match-videos` y borra las políticas de Storage que
  le daban acceso a `anon` o a `public` sobre ese bucket.
- Al final muestra una tabla de control (`rls = t`, `anon_puede = f`).
- Es idempotente. Si se agrega una tabla a `schema_cloud.sql`, hay que volver
  a correrlo: RLS no se activa sola en una tabla nueva.

**Las claves** (`src/db/supabase_client.py`, `.env.example`):
- **Secreta:** `SUPABASE_SECRET_KEY` (la "secret", `sb_secret_…`; en
  proyectos con las claves viejas, la "service_role"). También se acepta con
  el nombre que usaba la rama de Nico, `SUPABASE_SERVICE_ROLE_KEY`; si están
  las dos con valores distintos, el sync da error. `get_client()` y
  `get_privileged_client()` son el mismo cliente con esta clave. Se lee solo
  del entorno o del `.env`, **nunca** de `.streamlit/secrets.toml`: la app de
  Streamlit no tiene que tenerla.
- **Pública:** `SUPABASE_KEY`. Con RLS no da acceso a nada; solo la usa
  `get_client_publico()`, en `scripts/verificar_rls.py`.
- Las dos funciones rechazan la clave equivocada (la pública puesta como
  secreta y al revés), mirando el prefijo o el rol del JWT.

**Por qué no hay políticas reales en vez de bloquear todo:** una política
con sentido necesita algo contra qué decidir (¿este usuario puede ver este
club?), y eso requiere Supabase Auth con usuarios reales, que no existe
todavía. Bloquear todo para `anon` es correcto hoy porque nada en la app
corre contra Supabase con la clave pública: el único consumidor de
`supabase_client.py` es `sync.py`, con la secreta.

**Pasos, una vez, para quien tenga acceso al dashboard del proyecto (hoy Nico).
Hacerlos en este orden, para no cortar el sync:**

1. **Cargar la clave secreta.** En Dashboard → Settings → API Keys, copiar la clave **secret** (`sb_secret_…`; en proyectos con las claves viejas, la `service_role`) y agregarla al `.env` de la máquina que sincroniza:

   ```
   SUPABASE_SECRET_KEY=<clave secreta>
   ```

   - Nunca en el repo ni en `.streamlit/secrets.toml`.
   - Si el `.env` ya tiene `SUPABASE_SERVICE_ROLE_KEY` con la misma clave, alcanza con dejar una de las dos.
   - Dejar `SUPABASE_KEY` con la pública: la usa el paso 4.
2. **Probar el sync con la clave nueva**, todavía sin RLS, como referencia:

   ```bash
   python3 scripts/sync_to_cloud.py --all
   ```

   Tiene que andar igual que antes, y ahora también agrupa los partidos de dos tiempos (`match_halves`).
3. **Activar RLS:** en Dashboard → SQL Editor, pegar `db/rls_cloud.sql` entero y correrlo (Run).
   - La tabla del final tiene que dar `rls = true` y `anon_puede = false` en todas las filas, `match_halves` incluida.
   - Si en Storage había políticas abiertas para el bucket, aparecen como "Política de Storage borrada: …".
4. **Verificar contra el proyecto real:**

   ```bash
   python3 scripts/verificar_rls.py
   ```

   - **Escribe en la nube:** intenta insertar y subir un archivo con la clave pública (con RLS bien aplicada, la nube lo rechaza), e inserta y borra una fila de prueba con la secreta. Si algo se pudo escribir con la pública, lo borra y lo informa como FALLA.
   - Tiene que terminar en "N de N controles OK".
5. **Volver a probar el sync** (`--all`): tiene que dar lo mismo que en el paso 2. Si el 2 andaba y el 5 no, no seguir con RLS a mitad de camino: `verificar_rls.py` dice qué tabla o clave falla.

**Si algo sale mal:** `alter table public.<tabla> disable row level security;` vuelve una tabla al estado anterior. No debería hacer falta: el sync con la clave secreta no depende de RLS.

**Rotación:** si la clave secreta se filtra (repo, captura, mensaje), revocarla en Dashboard → API Keys, generar otra y cambiarla en el `.env`. Con RLS aplicada, la pública filtrada no da acceso a nada.

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
  El dashboard local ya tiene login propio y offline (26/10/2026, tabla
  `usuarios` en SQLite, mismos cuatro roles). Esos usuarios y sus hashes
  **no** se sincronizan: si se agrega login en la nube, va con Supabase Auth.
- **Aplicar "Seguridad de la nube" (arriba) contra el proyecto real** (hoy
  Nico): los 5 pasos. Mientras no se corran, cualquiera con la clave pública
  lee y escribe todo, sin pasar por la app.
- El día que haya Auth y una vista de solo lectura para coaches, escribir
  políticas RLS reales para `authenticated` (hoy `db/rls_cloud.sql`
  deliberadamente no le da ninguna).
