"""
Registro local de la ruta del video del partido — Nico
=========================================================
La app ya arma la ruta del video crudo por convención
(`data/videos/<match_name>.mp4`, ver `match_selector()` en app/main.py).
Esta tabla la hace explícita y persistente en SQLite, para dos cosas que
la convención sola no resuelve:

  1. Que la ruta quede guardada aunque el archivo no respete esa
     convención de nombre (video renombrado, guardado en otro disco, etc).
  2. Que scripts/sync_to_cloud.py sepa qué archivo subir a Supabase
     Storage y lo marque como sincronizado, con el mismo patrón de
     `synced_at` que roster/events/semaforo (ver src/db/sync.py).

Nunca guarda el video en sí acá — solo la ruta local y, después de
subirlo, la ubicación del archivo en Supabase Storage.
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


def init_video_table() -> None:
    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS match_videos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                match_name  TEXT NOT NULL UNIQUE,
                local_path  TEXT NOT NULL,
                storage_url TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                synced_at   TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


def set_video_path(match_name: str, local_path: str) -> None:
    """Alta o edición de la ruta local del video de un partido. Si la ruta
    cambia respecto de lo guardado, se limpia `synced_at` para que el
    próximo sync vuelva a subir el archivo correcto."""
    conn = _connect()
    try:
        existing = conn.execute(
            "SELECT local_path FROM match_videos WHERE match_name = ?", (match_name,)
        ).fetchone()
        now = datetime.now().isoformat()
        if existing is None:
            conn.execute(
                "INSERT INTO match_videos (match_name, local_path, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (match_name, local_path, now, now),
            )
        elif existing["local_path"] != local_path:
            conn.execute(
                "UPDATE match_videos SET local_path = ?, updated_at = ?, "
                "synced_at = NULL WHERE match_name = ?",
                (local_path, now, match_name),
            )
        conn.commit()
    finally:
        conn.close()


def get_video(match_name: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM match_videos WHERE match_name = ?", (match_name,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_unsynced() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM match_videos WHERE synced_at IS NULL"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_synced(match_name: str, storage_path: str, synced_at: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE match_videos SET storage_url = ?, synced_at = ? WHERE match_name = ?",
            (storage_path, synced_at, match_name),
        )
        conn.commit()
    finally:
        conn.close()
