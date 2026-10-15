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
— decisión explícita, no hay soft delete acá).
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
        conn.commit()
    finally:
        conn.close()


def add_player(team_id: int, full_name: str, jersey_number: int | None) -> int:
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO roster (team_id, jersey_number, full_name, created_at) "
            "VALUES (?, ?, ?, ?)",
            (team_id, jersey_number, full_name.strip(), datetime.now().isoformat()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_player(player_id: int, full_name: str, jersey_number: int | None) -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE roster SET full_name = ?, jersey_number = ?, synced_at = NULL WHERE id = ?",
            (full_name.strip(), jersey_number, player_id),
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
            "ORDER BY jersey_number IS NULL, jersey_number ASC, full_name ASC",
            (team_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_players(team_id: int) -> list[dict]:
    """Forma reducida {"number", "name"} — la que ya consume tagging.load_roster()."""
    return [
        {"number": p["jersey_number"], "name": p["full_name"]}
        for p in list_players_raw(team_id)
    ]
