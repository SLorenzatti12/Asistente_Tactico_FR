"""
Helpers de solo-lectura (+ marcado de sync) sobre la SQLite local — Nico
==========================================================================
No duplica ni reemplaza `app/components/tagging.py` (que sigue siendo dueño
de crear/leer/tagear eventos y semáforo durante el partido). Esto solo:

  1. Agrega, de forma aditiva, una columna `synced_at` a `events` y
     `semaforo` — igual patrón de migración que ya usa `tagging.init_db()`.
  2. Lee las filas todavía no sincronizadas.
  3. Marca filas como sincronizadas después de subirlas a Supabase.

Vive aparte para no tocar tagging.py y no arriesgar conflictos con el
desarrollo en curso de ese archivo.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "db" / "analizador.sqlite"


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"No existe {DB_PATH} todavía — corré la app al menos una vez "
            "(o tagueá un evento) para que se cree."
        )
    return sqlite3.connect(DB_PATH)


def ensure_sync_columns() -> None:
    """Migración aditiva: agrega `synced_at` si no existe. Seguro de correr
    muchas veces (chequea antes de alterar)."""
    conn = _connect()
    try:
        for table in ("events", "semaforo"):
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if "synced_at" not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN synced_at TEXT")
        conn.commit()
    finally:
        conn.close()


def list_match_names() -> list[str]:
    """Todos los match_name distintos que aparecen en events, semaforo o
    con un video registrado (un partido puede tener video guardado antes
    de tener eventos/calificaciones tagueados todavía)."""
    from . import video_repo
    video_repo.init_video_table()

    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT DISTINCT match_name FROM events "
            "UNION SELECT DISTINCT match_name FROM semaforo "
            "UNION SELECT DISTINCT match_name FROM match_videos"
        ).fetchall()
        return sorted({r[0] for r in rows if r[0]})
    finally:
        conn.close()


def get_unsynced_events(match_name: str) -> list[dict]:
    conn = _connect()
    try:
        conn.row_factory = sqlite3.Row
        cols = {row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()}
        team_col = "team" if "team" in cols else "NULL as team"
        rows = conn.execute(
            f"SELECT id, match_name, tag_type, time_sec, {team_col}, created_at "
            "FROM events WHERE match_name = ? AND synced_at IS NULL",
            (match_name,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_unsynced_ratings(match_name: str) -> list[dict]:
    conn = _connect()
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, match_name, player_number, rating, created_at "
            "FROM semaforo WHERE match_name = ? AND synced_at IS NULL",
            (match_name,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_events_synced(event_ids: list[int], synced_at: str) -> None:
    if not event_ids:
        return
    conn = _connect()
    try:
        conn.executemany(
            "UPDATE events SET synced_at = ? WHERE id = ?",
            [(synced_at, eid) for eid in event_ids],
        )
        conn.commit()
    finally:
        conn.close()


def mark_ratings_synced(rating_ids: list[int], synced_at: str) -> None:
    if not rating_ids:
        return
    conn = _connect()
    try:
        conn.executemany(
            "UPDATE semaforo SET synced_at = ? WHERE id = ?",
            [(synced_at, rid) for rid in rating_ids],
        )
        conn.commit()
    finally:
        conn.close()
