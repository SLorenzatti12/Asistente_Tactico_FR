"""
Analizador Táctico — Mapa 2D y métricas
==========================================
PERSONA B — Visualización de posiciones sobre la cancha y métricas tácticas.

Recibe el DataFrame con columnas: frame, time_sec, track_id, class_name,
field_x, field_y (generado por src/homography/calibrate.py).

Referencia de cancha: 105m x 68m, origen (0,0) en esquina sup-izquierda.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

FIELD_LENGTH = 105
FIELD_WIDTH  = 68


def _draw_field_shapes(fig: go.Figure) -> go.Figure:
    """Dibuja las líneas de la cancha (perímetro, mitad, círculo central)."""
    # TODO Persona B: agregar líneas de área grande/chica, arcos, etc.
    fig.add_shape(type="rect", x0=0, y0=0, x1=FIELD_LENGTH, y1=FIELD_WIDTH,
                   line=dict(color="white", width=2))
    fig.add_shape(type="line", x0=FIELD_LENGTH / 2, y0=0, x1=FIELD_LENGTH / 2, y1=FIELD_WIDTH,
                   line=dict(color="white", width=1))
    fig.add_shape(type="circle", x0=FIELD_LENGTH / 2 - 9.15, y0=FIELD_WIDTH / 2 - 9.15,
                   x1=FIELD_LENGTH / 2 + 9.15, y1=FIELD_WIDTH / 2 + 9.15,
                   line=dict(color="white", width=1))
    return fig


def render_map(df: pd.DataFrame, current_time: float) -> None:
    """
    Dibuja el mapa 2D cenital con las posiciones de los jugadores
    en el instante `current_time` (segundos).

    TODO Persona B:
      - Filtrar df al frame más cercano a current_time
      - Un color por track_id (o por equipo, si se llega a separar en Sprint futuro)
      - Considerar animación con st.slider ligado a current_time
      - Mostrar número de camiseta / track_id sobre cada punto
    """
    fig = go.Figure()
    fig = _draw_field_shapes(fig)

    # ── Placeholder: reemplazar por posiciones reales filtradas por tiempo ──
    nearest = df.iloc[(df["time_sec"] - current_time).abs().argsort()[:1]]
    frame_num = nearest["frame"].iloc[0] if not nearest.empty else None
    frame_df = df[df["frame"] == frame_num] if frame_num is not None else df.head(0)

    if not frame_df.empty:
        fig.add_trace(go.Scatter(
            x=frame_df["field_x"], y=frame_df["field_y"],
            mode="markers+text",
            text=frame_df["track_id"].astype(str),
            textposition="top center",
            marker=dict(size=14, color="crimson"),
        ))

    fig.update_layout(
        xaxis=dict(range=[-2, FIELD_LENGTH + 2], showgrid=False, zeroline=False, visible=False),
        yaxis=dict(range=[-2, FIELD_WIDTH + 2], showgrid=False, zeroline=False, visible=False,
                    scaleanchor="x"),
        plot_bgcolor="#2d7d3a", paper_bgcolor="#2d7d3a",
        height=420, margin=dict(l=0, r=0, t=10, b=10),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_metrics_panel(df: pd.DataFrame, current_time: float) -> None:
    """
    Panel lateral con métricas tácticas calculadas a partir de field_x/field_y.

    TODO Persona B:
      - Profundidad de bloque defensivo (necesita distinguir líneas —
        por ahora se puede aproximar con el rango de field_y de todos
        los jugadores trackeados, ya que el dataset no separa roles)
      - Evolución en el tiempo (gráfico de línea) — opcional, fase 2
      - Alertas automáticas cuando el bloque se abre más de X metros
    """
    st.markdown("**Métricas en vivo**")

    nearest = df.iloc[(df["time_sec"] - current_time).abs().argsort()[:1]]
    frame_num = nearest["frame"].iloc[0] if not nearest.empty else None
    frame_df = df[(df["frame"] == frame_num) & (df["class_name"] == "player")] if frame_num is not None else df.head(0)

    if frame_df.empty:
        st.caption("Sin datos para este instante.")
        return

    block_depth = frame_df["field_y"].max() - frame_df["field_y"].min()
    st.metric("Amplitud del bloque (aprox.)", f"{block_depth:.1f} m")
    st.caption("⚠️ Placeholder — reemplazar por cálculo real de línea defensiva vs. ofensiva "
               "cuando se tenga forma de distinguir roles.")