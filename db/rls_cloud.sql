-- ============================================================================
-- Asistente Táctico FR — Seguridad de la nube (RLS)
-- ============================================================================
-- Nico — ver "Seguridad de la nube" en docs/context/8-base-de-datos-hibrida.md
-- para el contexto completo. Resumen: hoy cualquiera con la key pública
-- ("anon") del proyecto puede leer y escribir TODAS las tablas directo
-- contra la API de Supabase, sin pasar por la app — porque ninguna tabla
-- tiene Row Level Security (RLS) activada.
--
-- Este script activa RLS en todas las tablas de schema_cloud.sql y
-- DELIBERADAMENTE no crea ninguna política para los roles `anon` ni
-- `authenticated`: en Postgres, una tabla con RLS activada y sin políticas
-- rechaza TODO acceso para esos roles (select/insert/update/delete), sin
-- excepción. Es el default-deny más simple posible, correcto acá porque
-- todavía no hay Auth ni usuarios reales (ver decisiones.md) — no hay según
-- qué criterio escribir una política permisiva sin inventar uno falso.
--
-- El único código que escribe en la nube (src/db/sync.py, corrido a mano
-- vía scripts/sync_to_cloud.py) pasa a usar la key "service_role", que
-- por diseño de Supabase BYPASSEA RLS por completo — así que sigue
-- funcionando exactamente igual después de correr esto. Ver
-- src/db/supabase_client.py (get_privileged_client) y .env.example.
--
-- Cómo correrlo: pegar este archivo entero en el SQL Editor del proyecto
-- de Supabase (Dashboard → SQL Editor → New query → Run), DESPUÉS de haber
-- agregado SUPABASE_SERVICE_ROLE_KEY a tu .env y probado el sync con el
-- estado actual (sin RLS) como referencia — ver los 5 pasos en el doc.
-- Es idempotente (ENABLE ROW LEVEL SECURITY no falla si ya está activada).
--
-- Nota aparte (no cubierta por este script): Supabase Storage protege sus
-- objetos con sus propias políticas (tabla storage.objects), separadas de
-- esto. El bucket "match-videos" ya se crea privado ("Public bucket"
-- desactivado — ver 8-base-de-datos-hibrida.md), y como sync.py ahora usa
-- service_role, que también bypassea las políticas de Storage, no hace
-- falta agregar ninguna acá. Si en el dashboard (Storage → match-videos →
-- Policies) aparece alguna política que le da acceso a `anon`, conviene
-- borrarla a mano — este script no toca Storage.
-- ============================================================================

alter table clubs            enable row level security;
alter table users             enable row level security;
alter table teams             enable row level security;
alter table players           enable row level security;
alter table matches           enable row level security;
alter table match_videos      enable row level security;
alter table calibrations      enable row level security;
alter table tracking_outputs  enable row level security;
alter table events            enable row level security;
alter table player_ratings    enable row level security;
alter table match_metrics     enable row level security;
alter table match_halves      enable row level security;
