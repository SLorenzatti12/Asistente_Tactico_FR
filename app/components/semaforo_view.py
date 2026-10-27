"""
Analizador Táctico — Semáforo: planilla del partido y plantel
================================================================
Santi (27/10/2026), con el OK de Luci (reemplaza la pestaña de semáforo de
tagging.py). Dos subvistas:

- **Planilla del partido:** una fila por jugador del plantel del equipo
  (cargado por el club, ver roster_view.py), con los minutos jugados y la
  valoración 🔴🟡🟢 de cada función del cuerpo técnico: DT, ayudante de
  campo y coordinador. Nada sale del video ni de los tracks: lo carga el
  cuerpo técnico.
  - Minutos: cualquiera con permiso de calificar (cuerpo técnico, admin).
  - Valoración: cada usuario solo su columna, la de su función
    (usuarios_repo.FUNCIONES, la asigna el admin en la vista Usuarios). Las
    otras columnas las ve.
  - Cada cambio se guarda al momento (src/db/semaforo_repo.py), con quién y
    cuándo; al pasar el mouse por una valoración se ve quién la puso.
  - Es por partido: los dos tiempos de un partido comparten la planilla.
- **Plantel:** el del equipo, con alta, corrección, baja e importación
  desde CSV (roster_view.render_plantel).
"""
import sys
from pathlib import Path

import html

import pandas as pd
import streamlit as st

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from components.roster_view import render_plantel  # noqa: E402
from components.sesion import puede, usuario_actual  # noqa: E402
from src.db import roster_repo, semaforo_repo, team_repo  # noqa: E402
from src.db.usuarios_repo import FUNCIONES  # noqa: E402

ICONO = {"bajo": "🔴", "regular": "🟡", "destacado": "🟢"}
# Valoraciones de otra función y minutos que no se pueden editar: etiquetas
# de solo lectura, legibles (un control deshabilitado apenas se distingue).
_ESTILOS = """<style>
.sem-chip { display:inline-flex; align-items:center; gap:6px; padding:5px 10px; border-radius:999px;
            font-size:0.85rem; border:1px solid var(--at-line, #242a35); white-space:nowrap; }
.sem-chip.bajo { background: rgba(239,68,68,.14); border-color: rgba(239,68,68,.45); }
.sem-chip.regular { background: rgba(234,179,8,.14); border-color: rgba(234,179,8,.45); }
.sem-chip.destacado { background: rgba(34,197,94,.14); border-color: rgba(34,197,94,.45); }
.sem-chip.vacio { opacity:.55; }
.sem-min { font-variant-numeric: tabular-nums; font-weight:600; }
</style>"""
_SUBVISTAS = {"planilla": ":material/assignment: Planilla del partido", "plantel": ":material/groups: Plantel"}
_FUNCION_CORTA = {"dt": "DT", "ayudante": "Ayudante", "coordinador": "Coordinador"}


def _fecha(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]} {iso[11:16]}"


def _al_cambiar_minutos(clave: str, partido: str, player_id: int, jugador: str) -> None:
    valor = st.session_state.get(clave)
    usuario = usuario_actual()
    semaforo_repo.guardar_minutos(partido, player_id, jugador, None if valor is None else int(valor),
                                  usuario["usuario"] if usuario else None)


def _al_cambiar_valoracion(clave: str, partido: str, player_id: int, jugador: str, funcion: str) -> None:
    usuario = usuario_actual()
    # Se vuelve a chequear acá: solo la función propia, y solo quien califica.
    if usuario is None or usuario.get("funcion") != funcion or not puede("calificar_semaforo"):
        return
    semaforo_repo.guardar_valoracion(partido, player_id, jugador, funcion, st.session_state.get(clave),
                                     usuario["usuario"])


def _chip(fila: dict | None) -> str:
    """Etiqueta de solo lectura de una valoración, con quién y cuándo en el
    tooltip."""
    if not fila or not fila["rating"]:
        return "<span class='sem-chip vacio'>Sin valorar</span>"
    titulo = html.escape(f"{fila['created_by'] or 'sin dato'} · {_fecha(fila['created_at'])}")
    return (f"<span class='sem-chip {fila['rating']}' title='{titulo}'>"
            f"{ICONO[fila['rating']]} {fila['rating'].capitalize()}</span>")


def _explicacion(usuario: dict, puede_minutos: bool, mi_funcion: str | None) -> str:
    if mi_funcion and puede_minutos:
        return (f"Sos **{FUNCIONES[mi_funcion]}**: completás la columna {_FUNCION_CORTA[mi_funcion]} y los minutos. "
                "Las otras columnas las ves. Cada cambio se guarda al momento.")
    if puede_minutos:
        return ("Cargás los minutos. Para valorar, el administrador te tiene que asignar una función "
                "(DT, ayudante de campo o coordinador) en la vista Usuarios.")
    return "Solo lectura: tu rol no carga minutos ni valoraciones."


def _planilla(match_name: str, equipo: dict | None) -> None:
    usuario = usuario_actual() or {}
    partido = semaforo_repo.clave_partido(match_name)
    puede_minutos = puede("calificar_semaforo")
    mi_funcion = usuario.get("funcion") if puede_minutos else None

    st.markdown(f"**Planilla del partido** · {partido}" + (f" · {equipo['team_name']}" if equipo else ""))
    if partido != match_name:
        st.caption("Partido de dos tiempos: la planilla es una sola para los dos.")
    if equipo is None:
        st.info("Este partido todavía no tiene equipo asignado. Asignalo en «Partido» (arriba a la derecha) "
                "para usar el plantel de ese equipo.")
        return
    jugadores = roster_repo.list_players_raw(equipo["team_id"])
    if not jugadores:
        st.info(f"Todavía no hay plantel cargado para {equipo['team_name']}. Cargalo en «Plantel».")
        return
    st.caption(_explicacion(usuario, puede_minutos, mi_funcion))

    estado = semaforo_repo.planilla(partido)
    st.html(_ESTILOS)

    def cargados(campo: str) -> int:
        return sum(1 for j in jugadores
                   if (f := estado.get(j["id"], {}).get(campo)) and f.get("minutos" if campo == "minutos" else "rating")
                   is not None)
    st.caption(" · ".join([f"Minutos **{cargados('minutos')}/{len(jugadores)}**"]
                          + [f"{_FUNCION_CORTA[f]} **{cargados(f)}/{len(jugadores)}**" for f in FUNCIONES]))

    anchos = [2.4, 1.1, 1.5, 1.5, 1.5]
    with st.container(border=True, key="planilla_semaforo"):
        cab = st.columns(anchos, vertical_alignment="bottom")
        cab[0].markdown("**Jugador**")
        cab[1].markdown("**Minutos**")
        for col, f in zip(cab[2:], FUNCIONES):
            col.markdown(f"**{_FUNCION_CORTA[f]}**" + (" · vos" if f == mi_funcion else ""))
        for j in jugadores:
            pid, nombre = j["id"], j["full_name"]
            fila = estado.get(pid, {})
            cols = st.columns(anchos, vertical_alignment="center")
            dorsal = f" · #{j['jersey_number']}" if j["jersey_number"] is not None else ""
            nombre_pila = f", {j['nombre']}" if j.get("nombre") else ""
            cols[0].markdown(f"**{html.escape(j.get('apellido') or nombre)}**{html.escape(nombre_pila)}"
                             f"<span style='opacity:.6'>{dorsal}</span>", unsafe_allow_html=True)

            minutos = fila.get("minutos")
            clave_min = f"sem_min_{partido}_{pid}"
            if not puede_minutos:
                valor = minutos["minutos"] if minutos else None
                cols[1].markdown(f"<span class='sem-min'>{valor}'</span>" if valor is not None
                                 else "<span class='sem-chip vacio'>—</span>", unsafe_allow_html=True)
            else:
                cols[1].number_input(
                    "Minutos", min_value=0, max_value=semaforo_repo.MAX_MINUTOS, step=1,
                    value=minutos["minutos"] if minutos else None, placeholder="—", key=clave_min,
                    label_visibility="collapsed", disabled=not puede_minutos,
                    help=f"Cargado por {minutos['created_by'] or 'sin dato'} el {_fecha(minutos['created_at'])}"
                    if minutos and minutos["minutos"] is not None else None,
                    on_change=_al_cambiar_minutos, args=(clave_min, partido, pid, nombre))

            for col, funcion in zip(cols[2:], FUNCIONES):
                actual = fila.get(funcion)
                if funcion != mi_funcion:
                    col.markdown(_chip(actual), unsafe_allow_html=True)
                    continue
                clave = f"sem_val_{funcion}_{partido}_{pid}"
                col.segmented_control(
                    _FUNCION_CORTA[funcion], list(semaforo_repo.RATINGS), format_func=ICONO.get,
                    default=actual["rating"] if actual else None, key=clave, label_visibility="collapsed",
                    help=f"{actual['rating'].capitalize()} · {actual['created_by'] or 'sin dato'} · "
                         f"{_fecha(actual['created_at'])}" if actual and actual["rating"] else "Sin valorar",
                    on_change=_al_cambiar_valoracion, args=(clave, partido, pid, nombre, funcion))

    with st.expander("Historial de cambios"):
        filas = semaforo_repo.historial(partido)
        if not filas:
            st.caption("Todavía no se cargó nada para este partido.")
        else:
            st.dataframe(pd.DataFrame([{
                "Fecha": f["created_at"].replace("T", " "),
                "Quién": f["created_by"] or "sin dato",
                "Jugador": f["jugador"],
                "Qué": _FUNCION_CORTA.get(f["que"], f["que"]),
                "Valor": (f"{ICONO.get(f['valor'], '')} {f['valor']}" if f["que"] in FUNCIONES else f["valor"])
                         if f["valor"] is not None else "borrado",
            } for f in filas]), hide_index=True, width="stretch", height=280)


def render_semaforo(match_name: str) -> None:
    """Vista "Semáforo": planilla del partido y plantel del equipo."""
    semaforo_repo.init_semaforo_tables()
    roster_repo.init_roster_table()
    subvista = st.segmented_control("Semáforo", list(_SUBVISTAS), format_func=_SUBVISTAS.get, default="planilla",
                                    required=True, key="semaforo_subvista", label_visibility="collapsed")
    equipo = team_repo.get_match_team(match_name)
    if subvista == "plantel":
        render_plantel(equipo["team_id"] if equipo else None)
    else:
        _planilla(match_name, equipo)
