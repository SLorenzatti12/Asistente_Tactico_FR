"""
Conexión a Supabase — Nico
===========================
Un solo punto para crear el cliente de Supabase, leyendo credenciales desde
(en este orden):

  1. Variables de entorno: SUPABASE_URL / SUPABASE_KEY
  2. .streamlit/secrets.toml (si corre dentro de la app Streamlit)
  3. .env en la raíz del repo (vía python-dotenv, para scripts standalone)

Ninguna credencial va hardcodeada ni se sube a Git — ver .env.example para
el template y .gitignore (ya ignora .env y .streamlit/secrets.toml).

Qué clave usar:
  - SUPABASE_KEY = la "anon public" key del proyecto, para uso normal desde
    la app/scripts del equipo.
  - Para tareas administrativas (crear usuarios, bypass de RLS) se usaría la
    "service_role" key aparte — no se contempla acá todavía, no meterla en
    este mismo cliente si en algún momento se agrega.
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
    """Devuelve un cliente `supabase-py` listo para usar.

    Lanza SupabaseConfigError si faltan credenciales, o ImportError si no
    está instalado `supabase` (ver requirements.txt).
    """
    from supabase import create_client, Client  # type: ignore

    url, key = get_supabase_credentials()
    client: Client = create_client(url, key)
    return client
