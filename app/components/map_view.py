"""
Analizador Táctico — Mapa 2D y métricas
==========================================
NICO — Visualización cenital de posiciones + panel de métricas tácticas.

Recibe el DataFrame con columnas: frame, time_sec, track_id, class_name,
field_x, field_y y (opcional) team. Lo genera src/homography/calibrate.py.

Referencia de cancha: 105m (largo, eje x) x 68m (ancho, eje y),
origen (0,0) en esquina sup-izquierda.

Color por EQUIPO (decisión de equipo). Si el parquet todavía no trae la
columna `team`, cae automáticamente a un color distinto por track_id.

Métricas de bloque
------------------
En vez del bounding-box crudo (max−min, muy sensible al arquero y a
detecciones espurias) se calcula:
  - amplitud / profundidad : extensión del bloque, con rechazo de outliers
                             por MAD (Iglewicz-Hoaglin) para filtrar glitches
                             de la homografía sin distorsionar la formación.
  - área ocupada           : superficie de la envolvente convexa (m²), la
                             ocupación real del bloque, no el rectángulo.
  - compacidad             : stretch index = distancia media de los jugadores
                             al centroide (Frencken et al., 2011). Robusto y
                             de un solo número.
"""

import colorsys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

FIELD_LENGTH = 105  # eje x — arco a arco
FIELD_WIDTH = 68    # eje y — lateral a lateral

# Umbral del test de outliers de Iglewicz-Hoaglin sobre el z-score robusto.
_MAD_Z_THRESHOLD = 3.5

# ── Colores ──────────────────────────────────────────────────
TEAM_COLORS = {"home": "#1f77b4", "away": "#d62728"}   # azul local / rojo visitante
TEAM_LABELS = {"home": "🔵 Local", "away": "🔴 Visitante"}
UNKNOWN_COLOR = "#9e9e9e"   # jugador sin equipo asignado
BALL_COLOR = "#ffffff"


# ── Helpers de datos ─────────────────────────────────────────
def _frame_at_time(df: pd.DataFrame, current_time: float) -> pd.DataFrame:
    """Devuelve todas las filas del frame cuyo time_sec es más cercano a current_time."""
    if df.empty or "time_sec" not in df.columns:
        return df.head(0)
    nearest_idx = (df["time_sec"] - current_time).abs().idxmin()
    frame_num = df.loc[nearest_idx, "frame"]
    return df[df["frame"] == frame_num]


def _players(frame_df: pd.DataFrame) -> pd.DataFrame:
    """Filtra solo jugadores (excluye pelota, árbitro, etc.)."""
    if "class_name" in frame_df.columns:
        return frame_df[frame_df["class_name"] == "player"]
    return frame_df


def _team_color(team) -> str:
    return TEAM_COLORS.get(team, UNKNOWN_COLOR)


def _track_color(track_id) -> str:
    """Color distinto por track_id: tonos separados por el ángulo áureo (sin colisiones)."""
    hue = (int(track_id) * 0.618_033_988_75) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.65, 0.95)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


# ── Geometría del bloque ─────────────────────────────────────
def _inlier_mask(values: np.ndarray, threshold: float = _MAD_Z_THRESHOLD) -> np.ndarray:
    """
    Máscara de inliers por MAD (Iglewicz-Hoaglin). Marca como outlier lo que
    tenga |z_robusto| > threshold, con z = 0.6745·(x − mediana) / MAD.
    Sirve para descartar detecciones imposibles (homografía que dispara un
    punto fuera de la cancha) sin tocar formaciones reales.
    """
    med = np.median(values)
    mad = np.median(np.abs(values - med))
    if mad == 0:  # todos iguales: nada que descartar
        return np.ones(len(values), dtype=bool)
    z = 0.6745 * (values - med) / mad
    return np.abs(z) <= threshold


def _clean_positions(players_df: pd.DataFrame) -> np.ndarray:
    """
    Posiciones (Nx2) del bloque sin NaN ni outliers groseros. Si el filtro de
    outliers dejara menos de 2 jugadores, se prefiere conservar todo (no vale
    la pena "limpiar" hasta romper la métrica).
    """
    pos = players_df[["field_x", "field_y"]].dropna().to_numpy(dtype=float)
    if len(pos) < 2:
        return pos
    keep = _inlier_mask(pos[:, 0]) & _inlier_mask(pos[:, 1])
    return pos[keep] if keep.sum() >= 2 else pos


def _convex_hull(points: np.ndarray) -> np.ndarray:
    """
    Envolvente convexa (monotone chain de Andrew), vértices ordenados en Kx2.
    Devuelve un array vacío si hay menos de 3 puntos no colineales.
    """
    pts = np.unique(points, axis=0)
    if len(pts) < 3:
        return np.empty((0, 2))
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in pts[::-1]:
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    hull = np.array(lower[:-1] + upper[:-1])
    return hull if len(hull) >= 3 else np.empty((0, 2))


def _polygon_area(polygon: np.ndarray) -> float:
    """Área de un polígono por la fórmula del zapatero (shoelace)."""
    if len(polygon) < 3:
        return 0.0
    x, y = polygon[:, 0], polygon[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _block_metrics(players_df: pd.DataFrame) -> dict | None:
    """
    Métricas del bloque a partir de field_x/field_y (ver docstring del módulo).
      - amplitud    : ancho del bloque, rango de field_y (eje 68m)
      - profundidad : largo del bloque, rango de field_x (eje 105m)
      - area        : superficie de la envolvente convexa (m²) — ocupación real
      - dispersion  : stretch index, distancia media al centroide (m)
      - cx, cy      : centroide del bloque
      - n           : jugadores usados (después de limpiar outliers)
    Devuelve None si hay menos de 2 jugadores (no hay bloque que medir).
    """
    pos = _clean_positions(players_df)
    if len(pos) < 2:
        return None

    x, y = pos[:, 0], pos[:, 1]
    cx, cy = float(x.mean()), float(y.mean())
    hull = _convex_hull(pos)
    return {
        "amplitud": float(y.max() - y.min()),
        "profundidad": float(x.max() - x.min()),
        "area": _polygon_area(hull),
        "dispersion": float(np.mean(np.hypot(x - cx, y - cy))),
        "cx": cx,
        "cy": cy,
        "n": int(len(pos)),
    }


# ── Dibujo del mapa ──────────────────────────────────────────
def _draw_field_shapes(fig: go.Figure) -> go.Figure:
    """Dibuja las líneas de la cancha (perímetro, mitad, círculo central)."""
    # TODO Nico: agregar áreas grande/chica y arcos en un sprint futuro.
    line = dict(color="white", width=2)
    fig.add_shape(type="rect", x0=0, y0=0, x1=FIELD_LENGTH, y1=FIELD_WIDTH, line=line)
    fig.add_shape(type="line", x0=FIELD_LENGTH / 2, y0=0, x1=FIELD_LENGTH / 2, y1=FIELD_WIDTH,
                  line=dict(color="white", width=1))
    fig.add_shape(type="circle",
                  x0=FIELD_LENGTH / 2 - 9.15, y0=FIELD_WIDTH / 2 - 9.15,
                  x1=FIELD_LENGTH / 2 + 9.15, y1=FIELD_WIDTH / 2 + 9.15,
                  line=dict(color="white", width=1))
    return fig


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _add_team_block(fig: go.Figure, players: pd.DataFrame, team_key: str) -> None:
    """Envolvente convexa (tenue) + centroide del bloque de un equipo."""
    pos = _clean_positions(players)
    if len(pos) < 3:
        return
    color = _team_color(team_key)
    hull = _convex_hull(pos)
    if len(hull) >= 3:
        ring = np.vstack([hull, hull[0]])  # cerrar el polígono
        fig.add_trace(go.Scatter(
            x=ring[:, 0], y=ring[:, 1], mode="lines",
            fill="toself", fillcolor=_hex_to_rgba(color, 0.12),
            line=dict(color=_hex_to_rgba(color, 0.5), width=1),
            hoverinfo="skip", showlegend=False,
        ))
    fig.add_trace(go.Scatter(
        x=[pos[:, 0].mean()], y=[pos[:, 1].mean()], mode="markers",
        marker=dict(symbol="x", size=11, color=color, line=dict(width=1)),
        hovertemplate="centroide<extra></extra>", showlegend=False,
    ))


def _add_players_by_team(fig: go.Figure, players: pd.DataFrame) -> None:
    """Una traza por equipo (leyenda con Local/Visitante/Sin equipo)."""
    for team_key, sub in players.groupby(players["team"].fillna("—"), dropna=False):
        fig.add_trace(go.Scatter(
            x=sub["field_x"], y=sub["field_y"],
            mode="markers+text",
            text=sub["track_id"].astype(str),
            textposition="top center",
            textfont=dict(color="white", size=9),
            marker=dict(size=14, color=_team_color(team_key),
                        line=dict(color="white", width=1)),
            name=TEAM_LABELS.get(team_key, "Sin equipo"),
            hovertemplate="track %{text}<extra></extra>",
        ))


def _add_players_by_track(fig: go.Figure, players: pd.DataFrame) -> None:
    """Fallback: un color distinto por track_id (cuando no hay columna `team`)."""
    fig.add_trace(go.Scatter(
        x=players["field_x"], y=players["field_y"],
        mode="markers+text",
        text=players["track_id"].astype(str),
        textposition="top center",
        textfont=dict(color="white", size=9),
        marker=dict(size=14,
                    color=[_track_color(t) for t in players["track_id"]],
                    line=dict(color="white", width=1)),
        showlegend=False,
        hovertemplate="track %{text}<extra></extra>",
    ))


# ── Componentes públicos (contrato con main.py) ───────────────
def render_map(df: pd.DataFrame, current_time: float) -> None:
    """Mapa 2D cenital con las posiciones de los jugadores en `current_time` (segundos)."""
    fig = go.Figure()
    _draw_field_shapes(fig)

    frame_df = _frame_at_time(df, current_time)
    players = _players(frame_df)
    has_team = "team" in df.columns

    if not players.empty:
        if has_team:
            # Bloques (envolvente + centroide) por debajo de los jugadores.
            for team_key in ("home", "away"):
                _add_team_block(fig, players[players["team"] == team_key], team_key)
            _add_players_by_team(fig, players)
        else:
            _add_players_by_track(fig, players)

    # Pelota (marker blanco, más chico)
    if "class_name" in frame_df.columns:
        ball = frame_df[frame_df["class_name"] == "ball"]
        if not ball.empty:
            fig.add_trace(go.Scatter(
                x=ball["field_x"], y=ball["field_y"], mode="markers",
                marker=dict(size=9, color=BALL_COLOR, line=dict(color="black", width=1)),
                name="Pelota", hoverinfo="skip",
            ))

    fig.update_layout(
        xaxis=dict(range=[-2, FIELD_LENGTH + 2], showgrid=False, zeroline=False, visible=False),
        yaxis=dict(range=[-2, FIELD_WIDTH + 2], showgrid=False, zeroline=False, visible=False,
                   scaleanchor="x"),
        plot_bgcolor="#2d7d3a", paper_bgcolor="#2d7d3a",
        height=420, margin=dict(l=0, r=0, t=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, font=dict(color="white")),
        showlegend=has_team,
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_team_metrics(label: str, players_df: pd.DataFrame) -> None:
    st.markdown(f"**{label}**")
    m = _block_metrics(players_df)
    if m is None:
        st.caption("Sin datos suficientes en este instante.")
        return
    c1, c2 = st.columns(2)
    c1.metric("Amplitud", f"{m['amplitud']:.1f} m", help="Ancho del bloque (eje lateral, 68 m).")
    c2.metric("Profundidad", f"{m['profundidad']:.1f} m", help="Largo del bloque (eje arco-arco, 105 m).")
    c3, c4 = st.columns(2)
    c3.metric("Área ocupada", f"{m['area']:.0f} m²", help="Superficie de la envolvente convexa del bloque.")
    c4.metric("Compacidad", f"{m['dispersion']:.1f} m", help="Distancia media al centroide (menor = más junto).")
    st.caption(f"{m['n']} jugadores en el bloque")


def render_metrics_panel(df: pd.DataFrame, current_time: float) -> None:
    """
    Panel lateral con métricas tácticas por equipo (amplitud, profundidad, área
    ocupada y compacidad del bloque) en el frame más cercano a `current_time`.
    """
    st.markdown("**Métricas en vivo**")

    frame_df = _frame_at_time(df, current_time)
    players = _players(frame_df)
    if players.empty:
        st.caption("Sin datos para este instante.")
        return

    if "team" in players.columns:
        first = True
        for team_key in ("home", "away"):
            sub = players[players["team"] == team_key]
            if sub.empty:
                continue
            if not first:
                st.divider()
            _render_team_metrics(TEAM_LABELS.get(team_key, team_key), sub)
            first = False
        # Jugadores sin equipo asignado (si los hubiera)
        unknown = players[~players["team"].isin(["home", "away"])]
        if not unknown.empty:
            st.divider()
            _render_team_metrics("⚪ Sin equipo", unknown)
    else:
        # Fallback: sin columna team, se mide el conjunto completo.
        _render_team_metrics("Bloque (todos)", players)
        st.caption("⚠️ Sin columna `team` — métricas sobre todos los jugadores juntos.")
