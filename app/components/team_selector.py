"""
Analizador Táctico — Asignación de equipo/categoría por partido
==================================================
Nico — el sistema soporta más de un plantel independiente (ej. Primera,
Reserva). Este componente deja elegir o crear el equipo que jugó el
partido actual, y lo recuerda (tabla local `match_team`, ver
src/db/team_repo.py) para no tener que reelegirlo cada vez que se reabre
el partido. El plantel (roster_view.py) y el semáforo (tagging.py) usan
el `team_id` que devuelve esta función.
"""
import sys
from pathlib import Path

import streamlit as st

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from db import team_repo as repo  # noqa: E402


def render_team_selector(match_name: str) -> dict | None:
    """Muestra el selector de equipo/categoría para `match_name` y
    devuelve {"team_id", "team_name"} del equipo asignado, o None si
    todavía no se asignó ninguno."""
    repo.init_teams_table()

    equipos = repo.list_teams()
    asignado = repo.get_match_team(match_name)

    nombres = [t["name"] for t in equipos]
    idx = nombres.index(asignado["team_name"]) if asignado and asignado["team_name"] in nombres else None

    col_sel, col_new = st.columns([2, 1])
    with col_sel:
        elegido = st.selectbox(
            "Equipo / categoría de este partido",
            nombres,
            index=idx,
            placeholder="Elegí un equipo...",
            key=f"team_select_{match_name}",
        ) if nombres else None
        if elegido and (asignado is None or asignado["team_name"] != elegido):
            team_id = next(t["id"] for t in equipos if t["name"] == elegido)
            repo.set_match_team(match_name, team_id)
            st.rerun()

    with col_new:
        with st.popover("➕ Nuevo equipo", use_container_width=True):
            nuevo_nombre = st.text_input("Nombre del equipo", key=f"new_team_name_{match_name}")
            if st.button("Crear y asignar", key=f"create_team_{match_name}"):
                if not nuevo_nombre.strip():
                    st.warning("Ingresá un nombre.")
                elif nuevo_nombre.strip() in nombres:
                    st.warning("Ya existe un equipo con ese nombre.")
                else:
                    team_id = repo.create_team(nuevo_nombre)
                    repo.set_match_team(match_name, team_id)
                    st.rerun()

    return repo.get_match_team(match_name)
