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
import json
import math
import urllib.parse
import streamlit as st
import pandas as pd
from pathlib import Path

# ── Imports de los otros módulos del equipo ────────────────
# Nico desarrolla estas funciones en components/map_view.py
from components.map_view import render_map, render_metrics_panel

# Luci desarrolla estas funciones en components/tagging.py
from components.tagging import init_db, render_tagging_panel, render_semaforo_tab, format_time

ROOT    = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "data" / "outputs"
THEME_PREF_PATH = ROOT / ".streamlit" / "ui_prefs.json"

st.set_page_config(page_title="Analizador Táctico", layout="wide")


# ── Preferencia de tema (persiste en disco, no es "por usuario") ────
def _load_theme_pref() -> str:
    if THEME_PREF_PATH.exists():
        try:
            return json.loads(THEME_PREF_PATH.read_text(encoding="utf-8")).get("theme", "dark")
        except json.JSONDecodeError:
            pass
    return "dark"


def _save_theme_pref(mode: str) -> None:
    THEME_PREF_PATH.parent.mkdir(parents=True, exist_ok=True)
    THEME_PREF_PATH.write_text(json.dumps({"theme": mode}), encoding="utf-8")


# ── CSS del modo claro ───────────────────────────────────────
# El tema base de Streamlit (config.toml) queda fijo en oscuro; esto
# encima simula modo claro con CSS. Apoyado sobre todo en las variables
# --st-* (el puente documentado que Streamlit expone para que el CSS
# cruce hacia sus propios componentes), más selectores genéricos como
# red de contención — no pude confirmar en un navegador real que cubra
# el 100% de los widgets, así que puede necesitar un ajuste después de
# verlo.
_LIGHT_MODE_CSS = """
<style>
:root {
    --st-background-color: #ffffff;
    --st-secondary-background-color: #f6f8fa;
    --st-text-color: #1f2328;
    --st-heading-color: #1f2328;
    --st-border-color: #d0d7de;
    --st-widget-border-color: #d0d7de;
    --st-code-background-color: #f6f8fa;
    --st-code-text-color: #1f2328;
}
body, .stApp,
[data-testid="stAppViewContainer"], [data-testid="stHeader"],
[data-testid="stMain"], [data-testid="stBottomBlockContainer"] {
    background-color: #ffffff !important;
    color: #1f2328 !important;
}
[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stDialog"] {
    background-color: #f6f8fa !important;
    border-color: #d0d7de !important;
}
/* Ojo: NO tocar `span`/`div` acá — pisaría con !important el
   <span style="color:..."> que ya usamos para pintar Local/Visitante
   en las tarjetas de métricas. Tampoco `button` en general — pisaría
   el texto blanco de los botones primarios (verdes) de los modales. */
p, label, h1, h2, h3, h4, h5, h6 {
    color: #1f2328 !important;
}
</style>
"""


def _inject_theme_css(mode: str) -> None:
    # Siempre se emite un bloque <style> (vacío en oscuro) en vez de no emitir
    # nada: así este elemento SIEMPRE existe en la misma posición del árbol y
    # Streamlit lo reemplaza al volver a correr. Si no se emitiera nada en
    # oscuro, un <style> de modo claro de una corrida anterior podría quedar
    # colgado en el DOM y seguir pintando la página de claro.
    st.markdown(_LIGHT_MODE_CSS if mode == "light" else "<style></style>", unsafe_allow_html=True)


# ── Switch custom claro/oscuro (pelota deslizante) ──────────────
# SVG en vez de emoji ⚽: se ve nítido a cualquier tamaño/DPI, en vez de
# depender de la fuente de emoji del sistema operativo (que en Windows
# suele quedar borrosa/pixelada a tamaños chicos).
#
# El patrón clásico (pentágono central + 5 satélites, unidos por costuras)
# se genera por trigonometría en vez de coordenadas tipeadas a mano, para
# no arriesgar un dibujo asimétrico o mal proporcionado. Se verificó
# visualmente (renderizado con matplotlib, incluso reducido a 48x48) antes
# de dejarlo en el código — ver el patrón de "estrella" que reemplaza.
def _polygon_points(cx: float, cy: float, radius: float, sides: int, rotation_deg: float = -90) -> str:
    pts = []
    for i in range(sides):
        angle = math.radians(rotation_deg + i * (360 / sides))
        pts.append(f"{cx + radius * math.cos(angle):.2f},{cy + radius * math.sin(angle):.2f}")
    return " ".join(pts)


def _build_football_svg() -> str:
    """
    Pentágono central + 5 satélites, SIN las costuras finas de la primera
    versión y con satélites más grandes — a tamaño real (24px, el que
    ocupa dentro del switch) las costuras se perdían por completo y los
    satélites chicos se veían como manchas en vez de pentágonos. Se
    probaron 3 variantes a 24px reales (con costuras finas, esta versión
    "en negrita", y una sin satélites) antes de elegir esta.
    """
    cx, cy = 12, 12
    outer_r = 11
    center_pent_r = 5.0
    satellite_r = 8.0
    satellite_size = 3.2

    parts = [f'<circle cx="{cx}" cy="{cy}" r="{outer_r}" fill="white" stroke="black" stroke-width="1"/>']
    parts.append(f'<polygon points="{_polygon_points(cx, cy, center_pent_r, 5)}" fill="black"/>')

    for i in range(5):
        # Cada satélite se alinea con el punto medio entre dos vértices
        # consecutivos del pentágono central (offset de 36°), pegado a una
        # arista en vez de a un vértice — así se lee como panel vecino, no
        # como rayo (el bug del diseño original).
        angle_deg = -90 + 36 + i * 72
        angle = math.radians(angle_deg)
        sx, sy = cx + satellite_r * math.cos(angle), cy + satellite_r * math.sin(angle)
        parts.append(f'<polygon points="{_polygon_points(sx, sy, satellite_size, 5, rotation_deg=angle_deg + 180)}" fill="black"/>')

    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{"".join(parts)}</svg>'


_BALL_SVG = _build_football_svg()
_BALL_DATA_URI = "data:image/svg+xml," + urllib.parse.quote(_BALL_SVG)


def _theme_switch_css(mode: str, animate: bool) -> str:
    """
    Reestiliza el st.button real (dentro de st.container(key="theme_switch"))
    para que parezca un switch sol/luna — acá pelota, sin sol ni luna, sin
    texto. La posición/gradiente se recalculan en Python; el `transition` de
    CSS es lo que anima el cambio entre un valor y el siguiente cuando
    Streamlit vuelve a pintar el botón.

    IMPORTANTE — el switch muestra el tema AL QUE CAMBIA, no el actual: si la
    página está en oscuro, se ve naranja/sol ("tocá para ir a claro"). Es la
    convención habitual de los toggles de tema y es lo que se eligió. Todo el
    visual (gradiente Y posición de la pelota) sale de `target_mode`, un solo
    lugar — si saliera en parte de `mode` y en parte de su opuesto, volvería a
    aparecer el tipo de desincronización que se reportó tres veces.

    `animate=False` en el primer pintado de cada sesión (ver render_theme_switch):
    el navegador podría pintar el botón una fracción de segundo antes de que
    llegue el <style> inyectado (va por WebSocket, no en el HTML inicial) — si
    eso pasa, la transition animaría desde un estado por-default.
    """
    target_mode = "light" if mode == "dark" else "dark"
    targets_light = target_mode == "light"
    track_gradient = (
        "linear-gradient(135deg, #fb923c, #f472b6)" if targets_light
        else "linear-gradient(135deg, #0f172a, #1e3a8a)"
    )
    ball_left = "29px" if targets_light else "3px"
    ball_rotate = "360deg" if targets_light else "0deg"
    track_transition = "transition: background 0.35s ease !important;" if animate else ""
    ball_transition = (
        "transition: left 0.35s cubic-bezier(0.34, 1.56, 0.64, 1), transform 0.35s ease !important;"
        if animate else ""
    )

    return f"""
    <style>
    .st-key-theme_switch button {{
        position: relative !important;
        width: 56px !important;
        height: 30px !important;
        min-width: 56px !important;
        min-height: 30px !important;
        padding: 0 !important;
        border: none !important;
        border-radius: 999px !important;
        background: {track_gradient} !important;
        box-shadow: inset 0 1px 3px rgba(0,0,0,0.3) !important;
        {track_transition}
        cursor: pointer !important;
    }}
    /* El label queda vacío, pero por las dudas ocultamos cualquier texto
       residual que Streamlit envuelva adentro del botón. */
    .st-key-theme_switch button p,
    .st-key-theme_switch button div {{
        display: none !important;
    }}
    .st-key-theme_switch button::after {{
        content: "" !important;
        position: absolute !important;
        top: 3px !important;
        left: {ball_left} !important;
        width: 24px !important;
        height: 24px !important;
        border-radius: 50% !important;
        background-color: white !important;
        background-image: url("{_BALL_DATA_URI}") !important;
        background-size: cover !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.4) !important;
        transform: rotate({ball_rotate}) !important;
        {ball_transition}
    }}
    </style>
    """


def render_theme_switch() -> None:
    """Botón real de Streamlit, reestilizado con CSS como switch de pelota."""
    with st.container(key="theme_switch"):
        # El click se procesa ANTES de calcular el CSS — este era el bug
        # real (confirmado con AppTest: en la misma corrida donde se
        # clickea, session_state ya pasaba a "light" pero el CSS emitido
        # seguía siendo el de "dark", porque se armaba con el valor viejo
        # antes de llegar a este `if`). Con el click primero, el CSS de
        # esta misma corrida ya usa el modo actualizado.
        if st.button("", key="_theme_switch_btn"):
            new_mode = "light" if st.session_state["theme_mode"] == "dark" else "dark"
            st.session_state["theme_mode"] = new_mode
            _save_theme_pref(new_mode)

        # Sin transición en el primer pintado de la sesión (ver docstring
        # de _theme_switch_css) — se activa recién después, para los
        # cambios que el usuario haga clickeando.
        animate = st.session_state.get("_theme_switch_painted", False)
        st.session_state["_theme_switch_painted"] = True
        st.markdown(_theme_switch_css(st.session_state["theme_mode"], animate), unsafe_allow_html=True)


# ── Encabezado tipo marcador de estadio ─────────────────────────
# La banda se mantiene oscura en los DOS temas, a propósito: es un
# marcador, no una superficie de la página. Eso además la deja fuera de
# la pelea de especificidad con el CSS de modo claro (que pinta de claro
# todo stVerticalBlockBorderWrapper y de oscuro todos los h1/p) — por eso
# los selectores de acá llevan una clase extra: `.st-key-app_header h1`
# (0,1,1) le gana a `h1` (0,0,1) aunque los dos usen !important.
#
# El data-testid del contenedor es `stVerticalBlock`, NO
# `stVerticalBlockBorderWrapper`: verificado leyendo el DOM real con
# Playwright (en 1.63 el border-wrapper no envuelve a este elemento). Con
# el testid equivocado el selector no matchea nada y la banda no se pinta.
_HEADER_CSS = f"""
<style>
[data-testid="stVerticalBlock"].st-key-app_header {{
    background: linear-gradient(135deg, #0b1220 0%, #131f33 100%) !important;
    border: 1px solid #1f2d44 !important;
    border-radius: 10px !important;
    padding: 14px 20px !important;
    margin-bottom: 6px !important;
}}
.st-key-app_header [data-testid="stHorizontalBlock"] {{
    align-items: center !important;
}}
.st-key-app_header .scoreboard {{
    display: flex;
    align-items: center;
    gap: 16px;
}}
.st-key-app_header .scoreboard-ball {{
    width: 44px;
    height: 44px;
    flex: 0 0 44px;
    filter: drop-shadow(0 2px 4px rgba(0,0,0,0.5));
}}
.st-key-app_header h1.scoreboard-title {{
    color: #ffffff !important;
    font-size: 1.7rem !important;
    font-weight: 800 !important;
    letter-spacing: 0.18em !important;
    line-height: 1.1 !important;
    margin: 0 0 6px 0 !important;
    padding: 0 !important;
    text-transform: uppercase;
}}
.st-key-app_header .scoreboard-rule {{
    width: 92px;
    height: 3px;
    border-radius: 2px;
    background: linear-gradient(90deg, #22c55e, rgba(34,197,94,0));
    margin-bottom: 7px;
}}
.st-key-app_header .scoreboard-sub {{
    color: #8ba0bd !important;
    font-size: 0.68rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.13em !important;
    text-transform: uppercase;
    margin: 0 !important;
}}
</style>
"""

_HEADER_HTML = f"""
<div class="scoreboard">
    <img class="scoreboard-ball" src="{_BALL_DATA_URI}" alt=""/>
    <div>
        <h1 class="scoreboard-title">Analizador Táctico</h1>
        <div class="scoreboard-rule"></div>
        <div class="scoreboard-sub">Liga de San Francisco · Análisis post-partido</div>
    </div>
</div>
"""


def render_app_header() -> None:
    """Banda de encabezado + switch de tema, alineados en la misma fila."""
    st.markdown(_HEADER_CSS, unsafe_allow_html=True)
    with st.container(key="app_header"):
        col_title, col_theme = st.columns([6, 1])
        with col_title:
            st.markdown(_HEADER_HTML, unsafe_allow_html=True)
        with col_theme:
            render_theme_switch()


# ── Estado inicial de la sesión ─────────────────────────────
def init_state():
    defaults = {
        "current_time": 0.0,     # segundo actual del video (sincroniza mapa y video)
        "playing": False,
        "selected_match": None,  # nombre del partido/video seleccionado
        "events": [],            # lista de tags: [{"type":..., "time":...}]
        "theme_mode": _load_theme_pref(),  # "dark" / "light", persistido en disco
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
    field_files = list(OUTPUTS.glob("*_field.parquet")) if OUTPUTS.exists() else []
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
    init_db()

    # Si se clickeó un evento en el timeline de tagging.py, el salto de
    # tiempo queda pendiente en esta clave intermedia — Streamlit no deja
    # reasignar session_state["current_time"] una vez que el slider (más
    # abajo) ya se instanció en la misma corrida, así que se aplica acá,
    # antes de crear el slider.
    if st.session_state.get("_pending_seek_time") is not None:
        st.session_state["current_time"] = st.session_state.pop("_pending_seek_time")

    render_app_header()

    _inject_theme_css(st.session_state["theme_mode"])

    match = match_selector()
    if match is None:
        return

    st.session_state["selected_match"] = match["name"]

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

            # ── Segundo actual (sincronización manual) ─
            # Streamlit no expone en qué momento va el reproductor de video,
            # así que este slider es la forma simple de decirle a la app
            # "estoy parado acá": alimenta tanto el mapa/métricas como el
            # tiempo que se guarda al tocar un botón de tagueo.
            has_time = "time_sec" in df.columns and not df.empty
            max_time = float(df["time_sec"].max()) if has_time else 3600.0
            # st.slider no tiene un `format` que pueda producir mm:ss para
            # NINGUNO de los tres números que dibuja (valor actual, mínimo,
            # máximo) — confirmado en su docstring, solo acepta printf-style
            # o formatos predefinidos. Por eso el mm:ss va en el label
            # (format_time(), la misma de "Editar eventos") y se intenta
            # ocultar los números crudos nativos con CSS.
            #
            # A diferencia de la flechita del popover (que fue una conjetura
            # a ciegas), estos data-testid SÍ están confirmados: se
            # extrajeron directamente del bundle JS instalado en este venv
            # (venv/.../streamlit/static/static/js/Slider.*.js — Streamlit
            # 1.63.0), no adivinados. `stSliderTickBar` es el único elemento
            # que dibuja min Y max juntos (no hay uno separado por lado) y
            # `stSliderThumbValue` es la burbuja de valor actual en verde
            # (el "0.00 duplicado" reportado). Lo que SÍ sigue sin poder
            # verificarse sin navegador real es que estas clases de React
            # no cambien de nombre entre builds — por eso el mm:ss también
            # se muestra aparte más abajo como respaldo garantizado.
            st.markdown(
                """
                <style>
                .st-key-time_slider [data-testid="stSliderTickBar"],
                .st-key-time_slider [data-testid="stSliderThumbValue"] {
                    display: none !important;
                }
                /* El label se restila en vez de colapsarlo con
                   label_visibility="collapsed": el ícono de ayuda (help=)
                   cuelga del label nativo, así que colapsarlo se lo lleva
                   puesto. */
                .st-key-time_slider label p {
                    font-size: 1.05rem !important;
                    font-weight: 700 !important;
                    letter-spacing: 0.01em !important;
                }
                /* Los extremos van en UNA fila flex, no en dos st.columns:
                   con columnas, el texto de la derecha se alinea a la
                   izquierda de SU columna y queda corrido respecto del
                   extremo real de la barra. */
                .st-key-time_slider .slider-bounds {
                    display: flex;
                    justify-content: space-between;
                    font-size: 0.78rem;
                    opacity: 0.65;
                    margin-top: -6px;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )
            current_label = format_time(st.session_state.get("current_time", 0.0))
            with st.container(key="time_slider"):
                st.slider(
                    f"Minuto actual — {current_label}",
                    min_value=0.0,
                    max_value=max_time,
                    step=1.0,
                    format="%.0f",
                    key="current_time",
                    help="Ajustá esto a mano mientras mirás el video, para sincronizar el mapa y el tagueo con lo que estás viendo.",
                )
                st.markdown(
                    f'<div class="slider-bounds"><span>{format_time(0.0)}</span>'
                    f"<span>{format_time(max_time)}</span></div>",
                    unsafe_allow_html=True,
                )

            # ── Mapa 2D (Nico) ─────────────────────────
            render_map(df, current_time=st.session_state["current_time"])

        with col_side:
            # Tabs en vez de apilar Métricas + Tagueo: así la columna
            # derecha no crece hacia abajo alejándose del video, y cambiar
            # de sección es un solo click (verificado: anidar tabs dentro
            # de una columna dentro de otro tabs no tiene problema en esta
            # versión de Streamlit).
            sub_metrics, sub_tagging = st.tabs(["📈 Métricas", "🏷️ Tagueo"])

            with sub_metrics:
                # ── Métricas (Nico) ────────────────────
                render_metrics_panel(df, current_time=st.session_state["current_time"])

            with sub_tagging:
                # ── Tagueo one-click (Luci) ─────────────
                render_tagging_panel()

    with tab_semaforo:
        # ── Semáforo (Luci) ────────────────────────────
        render_semaforo_tab(match["name"])


if __name__ == "__main__":
    main()

