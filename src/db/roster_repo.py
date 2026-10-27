"""
Plantel de jugadores por equipo — Nico
==========================================
Reemplaza `data/roster.json` (edición manual del archivo) por una tabla
SQLite editable desde la app, y sincronizable a Supabase (tabla `players`,
ver src/db/sync.py). El plantel se carga UNA SOLA VEZ por equipo (no por
partido) y se reutiliza en todos los partidos de ese equipo — ver
src/db/team_repo.py para el vínculo partido → equipo.

La baja de un jugador es un DELETE físico (se acepta perder el vínculo
con calificaciones de semáforo de partidos viejos a cambio de simplicidad
— decisión explícita, no hay soft delete acá). Las valoraciones y minutos
guardan además el nombre del jugador en el momento de cargarlos
(src/db/semaforo_repo.py), así el historial se sigue leyendo.

Apellido y nombre por separado (27/10/2026, Santi con el OK de Nico): el
club carga su plantilla con esos dos campos; el dorsal es opcional. Se
sigue llenando `full_name` ("Nombre Apellido"), porque es lo que sube el
sync a la nube (`players.full_name`). Las filas de antes se migran
partiendo `full_name`: la última palabra es el apellido.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "db" / "analizador.sqlite"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_roster_table() -> None:
    from . import team_repo
    team_repo.init_teams_table()  # roster.team_id referencia teams(id)

    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS roster (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id       INTEGER NOT NULL REFERENCES teams(id),
                jersey_number INTEGER,
                full_name     TEXT NOT NULL,
                created_at    TEXT NOT NULL,
                synced_at     TEXT
            )
        """)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(roster)").fetchall()}
        if "apellido" not in cols:
            conn.execute("ALTER TABLE roster ADD COLUMN apellido TEXT")
            conn.execute("ALTER TABLE roster ADD COLUMN nombre TEXT")
            for row in conn.execute("SELECT id, full_name FROM roster").fetchall():
                partes = row["full_name"].split()
                conn.execute("UPDATE roster SET apellido = ?, nombre = ? WHERE id = ?",
                             (partes[-1] if partes else "", " ".join(partes[:-1]), row["id"]))
        conn.commit()
    finally:
        conn.close()


def nombre_completo(nombre: str, apellido: str) -> str:
    return " ".join(p for p in (nombre.strip(), apellido.strip()) if p)


def add_player(team_id: int, apellido: str, nombre: str, jersey_number: int | None = None) -> int:
    if not apellido.strip():
        raise ValueError("El apellido es obligatorio.")
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO roster (team_id, jersey_number, full_name, apellido, nombre, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (team_id, jersey_number, nombre_completo(nombre, apellido), apellido.strip(), nombre.strip(),
             datetime.now().isoformat()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_player(player_id: int, apellido: str, nombre: str, jersey_number: int | None) -> None:
    if not apellido.strip():
        raise ValueError("El apellido es obligatorio.")
    conn = _connect()
    try:
        conn.execute(
            "UPDATE roster SET full_name = ?, apellido = ?, nombre = ?, jersey_number = ?, synced_at = NULL "
            "WHERE id = ?",
            (nombre_completo(nombre, apellido), apellido.strip(), nombre.strip(), jersey_number, player_id),
        )
        conn.commit()
    finally:
        conn.close()


def remove_player(player_id: int) -> None:
    """Baja del plantel (se fue del equipo) — DELETE físico. La próxima
    vez que se corra el sync, esta baja se replica en Supabase (ver
    sync_roster_for_team en src/db/sync.py, que hace un mirror completo
    del plantel local)."""
    conn = _connect()
    try:
        conn.execute("DELETE FROM roster WHERE id = ?", (player_id,))
        conn.commit()
    finally:
        conn.close()


def list_players_raw(team_id: int) -> list[dict]:
    """Filas completas (id, synced_at incluidos) — para la UI de gestión y el sync."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM roster WHERE team_id = ? "
            "ORDER BY apellido COLLATE NOCASE, nombre COLLATE NOCASE",
            (team_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
