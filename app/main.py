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
import urllib.parse
import streamlit as st
import pandas as pd
from pathlib import Path

# ── Imports de los otros módulos del equipo ────────────────
# Nico desarrolla estas funciones en components/map_view.py
from components.map_view import render_map, render_metrics_panel

# Luci desarrolla estas funciones en components/tagging.py
from components.tagging import init_db, render_tagging_panel, render_semaforo_tab, format_time
# Los atajos de teclado taguean con las mismas funciones que los botones de tagging.py
from components.tagging import TAG_TIME_BUFFER_SEC, get_event_types_for_team, save_event

# Estadísticas individuales por jugador (src/analysis/player_stats.py)
from components.player_stats_view import render_player_stats

# Reproductor de video sincronizado con el mapa (CCv2) — reemplaza a st.video()
from components.video_sync import render_video_sincronizado

# Base híbrida (Nico): equipo/categoría del partido, plantel y registro de
# la ruta del video local para el sync a Supabase (scripts/sync_to_cloud.py).
from components.team_selector import render_team_selector
from components.video_registry import render_video_registry

# Patrones tácticos detectados (src/analysis/tactical_patterns.py)
from components.tactical_patterns_view import render_tactical_patterns_tab

# Partidos de dos tiempos: un video por tiempo (src/db/partido_repo.py)
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db import partido_repo  # noqa: E402

from src.homography.medidas_cancha import medidas_de_df  # noqa: E402

# Identidad visual del sistema (paleta, tipografía, CSS global)
from theme import TEAM_LABELS, aplicar_estilos_globales

ROOT    = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "data" / "outputs"

st.set_page_config(page_title="Analizador Táctico", page_icon="⚽", layout="wide")
aplicar_estilos_globales()


# ── Identidad visual del mockup (mockup/styles.css) ─────────────
# Solo modo oscuro, como el mockup (el switch claro/oscuro se sacó el
# 22/10/2026). Los colores base (fondo, texto, lima) los pone
# .streamlit/config.toml; acá van los tokens de superficies, bordes y
# etiquetas que el tema nativo no tiene. Los estilos se atan a clases
# propias (.at-*) o a contenedores con key (.st-key-*), no a data-testid
# internos de Streamlit, que cambian entre versiones.
_ESTILOS_MOCKUP = """
<style>
:root {
  --at-surface-1: #121519;
  --at-surface-2: #181c22;
  --at-border: #242a35;
  --at-text-1: #f0f3f6;
  --at-text-2: #9aa4b2;
  --at-text-3: #626c7a;
  --at-lime: #c3ff00;
  --at-lime-dim: rgba(195, 255, 0, 0.15);
  --at-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
}
.st-key-app_header {
  background: var(--at-surface-1);
  border: 1px solid var(--at-border);
  border-radius: 12px;
  padding: 10px 16px;
}
.at-brand { display: flex; align-items: center; gap: 12px; }
.at-brand-icon {
  width: 36px; height: 36px; flex: 0 0 36px; border-radius: 9px;
  display: flex; align-items: center; justify-content: center;
  background: var(--at-lime-dim); color: var(--at-lime);
}
.at-brand-title { font-weight: 800; font-size: 0.95rem; letter-spacing: 0.12em; color: var(--at-text-1); line-height: 1.25; }
.at-brand-sub { font-size: 0.6rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--at-text-3); white-space: nowrap; }
.at-match-pill {
  display: inline-flex; align-items: center; gap: 10px; flex-wrap: wrap;
  background: var(--at-surface-2); border: 1px solid var(--at-border);
  border-radius: 999px; padding: 6px 14px; font-size: 0.82rem; color: var(--at-text-1);
}
.at-match-pill .at-name { font-weight: 700; }
.at-match-pill .at-meta { font-family: var(--at-mono); font-size: 0.72rem; color: var(--at-text-2); }
.at-panel-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }
.at-panel-tag { font-family: var(--at-mono); font-size: 0.68rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--at-text-2); }
.at-pill {
  font-family: var(--at-mono); font-size: 0.66rem; padding: 2px 8px; border-radius: 999px;
  border: 1px solid var(--at-border); color: var(--at-text-2); white-space: nowrap;
}
/* Métricas en una columna angosta (al lado del tagueo): números y
   etiquetas más chicos para que no se corten, como las celdas compactas
   del mockup. Los data-testid son de st.metric (map_view.py, Nico): si
   cambian con una versión nueva de Streamlit, esto deja de aplicar pero no
   rompe nada. */
.st-key-panel_metricas [data-testid="stMetric"] { padding: 0.5rem 0.65rem 0.4rem !important; }
.st-key-panel_metricas [data-testid="stMetricValue"] { font-size: 1.35rem !important; }
.st-key-panel_metricas [data-testid="stMetricLabel"] p { font-size: 0.75rem !important; }
.at-atajos { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 0.74rem; color: var(--at-text-2); }
.at-atajos kbd {
  font-family: var(--at-mono); font-size: 0.68rem; padding: 1px 6px; margin-right: 4px;
  border: 1px solid var(--at-border); border-bottom-width: 2px; border-radius: 4px;
  background: var(--at-surface-2); color: var(--at-text-1);
}
</style>
"""

# Ícono de la marca: el del mockup (mockup/index.html, .brand-icon). Va como
# imagen data: y no como <svg> en línea porque st.html descarta los SVG.
_ICONO_MARCA = "data:image/svg+xml," + urllib.parse.quote(
    '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" '
    'stroke="#c3ff00" stroke-width="2"><circle cx="12" cy="12" r="10"/>'
    '<path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>'
)

_HTML_MARCA = f"""
<div class="at-brand">
  <div class="at-brand-icon"><img src="{_ICONO_MARCA}" width="20" height="20" alt=""/></div>
  <div>
    <div class="at-brand-title">ANALIZADOR TÁCTICO</div>
    <div class="at-brand-sub">Liga San Francisco · Post-partido</div>
  </div>
</div>
"""

# Vistas de la app: solo se calcula y dibuja la elegida (con st.tabs se
# calculaban las cuatro en cada recarga aunque se viera una).
VISTAS = {
    "analisis": ":material/videocam: Mesa táctica",
    "jugadores": ":material/directions_run: Jugadores",
    "patrones": ":material/warning: Patrones",
    "semaforo": ":material/traffic: Semáforo",
}


def _html_partido(match: dict, medidas: dict) -> str:
    nombre = match["partido"] or match["name"]
    tiempo = f"{match['tiempo']}° tiempo" if match["tiempo"] else "video suelto"
    meta = f"{tiempo} · cancha {medidas['largo']:g} × {medidas['ancho']:g} m"
    return (f'<div class="at-match-pill"><span class="at-name">{nombre}</span>'
            f'<span class="at-meta">{meta}</span></div>')


def _html_panel(titulo: str, *pills: str) -> str:
    extra = "".join(f'<span class="at-pill">{p}</span>' for p in pills)
    return f'<div class="at-panel-head"><span class="at-panel-tag">{titulo}</span><span>{extra}</span></div>'


# ── Saltos del video ────────────────────────────────────────────
def _pedir_salto(t: float) -> None:
    """Lleva el video a `t` en la próxima corrida (ver `salto` en
    render_video_sincronizado): el componente aplica cada id una sola vez."""
    anterior = st.session_state.get("_salto") or {"id": 0}
    st.session_state["_salto"] = {"id": anterior["id"] + 1, "t": float(t)}


# ── Atajos de teclado (los escucha el componente de video) ───────
def _html_atajos(team: str) -> str:
    """Leyenda de atajos, con el número de cada botón de tagueo del equipo activo."""
    tipos = get_event_types_for_team(team)[:9]
    tags = " ".join(f"<span><kbd>{i}</kbd>{t['name']}</span>" for i, t in enumerate(tipos, start=1))
    return (
        '<div class="at-atajos">'
        "<span><kbd>Espacio</kbd>reproducir / pausar</span>"
        "<span><kbd>←</kbd><kbd>→</kbd>±1 s (con <kbd>Shift</kbd> ±5 s)</span>"
        "<span><kbd>L</kbd><kbd>V</kbd>taguear para Local / Visitante</span>"
        f"<span>Tags {TEAM_LABELS.get(team, team)}:</span>{tags}"
        "</div>"
    )


def _atajo_de_teclado(tecla: dict) -> None:
    """
    Atajos de tagueo que manda el componente de video. Hacen lo mismo que la
    botonera de tagging.py (Luci): el número N es el botón N del equipo
    activo, en el orden en que se ven, con el mismo colchón de
    TAG_TIME_BUFFER_SEC. El tiempo es el del video al apretar la tecla.
    """
    if tecla.get("accion") == "equipo":
        # El selector de equipo de tagging.py no se instanció en esta corrida
        # del fragmento, así que se puede cambiar su valor acá.
        st.session_state["tag_team"] = tecla["equipo"]
        st.toast(f"Tagueando para: {TEAM_LABELS[tecla['equipo']]}")
        st.rerun()
    elif tecla.get("accion") == "tag":
        team = st.session_state.get("tag_team") or "home"
        tipos = get_event_types_for_team(team)
        n = int(tecla["n"])
        if n > len(tipos):
            st.toast(f"No hay un botón {n} en la botonera de {TEAM_LABELS[team]} (hay {len(tipos)}).")
            return
        nombre = tipos[n - 1]["name"]
        t = max(0.0, float(tecla["t"]) - TAG_TIME_BUFFER_SEC)
        save_event(st.session_state["selected_match"], nombre, t, team)
        st.toast(f"Tag guardado: {nombre} @ {format_time(t)} ({TEAM_LABELS[team]})")
        st.rerun()      # la corrida completa actualiza el historial de tags


# ── Estado inicial de la sesión ─────────────────────────────
def init_state():
    defaults = {
        "current_time": 0.0,     # segundo actual del video (sincroniza mapa y video)
        "playing": False,
        "selected_match": None,  # nombre del partido/video seleccionado
        "events": [],            # lista de tags: [{"type":..., "time":...}]
        "vista": "analisis",     # vista elegida en el encabezado (ver VISTAS)
        "modo_visor": "dividido",  # Mesa táctica: dividido / cancha / video
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ── Selector de partido ──────────────────────────────────────
def _match_dict(name: str, field_parquet: Path, partido: str | None = None, tiempo: int | None = None) -> dict:
    return {
        "name": name,
        "field_parquet": field_parquet,
        "video_path": ROOT / "data" / "videos" / f"{name}.mp4",
        "tracked_video": OUTPUTS / f"{name}_tracked.mp4",
        "partido": partido,   # None si es un video suelto
        "tiempo": tiempo,     # 1 / 2, o None
    }


def match_selector() -> dict | None:
    """
    Busca en data/outputs los videos ya procesados (necesitan
    <nombre>_coords_field.parquet, generado por homography/calibrate.py).
    Los que son un tiempo de un partido registrado (scripts/partidos.py) se
    agrupan bajo el partido, con un selector de tiempo: cada tiempo sigue
    siendo un video propio (su parquet, su dirección de ataque, sus eventos).
    Retorna un dict con las rutas relevantes, o None si no hay nada.
    """
    field_files = list(OUTPUTS.glob("*_field.parquet")) if OUTPUTS.exists() else []
    if not field_files:
        return None     # main() avisa: este selector vive dentro de un popover

    parquets = {f.stem.replace("_coords_field", ""): f for f in field_files}
    partido_repo.init_partidos_table()
    partidos = {nombre: [t for t in tiempos if t["match_name"] in parquets]
                for nombre, tiempos in partido_repo.list_partidos().items()}
    partidos = {nombre: tiempos for nombre, tiempos in partidos.items() if tiempos}
    agrupados = {t["match_name"] for tiempos in partidos.values() for t in tiempos}
    opciones = ([("partido", nombre) for nombre in sorted(partidos)]
                + [("video", nombre) for nombre in sorted(parquets) if nombre not in agrupados])

    # Label oculto: el popover que lo envuelve (en main()) ya dice "Partido".
    tipo, elegido = st.selectbox("Partido", opciones, format_func=lambda o: o[1],
                                 label_visibility="collapsed", key="partido_elegido")
    if tipo == "video":
        return _match_dict(elegido, parquets[elegido])

    tiempos = {t["tiempo"]: t["match_name"] for t in partidos[elegido]}
    etiquetas = {1: "1° tiempo", 2: "2° tiempo"}
    tiempo = st.segmented_control("Tiempo", list(tiempos), format_func=etiquetas.get,
                                  default=min(tiempos), required=True, key=f"tiempo_elegido_{elegido}")
    faltan = [etiquetas[t] for t in (1, 2) if t not in tiempos]
    if faltan:
        st.caption(f"Sin procesar todavía: {', '.join(faltan)}.")
    nombre = tiempos[tiempo]
    return _match_dict(nombre, parquets[nombre], elegido, tiempo)


# ── Video sincronizado + slider manual + mapa + métricas ─────
_MODOS_VISOR = {
    "dividido": ":material/splitscreen_left: Dividido",
    "cancha": ":material/sports_soccer: Solo cancha",
    "video": ":material/videocam: Solo video",
}


@st.fragment
def _panel_sincronizado(df: pd.DataFrame, match: dict, col_visor, col_metricas) -> None:
    """
    Video + slider manual + mapa 2D + métricas, en un mismo st.fragment:
    mientras el video reproduce, components/video_sync.py actualiza
    `current_time` en session_state varias veces por segundo, y SOLO este
    bloque se vuelve a dibujar — no toda la vista. Por eso el mapa y las
    métricas tienen que vivir en el MISMO fragmento que el video: un cambio
    de session_state hecho por otro fragmento no le llega (cada fragmento
    solo se re-ejecuta por sus propios triggers).

    El modo del visor (dividido / solo cancha / solo video) también vive
    acá: cambiarlo redibuja solo este bloque.

    El tagueo (Luci) queda deliberadamente afuera de este fragmento — lo
    sigue escribiendo main() en col_metricas, después de esta llamada.
    """
    with col_visor:
        modo = st.segmented_control(
            "Modo del visor", list(_MODOS_VISOR), format_func=_MODOS_VISOR.get,
            required=True, key="modo_visor", label_visibility="collapsed",
        )
        hay_video = match["tracked_video"].exists()
        mostrar_video = hay_video and modo in ("dividido", "video")
        mostrar_cancha = modo in ("dividido", "cancha") or not hay_video
        if not hay_video:
            st.info("Video anotado no encontrado — mostrando solo el mapa.")
        if mostrar_video and mostrar_cancha:
            panel_video, panel_cancha = st.columns(2)
        else:
            panel_video = panel_cancha = st.container()

        duracion = float(df["time_sec"].max()) if not df.empty else 60.0
        # Clamp: session_state["current_time"] persiste entre partidos, y el
        # slider tira error si su value queda por encima del max de este.
        st.session_state["current_time"] = min(st.session_state["current_time"], duracion)

        # El componente de video se vuelve a montar cada vez que reaparece
        # (otra vista, otro modo del visor, otro partido) y arrancaría en
        # 0:00: se le pide que retome donde está el mapa.
        if mostrar_video and not st.session_state.get("_video_visible"):
            _pedir_salto(st.session_state["current_time"])
        st.session_state["_video_visible"] = mostrar_video

        if mostrar_video:
            with panel_video:
                st.html(_html_panel("Cámara · video anotado", "RF-DETR + ByteTrack"))
                # None salvo en la corrida exacta en que el video reportó un
                # tiempo nuevo (ver el docstring de render_video_sincronizado
                # para el porqué) — por eso alcanza con "si no es None, lo
                # piso"; cualquier otra corrida deja current_time como está,
                # que es lo que hace que el slider manual no se pelee con esto.
                # Tiene que ir ANTES de crear el slider de abajo — Streamlit no
                # deja tocar session_state[key] después de instanciado el
                # widget con ese key en la misma corrida.
                tick = render_video_sincronizado(
                    match["tracked_video"], key=f"video_{match['name']}",
                    salto=st.session_state.get("_salto"), al_tecla=_atajo_de_teclado,
                )
                if tick is not None:
                    st.session_state["current_time"] = tick

        # st.slider no tiene un `format` que pueda producir mm:ss para NINGUNO
        # de los tres números que dibuja (valor actual, mínimo, máximo): solo
        # acepta printf-style. Así que los números crudos nativos se ocultan
        # con CSS y el mm:ss se pone aparte. Los data-testid salieron del
        # bundle JS instalado en el venv (streamlit/static/.../Slider.*.js,
        # 1.63.0) y se verificó en Chrome que efectivamente los tapan.
        #
        # step=0.1 se mantiene (análisis cuadro a cuadro) — como la burbuja de
        # valor queda oculta, que el paso sea decimal ya no se ve feo.
        st.markdown(
            """
            <style>
            .st-key-time_slider [data-testid="stSliderTickBar"],
            .st-key-time_slider [data-testid="stSliderThumbValue"] {
                display: none !important;
            }
            /* El label se restila en vez de colapsarlo con
               label_visibility="collapsed": el ícono de ayuda (help=) cuelga
               del label nativo, así que colapsarlo se lo lleva puesto. */
            .st-key-time_slider label p {
                font-family: var(--at-mono) !important;
                font-size: 1.05rem !important;
                font-weight: 700 !important;
                letter-spacing: 0.01em !important;
            }
            /* Los extremos van en UNA fila flex, no en dos st.columns: con
               columnas, el texto de la derecha se alinea a la izquierda de SU
               columna y queda corrido respecto del extremo real de la barra. */
            .st-key-time_slider .slider-bounds {
                display: flex;
                justify-content: space-between;
                font-family: var(--at-mono);
                font-size: 0.75rem;
                opacity: 0.65;
                margin-top: -6px;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        with st.container(key="time_slider"):
            # Al moverlo a mano, el video lo sigue (como la barra del mockup).
            st.slider(
                f"{format_time(st.session_state['current_time'])} / {format_time(duracion)}",
                min_value=0.0, max_value=duracion, step=0.1,
                key="current_time",
                on_change=lambda: _pedir_salto(st.session_state["current_time"]),
                help="Mové la barra para ir a otro momento: el video y la cancha la siguen. "
                     "Mientras el video reproduce, la barra se sincroniza sola con él.",
            )
            st.markdown(
                f'<div class="slider-bounds"><span>{format_time(0.0)}</span>'
                f"<span>{format_time(duracion)}</span></div>",
                unsafe_allow_html=True,
            )
        if mostrar_video:
            st.html(_html_atajos(st.session_state.get("tag_team") or "home"))

        if mostrar_cancha:
            with panel_cancha:
                medidas = medidas_de_df(df)
                st.html(_html_panel(f"Cancha cenital {medidas['largo']:g} × {medidas['ancho']:g} m"))
                render_map(df, current_time=st.session_state["current_time"], medidas=medidas)

    with col_metricas:
        with st.container(border=True, key="panel_metricas"):
            render_metrics_panel(df, current_time=st.session_state["current_time"])


# ── App principal ─────────────────────────────────────────
def main():
    init_state()
    init_db()
    st.html(_ESTILOS_MOCKUP)

    # Si se clickeó un evento en el timeline de tagging.py, o la evidencia de
    # un patrón, el salto de tiempo queda pendiente en esta clave intermedia —
    # Streamlit no deja reasignar session_state["current_time"] una vez que el
    # slider (más abajo, dentro de _panel_sincronizado) ya se instanció en la
    # misma corrida, así que se aplica acá, antes de crear el slider. El salto
    # lleva a la Mesa táctica y mueve también el video.
    if st.session_state.get("_pending_seek_time") is not None:
        t = st.session_state.pop("_pending_seek_time")
        st.session_state["current_time"] = t
        st.session_state["vista"] = "analisis"
        _pedir_salto(t)

    # ── Encabezado: marca, partido, navegación y cambio de partido ──
    with st.container(key="app_header"):
        col_marca, col_partido, col_nav, col_cambiar = st.columns(
            [2.7, 2.4, 4.7, 1.2], vertical_alignment="center")
        # El popover va primero en el código (no en pantalla): el partido que
        # se elige ahí es el que muestra la píldora del medio.
        with col_cambiar:
            with st.popover("Partido", icon=":material/swap_horiz:", width="stretch"):
                match = match_selector()
                if match is not None:
                    render_team_selector(match["name"])
                    render_video_registry(match["name"], default_path=match["video_path"])
        with col_marca:
            st.html(_HTML_MARCA)
        with col_nav:
            vista = st.segmented_control(
                "Vista", list(VISTAS), format_func=VISTAS.get, required=True,
                key="vista", label_visibility="collapsed",
            )

    if match is None:
        st.warning(
            "No hay partidos procesados todavía. Corré primero:\n\n"
            "```\npython src/detection/run_inference.py <video>\n"
            "python src/homography/calibrate.py <video> --apply <coords.parquet>\n```"
        )
        return

    if match["name"] != st.session_state.get("selected_match"):
        st.session_state["_video_visible"] = False   # otro partido: video nuevo
    st.session_state["selected_match"] = match["name"]

    df = pd.read_parquet(match["field_parquet"])
    with col_partido:
        st.html(_html_partido(match, medidas_de_df(df)))

    # Solo se calcula y dibuja la vista elegida.
    if vista != "analisis":
        st.session_state["_video_visible"] = False
    if vista == "analisis":
        # Visor, tagueo y métricas lado a lado: se ven a la vez, sin scroll,
        # para mirar el video y marcar al mismo tiempo.
        col_visor, col_tagueo, col_metricas = st.columns([2.2, 1, 1], gap="small")

        # ── Video sincronizado + mapa (Nico) + métricas (Nico) ──
        _panel_sincronizado(df, match, col_visor, col_metricas)

        with col_tagueo:
            # ── Tagueo one-click (Luci) ────────────────
            with st.container(border=True, key="panel_tagueo"):
                render_tagging_panel()
    elif vista == "jugadores":
        # ── Estadísticas individuales por jugador ──
        render_player_stats(df)
    elif vista == "patrones":
        # ── Patrones tácticos detectados ──
        render_tactical_patterns_tab(df)
    else:
        # ── Semáforo (Luci) ────────────────────────────
        render_semaforo_tab(match["name"])


if __name__ == "__main__":
    main()
