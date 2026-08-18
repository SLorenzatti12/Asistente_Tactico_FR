"""
Analizador Táctico — Tagueo, Semáforo y persistencia
========================================================
PERSONA C — Botones de tagueo one-click, log de eventos, formulario
de semáforo post-partido, y guardado en SQLite.
"""

import streamlit as st
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "db" / "analizador.sqlite"

TAG_TYPES = ["Presión", "Salida", "Transición", "Pelota parada"]


# ── Base de datos ─────────────────────────────────────────────
def init_db() -> None:
    """
    Crea las tablas si no existen. Llamar una vez al arrancar la app
    (por ejemplo, desde main.py en init_state(), o acá mismo con un
    chequeo de "si no existe el archivo").

    TODO Persona C:
      - Revisar si conviene una tabla por partido o una columna match_name
      - Agregar índices si el volumen de tags crece mucho
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_name TEXT,
            tag_type TEXT,
            time_sec REAL,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS semaforo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_name TEXT,
            player_number INTEGER,
            rating TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_event(match_name: str, tag_type: str, time_sec: float) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO events (match_name, tag_type, time_sec, created_at) VALUES (?, ?, ?, ?)",
        (match_name, tag_type, time_sec, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def save_semaforo(match_name: str, player_number: int, rating: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO semaforo (match_name, player_number, rating, created_at) VALUES (?, ?, ?, ?)",
        (match_name, player_number, rating, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


# ── Componentes de UI ──────────────────────────────────────────
def render_tagging_panel() -> None:
    """
    Botones de tagueo one-click. Cada clic guarda un evento en SQLite
    con el tiempo actual del video.

    TODO Persona C:
      - Conectar el tiempo real del video (st.session_state["current_time"])
        en vez de un placeholder
      - Mostrar el log de eventos ya cargados (leer de la tabla `events`)
      - Considerar deshacer el último tag (botón "deshacer")
    """
    st.markdown("**Tagueo one-click**")

    match_name = st.session_state.get("selected_match", "sin_partido")
    current_time = st.session_state.get("current_time", 0)

    cols = st.columns(2)
    for i, tag in enumerate(TAG_TYPES):
        if cols[i % 2].button(tag, use_container_width=True):
            save_event(match_name, tag, current_time)
            st.toast(f"Tag guardado: {tag} @ {current_time}s")

    # TODO: reemplazar por lectura real de la tabla `events`
    st.caption("Log de eventos — placeholder, conectar a SQLite")


def render_semaforo_tab(match_name: str) -> None:
    """
    Formulario de calificación individual post-partido (🔴🟡🟢 por jugador).

    TODO Persona C:
      - Traer la lista real de jugadores (por ahora, números de ejemplo)
      - Guardar en SQLite al hacer clic
      - Mostrar resumen de calificaciones ya guardadas para este partido
    """
    st.markdown("**Semáforo post-partido**")
    st.caption("Calificación individual — hacé clic para evaluar a cada jugador.")

    # Placeholder — reemplazar por la nómina real del equipo
    example_numbers = list(range(1, 12))

    for n in example_numbers:
        col_num, col_btns = st.columns([1, 3])
        col_num.write(f"**#{n}**")
        b1, b2, b3 = col_btns.columns(3)
        if b1.button("🔴", key=f"low_{n}"):
            save_semaforo(match_name, n, "bajo")
        if b2.button("🟡", key=f"mid_{n}"):
            save_semaforo(match_name, n, "regular")
        if b3.button("🟢", key=f"high_{n}"):
            save_semaforo(match_name, n, "destacado")