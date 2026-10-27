"""
Analizador Táctico — Gestión de plantel (roster por equipo)
==================================================
Nico — alta/baja del plantel de un equipo. Se carga UNA SOLA VEZ por
equipo (no por partido, no hay que retipear nombres cada semana) y se
reutiliza para el tagueo y el semáforo de todos los partidos de ese
equipo — ver app/components/team_selector.py para cómo se asigna un
equipo a un partido. Persiste en SQLite local (tabla `roster`, ver
src/db/roster_repo.py) y se sincroniza a Supabase (tabla `players`) con
scripts/sync_to_cloud.py.

Se usa embebido en tagging.render_semaforo_tab (el plantel se carga ahí
para tagear las calificaciones), pero vive en su propio archivo para no
mezclar la lógica de CRUD con la de Luci en tagging.py.

Roles (27/10/2026, cambio hecho por Santi con el OK de Nico): sin el
permiso `gestionar_plantel` (cuerpo técnico, solo lectura) el plantel se ve
pero no se modifica. Además del parámetro `solo_lectura`, se vuelve a
chequear el permiso acá adentro, por si otra pantalla lo embebe sin pasarlo.
Cada alta y baja queda en el registro de accesos, con quién la hizo: son
datos personales de los jugadores (ver la sección 5.2 del informe).
"""
import sys
from pathlib import Path

import streamlit as st

# src/ es hermano de app/, no un subdirectorio — no queda en sys.path solo
# por correr `streamlit run app/main.py` (a diferencia de components/, que
# sí queda porque Streamlit agrega el directorio del script principal).
_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from db import roster_repo as repo  # noqa: E402
from components.sesion import puede, usuario_actual  # noqa: E402
# Por src.db (no db): el mismo módulo que usa sesion.py.
from src.db import registro_repo  # noqa: E402


def _render_solo_lectura(team_id: int) -> None:
    jugadores = repo.list_players_raw(team_id)
    if not jugadores:
        st.info("Todavía no hay jugadores cargados para este equipo.")
        return
    st.caption("Solo lectura: tu rol no modifica el plantel.")
    for p in jugadores:
        st.write(f"**#{p['jersey_number'] if p['jersey_number'] is not None else '-'}** {p['full_name']}")


def render_roster_manager(team_id: int, solo_lectura: bool = False) -> None:
    repo.init_roster_table()
    if solo_lectura or not puede("gestionar_plantel"):
        _render_solo_lectura(team_id)
        return

    st.caption(
        "Plantel del equipo — cargalo una sola vez acá y se reutiliza en "
        "todos los partidos de este equipo (tagueo y semáforo). Si un "
        "jugador deja el equipo, sacalo con 🗑️."
    )

    with st.form(f"form_nuevo_jugador_roster_{team_id}", clear_on_submit=True):
        c1, c2, c3 = st.columns([1, 3, 1])
        numero = c1.number_input("Dorsal", min_value=0, max_value=99, step=1, value=0)
        nombre = c2.text_input("Nombre completo")
        agregar = c3.form_submit_button("➕ Agregar", use_container_width=True)

    if agregar:
        if not nombre.strip():
            st.warning("Ingresá un nombre.")
        else:
            repo.add_player(team_id, nombre, numero or None)
            registro_repo.registrar("plantel_alta", usuario_actual(), objetivo=nombre.strip(),
                                    detalle=f"dorsal {numero or '-'} · equipo {team_id}")
            st.toast(f"Agregado al plantel: #{numero or '-'} {nombre}")
            st.rerun()

    jugadores = repo.list_players_raw(team_id)
    if not jugadores:
        st.info("Todavía no cargaste jugadores para este equipo.")
        return

    for p in jugadores:
        c1, c2, c3 = st.columns([1, 4, 1])
        c1.write(f"**#{p['jersey_number'] if p['jersey_number'] is not None else '-'}**")
        c2.write(p["full_name"])
        if c3.button("🗑️", key=f"del_roster_{p['id']}", help="Se fue del equipo"):
            repo.remove_player(p["id"])
            registro_repo.registrar("plantel_baja", usuario_actual(), objetivo=p["full_name"],
                                    detalle=f"dorsal {p['jersey_number'] if p['jersey_number'] is not None else '-'} · equipo {team_id}")
            st.toast(f"{p['full_name']} sacado del plantel")
            st.rerun()
