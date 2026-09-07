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

ROOT    = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "data" / "outputs"

st.set_page_config(page_title="Analizador Táctico", layout="wide")


# ── Estado inicial de la sesión ─────────────────────────────
def init_state():
    defaults = {
        "current_time": 0,       # segundo actual del video (sincroniza mapa y video)
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
    selected = st.selectbox("Partido", names)
    idx = names.index(selected)

    return {
        "name": selected,
        "field_parquet": field_files[idx],
        "video_path": ROOT / "data" / "videos" / f"{selected}.mp4",
        "tracked_video": OUTPUTS / f"{selected}_tracked.mp4",
    }


# ── App principal ─────────────────────────────────────────
def main():
    init_state()

    st.title("⚽ Analizador Táctico")
    st.caption("Liga de San Francisco — Análisis post-partido")

    match = match_selector()
    if match is None:
        return

    df = pd.read_parquet(match["field_parquet"])

    tab_live, tab_semaforo = st.tabs(["📊 Análisis", "🚦 Semáforo post-partido"])

    with tab_live:
        col_video, col_side = st.columns([2, 1])

        with col_video:
            # ── Reproductor de video (Santi) ───────────
            if match["tracked_video"].exists():
                st.video(str(match["tracked_video"]))
            else:
                st.info("Video anotado no encontrado — mostrando solo el mapa.")

            # ── Mapa 2D (Nico) ─────────────────────────
            render_map(df, current_time=st.session_state["current_time"])

        with col_side:
            # ── Métricas (Nico) ────────────────────────
            render_metrics_panel(df, current_time=st.session_state["current_time"])

            st.divider()

            # ── Tagueo one-click (Luci) ────────────────
            render_tagging_panel()

    with tab_semaforo:
        # ── Semáforo (Luci) ────────────────────────────
        render_semaforo_tab(match["name"])


if __name__ == "__main__":
    main()

