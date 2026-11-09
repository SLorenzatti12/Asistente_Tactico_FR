-- ============================================================================
-- Asistente Táctico FR — Seguridad de la nube: Row Level Security (RLS)
-- ============================================================================
-- 27/10/2026 · Santi, con el OK de Nico. Ver docs/context/decisiones.md
-- ("Supabase: RLS activada…") y docs/context/8-base-de-datos-hibrida.md.
--
-- Qué hace:
--   1. Activa RLS en TODAS las tablas del esquema `public` (las de
--      db/schema_cloud.sql, incluida match_halves, y cualquiera que se agregue
--      después), SIN políticas para `anon` ni `authenticated`: con la clave
--      pública (publishable / anon) no se lee ni se escribe ninguna fila.
--   2. Le saca a `anon` todos los permisos sobre esas tablas (defensa en
--      profundidad: aunque alguien desactive RLS por error, la clave pública
--      sigue sin acceso), también para las tablas que se creen más adelante.
--   3. Deja el bucket `match-videos` privado y borra las políticas de
--      Storage que le daban acceso a `anon` (o a `public`) sobre ese bucket.
--
-- El sync (scripts/sync_to_cloud.py) pasa a usar la clave SECRETA del
-- proyecto (SUPABASE_SECRET_KEY, solo en el .env de la máquina que
-- sincroniza): esa clave usa el rol `service_role`, que saltea RLS. Correr
-- este archivo ANTES de cargar la clave secreta corta el sync hasta que se
-- cargue.
--
-- Cómo correrlo: Dashboard de Supabase → SQL Editor → pegar todo → Run.
-- Es idempotente: se puede correr de nuevo sin romper nada.
--
-- Cuando haya login en la nube (Supabase Auth), se agregan políticas por
-- club/rol para `authenticated`; hasta entonces, nadie entra con la clave
-- pública.
-- ============================================================================

-- ── 1 y 2. Tablas ───────────────────────────────────────────────────────
-- Todas las tablas de `public`, no una lista fija: una lista se queda corta
-- cuando el esquema crece (le pasó a match_halves, 09/11/2026).
do $$
declare
    tabla text;
begin
    for tabla in select tablename from pg_tables where schemaname = 'public' loop
        execute format('alter table public.%I enable row level security', tabla);
        execute format('revoke all on table public.%I from anon', tabla);
    end loop;
end
$$;

-- Que las tablas que se creen más adelante tampoco le den permisos a `anon`.
-- (RLS no se activa sola en una tabla nueva: volver a correr este archivo
-- después de cambiar db/schema_cloud.sql.)
alter default privileges in schema public revoke all on tables from anon;

-- ── 3. Storage: bucket privado y sin acceso para la clave pública ───────
do $$
declare
    pol record;
begin
    if to_regclass('storage.buckets') is not null then
        update storage.buckets set public = false where id = 'match-videos';
    end if;
    if to_regclass('storage.objects') is not null then
        for pol in
            select policyname
            from pg_policies
            where schemaname = 'storage' and tablename = 'objects'
              and (roles && array['anon', 'public']::name[])
              and (coalesce(qual, '') || coalesce(with_check, '')) like '%match-videos%'
        loop
            execute format('drop policy %I on storage.objects', pol.policyname);
            raise notice 'Política de Storage borrada: %', pol.policyname;
        end loop;
    end if;
end
$$;

-- ── Control: tiene que dar rls = true en todas, y anon_puede = false ────
select c.relname as tabla,
       c.relrowsecurity as rls,
       has_table_privilege('anon', c.oid, 'select, insert, update, delete') as anon_puede
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r'
order by 1;
