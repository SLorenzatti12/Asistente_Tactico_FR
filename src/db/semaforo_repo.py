"""
Semáforo: minutos jugados y valoración de cada jugador, por partido
=====================================================================
Santi (27/10/2026), con el OK de Luci. Reemplaza al semáforo viejo de
tagging.py (tabla `semaforo`, una fila por dorsal), que identificaba al
jugador por el número de camiseta.

Ahora:
- **El jugador es el del plantel** que carga el club (`roster.id`), no un
  dorsal ni un track. El sistema no identifica a nadie: el cuerpo técnico
  carga minutos y valoraciones a mano, sobre la lista del club.
- **Por partido, no por video:** los dos tiempos de un partido
  (`partido_tiempos`) comparten la planilla. Un video suelto es su propio
  partido.
- **Tres valoraciones por jugador**, una por función del cuerpo técnico
  (usuarios_repo.FUNCIONES: DT, ayudante de campo, coordinador), con la
  escala del semáforo: bajo / regular / destacado. Cada usuario completa
  solo la columna de su función.
- **Minutos jugados:** los carga cualquiera que califica (cuerpo técnico o
  admin).

Las dos tablas solo agregan filas: cada cambio es una fila nueva, con quién
y cuándo, y vale la última por (partido, jugador[, función]). Así queda el
historial completo. Cada fila guarda también el nombre del jugador en ese
momento, para que el historial se lea aunque el jugador después salga del
plantel (la baja del plantel es física, ver roster_repo).

Solo local por ahora: el sync a la nube de estas tablas queda pendiente
(ver docs/context/decisiones.md, "Semáforo por partido…").
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from src.db import partido_repo
from src.db.usuarios_repo import FUNCIONES

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "db" / "analizador.sqlite"

RATINGS = ("bajo", "regular", "destacado")
MAX_MINUTOS = 130   # 90 + alargue + adicionados


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_semaforo_tables() -> None:
    funciones = ", ".join(repr(f) for f in FUNCIONES)
    ratings = ", ".join(repr(r) for r in RATINGS)
    conn = _connect()
    try:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS semaforo_minutos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                partido     TEXT NOT NULL,
                player_id   INTEGER NOT NULL,
                jugador     TEXT NOT NULL,
                minutos     INTEGER CHECK (minutos IS NULL OR minutos BETWEEN 0 AND {MAX_MINUTOS}),
                created_by  TEXT,
                created_at  TEXT NOT NULL
            )
        """)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS semaforo_valoraciones (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                partido     TEXT NOT NULL,
                player_id   INTEGER NOT NULL,
                jugador     TEXT NOT NULL,
                funcion     TEXT NOT NULL CHECK (funcion IN ({funciones})),
                rating      TEXT CHECK (rating IS NULL OR rating IN ({ratings})),
                created_by  TEXT,
                created_at  TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS semaforo_minutos_partido ON semaforo_minutos (partido, player_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS semaforo_valoraciones_partido "
                     "ON semaforo_valoraciones (partido, player_id, funcion)")
        conn.commit()
    finally:
        conn.close()


def clave_partido(match_name: str) -> str:
    """El partido al que pertenece un video: el registrado en
    `partido_tiempos` si es uno de sus tiempos, o el propio video si está
    suelto."""
    tiempo = partido_repo.get_tiempo(match_name)
    return tiempo["partido"] if tiempo else match_name


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def guardar_minutos(partido: str, player_id: int, jugador: str, minutos: int | None, usuario: str | None) -> None:
    """`minutos` None borra el dato (queda la fila, con quién lo borró)."""
    if minutos is not None and not 0 <= int(minutos) <= MAX_MINUTOS:
        raise ValueError(f"Los minutos van de 0 a {MAX_MINUTOS}.")
    init_semaforo_tables()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO semaforo_minutos (partido, player_id, jugador, minutos, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (partido, player_id, jugador, None if minutos is None else int(minutos), usuario, _ahora()))
        conn.commit()
    finally:
        conn.close()


def guardar_valoracion(partido: str, player_id: int, jugador: str, funcion: str, rating: str | None,
                       usuario: str | None) -> None:
    """`rating` None borra la valoración de esa función."""
    if funcion not in FUNCIONES:
        raise ValueError(f"Función desconocida: {funcion}")
    if rating is not None and rating not in RATINGS:
        raise ValueError(f"Valoración desconocida: {rating}")
    init_semaforo_tables()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO semaforo_valoraciones (partido, player_id, jugador, funcion, rating, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (partido, player_id, jugador, funcion, rating, usuario, _ahora()))
        conn.commit()
    finally:
        conn.close()


def planilla(partido: str) -> dict[int, dict]:
    """El estado vigente del partido: {player_id: {"minutos": fila | None,
    "dt": fila | None, "ayudante": …, "coordinador": …}}. Cada fila es la
    última cargada (con `created_by` y `created_at`)."""
    init_semaforo_tables()
    conn = _connect()
    try:
        out: dict[int, dict] = {}
        for f in conn.execute("SELECT * FROM semaforo_minutos WHERE partido = ? ORDER BY id", (partido,)):
            out.setdefault(f["player_id"], {})["minutos"] = dict(f)
        for f in conn.execute("SELECT * FROM semaforo_valoraciones WHERE partido = ? ORDER BY id", (partido,)):
            out.setdefault(f["player_id"], {})[f["funcion"]] = dict(f)
        return out
    finally:
        conn.close()


def historial(partido: str, limite: int = 200) -> list[dict]:
    """Los últimos cambios del partido (minutos y valoraciones), del más nuevo
    al más viejo."""
    init_semaforo_tables()
    conn = _connect()
    try:
        filas = conn.execute(
            "SELECT created_at, created_by, jugador, 'Minutos' AS que, CAST(minutos AS TEXT) AS valor "
            "FROM semaforo_minutos WHERE partido = ? "
            "UNION ALL "
            "SELECT created_at, created_by, jugador, funcion AS que, rating AS valor "
            "FROM semaforo_valoraciones WHERE partido = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (partido, partido, limite)).fetchall()
        return [dict(f) for f in filas]
    finally:
        conn.close()
