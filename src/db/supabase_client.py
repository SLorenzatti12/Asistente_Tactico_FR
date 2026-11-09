"""
Conexión a Supabase — Nico
===========================
Un solo punto para crear el cliente de Supabase, leyendo credenciales desde
(en este orden):

  1. Variables de entorno: SUPABASE_URL / SUPABASE_KEY (o _SERVICE_ROLE_KEY)
  2. .streamlit/secrets.toml (si corre dentro de la app Streamlit)
  3. .env en la raíz del repo (vía python-dotenv, para scripts standalone)

Ninguna credencial va hardcodeada ni se sube a Git — ver .env.example para
el template y .gitignore (ya ignora .env y .streamlit/secrets.toml).

Qué clave usar — ver "Seguridad de la nube" en
docs/context/8-base-de-datos-hibrida.md para el por qué:
  - get_client() → SUPABASE_KEY, la "anon public" key. Con RLS activada
    (db/rls_cloud.sql) y sin políticas para `anon`, esta key no puede leer
    ni escribir nada — queda reservada para un futuro consumo de solo
    lectura desde la app, el día que haya políticas reales para eso.
  - get_privileged_client() → SUPABASE_SERVICE_ROLE_KEY, que bypassea RLS
    por diseño de Supabase. Es la que usa src/db/sync.py (el único código
    que escribe en la nube) — nunca debe usarse desde código que corra en
    el navegador del usuario ni exponerse fuera de este .env local.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


class SupabaseConfigError(RuntimeError):
    """Faltan credenciales de Supabase — ver .env.example."""


def _load_dotenv_if_present() -> None:
    """Carga .env a os.environ si existe (no pisa variables ya seteadas)."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv  # python-dotenv
        load_dotenv(env_path, override=False)
    except ImportError:
        # Fallback sin dependencia extra: parseo manual línea por línea.
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _load_streamlit_secrets() -> dict:
    """Si corre dentro de Streamlit y hay secrets.toml, los devuelve como dict."""
    try:
        import streamlit as st
        return dict(st.secrets) if hasattr(st, "secrets") else {}
    except Exception:
        # Sin contexto de Streamlit corriendo, o sin secrets.toml — normal
        # cuando esto se llama desde un script standalone (scripts/sync_to_cloud.py).
        return {}


def get_supabase_credentials() -> tuple[str, str]:
    """Resuelve (url, key) probando env vars -> secrets.toml -> .env."""
    _load_dotenv_if_present()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        secrets = _load_streamlit_secrets()
        url = url or secrets.get("SUPABASE_URL")
        key = key or secrets.get("SUPABASE_KEY")

    if not url or not key:
        raise SupabaseConfigError(
            "Faltan credenciales de Supabase. Copiá .env.example a .env "
            "(o cargalas en .streamlit/secrets.toml) con SUPABASE_URL y "
            "SUPABASE_KEY del proyecto (Dashboard de Supabase → Settings → API)."
        )
    return url, key


def get_client():
    """Cliente `supabase-py` con la key pública (anon). Ver el docstring
    del módulo: con RLS activada y sin políticas para `anon`, este cliente
    no puede leer ni escribir nada — es intencional.

    Lanza SupabaseConfigError si faltan credenciales, o ImportError si no
    está instalado `supabase` (ver requirements.txt).
    """
    from supabase import create_client, Client  # type: ignore

    url, key = get_supabase_credentials()
    client: Client = create_client(url, key)
    return client


def get_privileged_credentials() -> tuple[str, str]:
    """Resuelve (url, service_role_key), mismo orden que get_supabase_credentials."""
    _load_dotenv_if_present()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        secrets = _load_streamlit_secrets()
        url = url or secrets.get("SUPABASE_URL")
        key = key or secrets.get("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        raise SupabaseConfigError(
            "Falta SUPABASE_SERVICE_ROLE_KEY en tu .env (Dashboard de "
            "Supabase → Settings → API → 'service_role' secret — NUNCA la "
            "'anon public'). Ver 'Seguridad de la nube' en "
            "docs/context/8-base-de-datos-hibrida.md."
        )
    return url, key


def get_privileged_client():
    """Cliente `supabase-py` con la service_role key — bypassea RLS.

    Lo usa únicamente src/db/sync.py (vía scripts/sync_to_cloud.py), que
    corre a mano en la laptop del analista, nunca en el navegador. Lanza
    SupabaseConfigError si falta la credencial.
    """
    from supabase import create_client, Client  # type: ignore

    url, key = get_privileged_credentials()
    client: Client = create_client(url, key)
    return client
