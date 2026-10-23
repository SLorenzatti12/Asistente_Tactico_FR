"""
Analizador Táctico — Estadísticas individuales por jugador (vista)
====================================================================
Vista "Jugadores": envuelve src/analysis/player_stats.py para el dashboard,
con el aspecto del mockup (mockup/index.html, "Rendimiento individual"):
barra de filtros (equipo, zona, búsqueda), tarjetas de totales, tabla
ordenable con barras y una ficha lateral del track elegido (posición
promedio y dispersión sobre una mini cancha, y salto a la Mesa táctica).

Muestra solo datos que el sistema mide: es una fila por TRACK, no por
jugador (no hay dorsales ni nombres sobre los tracks), y no hay sprints ni
rangos de velocidad (la velocidad lejos de la cámara es orientativa — ver
docs/context/decisiones.md). Rediseño hecho por Santi con el OK de Nico
(22/10/2026).

Recibe el DataFrame con columnas: frame, time_sec, track_id, class_name,
field_x, field_y[, team]. Lo genera src/homography/calibrate.py (igual que
map_view.py, con el que comparte convención de ejes y colores de cancha).
"""

import html
import inspect
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Reutilizamos el dibujo de cancha de Nico para mantener el mismo look
# (mismo verde, mismas líneas) entre el mapa en vivo y estos mapas.
from components.map_view import _draw_field_shapes
from components.tagging import format_time

# Paleta e identidad visual centralizadas — ver theme.py. ZONE_* ya trae
# "arquero" como cuarta categoría (además de defensa/mediocampo/ataque),
# pensada justo para esta vista.
from theme import FIELD_BG, FIELD_LINES, TEAM_COLORS, TEAM_LABELS
from theme import ZONE_COLORS as ZONA_COLORS
from theme import ZONE_LABELS as ZONA_LABELS
from theme import ZONE_ORDER as ORDEN_ZONAS
from theme import plotly_layout_base

# src/analysis vive fuera de app/ — lo sumamos a sys.path para poder importarlo
# como paquete (calibrate.py y run_inference.py se corren como script directo
# y no necesitan esto; este módulo se importa desde main.py, así que sí).
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.analysis.player_stats import (  # noqa: E402
    MAX_SPEED_MS,
    MIN_FRAMES,
    compute_player_stats,
    filter_noise,
    infer_formation_zones,
)
from src.homography.medidas_cancha import medidas_de_df  # noqa: E402

# Ventana de suavizado por defecto: la tomamos de la firma de la función en vez
# de repetir el número acá, para no desincronizarnos si cambia en el módulo.
_DEFAULT_VENTANA = inspect.signature(compute_player_stats).parameters["ventana_suavizado"].default

CLASE_LABELS = {"player": "Jugador", "goalkeeper": "Arquero"}
EQUIPOS = {"todos": "Ambos equipos", "home": TEAM_LABELS["home"], "away": TEAM_LABELS["away"]}
SIN_EQUIPO = "Sin equipo"

# Estilo del mockup (.analytics-table, .player-inspector-card). Usa los tokens
# --at-* que define main.py; atado a clases propias, no a data-testid.
_ESTILOS = """
<style>
.at-insp-head { display: flex; align-items: center; gap: 14px; }
.at-insp-num {
  font-family: var(--at-mono, monospace); font-weight: 800; font-size: 1.1rem;
  padding: 8px 10px; border-radius: 10px; border: 2px solid; min-width: 64px; text-align: center;
}
.at-insp-title { font-weight: 700; font-size: 1.05rem; color: var(--at-text-1, #f0f3f6); }
.at-insp-sub { font-size: 0.8rem; color: var(--at-text-2, #9aa4b2); display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.at-insp-pill { font-size: 0.72rem; font-weight: 700; padding: 1px 8px; border-radius: 999px; border: 1px solid; }
.at-insp-sec { font-family: var(--at-mono, monospace); font-size: 0.68rem; letter-spacing: 0.08em;
               text-transform: uppercase; color: var(--at-text-2, #9aa4b2); margin-top: 6px; }
.at-insp-rows { display: grid; grid-template-columns: 1fr auto; gap: 6px 12px; font-size: 0.85rem; }
.at-insp-rows .k { color: var(--at-text-2, #9aa4b2); }
.at-insp-rows .v { font-family: var(--at-mono, monospace); color: var(--at-text-1, #f0f3f6); text-align: right; }
.at-insp-note { font-size: 0.75rem; color: var(--at-text-3, #626c7a); }
</style>
"""


# ── Cálculo (cacheado) ───────────────────────────────────────
@st.cache_data(show_spinner="Calculando estadísticas de jugadores…")
def _calcular_stats(
    df: pd.DataFrame,
    min_frames: int,
    max_speed_ms: float,
    ventana_suavizado: int,
    largo_cancha: float,
) -> pd.DataFrame:
    """
    filter_noise → compute_player_stats → infer_formation_zones, cacheado por
    contenido del DataFrame + parámetros (así los controles no recalculan
    sobre el mismo partido dos veces con los mismos valores). `largo_cancha`
    va como parámetro y no se lee de df.attrs adentro: st.cache_data arma la
    clave con los argumentos, y dos partidos con el mismo contenido pero otra
    cancha no deben compartir el resultado.

    Agrega por track el equipo (el más frecuente en sus filas) y el segundo
    en que aparece por primera vez (para saltar a la Mesa táctica).
    """
    limpio = filter_noise(df, min_frames=min_frames, max_speed_ms=max_speed_ms)
    stats = infer_formation_zones(compute_player_stats(limpio, ventana_suavizado=ventana_suavizado),
                                  largo_cancha=largo_cancha)
    if stats.empty:
        return stats

    stats = stats.copy()
    # infer_formation_zones() clasifica por tercios de cancha, pensado para
    # jugadores de campo. Al arquero lo sacamos de esa lógica: es su propio
    # puesto, no "ataque" o "defensa" según dónde promedie parado.
    stats["zona"] = stats["zona"].astype(object)
    stats.loc[stats["class_name"] == "goalkeeper", "zona"] = "arquero"
    stats["clase"] = stats["class_name"].map(CLASE_LABELS).fillna(stats["class_name"])

    por_track = limpio.groupby("track_id")
    stats["t_inicio"] = stats["track_id"].map(por_track["time_sec"].min())
    if "team" in limpio.columns:
        equipo = por_track["team"].agg(lambda s: s.mode().iat[0] if not s.mode().empty else None)
        stats["equipo"] = stats["track_id"].map(equipo)
    else:
        stats["equipo"] = None
    return stats.sort_values("distancia_total_m", ascending=False).reset_index(drop=True)


# ── Controles ────────────────────────────────────────────────
def _controles() -> tuple[int, float, int]:
    """Sliders de min_frames / max_speed_ms / ventana_suavizado, con su explicación."""
    with st.popover("Parámetros", icon=":material/tune:"):
        min_frames = st.slider(
            "Mínimo de frames por track", min_value=1, max_value=60,
            value=MIN_FRAMES, key="ps_min_frames",
        )
        st.caption(
            "Descarta tracks que aparecen en menos frames que esto: son fragmentos "
            "espurios del tracker, no jugadores reales."
        )
        max_speed_ms = st.slider(
            "Velocidad máxima plausible (m/s)", min_value=5.0, max_value=15.0,
            value=float(MAX_SPEED_MS), step=0.5, key="ps_max_speed",
        )
        st.caption(
            "Un jugador amateur no supera esto en la cancha (~12 m/s ≈ 43 km/h). "
            "Los saltos de posición más rápidos se descartan: son glitches de la "
            "homografía o cruces de identidad del tracker."
        )
        ventana_suavizado = st.slider(
            "Ventana de suavizado de posición (frames)", min_value=0, max_value=15,
            value=_DEFAULT_VENTANA, key="ps_ventana",
        )
        st.caption(
            "Mediana móvil sobre la trayectoria antes de medir distancia y velocidad. "
            "La homografía tiembla un poco aun con el jugador quieto; sin suavizar, "
            "ese temblor se cuenta como recorrido. En 0 se usan las posiciones crudas."
        )
    return min_frames, max_speed_ms, ventana_suavizado


# ── Filtros (equipo, zona, búsqueda) ─────────────────────────
def _filtrar(stats: pd.DataFrame) -> pd.DataFrame:
    """Barra de filtros del mockup. Devuelve los tracks que pasan los tres."""
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        equipo = st.segmented_control(
            "Equipo", list(EQUIPOS), format_func=EQUIPOS.get, default="todos",
            required=True, key="ps_equipo", label_visibility="collapsed",
        )
        sub = stats if equipo == "todos" else stats[stats["equipo"] == equipo]

        conteo = sub["zona"].value_counts()
        zonas = ["todas"] + [z for z in ORDEN_ZONAS if conteo.get(z, 0) > 0]
        etiqueta = (lambda z: f"Todas ({len(sub)})" if z == "todas"
                    else f"{ZONA_LABELS[z]} ({conteo.get(z, 0)})")
        zona = st.pills("Zona", zonas, format_func=etiqueta, default="todas",
                        required=True, key="ps_zona", label_visibility="collapsed")
        if zona != "todas":
            sub = sub[sub["zona"] == zona]

        buscar = st.text_input("Buscar track", placeholder="Buscar por número de track…",
                               key="ps_buscar", label_visibility="collapsed", width=230)
        if buscar.strip():
            sub = sub[sub["track_id"].astype(str).str.contains(buscar.strip(), regex=False)]
    return sub


# ── Tarjetas de totales ──────────────────────────────────────
def _render_totales(sub: pd.DataFrame) -> None:
    with st.container(horizontal=True):
        st.metric(
            "Distancia total", f"{sub['distancia_total_m'].sum() / 1000:.1f} km", border=True,
            help="Suma de la distancia de los tracks filtrados. Un mismo jugador puede estar "
                 "partido en varios tracks; la suma no depende de eso.",
        )
        st.metric(
            "Tracks", f"{len(sub)}", border=True,
            help=f"Promedio {sub['distancia_total_m'].mean():.0f} m por track.",
        )
        v_max = sub["velocidad_max_ms"].max()
        st.metric(
            "Velocidad máxima", "—" if pd.isna(v_max) else f"{v_max * 3.6:.1f} km/h", border=True,
            help="Orientativa: lejos de la cámara, el temblor de la detección se ve como pique "
                 "(ver decisiones.md). Solo tracks de 5 s o más.",
        )
        st.metric(
            "Tiempo promedio en cancha", format_time(sub["tiempo_en_cancha_seg"].mean()), border=True,
            help="Cuánto dura en promedio cada track (mm:ss).",
        )


# ── Tabla ────────────────────────────────────────────────────
def _render_tabla(sub: pd.DataFrame) -> int | None:
    """Tabla del mockup: una fila por track, con barras de distancia. Devuelve
    el track elegido (clic en una fila), o None."""
    tabla = pd.DataFrame({
        "track": "#" + sub["track_id"].astype(str),
        "equipo": sub["equipo"].map(lambda e: TEAM_LABELS.get(e, SIN_EQUIPO)),
        "zona": sub["zona"].map(ZONA_LABELS).fillna(sub["zona"]),
        "tiempo": sub["tiempo_en_cancha_seg"].map(format_time),
        "distancia": sub["distancia_total_m"],
        "vmax": sub["velocidad_max_ms"] * 3.6,
        "vprom": sub["velocidad_prom_ms"] * 3.6,
    })
    evento = st.dataframe(
        tabla,
        hide_index=True,
        width="stretch",
        height=520,
        on_select="rerun",
        selection_mode="single-row",
        key="ps_tabla",
        column_config={
            "track": st.column_config.TextColumn("Track", width="small"),
            "equipo": st.column_config.TextColumn("Equipo"),
            "zona": st.column_config.TextColumn("Zona"),
            "tiempo": st.column_config.TextColumn("En cancha", help="Duración del track (mm:ss)."),
            "distancia": st.column_config.ProgressColumn(
                "Distancia", format="%.0f m", min_value=0.0,
                max_value=float(max(sub["distancia_total_m"].max(), 1.0)),
            ),
            "vmax": st.column_config.NumberColumn("Vel. máx", format="%.1f km/h",
                                                  help="Orientativa (ver la tarjeta de arriba)."),
            "vprom": st.column_config.NumberColumn("Vel. promedio", format="%.1f km/h"),
        },
    )
    filas = evento.selection.rows if evento is not None else []
    if filas and filas[0] < len(sub):
        return int(sub.iloc[filas[0]]["track_id"])
    return None


# ── Ficha del track ─────────────────────────────────────────
def _mini_cancha(fila: pd.Series, medidas: dict) -> go.Figure:
    """Mini cancha: posición promedio del track y su dispersión (elipse con
    los rangos de movimiento en X e Y)."""
    color = TEAM_COLORS.get(fila["equipo"], "#c3ff00")
    x, y = float(fila["pos_promedio_x"]), float(fila["pos_promedio_y"])
    rx, ry = max(float(fila["rango_x"]) / 2, 1.0), max(float(fila["rango_y"]) / 2, 1.0)
    fig = go.Figure()
    _draw_field_shapes(fig, medidas)
    fig.add_shape(type="circle", x0=x - rx, x1=x + rx, y0=y - ry, y1=y + ry,
                  line=dict(color=color, width=1), fillcolor=color, opacity=0.25)
    fig.add_trace(go.Scatter(
        x=[x], y=[y], mode="markers",
        marker=dict(size=14, color="#c3ff00", line=dict(color=FIELD_LINES, width=2)),
        hovertemplate="X %{x:.1f} m · Y %{y:.1f} m<extra></extra>", showlegend=False,
    ))
    largo, ancho = medidas["largo"], medidas["ancho"]
    fig.update_layout(**plotly_layout_base(
        plot_bgcolor=FIELD_BG, paper_bgcolor=FIELD_BG, height=230,
        margin=dict(l=0, r=0, t=4, b=4), showlegend=False,
    ))
    fig.update_layout(
        xaxis=dict(range=[-2, largo + 2], fixedrange=True, showgrid=False, zeroline=False, visible=False),
        yaxis=dict(range=[-2, ancho + 2], fixedrange=True, showgrid=False, zeroline=False,
                   visible=False, scaleanchor="x"),
    )
    return fig


def _ir_a(t: float) -> None:
    """Pide el salto a la Mesa táctica (main.py aplica `_pending_seek_time`)."""
    st.session_state["_pending_seek_time"] = float(t)


def _render_ficha(fila: pd.Series, medidas: dict) -> None:
    equipo = fila["equipo"]
    color = TEAM_COLORS.get(equipo, "#9aa4b2")
    zona = fila["zona"]
    st.html(_ESTILOS + f"""
<div class="at-insp-head">
  <div class="at-insp-num" style="color:{color}; border-color:{color}">#{int(fila['track_id'])}</div>
  <div>
    <div class="at-insp-title">Track {int(fila['track_id'])}</div>
    <div class="at-insp-sub">
      <span>{html.escape(TEAM_LABELS.get(equipo, SIN_EQUIPO))}</span>
      <span class="at-insp-pill" style="color:{ZONA_COLORS.get(zona, '#9aa4b2')};
            border-color:{ZONA_COLORS.get(zona, '#9aa4b2')}">{html.escape(ZONA_LABELS.get(zona, str(zona)))}</span>
    </div>
  </div>
</div>
<div class="at-insp-sec">Posición promedio y dispersión</div>
""")
    st.plotly_chart(_mini_cancha(fila, medidas), width="stretch", config={"displayModeBar": False},
                    key="ps_mini_cancha")
    st.html(f"""
<div class="at-insp-note">X {fila['pos_promedio_x']:.1f} m · Y {fila['pos_promedio_y']:.1f} m ·
movimiento {fila['rango_x']:.0f} × {fila['rango_y']:.0f} m</div>
<div class="at-insp-sec">Números del track</div>
<div class="at-insp-rows">
  <span class="k">Aparece</span><span class="v">{format_time(fila['t_inicio'])}</span>
  <span class="k">En cancha</span><span class="v">{format_time(fila['tiempo_en_cancha_seg'])}</span>
  <span class="k">Distancia</span><span class="v">{fila['distancia_total_m']:.0f} m</span>
  <span class="k">Vel. promedio</span><span class="v">{fila['velocidad_prom_ms'] * 3.6:.1f} km/h</span>
  <span class="k">Vel. máx (orientativa)</span><span class="v">{'—' if pd.isna(fila['velocidad_max_ms']) else f"{fila['velocidad_max_ms'] * 3.6:.1f} km/h"}</span>
</div>
""")
    st.button(
        f"Ver en la Mesa táctica ({format_time(fila['t_inicio'])})",
        icon=":material/play_arrow:", type="primary", width="stretch",
        on_click=_ir_a, args=(fila["t_inicio"],), key="ps_ver_en_mesa",
    )


# ── Mapa de todos los tracks (desplegable) ──────────────────
def _render_mapa_posiciones(stats: pd.DataFrame, medidas: dict) -> None:
    amplitud = (stats["rango_x"].fillna(0) + stats["rango_y"].fillna(0)).clip(lower=0)
    # Fórmula recomendada de Plotly para que el ÁREA del marcador (no el
    # diámetro) sea proporcional al valor: evita que los que más se movieron
    # se vean desproporcionadamente grandes.
    pico = float(amplitud.max())
    sizeref = (2.0 * pico / (42.0 ** 2)) if pico > 0 else 1.0

    fig = go.Figure()
    _draw_field_shapes(fig, medidas)

    for zona in ORDEN_ZONAS:
        sub = stats[stats["zona"] == zona]
        if sub.empty:
            continue
        tam = (sub["rango_x"].fillna(0) + sub["rango_y"].fillna(0)).clip(lower=0)
        fig.add_trace(go.Scatter(
            x=sub["pos_promedio_x"], y=sub["pos_promedio_y"],
            mode="markers+text",
            text=sub["track_id"].astype(str),
            textposition="top center",
            textfont=dict(color=FIELD_LINES, size=9),
            marker=dict(
                size=tam, sizemode="area", sizeref=sizeref, sizemin=6,
                color=ZONA_COLORS[zona], line=dict(color=FIELD_LINES, width=1),
            ),
            name=ZONA_LABELS[zona],
            customdata=tam,
            hovertemplate="track %{text}<br>rango: %{customdata:.1f} m<extra></extra>",
        ))

    # Mismo criterio que el mapa en vivo de map_view.py: tipografía/margen de
    # la base común, verde de cancha (no el fondo oscuro genérico) y ejes
    # ocultos del todo en una segunda llamada.
    fig.update_layout(**plotly_layout_base(
        plot_bgcolor=FIELD_BG, paper_bgcolor=FIELD_BG,
        margin=dict(l=0, r=0, t=10, b=10),
        legend_extra=dict(orientation="h", yanchor="bottom", y=1.0, x=0, font=dict(color=FIELD_LINES)),
    ))
    fig.update_layout(
        xaxis=dict(range=[-2, medidas["largo"] + 2], showgrid=False, zeroline=False, visible=False),
        yaxis=dict(range=[-2, medidas["ancho"] + 2], showgrid=False, zeroline=False, visible=False,
                   scaleanchor="x"),
    )
    st.plotly_chart(fig, width="stretch")
    st.caption("Tamaño del punto ∝ amplitud de movimiento (rango X + rango Y).")


# ── Componente público (contrato con main.py) ─────────────────
def render_player_stats(df: pd.DataFrame) -> None:
    """Vista completa de estadísticas por track: filtros + totales + tabla + ficha."""
    if df is None or df.empty:
        st.info("No hay datos cargados para este partido todavía.")
        return
    if "field_x" not in df.columns or "field_y" not in df.columns:
        st.warning(
            "Este partido no tiene coordenadas de cancha (`field_x` / `field_y`). "
            "Corré primero la homografía:\n\n"
            "```\npython src/homography/calibrate.py <video> --apply <coords.parquet>\n```"
        )
        return

    medidas = medidas_de_df(df)
    col_tabla, col_ficha = st.columns([3, 1.15], gap="medium")

    with col_tabla:
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown("**Rendimiento por track**")
            min_frames, max_speed_ms, ventana_suavizado = _controles()
        try:
            stats = _calcular_stats(df, min_frames, max_speed_ms, ventana_suavizado, medidas["largo"])
        except ValueError as e:
            st.error(f"No se pudo calcular las estadísticas: {e}")
            return
        if stats.empty:
            st.info(
                "Ningún track quedó tras el filtro con estos parámetros. "
                "Probá bajar el mínimo de frames o subir la velocidad máxima."
            )
            return

        sub = _filtrar(stats)
        if sub.empty:
            st.info("Ningún track coincide con estos filtros.")
            return
        _render_totales(sub)
        elegido = _render_tabla(sub)
        st.caption("Ordená por cualquier columna con un clic en el encabezado; elegí una fila para ver su ficha. "
                   "Una fila es un track: el mismo jugador puede aparecer en varios.")

    with col_ficha:
        fila = sub[sub["track_id"] == elegido].iloc[0] if elegido is not None else sub.iloc[0]
        with st.container(border=True, key="ps_ficha"):
            _render_ficha(fila, medidas)

    with st.expander("Mapa de posición promedio de todos los tracks", expanded=False):
        _render_mapa_posiciones(sub, medidas)
