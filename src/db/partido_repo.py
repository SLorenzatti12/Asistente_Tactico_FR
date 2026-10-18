"""
Partidos y sus tiempos — un video por tiempo
==============================================
La unidad de procesamiento sigue siendo UN VIDEO = UN TIEMPO: cada uno tiene
su parquet, su calibración, su verificación de cámara, su dirección de
ataque y su asignación de equipos. Esta tabla los agrupa:

    partido_tiempos: match_name (el nombre del video, como en el resto de
                     las tablas) → partido, tiempo (1 o 2)

Así las tablas existentes, que identifican el partido por el nombre del
video (match_team, match_estadio, match_videos, events, semaforo), no
cambian. El equipo y el estadio se asignan una vez al partido y se copian a
sus dos tiempos (scripts/partidos.py). Pendiente para Luci: el semáforo
debería ir por partido, no por video. Pendiente para Nico: sincronizar esta
tabla con Supabase.
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


def init_partidos_table() -> None:
    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS partido_tiempos (
                match_name TEXT PRIMARY KEY,
                partido    TEXT NOT NULL,
                tiempo     INTEGER NOT NULL CHECK (tiempo IN (1, 2)),
                created_at TEXT NOT NULL,
                UNIQUE (partido, tiempo)
            )
        """)
        conn.commit()
    finally:
        conn.close()


def set_tiempo(match_name: str, partido: str, tiempo: int) -> None:
    """Asigna el video `match_name` como tiempo `tiempo` (1 o 2) de `partido`."""
    if tiempo not in (1, 2):
        raise ValueError("El tiempo tiene que ser 1 o 2")
    conn = _connect()
    try:
        conn.execute("DELETE FROM partido_tiempos WHERE partido = ? AND tiempo = ? AND match_name != ?",
                     (partido, tiempo, match_name))
        conn.execute(
            "INSERT INTO partido_tiempos (match_name, partido, tiempo, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(match_name) DO UPDATE SET partido = excluded.partido, tiempo = excluded.tiempo",
            (match_name, partido.strip(), tiempo, datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def get_tiempo(match_name: str) -> dict | None:
    """{"match_name", "partido", "tiempo"} de este video, o None si no pertenece a un partido."""
    conn = _connect()
    try:
        row = conn.execute("SELECT match_name, partido, tiempo FROM partido_tiempos WHERE match_name = ?",
                           (match_name,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def tiempos_de(partido: str) -> list[dict]:
    """Los videos del partido, ordenados por tiempo."""
    conn = _connect()
    try:
        rows = conn.execute("SELECT match_name, partido, tiempo FROM partido_tiempos WHERE partido = ? "
                            "ORDER BY tiempo", (partido,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_partidos() -> dict[str, list[dict]]:
    """{partido: [tiempos ordenados]}."""
    conn = _connect()
    try:
        rows = conn.execute("SELECT match_name, partido, tiempo FROM partido_tiempos ORDER BY partido, tiempo").fetchall()
    finally:
        conn.close()
    partidos: dict[str, list[dict]] = {}
    for r in rows:
        partidos.setdefault(r["partido"], []).append(dict(r))
    return partidos


def otro_tiempo(match_name: str) -> dict | None:
    """El otro tiempo del mismo partido que `match_name`, si está registrado."""
    propio = get_tiempo(match_name)
    if propio is None:
        return None
    for t in tiempos_de(propio["partido"]):
        if t["match_name"] != match_name:
            return t
    return None
