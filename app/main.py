"""
Analizador Táctico — Dashboard principal (Streamlit)
======================================================
Santi — Estructura, layout, estado y reproductor de video.

Este archivo es el punto de entrada. Importa los componentes de
map_view.py (Nico) y tagging.py (Luci), y los ubica en el
layout. Cada quien puede desarrollar su módulo en paralelo — el
"contrato" entre módulos son las funciones que se importan abajo.

Correr con:
    streamlit run app/main.py
"""
import streamlit as st
import pandas as pd
from pathlib import Path

# ── Imports de los otros módulos del equipo ────────────────
# Nico desarrolla estas funciones en components/map_view.py
from components.map_view import render_map, render_metrics_panel

# Luci desarrolla estas funciones en components/tagging.py
from components.tagging import render_tagging_panel, render_semaforo_tab

# Estadísticas individuales por jugador (src/analysis/player_stats.py)
from components.player_stats_view import render_player_stats

# Reproductor de video sincronizado con el mapa (CCv2) — reemplaza a st.video()
from components.video_sync import render_video_sincronizado

# Identidad visual del sistema (paleta, tipografía, CSS global)
from theme import aplicar_estilos_globales

ROOT    = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "data" / "outputs"

st.set_page_config(page_title="Analizador Táctico", page_icon="⚽", layout="wide")
aplicar_estilos_globales()


# ── Estado inicial de la sesión ─────────────────────────────
def init_state():
    defaults = {
        "current_time": 0.0,     # segundo actual del video (sincroniza mapa y video)
        "playing": False,
        "selected_match": None,  # nombre del partido/video seleccionado
        "events": [],            # lista de tags: [{"type":..., "time":...}]
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ── Selector de partido ──────────────────────────────────────
def match_selector() -> dict | None:
    """
    Busca en data/outputs los partidos ya procesados (necesitan
    <nombre>_field.parquet, generado por homography/calibrate.py).
    Retorna un dict con las rutas relevantes, o None si no hay nada.
    """
    if not OUTPUTS.exists():
        return None

    field_files = list(OUTPUTS.glob("*_field.parquet"))
    if not field_files:
        st.warning(
            "No hay partidos procesados todavía. Corré primero:\n\n"
            "```\npython src/detection/run_inference.py <video>\n"
            "python src/homography/calibrate.py <video> --apply <coords.parquet>\n```"
        )
        return None

    names = [f.stem.replace("_coords_field", "") for f in field_files]
    # Label oculto: el contenedor que lo envuelve (en main()) ya dice "Partido".
    selected = st.selectbox("Partido", names, label_visibility="collapsed")
    idx = names.index(selected)

    return {
        "name": selected,
        "field_parquet": field_files[idx],
        "video_path": ROOT / "data" / "videos" / f"{selected}.mp4",
        "tracked_video": OUTPUTS / f"{selected}_tracked.mp4",
    }


# ── Video sincronizado + slider manual + mapa + métricas ─────
@st.fragment
def _panel_sincronizado(df: pd.DataFrame, match: dict, col_video, col_metricas) -> None:
    """
    Video + slider manual + mapa 2D + métricas, en un mismo st.fragment:
    mientras el video reproduce, components/video_sync.py actualiza
    `current_time` en session_state varias veces por segundo, y SOLO este
    bloque se vuelve a dibujar — no toda la pestaña, no las otras. Por eso
    el mapa y las métricas tienen que vivir en el MISMO fragmento que el
    video: un cambio de session_state hecho por otro fragmento no le llega
    (cada fragmento solo se re-ejecuta por sus propios triggers).

    El tagueo (Luci) queda deliberadamente afuera de este fragmento — lo
    sigue escribiendo main() en col_metricas, después de esta llamada.
    """
    with col_video:
        if not match["tracked_video"].exists():
            st.info("Video anotado no encontrado — mostrando solo el mapa.")
        else:
            # None salvo en la corrida exacta en que el video reportó un
            # tiempo nuevo (ver el docstring de render_video_sincronizado
            # para el porqué) — por eso alcanza con "si no es None, lo
            # piso"; cualquier otra corrida deja current_time como está,
            # que es lo que hace que el slider manual no se pelee con esto.
            # Tiene que ir ANTES de crear el slider de abajo — Streamlit no
            # deja tocar session_state[key] después de instanciado el
            # widget con ese key en la misma corrida.
            tick = render_video_sincronizado(
                match["tracked_video"], key=f"video_{match['name']}"
            )
            if tick is not None:
                st.session_state["current_time"] = tick

        duracion = float(df["time_sec"].max()) if not df.empty else 60.0
        # Clamp: session_state["current_time"] persiste entre partidos, y el
        # slider tira error si su value queda por encima del max de este.
        st.session_state["current_time"] = min(st.session_state["current_time"], duracion)

        st.slider(
            "Tiempo (s)", min_value=0.0, max_value=duracion, step=0.1,
            key="current_time",
            help="Control manual — útil para análisis cuadro a cuadro. "
                 "Mientras el video reproduce, se sincroniza solo con él.",
        )

        render_map(df, current_time=st.session_state["current_time"])

    with col_metricas:
        render_metrics_panel(df, current_time=st.session_state["current_time"])


# ── App principal ─────────────────────────────────────────
def main():
    init_state()

    st.title("⚽ Analizador Táctico")
    st.caption("Liga de San Francisco — Análisis táctico post-partido a partir del video")

    with st.container(border=True):
        st.markdown("##### 📁 Partido")
        match = match_selector()
    if match is None:
        return

    df = pd.read_parquet(match["field_parquet"])

    tab_live, tab_jugadores, tab_semaforo = st.tabs(
        ["📊 Análisis", "🏃 Jugadores", "🚦 Semáforo post-partido"]
    )

    with tab_live:
        col_video, col_side = st.columns([2, 1])

        # ── Video sincronizado + mapa (Nico) + métricas (Nico) ──
        _panel_sincronizado(df, match, col_video, col_side)

        with col_side:
            st.divider()
            # ── Tagueo one-click (Luci) ────────────────
            render_tagging_panel()

    with tab_jugadores:
        # ── Estadísticas individuales por jugador ──
        render_player_stats(df)

    with tab_semaforo:
        # ── Semáforo (Luci) ────────────────────────────
        render_semaforo_tab(match["name"])


if __name__ == "__main__":
    main()

