-- ============================================================================
-- Asistente Táctico FR — Esquema CLOUD (Supabase / Postgres)
-- ============================================================================
-- Nico — capa de nube del modelo híbrido (ver docs/context/8-base-de-datos-hibrida.md)
--
-- Esto NO reemplaza a SQLite local (data/db/analizador.sqlite). Es la mitad
-- "en la nube" del híbrido: gestión de usuarios/clubes/plantillas y el
-- histórico consolidado de partidos, sincronizado desde SQLite cuando hay
-- conexión (ver scripts/sync_to_cloud.py). El día del partido, en el
-- estadio, la app sigue funcionando 100% contra SQLite sin tocar esto.
--
-- Cómo correrlo: pegar este archivo entero en el SQL Editor del proyecto
-- de Supabase (Dashboard → SQL Editor → New query → Run). Es idempotente
-- (create table if not exists), se puede correr de nuevo sin romper nada.
-- ============================================================================

create extension if not exists pgcrypto; -- para gen_random_uuid()

-- ── Clubes ───────────────────────────────────────────────────────────────
create table if not exists clubs (
    id         uuid primary key default gen_random_uuid(),
    name       text not null,
    city       text,
    created_at timestamptz not null default now()
);

-- ── Usuarios ─────────────────────────────────────────────────────────────
-- Si más adelante se activa Supabase Auth, este `id` puede ser el mismo
-- que auth.users(id) (login real con email/password). Por ahora es una
-- tabla propia para no acoplar el diseño a esa decisión todavía.
create table if not exists users (
    id         uuid primary key default gen_random_uuid(),
    club_id    uuid references clubs(id) on delete cascade,
    full_name  text not null,
    email      text unique not null,
    role       text not null check (role in ('admin', 'coach', 'analyst', 'viewer')),
    created_at timestamptz not null default now()
);

-- ── Equipos / categorías dentro de un club ──────────────────────────────
create table if not exists teams (
    id         uuid primary key default gen_random_uuid(),
    club_id    uuid references clubs(id) on delete cascade,
    name       text not null,
    category   text,   -- "Primera", "Reserva", "Sub-17"...
    season     text,
    created_at timestamptz not null default now()
);

-- ── Plantilla de jugadores ───────────────────────────────────────────────
-- Espejo cloud del plantel único de SQLite (tabla `roster`, ver
-- src/db/roster_repo.py) — se carga una sola vez del lado local y se
-- sincroniza acá, no por partido. `local_id` = `roster.id` en SQLite,
-- mismo patrón que `events.local_id` / `player_ratings.local_id`, para que
-- el upsert sea idempotente (correr el sync dos veces no duplica filas).
-- `active = false` es la baja de un jugador que dejó el equipo (soft
-- delete del lado local, para no huerfanar calificaciones viejas).
create table if not exists players (
    id            uuid primary key default gen_random_uuid(),
    team_id       uuid references teams(id) on delete cascade,
    local_id      int,
    jersey_number int,
    full_name     text not null,
    position      text,
    active        boolean not null default true,
    created_at    timestamptz not null default now(),
    unique (team_id, local_id)
);

-- ── Partidos ─────────────────────────────────────────────────────────────
-- `local_key` = el `match_name` (texto) que ya usa SQLite/roster.json hoy.
-- Es el puente entre el mundo local (sin UUID) y el mundo cloud: el script
-- de sync busca/crea la fila acá por local_key, sin tener que renombrar
-- nada del lado local.
create table if not exists matches (
    id             uuid primary key default gen_random_uuid(),
    local_key      text unique not null,
    team_id        uuid references teams(id) on delete cascade,
    opponent_name  text,
    match_date     date,
    competition    text,
    is_home        boolean,
    goals_for      int,
    goals_against  int,
    status         text not null default 'pending'
                   check (status in ('pending', 'uploaded', 'processed', 'analyzed')),
    created_by     uuid references users(id),
    created_at     timestamptz not null default now()
);

-- ── Videos del partido (norte/sur) ───────────────────────────────────────
-- `storage_url` apunta al archivo subido a Supabase Storage (bucket
-- "match-videos", ver docs/context/8-base-de-datos-hibrida.md) — nunca se
-- guarda el video como bytes en esta tabla. `local_id` = el id de la fila
-- local en SQLite (tabla `match_videos`, ver src/db/video_repo.py), mismo
-- patrón que `events.local_id`, para que subir el mismo video dos veces
-- no duplique la fila.
create table if not exists match_videos (
    id            uuid primary key default gen_random_uuid(),
    match_id      uuid references matches(id) on delete cascade,
    local_id      int,
    camera_side   text check (camera_side in ('norte', 'sur')),
    storage_url   text not null,
    duration_sec  numeric,
    fps           numeric,
    uploaded_by   uuid references users(id),
    uploaded_at   timestamptz not null default now(),
    unique (match_id, local_id)
);

-- ── Calibración (matriz de homografía) por cámara/partido ────────────────
create table if not exists calibrations (
    id                 uuid primary key default gen_random_uuid(),
    match_id           uuid references matches(id) on delete cascade,
    camera_side        text check (camera_side in ('norte', 'sur')),
    homography_matrix  jsonb not null,
    reference_points   jsonb,
    created_at         timestamptz not null default now()
);

-- ── Salida del pipeline de tracking ──────────────────────────────────────
-- Apunta al .parquet (local u objeto en la nube) — nunca guarda el
-- frame-a-frame como filas de SQL.
create table if not exists tracking_outputs (
    id            uuid primary key default gen_random_uuid(),
    match_id      uuid references matches(id) on delete cascade,
    parquet_url   text not null,
    model_version text,
    frame_count   int,
    fps           numeric,
    generated_at  timestamptz not null default now(),
    status        text default 'ready' check (status in ('processing', 'ready', 'failed'))
);

-- ── Eventos tagueados (espejo cloud de la tabla `events` de SQLite) ──────
create table if not exists events (
    id            uuid primary key default gen_random_uuid(),
    match_id      uuid references matches(id) on delete cascade,
    local_id      int,        -- id original en SQLite, para no duplicar en re-sync
    tag_type      text not null,
    time_sec      numeric not null,
    team_side     text check (team_side in ('home', 'away')),
    player_id     uuid references players(id),
    clip_url      text,
    created_by    uuid references users(id),
    created_at    timestamptz not null default now(),
    unique (match_id, local_id)
);

-- ── Semáforo / calificación por jugador (espejo cloud de `semaforo`) ─────
create table if not exists player_ratings (
    id            uuid primary key default gen_random_uuid(),
    match_id      uuid references matches(id) on delete cascade,
    local_id      int,
    player_number int,        -- hasta que haya vínculo real a `players.id`
    player_id     uuid references players(id),
    rating        text check (rating in ('bajo', 'regular', 'destacado')),
    rated_by      uuid references users(id),
    created_at    timestamptz not null default now(),
    unique (match_id, local_id)
);

-- ── Métricas tácticas agregadas (compacidad, ancho de bloque, etc.) ──────
create table if not exists match_metrics (
    id                 uuid primary key default gen_random_uuid(),
    match_id           uuid references matches(id) on delete cascade,
    team_side          text check (team_side in ('home', 'away')),
    metric_name        text not null,
    time_window_start  numeric,
    time_window_end    numeric,
    value              numeric
);

-- ── Índices ──────────────────────────────────────────────────────────────
create index if not exists idx_events_match_time on events (match_id, time_sec);
create index if not exists idx_matches_team_date on matches (team_id, match_date);
create index if not exists idx_ratings_match on player_ratings (match_id);
