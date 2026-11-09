"""
Conexión a Supabase — Nico y Santi
===================================
Un solo punto para crear el cliente de Supabase. Ninguna credencial va
hardcodeada ni se sube a Git — ver .env.example para el template y
.gitignore (ya ignora .env y .streamlit/secrets.toml).

Con RLS activada (db/rls_cloud.sql) hay un solo modelo, y dos claves:

  - **Clave secreta** (SUPABASE_SECRET_KEY): la "secret" del proyecto
    (sb_secret_…) o la "service_role" de las claves viejas. Saltea RLS, así
    que es la única que lee y escribe. La usa el sync (src/db/sync.py, vía
    scripts/sync_to_cloud.py), que corre a mano en la laptop que sincroniza.
    `get_client()` y `get_privileged_client()` son el mismo cliente con esta
    clave (el segundo nombre es el que usa sync.py desde el merge con la rama
    de Nico, 09/11/2026). Se acepta también con el nombre viejo
    SUPABASE_SERVICE_ROLE_KEY; si están los dos y son distintos, es un error.
    Sale solo de variables de entorno o del .env, NUNCA de st.secrets: la app
    de Streamlit no tiene que tenerla nunca.
  - **Clave pública** (SUPABASE_KEY: publishable / anon): con RLS activada y
    sin políticas para `anon` no da acceso a nada. Queda solo para
    `get_client_publico()`, que usa scripts/verificar_rls.py para comprobar
    justamente eso.

Las dos funciones rechazan la clave equivocada (la pública puesta como
secreta y al revés), mirando el prefijo o el rol del JWT. Orden de búsqueda:
variables de entorno, después .env en la raíz del repo (python-dotenv); la
URL y la clave pública también pueden venir de .streamlit/secrets.toml.
Detalle y pasos en docs/context/8-base-de-datos-hibrida.md, "Seguridad de la
nube".
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


def _clave_secreta() -> str | None:
    """SUPABASE_SECRET_KEY, o SUPABASE_SERVICE_ROLE_KEY (el nombre que usaba
    la rama de Nico). A propósito solo de env/.env, nunca de st.secrets."""
    _load_dotenv_if_present()
    secreta = os.environ.get("SUPABASE_SECRET_KEY")
    vieja = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if secreta and vieja and secreta != vieja:
        raise SupabaseConfigError(
            "Hay dos claves secretas distintas: SUPABASE_SECRET_KEY y SUPABASE_SERVICE_ROLE_KEY "
            "(el nombre viejo). Dejá una sola en el .env, con la clave secreta vigente."
        )
    return secreta or vieja


def get_client():
    """Cliente con la clave SECRETA, para el sync (saltea RLS).

    Lanza SupabaseConfigError si falta SUPABASE_URL o la clave secreta, si la
    clave cargada como secreta es la pública o si hay dos secretas distintas;
    ImportError si no está instalado `supabase` (ver requirements.txt).
    """
    from supabase import create_client, Client  # type: ignore

    key = _clave_secreta()
    url = os.environ.get("SUPABASE_URL") or _load_streamlit_secrets().get("SUPABASE_URL")
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


def get_privileged_client():
    """El mismo cliente que get_client(), con la clave secreta. Es el nombre
    que usa src/db/sync.py desde el merge con la rama de Nico (09/11/2026)."""
    return get_client()


def get_client_publico():
    """Cliente con la clave PÚBLICA (SUPABASE_KEY). Solo para comprobar que
    no tiene acceso (scripts/verificar_rls.py)."""
    from supabase import create_client  # type: ignore

    url, key = get_supabase_credentials()
    if rol_de_la_clave(key) == "service_role":
        raise SupabaseConfigError("SUPABASE_KEY tiene la clave SECRETA: ahí va la pública.")
    return create_client(url, key)
