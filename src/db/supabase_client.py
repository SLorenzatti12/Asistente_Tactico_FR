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

Qué clave usar (27/10/2026, Santi con el OK de Nico — ver decisiones.md,
"Supabase: RLS activada"):
  - El sync usa SUPABASE_SECRET_KEY: la clave SECRETA del proyecto ("secret",
    sb_secret_…, o la "service_role" de las claves viejas). Con RLS activada
    (db/rls_cloud.sql) es la única que lee y escribe. Va solo en el .env de
    la máquina que sincroniza, nunca en el repo ni en secrets.toml de
    Streamlit: no se lee de st.secrets, para que la app nunca la tenga.
  - SUPABASE_KEY (la pública: publishable / anon) ya no da acceso a nada;
    queda solo para scripts/verificar_rls.py, que comprueba justamente eso.
  - get_client() rechaza una clave pública puesta como secreta (y al revés
    en get_client_publico), mirando el prefijo o el rol del JWT.
"""
from __future__ import annotations

import base64
import json
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


def rol_de_la_clave(key: str) -> str | None:
    """"service_role" o "anon" según la clave (prefijo de las claves nuevas,
    o el rol dentro del JWT de las viejas); None si no se puede saber."""
    if key.startswith("sb_secret_"):
        return "service_role"
    if key.startswith("sb_publishable_"):
        return "anon"
    partes = key.split(".")
    if len(partes) == 3:
        try:
            carga = partes[1] + "=" * (-len(partes[1]) % 4)
            return json.loads(base64.urlsafe_b64decode(carga)).get("role")
        except (ValueError, json.JSONDecodeError):
            return None
    return None


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
    """Cliente con la clave SECRETA, para el sync (saltea RLS).

    Lanza SupabaseConfigError si falta SUPABASE_URL o SUPABASE_SECRET_KEY,
    o si la clave cargada como secreta es la pública; ImportError si no está
    instalado `supabase` (ver requirements.txt).
    """
    from supabase import create_client, Client  # type: ignore

    _load_dotenv_if_present()
    url = os.environ.get("SUPABASE_URL") or _load_streamlit_secrets().get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")   # a propósito, no de st.secrets
    if not url or not key:
        raise SupabaseConfigError(
            "Falta SUPABASE_SECRET_KEY (o SUPABASE_URL). Desde que la nube tiene RLS "
            "activada (db/rls_cloud.sql), el sync necesita la clave SECRETA del proyecto: "
            "Dashboard de Supabase → Settings → API Keys → secret. Va solo en el .env de "
            "esta máquina, nunca en el repo. Ver docs/context/8-base-de-datos-hibrida.md."
        )
    if rol_de_la_clave(key) == "anon":
        raise SupabaseConfigError(
            "SUPABASE_SECRET_KEY tiene la clave PÚBLICA (publishable/anon). Con RLS activada "
            "esa clave no puede leer ni escribir: poné la clave secreta."
        )
    client: Client = create_client(url, key)
    return client


def get_client_publico():
    """Cliente con la clave PÚBLICA (SUPABASE_KEY). Solo para comprobar que
    no tiene acceso (scripts/verificar_rls.py)."""
    from supabase import create_client  # type: ignore

    url, key = get_supabase_credentials()
    if rol_de_la_clave(key) == "service_role":
        raise SupabaseConfigError("SUPABASE_KEY tiene la clave SECRETA: ahí va la pública.")
    return create_client(url, key)
