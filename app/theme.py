"""
Analizador Táctico — Identidad visual del sistema
====================================================
Fuente única de colores, tipografía y medidas de layout para todo el
dashboard. Ningún componente (map_view, player_stats_view, tagging,
main) debería tener un color hardcodeado propio — lo importa de acá.

Modo oscuro como base: los videos de partido y la cancha en verde se
leen mejor sobre fondo oscuro, y es el estándar de los tableros
deportivos/analíticos (Opta, Wyscout, etc.).

Sincronización con .streamlit/config.toml
------------------------------------------
Streamlit no expone su config.toml para leerlo desde Python, así que
BG_COLOR / BG_SECONDARY / TEXT_COLOR / ACCENT_COLOR de acá están
duplicados a mano en `backgroundColor` / `secondaryBackgroundColor` /
`textColor` / `primaryColor` del config.toml. Si se cambia un color acá,
cambiarlo también ahí (son solo 4 valores).

Qué va en este módulo vs. en aplicar_estilos_globales()
---------------------------------------------------------
- Colores y medidas: constantes de este archivo, siempre.
- Estilo de los gráficos Plotly: `plotly_layout_base()`.
- CSS de la app (ocultar chrome, tarjetas de métrica, espaciado):
  `aplicar_estilos_globales()`, pensada para reglas genéricas de toda
  la app. El CSS específico de un componente (p. ej. los colores del
  semáforo en tagging.py) se inyecta en ese mismo componente, tomando
  los colores de acá — así este módulo no necesita conocer el DOM de
  cada componente.
"""

import streamlit as st

# ── Identidad de marca (debe coincidir con .streamlit/config.toml) ────
BG_COLOR = "#0e1117"            # fondo principal — casi negro
BG_SECONDARY = "#181c25"        # widgets, tarjetas, fondo de gráficos analíticos
TEXT_COLOR = "#e6e9ef"          # blanco cálido, no puro (menos duro a la vista)
BORDER_COLOR = "#2a2f3a"        # bordes sutiles sobre fondo oscuro
ACCENT_COLOR = "#b45309"        # ámbar — acentos, botones primarios, métricas
ACCENT_COLOR_SOFT = "rgba(180, 83, 9, 0.16)"  # el mismo ámbar, para fondos/badges

# ── Cancha ──────────────────────────────────────────────────
FIELD_LENGTH = 105  # eje x — arco a arco (m)
FIELD_WIDTH = 68    # eje y — lateral a lateral (m)
FIELD_BG = "#2d7d3a"     # verde césped
FIELD_LINES = "#ffffff"  # líneas de cancha y texto sobre el verde

# ── Equipos ──────────────────────────────────────────────────
TEAM_COLORS = {"home": "#1f77b4", "away": "#d62728"}   # azul local / rojo visitante
TEAM_LABELS = {"home": "🔵 Local", "away": "🔴 Visitante"}
UNKNOWN_COLOR = "#9e9e9e"   # jugador sin equipo asignado
BALL_COLOR = "#ffffff"

# ── Zonas tácticas (defensa/mediocampo/ataque/arquero) ─────────
# Deliberadamente distintas de TEAM_COLORS: en el mapa de posiciones
# conviven ambas paletas (color de equipo en el mapa en vivo, color de
# zona en el análisis por jugador) y no deben confundirse entre sí.
ZONE_COLORS = {
    "arquero": "#f59e0b",
    "defensa": "#3b82f6",
    "mediocampo": "#22c55e",
    "ataque": "#ef4444",
}
ZONE_LABELS = {
    "arquero": "🧤 Arquero",
    "defensa": "🔵 Defensa",
    "mediocampo": "🟢 Mediocampo",
    "ataque": "🔴 Ataque",
}
ZONE_ORDER = ["arquero", "defensa", "mediocampo", "ataque"]

# ── Estados (semáforo, alertas) ────────────────────────────────
STATUS_COLORS = {
    "ok": "#22c55e",        # verde — destacado
    "alerta": "#eab308",    # amarillo — regular
    "critico": "#ef4444",   # rojo — bajo
}

# ── Layout de gráficos ───────────────────────────────────────
CHART_HEIGHT = 420
CHART_MARGIN = {"l": 10, "r": 10, "t": 30, "b": 10}
FONT_FAMILY = "Inter, -apple-system, 'Segoe UI', sans-serif"


# ── Plotly ───────────────────────────────────────────────────
def plotly_layout_base(*, xaxis_extra: dict | None = None, yaxis_extra: dict | None = None,
                        legend_extra: dict | None = None, **overrides) -> dict:
    """
    Layout común a todos los gráficos Plotly de la app: fondo, tipografía,
    grilla y colores de eje. Se pasa como `fig.update_layout(**plotly_layout_base(...))`.

    Pensado para charts "analíticos" (barras, dispersión de estadísticas).
    Los charts "cartográficos" (mapa 2D, scatter de posiciones sobre la
    cancha) lo usan para heredar tipografía/margen/alto y después pisan
    plot_bgcolor/paper_bgcolor (FIELD_BG) y ocultan los ejes por completo
    en una segunda llamada a update_layout — ahí la grilla no aplica.

    Args:
        xaxis_extra / yaxis_extra / legend_extra: se mezclan sobre el
            default (título, rango, orden de categorías, orientación...)
            sin perder grilla/color/tipografía. Usar esto en vez de pasar
            "xaxis"/"yaxis"/"legend" directo en overrides, que los
            reemplazaría enteros y perdería el estilo de fondo oscuro.
        overrides: cualquier otra clave de layout de Plotly; pisa el
            default tal cual (p. ej. plot_bgcolor, height, barmode).
    """
    xaxis = {"gridcolor": BORDER_COLOR, "zeroline": False, "color": TEXT_COLOR,
              "linecolor": BORDER_COLOR}
    yaxis = {"gridcolor": BORDER_COLOR, "zeroline": False, "color": TEXT_COLOR,
              "linecolor": BORDER_COLOR}
    legend = {"font": dict(color=TEXT_COLOR), "bgcolor": "rgba(0,0,0,0)"}
    xaxis.update(xaxis_extra or {})
    yaxis.update(yaxis_extra or {})
    legend.update(legend_extra or {})

    base = dict(
        paper_bgcolor=BG_COLOR,
        plot_bgcolor=BG_SECONDARY,
        font=dict(family=FONT_FAMILY, color=TEXT_COLOR, size=12),
        margin=dict(CHART_MARGIN),
        height=CHART_HEIGHT,
        legend=legend,
        hoverlabel=dict(bgcolor=BG_SECONDARY, font=dict(color=TEXT_COLOR)),
        xaxis=xaxis,
        yaxis=yaxis,
    )
    base.update(overrides)
    return base


# ── CSS global ───────────────────────────────────────────────
def aplicar_estilos_globales() -> None:
    """
    CSS de toda la app — llamar una sola vez, al principio de main.py.

    Cubre lo que .streamlit/config.toml no puede resolver por sí solo:
    ocultar chrome de Streamlit, afinar espaciado entre secciones, y
    convertir las métricas en tarjetas con borde. Los colores base
    (fondo, texto, tipografía) ya los pone el tema nativo — acá no se
    redefinen, solo se referencian para las tarjetas.

    Nota: los selectores `data-testid` son parte del DOM interno de
    Streamlit y pueden cambiar en versiones futuras; si dejan de tener
    efecto tras un upgrade, es el primer lugar donde mirar.
    """
    st.markdown(f"""
    <style>
      /* Oculta el menú hamburguesa y el footer "Made with Streamlit" */
      #MainMenu {{ visibility: hidden; }}
      footer {{ visibility: hidden; }}

      /* Más aire arriba del contenido y entre pestañas */
      .block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; }}
      div[data-testid="stTabs"] {{ margin-top: 0.5rem; }}

      /* Tarjetas de métrica: borde sutil + esquinas redondeadas */
      div[data-testid="stMetric"] {{
          background-color: {BG_SECONDARY};
          border: 1px solid {BORDER_COLOR};
          border-radius: 10px;
          padding: 0.9rem 1.1rem 0.7rem 1.1rem;
      }}
      div[data-testid="stMetricLabel"] {{ opacity: 0.75; }}

      /* Números de métrica alineados (tabular), look de tablero de datos */
      div[data-testid="stMetricValue"] {{
          font-variant-numeric: tabular-nums;
          letter-spacing: -0.02em;
      }}
    </style>
    """, unsafe_allow_html=True)
