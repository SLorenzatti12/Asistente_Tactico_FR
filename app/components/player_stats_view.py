"""
Analizador Táctico — Estadísticas individuales por jugador (vista)
====================================================================
Pestaña "🏃 Jugadores": envuelve src/analysis/player_stats.py para el
dashboard — métricas globales, tabla ordenable, gráfico de distancia
recorrida y mapa de posiciones promedio sobre la cancha.

Recibe el DataFrame con columnas: frame, time_sec, track_id, class_name,
field_x, field_y. Lo genera src/homography/calibrate.py (igual que
map_view.py, con el que comparte convención de ejes y colores de cancha).
"""

import inspect
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Reutilizamos el dibujo de cancha de Nico para mantener el mismo look
# (mismo verde, mismas líneas) entre el mapa en vivo y este mapa de posiciones.
from components.map_view import _draw_field_shapes

# Paleta e identidad visual centralizadas — ver theme.py. ZONE_* ya trae
# "arquero" como cuarta categoría (además de defensa/mediocampo/ataque),
# pensada justo para esta vista.
from theme import FIELD_BG, FIELD_LENGTH, FIELD_LINES, FIELD_WIDTH
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

# Ventana de suavizado por defecto: la tomamos de la firma de la función en vez
# de repetir el número acá, para no desincronizarnos si cambia en el módulo.
_DEFAULT_VENTANA = inspect.signature(compute_player_stats).parameters["ventana_suavizado"].default

CLASE_LABELS = {"player": "Jugador", "goalkeeper": "Arquero"}

# Columnas de la tabla, en el orden en que se muestran.
_COLUMNAS_TABLA = [
    "track_id", "clase", "zona", "n_frames", "tiempo_en_cancha_seg",
    "distancia_total_m", "velocidad_max_ms", "velocidad_prom_ms",
    "pos_promedio_x", "pos_promedio_y", "rango_x", "rango_y",
]


# ── Cálculo (cacheado) ───────────────────────────────────────
@st.cache_data(show_spinner="Calculando estadísticas de jugadores…")
def _calcular_stats(
    df: pd.DataFrame,
    min_frames: int,
    max_speed_ms: float,
    ventana_suavizado: int,
) -> pd.DataFrame:
    """
    filter_noise → compute_player_stats → infer_formation_zones, cacheado por
    contenido del DataFrame + parámetros (así los sliders no recalculan sobre
    el mismo partido dos veces con los mismos valores).
    """
    limpio = filter_noise(df, min_frames=min_frames, max_speed_ms=max_speed_ms)
    stats = infer_formation_zones(compute_player_stats(limpio, ventana_suavizado=ventana_suavizado))
    if stats.empty:
        return stats

    stats = stats.copy()
    # infer_formation_zones() clasifica por tercios de cancha, pensado para
    # jugadores de campo. Al arquero lo sacamos de esa lógica: es su propio
    # puesto, no "ataque" o "defensa" según dónde promedie parado.
    stats["zona"] = stats["zona"].astype(object)
    stats.loc[stats["class_name"] == "goalkeeper", "zona"] = "arquero"
    stats["clase"] = stats["class_name"].map(CLASE_LABELS).fillna(stats["class_name"])
    return stats


# ── Controles ────────────────────────────────────────────────
def _controles() -> tuple[int, float, int]:
    """Sliders de min_frames / max_speed_ms / ventana_suavizado, con su explicación."""
    with st.expander("⚙️ Parámetros de análisis", expanded=False):
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


# ── Métricas globales ────────────────────────────────────────
def _render_metricas_globales(stats: pd.DataFrame) -> None:
    with st.container(horizontal=True):
        st.metric("Tracks analizados", f"{len(stats)}", border=True)
        st.metric(
            "Distancia media", f"{stats['distancia_total_m'].mean():.1f} m",
            border=True, help="Promedio de distancia recorrida entre todos los tracks.",
        )
        v_max = stats["velocidad_max_ms"].max()
        st.metric(
            "Velocidad máxima", f"{v_max:.2f} m/s",
            border=True, help=f"Pico de velocidad del partido ({v_max * 3.6:.1f} km/h).",
        )
        st.metric(
            "Tiempo promedio en cancha", f"{stats['tiempo_en_cancha_seg'].mean():.1f} s",
            border=True, help="Segundos promedio en los que cada track fue detectado.",
        )


# ── Tabla ────────────────────────────────────────────────────
def _render_tabla(stats: pd.DataFrame) -> None:
    tabla = stats.copy()
    tabla["zona"] = tabla["zona"].map(ZONA_LABELS).fillna(tabla["zona"])
    tabla = tabla[[c for c in _COLUMNAS_TABLA if c in tabla.columns]]

    st.dataframe(
        tabla,
        hide_index=True,
        width="stretch",
        column_config={
            "track_id": st.column_config.NumberColumn("ID", format="%d"),
            "clase": st.column_config.TextColumn("Clase"),
            "zona": st.column_config.TextColumn("Zona"),
            "n_frames": st.column_config.NumberColumn("Frames", format="%d"),
            "tiempo_en_cancha_seg": st.column_config.NumberColumn("Tiempo (s)", format="%.1f"),
            "distancia_total_m": st.column_config.NumberColumn("Distancia (m)", format="%.1f"),
            "velocidad_max_ms": st.column_config.NumberColumn("V. máx (m/s)", format="%.2f"),
            "velocidad_prom_ms": st.column_config.NumberColumn("V. prom (m/s)", format="%.2f"),
            "pos_promedio_x": st.column_config.NumberColumn("X prom (m)", format="%.1f"),
            "pos_promedio_y": st.column_config.NumberColumn("Y prom (m)", format="%.1f"),
            "rango_x": st.column_config.NumberColumn("Rango X (m)", format="%.1f"),
            "rango_y": st.column_config.NumberColumn("Rango Y (m)", format="%.1f"),
        },
    )
    st.caption("Hacé clic en un encabezado para ordenar por esa columna.")


# ── Gráfico de barras: distancia por track ──────────────────
def _render_barras_distancia(stats: pd.DataFrame) -> None:
    # Ascendente: el primero queda abajo del gráfico y el de mayor distancia
    # arriba, que es como se lee "de mayor a menor" en un horizontal bar.
    data = stats.sort_values("distancia_total_m", ascending=True)
    orden_y = data["track_id"].astype(str).tolist()

    fig = go.Figure()
    for zona in ORDEN_ZONAS:
        sub = data[data["zona"] == zona]
        if sub.empty:
            continue
        fig.add_trace(go.Bar(
            y=sub["track_id"].astype(str), x=sub["distancia_total_m"],
            orientation="h", name=ZONA_LABELS[zona], marker_color=ZONA_COLORS[zona],
            hovertemplate="track %{y}<br>%{x:.1f} m<extra></extra>",
        ))

    fig.update_layout(**plotly_layout_base(
        yaxis_extra=dict(categoryorder="array", categoryarray=orden_y, title="Track ID"),
        xaxis_extra=dict(title="Distancia recorrida (m)"),
        legend_extra=dict(title="Zona", orientation="h", yanchor="bottom", y=1.0),
        barmode="overlay",
        height=max(320, 24 * len(data)),
        margin=dict(l=10, r=10, t=30, b=10),
    ))
    st.plotly_chart(fig, width="stretch")


# ── Scatter: posiciones promedio sobre la cancha ─────────────
def _render_mapa_posiciones(stats: pd.DataFrame) -> None:
    amplitud = (stats["rango_x"].fillna(0) + stats["rango_y"].fillna(0)).clip(lower=0)
    # Fórmula recomendada de Plotly para que el ÁREA del marcador (no el
    # diámetro) sea proporcional al valor: evita que los que más se movieron
    # se vean desproporcionadamente grandes.
    pico = float(amplitud.max())
    sizeref = (2.0 * pico / (42.0 ** 2)) if pico > 0 else 1.0

    fig = go.Figure()
    _draw_field_shapes(fig)

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
        xaxis=dict(range=[-2, FIELD_LENGTH + 2], showgrid=False, zeroline=False, visible=False),
        yaxis=dict(range=[-2, FIELD_WIDTH + 2], showgrid=False, zeroline=False, visible=False,
                   scaleanchor="x"),
    )
    st.plotly_chart(fig, width="stretch")
    st.caption("Tamaño del punto ∝ amplitud de movimiento (rango X + rango Y).")


# ── Componente público (contrato con main.py) ─────────────────
def render_player_stats(df: pd.DataFrame) -> None:
    """Pestaña completa de estadísticas individuales: controles + métricas + tabla + gráficos."""
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

    min_frames, max_speed_ms, ventana_suavizado = _controles()

    try:
        stats = _calcular_stats(df, min_frames, max_speed_ms, ventana_suavizado)
    except ValueError as e:
        st.error(f"No se pudo calcular las estadísticas: {e}")
        return

    if stats.empty:
        st.info(
            "Ningún track quedó tras el filtro con estos parámetros. "
            "Probá bajar el mínimo de frames o subir la velocidad máxima."
        )
        return

    _render_metricas_globales(stats)
    st.divider()

    st.markdown("**Estadísticas por jugador**")
    _render_tabla(stats)
    st.divider()

    col_barras, col_mapa = st.columns(2)
    with col_barras:
        st.markdown("**Distancia recorrida por track**")
        _render_barras_distancia(stats)
    with col_mapa:
        st.markdown("**Posición promedio en la cancha**")
        _render_mapa_posiciones(stats)
