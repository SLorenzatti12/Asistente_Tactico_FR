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
from components.tagging import init_db, render_tagging_panel, format_time
from components.semaforo_view import render_semaforo
from components.clips_view import render_clips
# Los atajos de teclado taguean con las mismas funciones que los botones de tagging.py
from components.tagging import alternar_parada, get_event_types_for_team, save_event, ventana_tag

# Estadísticas individuales por jugador (src/analysis/player_stats.py)
from components.player_stats_view import render_player_stats

# Reproductor de video sincronizado con el mapa (CCv2) — reemplaza a st.video()
from components.video_sync import render_video_sincronizado

# Base híbrida (Nico): equipo/categoría del partido, plantel y registro de
# la ruta del video local para el sync a Supabase (scripts/sync_to_cloud.py).
from components.team_selector import render_team_selector
from components.video_registry import render_video_registry

# Patrones tácticos detectados (src/analysis/tactical_patterns.py)
from components.tactical_patterns_view import hay_regreso_a_patrones, render_tactical_patterns_tab, volver_a_patrones

# Login local, roles y administración de usuarios (src/db/usuarios_repo.py)
from components.sesion import (nombre_rol, puede, render_login, render_menu_usuario, usuario_actual,
                               vigilar_inactividad)
from components.usuarios_view import render_usuarios

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
/* Cinco vistas en una sola línea a 1440 px: menos margen interno en cada botón. */
.st-key-vista button { padding-left: 8px; padding-right: 8px; }
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
    "clips": ":material/movie: Clips",
    "semaforo": ":material/traffic: Semáforo",
}
# Vista → permiso necesario (las que no figuran, las ve cualquier usuario).
# El semáforo lo ven todos los roles; quien no califica, en solo lectura
# (components/semaforo_view.py). La vista "Usuarios" del admin se abre desde
# el menú del usuario, no desde acá.
PERMISO_VISTA = {"semaforo": "ver_semaforo"}


def _vistas_permitidas() -> list[str]:
    return [v for v in VISTAS if v not in PERMISO_VISTA or puede(PERMISO_VISTA[v])]


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
def _html_atajos(team: str, con_tags: bool = True) -> str:
    """Leyenda de atajos, con el número de cada botón de tagueo del equipo
    activo (sin la parte de tagueo para los roles que no taguean)."""
    html = ('<div class="at-atajos">'
            "<span><kbd>Espacio</kbd>reproducir / pausar</span>"
            "<span><kbd>←</kbd><kbd>→</kbd>±1 s (con <kbd>Shift</kbd> ±5 s)</span>")
    if con_tags:
        tipos = get_event_types_for_team(team)[:9]
        tags = " ".join(f"<span><kbd>{i}</kbd>{t['name']}</span>" for i, t in enumerate(tipos, start=1))
        html += ("<span><kbd>L</kbd><kbd>V</kbd>taguear para Local / Visitante</span>"
                 "<span><kbd>D</kbd>juego detenido / se reanudó</span>"
                 f"<span>Tags {TEAM_LABELS.get(team, team)}:</span>{tags}")
    return html + "</div>"


def _atajo_de_teclado(tecla: dict) -> None:
    """
    Atajos de tagueo que manda el componente de video. Hacen lo mismo que la
    botonera de tagging.py (Luci): el número N es el botón N del equipo
    activo, en el orden en que se ven, con la misma ventana alrededor del
    instante en que se apretó (tagging.ventana_tag), y D abre o cierra una
    parada ("Juego detenido"). El tiempo es el del video al apretar la tecla.
    Solo para los roles que taguean (usuarios_repo.PERMISOS).
    """
    if not puede("taguear"):
        st.toast("Tu rol no puede taguear.")
        return
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
        t = float(tecla["t"])
        usuario = usuario_actual()
        save_event(st.session_state["selected_match"], nombre, t, team, usuario["usuario"] if usuario else None)
        inicio, fin = ventana_tag(t)
        st.toast(f"Tag guardado: {nombre} · clip {format_time(inicio)}–{format_time(fin)} ({TEAM_LABELS[team]})")
        st.rerun()      # la corrida completa actualiza el historial de tags
    elif tecla.get("accion") == "detenido":
        usuario = usuario_actual()
        estado, parada = alternar_parada(st.session_state["selected_match"], float(tecla["t"]),
                                         usuario["usuario"] if usuario else None)
        st.toast(f"Juego detenido desde {format_time(parada['inicio_sec'])}" if estado == "abierta" else
                 f"Parada guardada: {format_time(parada['inicio_sec'])}–{format_time(parada['fin_sec'])}")
        st.rerun()


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
def _panel_sincronizado(df: pd.DataFrame, match: dict, hay_video: bool, mostrar_video: bool, mostrar_cancha: bool,
                        hueco_video, hueco_tiempo, col_cancha, col_metricas) -> None:
    """
    Video + slider manual + mapa 2D + métricas, en un mismo st.fragment:
    mientras el video reproduce, components/video_sync.py actualiza
    `current_time` en session_state varias veces por segundo, y SOLO este
    bloque se vuelve a dibujar — no toda la vista. Por eso el mapa y las
    métricas tienen que vivir en el MISMO fragmento que el video: un cambio
    de session_state hecho por otro fragmento no le llega (cada fragmento
    solo se re-ejecuta por sus propios triggers).

    Los huecos los arma main() según el modo del visor: arriba el video
    (hueco_video) con la barra de tiempo debajo (hueco_tiempo), al lado del
    tagueo; abajo, la cancha y las métricas. El tagueo (Luci) queda
    deliberadamente afuera de este fragmento — lo escribe main() después de
    esta llamada.
    """
    with hueco_tiempo:
        duracion = float(df["time_sec"].max()) if not df.empty else 60.0
        # Clamp: session_state["current_time"] persiste entre partidos, y el
        # slider tira error si su value queda por encima del max de este.
        st.session_state["current_time"] = min(st.session_state["current_time"], duracion)

        # El video siempre se monta si existe: es lo que hace avanzar el
        # tiempo. En "Solo cancha" va en modo mini (oculto, con un botón de
        # reproducir/pausar arriba de la barra). El componente se vuelve a
        # montar cada vez que cambia de lugar (otra vista, otro modo del
        # visor, otro partido) y arrancaría en 0:00: se le pide que retome
        # donde está la cancha.
        lugar = ("completo" if mostrar_video else "mini") if hay_video else None
        if lugar and st.session_state.get("_video_lugar") != lugar:
            _pedir_salto(st.session_state["current_time"])
        st.session_state["_video_lugar"] = lugar

        if lugar:
            with hueco_video if lugar == "completo" else st.container():
                if lugar == "completo":
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
                    mini=lugar == "mini",
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
        if lugar:
            st.html(_html_atajos(st.session_state.get("tag_team") or "home", con_tags=puede("taguear")))

    if mostrar_cancha:
        with col_cancha:
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

    # Login local: sin usuario no se muestra nada del partido.
    usuario = usuario_actual()
    if usuario is None:
        render_login(_HTML_MARCA)
        return
    # Cierra la sesión sola tras un rato sin uso (ver sesion.py).
    vigilar_inactividad()
    # Si el rol cambió y la vista elegida ya no le corresponde, vuelve a la Mesa táctica.
    vistas = _vistas_permitidas()
    if st.session_state.get("vista") not in vistas:
        st.session_state["vista"] = "analisis"

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
        st.session_state["_subir_pagina"] = True
        _pedir_salto(t)

    # ── Encabezado: marca, partido, navegación y cambio de partido ──
    with st.container(key="app_header"):
        col_marca, col_partido, col_nav, col_cambiar, col_usuario = st.columns(
            # Proporcional a lo que ocupa cada uno a 1440 px con las cinco vistas.
            [2.54, 2.22, 4.93, 1.13, 1.13], vertical_alignment="center")
        # El popover va primero en el código (no en pantalla): el partido que
        # se elige ahí es el que muestra la píldora del medio.
        with col_cambiar:
            with st.popover("Partido", icon=":material/swap_horiz:", width="stretch"):
                match = match_selector()
                if match is not None and puede("gestionar_partido"):
                    render_team_selector(match["name"])
                    render_video_registry(match["name"], default_path=match["video_path"])
        with col_marca:
            st.html(_HTML_MARCA)
        with col_nav:
            vista = st.segmented_control(
                "Vista", vistas, format_func=VISTAS.get, required=True,
                key="vista", label_visibility="collapsed",
                on_change=lambda: st.session_state.pop("_ver_usuarios", None),
            )
        with col_usuario:
            render_menu_usuario(usuario)

    # Administración de usuarios (solo admin), abierta desde el menú del usuario.
    if st.session_state.get("_ver_usuarios") and puede("administrar_usuarios"):
        st.button("Volver", icon=":material/arrow_back:", key="volver_de_usuarios",
                  on_click=lambda: st.session_state.pop("_ver_usuarios", None))
        render_usuarios(usuario)
        return

    if match is None:
        st.warning(
            "No hay partidos procesados todavía. Corré primero:\n\n"
            "```\npython src/detection/run_inference.py <video>\n"
            "python src/homography/calibrate.py <video> --apply <coords.parquet>\n```"
        )
        return

    if match["name"] != st.session_state.get("selected_match"):
        st.session_state["_video_lugar"] = None   # otro partido: video nuevo
    st.session_state["selected_match"] = match["name"]

    df = pd.read_parquet(match["field_parquet"])
    with col_partido:
        st.html(_html_partido(match, medidas_de_df(df)))

    # Solo se calcula y dibuja la vista elegida.
    if vista != "analisis":
        st.session_state["_video_lugar"] = None
    if vista == "analisis":
        # Después de un salto, la página seguía donde estaba en la otra vista,
        # con el video y "Volver a Patrones" fuera de la pantalla.
        if st.session_state.pop("_subir_pagina", False):
            st.html("""<script>setTimeout(() => {
                let e = document.querySelector(".st-key-app_header");
                while (e && e.scrollHeight <= e.clientHeight) e = e.parentElement;
                e?.scrollTo(0, 0);
            }, 100);</script>""", unsafe_allow_javascript=True)
        # El modo del visor cambia la disposición, así que vive afuera del
        # fragmento: cambiarlo redibuja la página entera (pasa pocas veces).
        with st.container(horizontal=True, vertical_alignment="center"):
            modo = st.segmented_control(
                "Modo del visor", list(_MODOS_VISOR), format_func=_MODOS_VISOR.get,
                required=True, key="modo_visor", label_visibility="collapsed",
            )
            # Después de saltar desde una tarjeta de Patrones, para volver a ella.
            if hay_regreso_a_patrones(match["name"]):
                st.button("Volver a Patrones", icon=":material/arrow_back:", key="volver_a_patrones",
                          on_click=volver_a_patrones)
        hay_video = match["tracked_video"].exists()
        mostrar_video = hay_video and modo in ("dividido", "video")
        mostrar_cancha = modo in ("dividido", "cancha") or not hay_video
        if not hay_video:
            st.info("Video anotado no encontrado — mostrando solo el mapa.")

        # Fila de arriba: video ancho y, a su derecha, el tagueo, para mirar y
        # marcar a la vez. La cámara de los partidos es panorámica
        # (sportivo_crop3: 1920 × 460): en una columna angosta quedaba de unos
        # 70 px de alto. Debajo del video, la barra de tiempo.
        # Fila de abajo: cancha y métricas. En "Solo cancha", la cancha sube
        # al lugar del video.
        # Quien no taguea (cuerpo técnico, solo lectura) ve en esa columna los
        # eventos del partido en solo lectura (gráficos e historial, para ir
        # a cada momento), sin botonera.
        col_principal, col_tagueo = st.columns([2.6, 1], gap="small")
        with col_principal:
            hueco_video, hueco_tiempo = st.container(), st.container()
        if mostrar_video and mostrar_cancha:
            col_cancha, col_metricas = st.columns([1.4, 1], gap="small")
        elif mostrar_cancha:
            col_cancha, col_metricas = hueco_video, st.container()
        else:
            col_cancha, col_metricas = None, st.container()

        # ── Video sincronizado + mapa (Nico) + métricas (Nico) ──
        _panel_sincronizado(df, match, hay_video, mostrar_video, mostrar_cancha,
                            hueco_video, hueco_tiempo, col_cancha, col_metricas)

        # ── Tagueo one-click (Luci) ────────────────
        # Gráficos e historial van plegados (tagging.py): cerrada, la
        # tarjeta mide como la columna del video y no empuja la fila de
        # abajo; se agranda solo si se abre un desplegable.
        with col_tagueo, st.container(border=True, key="panel_tagueo"):
            render_tagging_panel(solo_lectura=not puede("taguear"))
    elif vista == "jugadores":
        # ── Estadísticas individuales por jugador ──
        render_player_stats(df)
    elif vista == "patrones":
        # ── Patrones tácticos detectados ──
        render_tactical_patterns_tab(df)
    elif vista == "clips":
        # ── Clips de los tags, uno detrás de otro ──
        render_clips(match)
    else:
        # ── Semáforo: planilla del partido y plantel ────
        render_semaforo(match["name"])


if __name__ == "__main__":
    main()
