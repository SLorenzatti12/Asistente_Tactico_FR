"""
Analizador Táctico — Vista Clips
=================================
Santi (12/11/2026). Los clips de los tags del partido: cada tag tiene su
ventana (5 s antes y 10 s después de apretar el botón, ver tagging.py), y cada
parada del botón "Juego detenido" va de que se detuvo a que se reanudó. Se
filtran por tipo y equipo y se reproducen uno detrás de otro (por ejemplo,
todas las salidas del partido), cada uno solo de su comienzo a su fin, sobre el
mismo video anotado de la Mesa táctica: no se generan archivos nuevos.
"""
import pandas as pd
import streamlit as st

from components.tagging import JUEGO_DETENIDO, format_time, get_events, get_paradas
from components.video_sync import render_video_sincronizado
from theme import TEAM_LABELS


def _clips(match_name: str) -> pd.DataFrame:
    """Un clip por tag y por parada cerrada, en orden."""
    eventos = get_events(match_name)
    filas = [{"tipo": e.tag_type, "equipo": e.team, "inicio": float(e.inicio_sec), "fin": float(e.fin_sec),
              "autor": e.created_by} for e in eventos.itertuples()]
    paradas = get_paradas(match_name, solo_cerradas=True)
    filas += [{"tipo": JUEGO_DETENIDO, "equipo": None, "inicio": float(p.inicio_sec), "fin": float(p.fin_sec),
               "autor": p.created_by} for p in paradas.itertuples()]
    if not filas:
        return pd.DataFrame(columns=["tipo", "equipo", "inicio", "fin", "autor"])
    return pd.DataFrame(filas).sort_values("inicio").reset_index(drop=True)


def _reproducir(desde: int) -> None:
    anterior = st.session_state.get("_clips_pedido") or {"id": 0}
    st.session_state["_clips_pedido"] = {"id": anterior["id"] + 1, "desde": desde}


def render_clips(match: dict) -> None:
    """La vista: filtros, el video y la lista de clips."""
    match_name = match["name"]
    clips = _clips(match_name)
    if clips.empty:
        st.info("Todavía no hay tags en este partido. En la Mesa táctica, cada botón de tagueo guarda un clip "
                "de 5 s antes a 10 s después de apretarlo, y «⏸ Juego detenido» guarda la parada entera.")
        return

    with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
        tipos = list(dict.fromkeys(clips["tipo"]))
        elegidos = st.pills("Tipo", tipos, selection_mode="multi", default=tipos, key=f"clips_tipos_{match_name}")
        equipo = st.segmented_control(
            "Equipo", ["todos", "home", "away"], default="todos", key=f"clips_equipo_{match_name}",
            format_func=lambda x: "Ambos equipos" if x == "todos" else TEAM_LABELS.get(x, x))
    filtrados = clips[clips["tipo"].isin(elegidos or [])]
    if equipo not in (None, "todos"):
        # Las paradas no son de un equipo: quedan solo con "Ambos equipos".
        filtrados = filtrados[filtrados["equipo"] == equipo]
    filtrados = filtrados.reset_index(drop=True)

    total = float((filtrados["fin"] - filtrados["inicio"]).sum())
    st.caption(f"**{len(filtrados)} clips** · {format_time(total)} en total. Cada uno se reproduce de su comienzo "
               "a su fin y sigue el próximo; mover el video fuera del clip corta la secuencia.")

    pedido = st.session_state.get("_clips_pedido")
    lista = [[r.inicio, r.fin, f"{r.tipo}" + (f" · {TEAM_LABELS.get(r.equipo, r.equipo)}" if r.equipo else "")]
             for r in filtrados.itertuples()]
    if not match["tracked_video"].exists():
        st.warning("No encontré el video anotado de este partido.")
    else:
        render_video_sincronizado(
            match["tracked_video"], key=f"clips_video_{match_name}",
            clips={"id": pedido["id"], "desde": pedido["desde"], "lista": lista} if pedido and lista else None)

    if filtrados.empty:
        st.caption("Ningún clip con estos filtros.")
        return
    st.button(f"▶ Reproducir los {len(filtrados)} clips", type="primary", key="clips_todos",
              on_click=_reproducir, args=(0,))
    tabla = pd.DataFrame({
        "Tipo": filtrados["tipo"],
        "Equipo": [TEAM_LABELS.get(e, e) if e else "—" for e in filtrados["equipo"]],
        "Desde": [format_time(t) for t in filtrados["inicio"]],
        "Hasta": [format_time(t) for t in filtrados["fin"]],
        "Duración": [f"{fin - ini:.0f} s" for ini, fin in zip(filtrados["inicio"], filtrados["fin"])],
        "Tagueado por": filtrados["autor"].fillna("sin dato"),
    })
    seleccion = st.dataframe(tabla, hide_index=True, width="stretch", on_select="rerun",
                             selection_mode="single-row", key=f"clips_tabla_{match_name}")
    filas = seleccion.selection.rows if seleccion else []
    if filas:
        st.button(f"▶ Desde el clip elegido ({tabla['Tipo'][filas[0]]}, {tabla['Desde'][filas[0]]})",
                  key="clips_desde_elegido", on_click=_reproducir, args=(filas[0],))
