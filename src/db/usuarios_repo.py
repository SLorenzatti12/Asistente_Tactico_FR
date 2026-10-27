"""
Usuarios locales, contraseñas y permisos por rol
==================================================
El login del dashboard es LOCAL: usuarios y contraseñas viven en la misma
SQLite de la laptop (data/db/analizador.sqlite) y funciona sin internet,
como todo lo que pasa en la cancha. El login de Streamlit (`st.login`) no
sirve acá: usa un proveedor externo (Google, etc.) por internet.

Las contraseñas no se guardan: se guarda un hash scrypt (biblioteca estándar,
`hashlib.scrypt`) con sal aleatoria por usuario. Este control es de la
pantalla: quien tenga acceso a los archivos de la laptop puede leer la base
o los parquets directamente. Los usuarios y sus hashes NO se sincronizan a
Supabase (allá, si se agrega login, va Supabase Auth — ver
docs/context/8-base-de-datos-hibrida.md).

Roles: los mismos cuatro del esquema de la nube (db/schema_cloud.sql).
El primer admin se crea por consola (scripts/usuarios.py); después el admin
administra el resto desde la vista "Usuarios" del dashboard.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "db" / "analizador.sqlite"

ROLES = {
    "admin": "Administrador",
    "analyst": "Analista",
    "coach": "Cuerpo técnico",
    "viewer": "Solo lectura",
}

# Qué puede hacer cada rol. Ver el dashboard (Mesa táctica, Jugadores,
# Patrones) lo puede cualquier usuario activo.
PERMISOS = {
    "admin":   {"taguear", "gestionar_partido", "gestionar_plantel", "calificar_semaforo",
                "ver_semaforo", "administrar_usuarios"},
    "analyst": {"taguear", "gestionar_partido", "gestionar_plantel", "ver_semaforo"},
    "coach":   {"calificar_semaforo", "ver_semaforo"},
    "viewer":  {"ver_semaforo"},
}

MIN_LARGO_CONTRASENA = 8

# scrypt: N=2^14, r=8, p=1 (~16 MB, decenas de ms por intento en una laptop).
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}


def puede(rol: str | None, permiso: str) -> bool:
    return permiso in PERMISOS.get(rol or "", set())


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_usuarios_table() -> None:
    conn = _connect()
    try:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS usuarios (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario         TEXT NOT NULL UNIQUE COLLATE NOCASE,
                nombre          TEXT NOT NULL,
                rol             TEXT NOT NULL CHECK (rol IN ({", ".join(repr(r) for r in ROLES)})),
                hash_contrasena TEXT NOT NULL,
                activo          INTEGER NOT NULL DEFAULT 1,
                created_at      TEXT NOT NULL,
                ultimo_ingreso  TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


# ── Contraseñas ─────────────────────────────────────────────
def _hashear(contrasena: str, sal: bytes | None = None) -> str:
    sal = sal or os.urandom(16)
    h = hashlib.scrypt(contrasena.encode("utf-8"), salt=sal, **_SCRYPT)
    return "scrypt${n}${r}${p}${sal}${h}".format(
        n=_SCRYPT["n"], r=_SCRYPT["r"], p=_SCRYPT["p"],
        sal=base64.b64encode(sal).decode(), h=base64.b64encode(h).decode())


def _coincide(contrasena: str, guardado: str) -> bool:
    try:
        _, n, r, p, sal, h = guardado.split("$")
        calculado = hashlib.scrypt(contrasena.encode("utf-8"), salt=base64.b64decode(sal),
                                   n=int(n), r=int(r), p=int(p), dklen=len(base64.b64decode(h)))
        return hmac.compare_digest(calculado, base64.b64decode(h))
    except (ValueError, TypeError):
        return False


def validar_contrasena(contrasena: str) -> str | None:
    """Mensaje de error si la contraseña no sirve, o None si está bien."""
    if len(contrasena) < MIN_LARGO_CONTRASENA:
        return f"La contraseña tiene que tener al menos {MIN_LARGO_CONTRASENA} caracteres."
    return None


# ── Usuarios ────────────────────────────────────────────────
def _publico(row: sqlite3.Row | None) -> dict | None:
    """Datos del usuario sin el hash de la contraseña."""
    if row is None:
        return None
    d = dict(row)
    d.pop("hash_contrasena", None)
    d["activo"] = bool(d["activo"])
    return d


def crear_usuario(usuario: str, nombre: str, rol: str, contrasena: str) -> dict:
    usuario = usuario.strip()
    if not usuario or not nombre.strip():
        raise ValueError("Usuario y nombre son obligatorios.")
    if rol not in ROLES:
        raise ValueError(f"Rol desconocido: {rol}")
    error = validar_contrasena(contrasena)
    if error:
        raise ValueError(error)
    conn = _connect()
    try:
        try:
            conn.execute(
                "INSERT INTO usuarios (usuario, nombre, rol, hash_contrasena, created_at) VALUES (?, ?, ?, ?, ?)",
                (usuario, nombre.strip(), rol, _hashear(contrasena), datetime.now().isoformat(timespec="seconds")))
        except sqlite3.IntegrityError:
            raise ValueError(f"Ya existe el usuario '{usuario}'.") from None
        conn.commit()
        return _publico(conn.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,)).fetchone())
    finally:
        conn.close()


def verificar(usuario: str, contrasena: str) -> dict | None:
    """El usuario si la contraseña es correcta y está activo; None si no.
    Registra el último ingreso."""
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario.strip(),)).fetchone()
        if row is None:
            _coincide(contrasena, _hashear("relleno"))   # mismo costo que un usuario real
            return None
        if not _coincide(contrasena, row["hash_contrasena"]) or not row["activo"]:
            return None
        conn.execute("UPDATE usuarios SET ultimo_ingreso = ? WHERE id = ?",
                     (datetime.now().isoformat(timespec="seconds"), row["id"]))
        conn.commit()
        return _publico(conn.execute("SELECT * FROM usuarios WHERE id = ?", (row["id"],)).fetchone())
    finally:
        conn.close()


def obtener(usuario_id: int) -> dict | None:
    conn = _connect()
    try:
        return _publico(conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone())
    finally:
        conn.close()


def listar() -> list[dict]:
    conn = _connect()
    try:
        return [_publico(r) for r in conn.execute("SELECT * FROM usuarios ORDER BY activo DESC, nombre").fetchall()]
    finally:
        conn.close()


def hay_usuarios() -> bool:
    conn = _connect()
    try:
        return conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] > 0
    finally:
        conn.close()


def _admins_activos(conn: sqlite3.Connection, salvo: int | None = None) -> int:
    return conn.execute("SELECT COUNT(*) FROM usuarios WHERE rol = 'admin' AND activo = 1 AND id != ?",
                        (salvo if salvo is not None else -1,)).fetchone()[0]


def cambiar_rol(usuario_id: int, rol: str) -> None:
    if rol not in ROLES:
        raise ValueError(f"Rol desconocido: {rol}")
    conn = _connect()
    try:
        actual = conn.execute("SELECT rol, activo FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
        if actual and actual["rol"] == "admin" and rol != "admin" and actual["activo"] \
                and _admins_activos(conn, salvo=usuario_id) == 0:
            raise ValueError("Tiene que quedar al menos un administrador activo.")
        conn.execute("UPDATE usuarios SET rol = ? WHERE id = ?", (rol, usuario_id))
        conn.commit()
    finally:
        conn.close()


def cambiar_activo(usuario_id: int, activo: bool) -> None:
    conn = _connect()
    try:
        actual = conn.execute("SELECT rol, activo FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
        if actual and not activo and actual["rol"] == "admin" and actual["activo"] \
                and _admins_activos(conn, salvo=usuario_id) == 0:
            raise ValueError("Tiene que quedar al menos un administrador activo.")
        conn.execute("UPDATE usuarios SET activo = ? WHERE id = ?", (int(activo), usuario_id))
        conn.commit()
    finally:
        conn.close()


def cambiar_contrasena(usuario_id: int, contrasena: str) -> None:
    error = validar_contrasena(contrasena)
    if error:
        raise ValueError(error)
    conn = _connect()
    try:
        conn.execute("UPDATE usuarios SET hash_contrasena = ? WHERE id = ?", (_hashear(contrasena), usuario_id))
        conn.commit()
    finally:
        conn.close()


def obtener_por_usuario(usuario: str) -> dict | None:
    conn = _connect()
    try:
        return _publico(conn.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario.strip(),)).fetchone())
    finally:
        conn.close()
