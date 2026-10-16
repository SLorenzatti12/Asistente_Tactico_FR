"""
Estadios (medidas de cancha) y en qué estadio se jugó cada partido
====================================================================
Las medidas de la cancha son un dato del ESTADIO, no del partido ni del
equipo: se cargan una vez por estadio y se reutilizan en todos los
partidos que se juegan ahí (un mismo equipo juega de visitante en otras
canchas, y Primera y Reserva comparten estadio). `match_estadio` recuerda,
por partido, dónde se jugó — mismo patrón que `match_team` en team_repo.py.

Quién las usa: src/homography/calibrate.py --estadio copia las medidas al
JSON de la calibración (ver src/homography/medidas_cancha.py, que explica
por qué es una copia y no una referencia). Alta/edición por consola con
scripts/estadios.py.

Columnas de marcas (áreas, círculo, penal) opcionales: NULL = reglamentaria.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "db" / "analizador.sqlite"

# Columnas de medidas (metros) — mismas claves que
# src/homography/medidas_cancha.MEDIDAS_REGLAMENTARIAS, con sufijo _m.
COLUMNAS_MEDIDAS = (
    "largo", "ancho",
    "area_grande_largo", "area_grande_ancho",
    "area_chica_largo", "area_chica_ancho",
    "radio_circulo", "distancia_penal",
)


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_estadios_table() -> None:
    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS estadios (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre              TEXT NOT NULL UNIQUE,
                largo_m             REAL NOT NULL,
                ancho_m             REAL NOT NULL,
                area_grande_largo_m REAL,
                area_grande_ancho_m REAL,
                area_chica_largo_m  REAL,
                area_chica_ancho_m  REAL,
                radio_circulo_m     REAL,
                distancia_penal_m   REAL,
                created_at          TEXT NOT NULL,
                updated_at          TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS match_estadio (
                match_name TEXT PRIMARY KEY,
                estadio_id INTEGER NOT NULL REFERENCES estadios(id)
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _a_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    d["medidas"] = medidas_de_estadio(d)
    return d


def medidas_de_estadio(estadio: dict) -> dict:
    """{"largo", "ancho", ...} en el formato de medidas_cancha.py, sin las
    marcas que quedaron en NULL (= reglamentarias), más "estadio" = nombre."""
    medidas = {c: estadio[f"{c}_m"] for c in COLUMNAS_MEDIDAS if estadio.get(f"{c}_m") is not None}
    medidas["estadio"] = estadio["nombre"]
    return medidas


def upsert_estadio(nombre: str, largo: float, ancho: float, **marcas) -> int:
    """
    Alta o edición de un estadio por nombre. `marcas` acepta las claves de
    COLUMNAS_MEDIDAS sin sufijo (p.ej. area_chica_largo=6.0); una marca no
    pasada queda NULL (reglamentaria). Devuelve el id.
    """
    desconocidas = set(marcas) - set(COLUMNAS_MEDIDAS)
    if desconocidas:
        raise ValueError(f"Medidas no reconocidas: {sorted(desconocidas)}")
    valores = {"largo": largo, "ancho": ancho, **marcas}
    columnas = [f"{c}_m" for c in COLUMNAS_MEDIDAS]
    datos = [valores.get(c) for c in COLUMNAS_MEDIDAS]
    ahora = datetime.now().isoformat()
    conn = _connect()
    try:
        conn.execute(
            f"INSERT INTO estadios (nombre, {', '.join(columnas)}, created_at, updated_at) "
            f"VALUES (?, {', '.join('?' * len(columnas))}, ?, ?) "
            f"ON CONFLICT(nombre) DO UPDATE SET "
            + ", ".join(f"{c} = excluded.{c}" for c in columnas)
            + ", updated_at = excluded.updated_at",
            (nombre.strip(), *datos, ahora, ahora),
        )
        conn.commit()
        return conn.execute("SELECT id FROM estadios WHERE nombre = ?", (nombre.strip(),)).fetchone()["id"]
    finally:
        conn.close()


def list_estadios() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM estadios ORDER BY nombre").fetchall()
        return [_a_dict(r) for r in rows]
    finally:
        conn.close()


def get_estadio(nombre: str) -> dict | None:
    conn = _connect()
    try:
        return _a_dict(conn.execute("SELECT * FROM estadios WHERE nombre = ?", (nombre.strip(),)).fetchone())
    finally:
        conn.close()


def set_match_estadio(match_name: str, estadio_id: int) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO match_estadio (match_name, estadio_id) VALUES (?, ?) "
            "ON CONFLICT(match_name) DO UPDATE SET estadio_id = excluded.estadio_id",
            (match_name, estadio_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_match_estadio(match_name: str) -> dict | None:
    """El estadio asignado a este partido (mismo formato que get_estadio),
    o None si todavía no se asignó ninguno."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT e.* FROM match_estadio me JOIN estadios e ON e.id = me.estadio_id "
            "WHERE me.match_name = ?",
            (match_name,),
        ).fetchone()
        return _a_dict(row)
    finally:
        conn.close()
