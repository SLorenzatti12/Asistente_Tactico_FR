"""
Equipos/categorías y qué equipo jugó cada partido — Nico
============================================================
Soporta más de un plantel independiente en la misma app (ej. Primera,
Reserva) — cada equipo tiene su propio roster (ver src/db/roster_repo.py,
que ahora cuelga de `team_id`). `match_team` recuerda, por partido, qué
equipo le corresponde, para no tener que volver a elegirlo cada vez que
se reabre el partido en la app.
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


def init_teams_table() -> None:
    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS match_team (
                match_name TEXT PRIMARY KEY,
                team_id    INTEGER NOT NULL REFERENCES teams(id)
            )
        """)
        conn.commit()
    finally:
        conn.close()


def create_team(name: str) -> int:
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO teams (name, created_at) VALUES (?, ?)",
            (name.strip(), datetime.now().isoformat()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_teams() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM teams ORDER BY name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def set_match_team(match_name: str, team_id: int) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO match_team (match_name, team_id) VALUES (?, ?) "
            "ON CONFLICT(match_name) DO UPDATE SET team_id = excluded.team_id",
            (match_name, team_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_match_team(match_name: str) -> dict | None:
    """Devuelve {"team_id", "team_name"} del equipo asignado a este
    partido, o None si todavía no se asignó ninguno."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT t.id AS team_id, t.name AS team_name "
            "FROM match_team mt JOIN teams t ON t.id = mt.team_id "
            "WHERE mt.match_name = ?",
            (match_name,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
