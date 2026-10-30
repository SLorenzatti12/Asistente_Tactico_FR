"""
Revisión de los "momentos para revisar" por el cuerpo técnico
================================================================
Santi (27/10/2026). Cada momento que detecta src/analysis/tactical_patterns.py
lo puede calificar alguien del club después de mirarlo en el video:

- **util**: es lo que el club busca marcar.
- **correcto**: se ve, pero es tácticamente correcto (desmarque, marca
  personal, basculación): no es un problema.
- **no_se_ve**: en el video no se ve lo que dice el sistema (error de
  tracking, de calibración, de equipo…).

Más un comentario opcional. Es la evidencia para ajustar los criterios de
cada patrón con datos del club, no a ojo (ver decisiones.md, "Criterios
propios del club para los patrones").

La tabla solo agrega filas: vale la última revisión de cada momento
(partido, patrón, track) y queda el historial. Cada fila guarda además el
valor medido, la severidad, el comienzo del primer tramo y los criterios con
que se calculó el momento: si después se cambia un criterio o se reprocesa
el video (los números de track cambian, ver decisiones.md, caso 626 → 587),
la revisión sigue diciendo sobre qué se opinó.

Además, cada tramo de un momento se puede calificar aparte (tabla
`patrones_revision_tramos`, 30/10/2026): en un mismo momento puede haber
tramos que son un error y otros donde la posición es correcta (track 931 de
sportivo_crop3). Es opcional y no reemplaza la calificación del momento.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "db" / "analizador.sqlite"

VEREDICTOS = {
    "util": "Útil",
    "correcto": "Correcto tácticamente",
    "no_se_ve": "No se ve en el video",
}


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_revision_table() -> None:
    opciones = ", ".join(repr(v) for v in VEREDICTOS)
    conn = _connect()
    try:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS patrones_revision (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                match_name     TEXT NOT NULL,
                patron         TEXT NOT NULL,
                track_id       INTEGER NOT NULL,
                team           TEXT,
                t_inicio       REAL,
                valor_tecnico  REAL,
                severidad      REAL,
                veredicto      TEXT CHECK (veredicto IS NULL OR veredicto IN ({opciones})),
                comentario     TEXT,
                criterios      TEXT,
                created_by     TEXT,
                created_at     TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS patrones_revision_momento "
                     "ON patrones_revision (match_name, patron, track_id)")
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS patrones_revision_tramos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                match_name  TEXT NOT NULL,
                patron      TEXT NOT NULL,
                track_id    INTEGER NOT NULL,
                t_ini       REAL NOT NULL,
                t_fin       REAL NOT NULL,
                veredicto   TEXT CHECK (veredicto IS NULL OR veredicto IN ({opciones})),
                criterios   TEXT,
                created_by  TEXT,
                created_at  TEXT NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def guardar(match_name: str, momento: dict, veredicto: str | None, comentario: str | None,
            criterios: dict | None, usuario: str | None) -> None:
    """`momento`: una fila de detectar_patrones (patron, track_id, team,
    evidencia_seg, valor_tecnico, severidad). `veredicto` None = sin
    calificar (por ejemplo, solo un comentario, o se sacó la calificación)."""
    if veredicto is not None and veredicto not in VEREDICTOS:
        raise ValueError(f"Veredicto desconocido: {veredicto}")
    evidencia = momento.get("evidencia_seg") or []
    init_revision_table()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO patrones_revision (match_name, patron, track_id, team, t_inicio, valor_tecnico, severidad, "
            "veredicto, comentario, criterios, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (match_name, momento["patron"], int(momento["track_id"]), momento.get("team"),
             float(evidencia[0][0]) if len(evidencia) else None,
             float(momento["valor_tecnico"]) if momento.get("valor_tecnico") is not None else None,
             float(momento["severidad"]) if momento.get("severidad") is not None else None,
             veredicto, (comentario or "").strip() or None,
             json.dumps(criterios, sort_keys=True) if criterios else None,
             usuario, datetime.now().isoformat(timespec="seconds")))
        conn.commit()
    finally:
        conn.close()


def _vigentes(conn: sqlite3.Connection, match_name: str | None = None) -> list[dict]:
    filtro, params = ("WHERE match_name = ?", (match_name,)) if match_name else ("", ())
    filas = conn.execute(
        f"SELECT * FROM patrones_revision {filtro} ORDER BY id", params).fetchall()
    ultimas: dict = {}
    for f in filas:
        ultimas[(f["match_name"], f["patron"], f["track_id"])] = dict(f)
    return list(ultimas.values())


def vigentes(match_name: str) -> dict[tuple[str, int], dict]:
    """La última revisión de cada momento del partido: {(patron, track_id): fila}."""
    init_revision_table()
    conn = _connect()
    try:
        return {(f["patron"], f["track_id"]): f for f in _vigentes(conn, match_name)}
    finally:
        conn.close()


def resumen_por_patron() -> dict[str, dict]:
    """En todos los partidos, cuántos momentos de cada patrón están
    calificados con cada veredicto (la última revisión de cada uno)."""
    init_revision_table()
    conn = _connect()
    try:
        out: dict[str, dict] = {}
        for f in _vigentes(conn):
            if f["veredicto"] is None:
                continue
            fila = out.setdefault(f["patron"], {v: 0 for v in VEREDICTOS})
            fila[f["veredicto"]] += 1
        return out
    finally:
        conn.close()


def con_comentario(limite: int = 100) -> list[dict]:
    """Las revisiones vigentes que tienen comentario, de la más nueva a la más vieja."""
    init_revision_table()
    conn = _connect()
    try:
        filas = [f for f in _vigentes(conn) if f["comentario"]]
        return sorted(filas, key=lambda f: f["created_at"], reverse=True)[:limite]
    finally:
        conn.close()


def guardar_tramo(match_name: str, patron: str, track_id: int, t_ini: float, t_fin: float,
                  veredicto: str | None, criterios: dict | None, usuario: str | None) -> None:
    """`veredicto` None = se sacó la calificación del tramo."""
    if veredicto is not None and veredicto not in VEREDICTOS:
        raise ValueError(f"Veredicto desconocido: {veredicto}")
    init_revision_table()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO patrones_revision_tramos (match_name, patron, track_id, t_ini, t_fin, veredicto, "
            "criterios, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (match_name, patron, int(track_id), float(t_ini), float(t_fin), veredicto,
             json.dumps(criterios, sort_keys=True) if criterios else None,
             usuario, datetime.now().isoformat(timespec="seconds")))
        conn.commit()
    finally:
        conn.close()


def clave_tramo(patron: str, track_id: int, t_ini: float) -> tuple[str, int, float]:
    """Un tramo se identifica por su comienzo, redondeado a la décima."""
    return patron, int(track_id), round(float(t_ini), 1)


def _tramos_vigentes(conn: sqlite3.Connection, match_name: str | None = None) -> list[dict]:
    filtro, params = ("WHERE match_name = ?", (match_name,)) if match_name else ("", ())
    filas = conn.execute(
        f"SELECT * FROM patrones_revision_tramos {filtro} ORDER BY id", params).fetchall()
    ultimas: dict = {}
    for f in filas:
        ultimas[(f["match_name"], *clave_tramo(f["patron"], f["track_id"], f["t_ini"]))] = dict(f)
    return list(ultimas.values())


def tramos_vigentes(match_name: str) -> dict[tuple[str, int, float], dict]:
    """La última calificación de cada tramo del partido: {clave_tramo: fila}."""
    init_revision_table()
    conn = _connect()
    try:
        return {clave_tramo(f["patron"], f["track_id"], f["t_ini"]): f for f in _tramos_vigentes(conn, match_name)}
    finally:
        conn.close()


def resumen_tramos_por_patron() -> dict[str, dict]:
    """Como resumen_por_patron(), contando tramos en vez de momentos."""
    init_revision_table()
    conn = _connect()
    try:
        out: dict[str, dict] = {}
        for f in _tramos_vigentes(conn):
            if f["veredicto"] is None:
                continue
            fila = out.setdefault(f["patron"], {v: 0 for v in VEREDICTOS})
            fila[f["veredicto"]] += 1
        return out
    finally:
        conn.close()
