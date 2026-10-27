"""
Registro de accesos y acciones críticas
=========================================
Santi. Quién hizo qué y cuándo: ingresos (y los fallidos), salidas,
sesiones vencidas por inactividad, altas y cambios de usuarios, respaldos
de la base, ediciones y borrados de eventos tagueados, y altas y bajas del
plantel. Quién creó cada evento y quién calificó a cada jugador queda en
la propia fila (`events.created_by`, `semaforo.created_by`), no acá. Vive en la misma SQLite local (tabla `registro`) y no se
sincroniza a la nube.

Nunca se guardan contraseñas ni hashes: solo el nombre de usuario escrito,
la acción y un detalle legible (p.ej. "rol: analyst → coach").

Los ingresos fallidos de acá son también la fuente del bloqueo por intentos
(ver usuarios_repo.verificar): se cuentan por el nombre de usuario escrito,
exista o no, para que el bloqueo no revele qué usuarios existen.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "db" / "analizador.sqlite"

ACCIONES = {
    "ingreso": "Ingreso",
    "ingreso_fallido": "Ingreso fallido",
    "ingreso_bloqueado": "Ingreso bloqueado (demasiados intentos)",
    "salida": "Salida",
    "sesion_vencida": "Sesión cerrada por inactividad",
    "usuario_creado": "Usuario creado",
    "rol_cambiado": "Rol cambiado",
    "usuario_desactivado": "Usuario desactivado",
    "usuario_activado": "Usuario activado",
    "contrasena_cambiada": "Contraseña cambiada",
    "contrasena_actual_incorrecta": "Contraseña actual incorrecta al cambiarla",
    "respaldo_creado": "Respaldo de la base creado",
    "respaldo_restaurado": "Respaldo restaurado",
    "evento_editado": "Evento tagueado editado",
    "evento_borrado": "Evento tagueado borrado",
    "plantel_alta": "Jugador agregado al plantel",
    "plantel_baja": "Jugador sacado del plantel",
    "plantel_edicion": "Jugador del plantel corregido",
    "equipo_creado": "Equipo creado",
    "funcion_cambiada": "Función en el cuerpo técnico cambiada",
}


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_registro_table() -> None:
    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS registro (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha     TEXT NOT NULL,
                actor_id  INTEGER,
                actor     TEXT NOT NULL,
                accion    TEXT NOT NULL,
                objetivo  TEXT,
                detalle   TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS registro_accion_objetivo ON registro (accion, objetivo)")
        conn.commit()
    finally:
        conn.close()


def registrar(accion: str, actor: dict | str | None = None, objetivo: str | None = None,
              detalle: str | None = None) -> None:
    """Agrega una fila. `actor` es el usuario que hace la acción (dict con id y
    usuario), un texto ("sistema") o None si viene de la consola."""
    if accion not in ACCIONES:
        raise ValueError(f"Acción desconocida: {accion}")
    if isinstance(actor, dict):
        actor_id, actor_txt = actor.get("id"), actor.get("usuario")
    else:
        actor_id, actor_txt = None, actor or "consola"
    init_registro_table()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO registro (fecha, actor_id, actor, accion, objetivo, detalle) VALUES (?, ?, ?, ?, ?, ?)",
            (_ahora(), actor_id, actor_txt, accion, objetivo, detalle))
        conn.commit()
    finally:
        conn.close()


def listar(limite: int = 200, acciones: list[str] | None = None) -> list[dict]:
    """Las últimas filas, de la más nueva a la más vieja."""
    init_registro_table()
    conn = _connect()
    try:
        if acciones:
            marcas = ", ".join("?" for _ in acciones)
            filas = conn.execute(f"SELECT * FROM registro WHERE accion IN ({marcas}) ORDER BY id DESC LIMIT ?",
                                 (*acciones, limite)).fetchall()
        else:
            filas = conn.execute("SELECT * FROM registro ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
        return [dict(f) for f in filas]
    finally:
        conn.close()


def fallidos_recientes(usuario: str, ventana_min: int) -> list[str]:
    """Fechas de los ingresos fallidos con este nombre de usuario (sin
    distinguir mayúsculas) en los últimos `ventana_min` minutos, posteriores
    al último ingreso correcto o cambio de contraseña. De la más vieja a la
    más nueva."""
    init_registro_table()
    desde = (datetime.now() - timedelta(minutes=ventana_min)).isoformat(timespec="seconds")
    conn = _connect()
    try:
        # "Posterior" por orden de inserción (id), no por fecha: la fecha va al
        # segundo y un fallido puede caer en el mismo segundo que el ingreso.
        ultimo_ok = conn.execute(
            "SELECT MAX(id) FROM registro WHERE accion IN ('ingreso', 'contrasena_cambiada') "
            "AND objetivo = ? COLLATE NOCASE", (usuario,)).fetchone()[0]
        filas = conn.execute(
            "SELECT fecha FROM registro WHERE accion = 'ingreso_fallido' AND objetivo = ? COLLATE NOCASE "
            "AND fecha >= ? AND id > ? ORDER BY id",
            (usuario, desde, ultimo_ok or 0)).fetchall()
        return [f[0] for f in filas]
    finally:
        conn.close()
