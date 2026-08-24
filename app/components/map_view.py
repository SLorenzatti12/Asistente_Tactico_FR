"""
Analizador Táctico — Mapa 2D y métricas
==========================================
NICO — Visualización cenital de posiciones + panel de métricas tácticas.

Recibe el DataFrame con columnas: frame, time_sec, track_id, class_name,
field_x, field_y y (opcional) team. Lo genera src/homography/calibrate.py.

Referencia de cancha: 105m (largo, eje x) x 68m (ancho, eje y),
origen (0,0) en esquina sup-izquierda.

Color por EQUIPO (decisión de equipo). Si el parquet todavía no trae la
columna `team`, cae automáticamente a un color por track_id.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

FIELD_LENGTH = 105  # eje x — arco a arco
FIELD_WIDTH = 68    # eje y — lateral a lateral

# ── Colores ──────────────────────────────────────────────────
TEAM_COLORS = {"home": "#1f77b4", "away": "#d62728"}   # azul local / rojo visitante
TEAM_LABELS = {"home": "🔵 Local", "away": "🔴 Visitante"}
UNKNOWN_COLOR = "#9e9e9e"   # jugador sin equipo asignado
BALL_COLOR = "#ffffff"

# Paleta de fallback (cuando no hay columna `team`): color por track_id.
_TRACK_PALETTE = [
    "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4",
    "#46f0f0", "#f032e6", "#bcf60c", "#008080", "#9a6324", "#800000",
    "#808000", "#000075", "#e6beff", "#fabebe",
]


# ── Helpers ──────────────────────────────────────────────────
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
    return _TRACK_PALETTE[int(track_id) % len(_TRACK_PALETTE)]


def _block_metrics(players_df: pd.DataFrame) -> dict | None:
    """
    Métricas del bloque a partir de field_x/field_y.
      - amplitud   : qué tan abierto está a lo ancho  (rango de field_y, eje 68m)
      - profundidad: distancia del más adelantado al más retrasado (rango de field_x, eje 105m)
      - area       : amplitud x profundidad, proxy de (in)compacidad del bloque (m²)
    Devuelve None si hay menos de 2 jugadores (no se puede medir un bloque).
    """
    if len(players_df) < 2:
        return None
    amplitud = float(players_df["field_y"].max() - players_df["field_y"].min())
    profundidad = float(players_df["field_x"].max() - players_df["field_x"].min())
    return {
        "amplitud": amplitud,
        "profundidad": profundidad,
        "area": amplitud * profundidad,
        "n": int(len(players_df)),
    }


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
    """Fallback: un color por track_id (cuando no hay columna `team`)."""
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
    c1.metric("Amplitud", f"{m['amplitud']:.1f} m")
    c2.metric("Profundidad", f"{m['profundidad']:.1f} m")
    st.caption(f"Área del bloque: **{m['area']:.0f} m²** · {m['n']} jugadores")


def render_metrics_panel(df: pd.DataFrame, current_time: float) -> None:
    """
    Panel lateral con métricas tácticas por equipo (amplitud, profundidad, área
    del bloque) calculadas en el frame más cercano a `current_time`.
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
