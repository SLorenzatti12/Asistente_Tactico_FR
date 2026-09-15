"""
Analizador Táctico — Tagueo, Semáforo y persistencia
========================================================
PERSONA C — Botones de tagueo one-click, timeline + tarjetas de eventos
(editar/eliminar con modales), formulario de semáforo post-partido, y
guardado en SQLite.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_sortables import sort_items

# Mismos colores/etiquetas que usa el mapa 2D, para que "Local"/"Visitante"
# se vea igual en todos lados (ver components/map_view.py).
from components.map_view import TEAM_COLORS, TEAM_LABELS

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "db" / "analizador.sqlite"
ROSTER_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "roster.json"

# Semilla de event_types la primera vez que se crea la tabla (ver init_db).
# Ya no es la lista "viva" de botones — eso ahora sale de la base.
_DEFAULT_TAG_TYPES = ["Presión", "Salida", "Transición", "Pelota parada"]
TEAM_OPTIONS = ["home", "away"]
SCOPE_OPTIONS = ["home", "away", "both"]
SCOPE_LABELS = {"home": "Solo Local", "away": "Solo Visitante", "both": "Ambos equipos"}

# Colchón hacia atrás al tagear "ahora": la jugada se ve unos segundos antes
# de llegar a tocar el botón, así que se guarda current_time - N (piso en 0).
# Un solo lugar para cambiarlo si hace falta ajustar el valor.
TAG_TIME_BUFFER_SEC = 10


def format_time(seconds: float) -> str:
    """Segundos crudos a mm:ss, para que el log se lea como un video y no como un timestamp."""
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _nice_time_ticks(max_time: float, target_count: int = 6) -> list[float]:
    """Posiciones de eje en segundos, en pasos 'redondos' (30s/1min/5min/...),
    para el eje X del timeline — ver _render_events_timeline."""
    steps = [15, 30, 60, 120, 300, 600, 900, 1800, 3600]
    step = steps[-1]
    for s in steps:
        if max_time / s <= target_count:
            step = s
            break
    n_ticks = int(max_time // step) + 1
    return [i * step for i in range(n_ticks + 1)]


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


# ── Base de datos ─────────────────────────────────────────────
def init_db() -> None:
    """
    Crea las tablas si no existen, y migra `events` agregando la columna
    `team` si la base ya existía de antes (creada sin esa columna).
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_name TEXT,
            tag_type TEXT,
            time_sec REAL,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS semaforo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_name TEXT,
            player_number INTEGER,
            rating TEXT,
            created_at TEXT
        )
    """)

    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()}
    if "team" not in existing_cols:
        conn.execute("ALTER TABLE events ADD COLUMN team TEXT")

    # Chequeo ANTES del CREATE: si la tabla ya existía (aunque hoy esté
    # vacía porque alguien borró todos los tipos a propósito), no la
    # volvemos a sembrar — solo se siembra la primera vez que se crea.
    event_types_existed = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='event_types'"
    ).fetchone() is not None

    conn.execute("""
        CREATE TABLE IF NOT EXISTS event_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            scope TEXT NOT NULL CHECK(scope IN ('home', 'away', 'both'))
        )
    """)

    if not event_types_existed:
        conn.executemany(
            "INSERT INTO event_types (name, scope) VALUES (?, 'both')",
            [(name,) for name in _DEFAULT_TAG_TYPES],
        )

    # Migración aditiva para el orden manual (drag-and-drop) POR EQUIPO: dos
    # columnas en vez de una sola, porque un mismo tipo puede ir en distinta
    # posición para Local que para Visitante.
    event_type_cols = {row[1] for row in conn.execute("PRAGMA table_info(event_types)").fetchall()}
    if "sort_order_home" not in event_type_cols:
        conn.execute("ALTER TABLE event_types ADD COLUMN sort_order_home INTEGER")
        conn.execute("ALTER TABLE event_types ADD COLUMN sort_order_away INTEGER")
        if "sort_order" in event_type_cols:
            # Ya existía un único orden (de antes de separar por equipo) —
            # se usa como punto de partida para las dos listas nuevas, así
            # no se pierde el orden que ya se había armado a mano. Queda
            # como punto de partida común; a partir de acá pueden divergir.
            conn.execute("UPDATE event_types SET sort_order_home = sort_order, sort_order_away = sort_order")
        else:
            for i, (row_id,) in enumerate(conn.execute("SELECT id FROM event_types ORDER BY id").fetchall()):
                conn.execute(
                    "UPDATE event_types SET sort_order_home = ?, sort_order_away = ? WHERE id = ?",
                    (i, i, row_id),
                )

    # Emoji opcional por tipo, para el timeline (ver _render_events_timeline).
    if "emoji" not in event_type_cols:
        conn.execute("ALTER TABLE event_types ADD COLUMN emoji TEXT")

    conn.commit()
    conn.close()


def save_event(match_name: str, tag_type: str, time_sec: float, team: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO events (match_name, tag_type, time_sec, team, created_at) VALUES (?, ?, ?, ?, ?)",
        (match_name, tag_type, time_sec, team, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def update_event(event_id: int, tag_type: str, time_sec: float, team: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE events SET tag_type = ?, time_sec = ?, team = ? WHERE id = ?",
        (tag_type, time_sec, team, event_id),
    )
    conn.commit()
    conn.close()


def delete_event(event_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()


# ── Tipos de evento (botones configurables) ─────────────────────
_SORT_COL = {"home": "sort_order_home", "away": "sort_order_away"}


def get_all_event_types() -> list[dict]:
    """Todos los tipos de evento (cualquier equipo), por orden de creación — usado
    para el dropdown de "re-tipear" un evento histórico en _edit_event_dialog,
    donde el orden por equipo no aplica."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id, name, scope, emoji FROM event_types ORDER BY id").fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "scope": r[2], "emoji": r[3] or ""} for r in rows]


def get_event_types_for_team(team: str) -> list[dict]:
    """Tipos visibles para tagear con este equipo activo (scope propio o 'both'),
    en el orden manual PROPIO de ese equipo (sort_order_home / sort_order_away)."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        f"SELECT id, name, scope, emoji FROM event_types WHERE scope = ? OR scope = 'both' ORDER BY {_SORT_COL[team]}",
        (team,),
    ).fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "scope": r[2], "emoji": r[3] or ""} for r in rows]


def reorder_event_types(team: str, ordered_names: list[str]) -> None:
    """Aplica el nuevo orden (de streamlit_sortables, que trabaja con nombres) SOLO
    a la columna de orden de `team` — el orden del otro equipo no se toca."""
    conn = sqlite3.connect(DB_PATH)
    col = _SORT_COL[team]
    for i, name in enumerate(ordered_names):
        conn.execute(f"UPDATE event_types SET {col} = ? WHERE name = ?", (i, name))
    conn.commit()
    conn.close()


def create_event_type(name: str, scope: str, emoji: str = "") -> tuple[bool, str]:
    """(ok, mensaje). Falla si el nombre está vacío o ya existe (UNIQUE). Se agrega
    al final del orden de cada equipo al que aplique según `scope`. `emoji` es opcional."""
    name = name.strip()
    if not name:
        return False, "El nombre no puede estar vacío."
    conn = sqlite3.connect(DB_PATH)
    try:
        order_home = order_away = None
        if scope in ("home", "both"):
            order_home = conn.execute("SELECT COALESCE(MAX(sort_order_home), -1) + 1 FROM event_types").fetchone()[0]
        if scope in ("away", "both"):
            order_away = conn.execute("SELECT COALESCE(MAX(sort_order_away), -1) + 1 FROM event_types").fetchone()[0]
        conn.execute(
            "INSERT INTO event_types (name, scope, sort_order_home, sort_order_away, emoji) VALUES (?, ?, ?, ?, ?)",
            (name, scope, order_home, order_away, emoji.strip() or None),
        )
        conn.commit()
        return True, f'Tipo "{name}" creado.'
    except sqlite3.IntegrityError:
        return False, f'Ya existe un tipo de evento llamado "{name}".'
    finally:
        conn.close()


def update_event_type(type_id: int, name: str, scope: str, emoji: str = "") -> tuple[bool, str]:
    """
    (ok, mensaje). No toca `events` — los eventos ya tagueados conservan el nombre viejo.
    Si el nuevo scope agrega un equipo que este tipo no tenía antes (ej. pasa de
    "Solo Local" a "Ambos"), le asigna un sort_order al final de la lista de ese
    equipo — si no, quedaría sin orden y no aparecería en el drag-and-drop.
    """
    name = name.strip()
    if not name:
        return False, "El nombre no puede estar vacío."
    conn = sqlite3.connect(DB_PATH)
    try:
        for team, col in _SORT_COL.items():
            if scope in (team, "both"):
                current = conn.execute(f"SELECT {col} FROM event_types WHERE id = ?", (type_id,)).fetchone()[0]
                if current is None:
                    next_order = conn.execute(f"SELECT COALESCE(MAX({col}), -1) + 1 FROM event_types").fetchone()[0]
                    conn.execute(f"UPDATE event_types SET {col} = ? WHERE id = ?", (next_order, type_id))
        conn.execute(
            "UPDATE event_types SET name = ?, scope = ?, emoji = ? WHERE id = ?",
            (name, scope, emoji.strip() or None, type_id),
        )
        conn.commit()
        return True, f'Tipo actualizado a "{name}".'
    except sqlite3.IntegrityError:
        return False, f'Ya existe un tipo de evento llamado "{name}".'
    finally:
        conn.close()


def delete_event_type(type_id: int) -> None:
    """Borra el tipo de la lista de botones. No toca `events`: el historial queda intacto."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM event_types WHERE id = ?", (type_id,))
    conn.commit()
    conn.close()


def save_semaforo(match_name: str, player_number: int, rating: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO semaforo (match_name, player_number, rating, created_at) VALUES (?, ?, ?, ?)",
        (match_name, player_number, rating, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_events(match_name: str) -> pd.DataFrame:
    """
    Todos los eventos tagueados de este partido (id incluido), orden cronológico.
    El emoji sale de un LEFT JOIN por nombre contra event_types — es un lookup
    "mejor esfuerzo" (no una FK real, ver decisión de diseño de tag_type como
    texto libre): si el tipo fue renombrado o borrado, el evento viejo queda
    sin emoji en vez de romper o mostrar uno incorrecto.
    """
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT e.id, e.team, e.tag_type, e.time_sec, et.emoji
        FROM events e
        LEFT JOIN event_types et ON et.name = e.tag_type
        WHERE e.match_name = ?
        ORDER BY e.time_sec ASC
        """,
        conn,
        params=(match_name,),
    )
    conn.close()
    return df


def load_roster(match_name: str) -> list[dict]:
    """
    Nómina real (número + nombre) para este partido, leída de data/roster.json.
    Si no hay nómina cargada para este match_name, cae a números sueltos del
    1 al 11 para no romper la pantalla de semáforo mientras tanto.
    """
    if ROSTER_PATH.exists():
        try:
            data = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        roster = data.get(match_name)
        if roster:
            return roster
    return [{"number": n, "name": f"Jugador #{n}"} for n in range(1, 12)]


# ── Fondo según equipo activo ───────────────────────────────────
def _inject_team_background(team: str) -> None:
    """
    Tinte suave + borde del color del equipo sobre el contenedor con
    key="tagging_section" (más abajo). Streamlit genera la clase CSS
    `.st-key-<key>` específicamente para poder engancharle estilos así —
    es un mecanismo soportado, aunque no forma parte de la API pública
    "oficial" de widgets, así que si una futura versión de Streamlit
    cambia esa convención, esto se degrada en silencio (deja de pintarse,
    no rompe nada).
    """
    color = TEAM_COLORS[team]
    st.markdown(
        f"""
        <style>
        .st-key-tagging_section {{
            background-color: {_hex_to_rgba(color, 0.13)};
            border-left: 4px solid {color};
            border-radius: 8px;
            padding: 0.9rem 1rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── Salto al segundo de un evento ───────────────────────────────
def _request_seek(time_sec: float) -> None:
    """
    Pide mover session_state["current_time"] a `time_sec`. Usado tanto por
    el click en el timeline como por el click en una tarjeta de evento —
    ver la nota sobre `_pending_seek_time` en main.py (no se puede
    reasignar acá directamente porque el slider ya se instanció más arriba
    en esta misma corrida).
    """
    if time_sec != st.session_state.get("current_time"):
        st.session_state["_pending_seek_time"] = time_sec
        st.rerun()


# Paletas del timeline por modo — Plotly dibuja su propio SVG, así que el
# CSS de main.py no lo puede recolorear desde afuera. Se resuelve leyendo
# session_state["theme_mode"] (el mismo switch del header) acá directo.
_CHART_STYLE = {
    "dark": dict(bg="#111", grid="#333", zero="#444", font="white"),
    "light": dict(bg="#ffffff", grid="#e1e4e8", zero="#d0d7de", font="#1f2328"),
}

# ── Geometría del timeline (marcador + emoji) ──────────────────
# Medido sobre el PNG real exportado con kaleido, no estimado:
#
# - El emoji de 13px dentro de un marcador de 16px dejaba un anillo de
#   ~1.5px. Con un glyph que llena su caja (🔴 es un círculo pleno) el
#   anillo se veía solo como una medialuna abajo y el emoji se desbordaba
#   arriba — eso es lo que se reportó como "el emoji sobresale del círculo".
#   Con 22 vs 12 queda un anillo parejo de ~5px alrededor del emoji.
#
# - Además el glyph se dibuja ~1.3px ARRIBA del punto: Plotly centra el
#   texto por la caja de línea de la fuente (que incluye ascendente y
#   descendente), no por la tinta visible del emoji. No hay parámetro de
#   offset en un trace de texto, así que se compensa en unidades de dato,
#   calculadas desde la geometría del gráfico (abajo) en vez de hardcodear
#   un número que se rompa si cambia la altura.
_MARKER_SIZE = 22
_EMOJI_SIZE = 12
_CHART_HEIGHT = 240
_CHART_MARGIN_T, _CHART_MARGIN_B = 10, 40
_Y_RANGE = (-2, 2)
_EMOJI_BASELINE_SHIFT_PX = 1.3

# px → unidades del eje Y, para bajar el emoji lo que la fuente lo sube.
_EMOJI_Y_OFFSET = -_EMOJI_BASELINE_SHIFT_PX * (
    (_Y_RANGE[1] - _Y_RANGE[0]) / (_CHART_HEIGHT - _CHART_MARGIN_T - _CHART_MARGIN_B)
)


# ── Timeline de eventos (Plotly) ───────────────────────────────
def _build_timeline_figure(events_df: pd.DataFrame, current_time: float, style: dict) -> go.Figure:
    """
    Arma la figura del timeline. Separada del render para poder exportarla a
    PNG (kaleido) y revisarla píxel a píxel sin levantar Streamlit — el
    centrado del emoji ya se reportó mal tres veces mirando solo el código.
    """
    fig = go.Figure()
    for team_key, y in (("home", 1), ("away", -1)):
        sub = events_df[events_df["team"] == team_key]
        if sub.empty:
            continue

        # Tallos (estilo lollipop): una línea del eje central (y=0, la
        # misma horizontal que separa Local/Visitante) hasta cada punto.
        # Se dibuja ANTES que los marcadores para que quede detrás. Los
        # "None" entre tallos cortan la línea para que Plotly no una un
        # tallo con el siguiente en un solo zigzag.
        stem_x, stem_y = [], []
        for t in sub["time_sec"]:
            stem_x += [t, t, None]
            stem_y += [0, y, None]
        fig.add_trace(go.Scatter(
            x=stem_x, y=stem_y, mode="lines",
            line=dict(color=TEAM_COLORS[team_key], width=1.5),
            hoverinfo="skip", showlegend=False,
        ))

        # mm:ss precalculado con la misma format_time() de siempre — el
        # hovertemplate de Plotly no puede llamar funciones Python, así que
        # va como un campo más de customdata en vez de formatear "a mano"
        # con %{x:.0f}s (eso era lo que mostraba segundos crudos en el hover).
        formatted = sub["time_sec"].apply(format_time)
        fig.add_trace(go.Scatter(
            x=sub["time_sec"], y=[y] * len(sub),
            mode="markers+text",
            text=sub["tag_type"],
            textposition="top center" if y > 0 else "bottom center",
            textfont=dict(color=style["font"], size=10),
            marker=dict(size=_MARKER_SIZE, color=TEAM_COLORS[team_key], line=dict(color=style["font"], width=1)),
            customdata=list(zip(sub["id"], sub["time_sec"], formatted)),
            hovertemplate="%{text} — %{customdata[2]}<extra></extra>",
            showlegend=False,
        ))

        # Emoji centrado sobre el mismo punto, solo para los eventos cuyo
        # tipo tiene uno asignado — capa de texto aparte porque un mismo
        # trace de Plotly no puede tener dos textposition distintos (el
        # nombre arriba/abajo Y el emoji centrado).
        #
        # Horizontalmente el centrado ya era correcto (medido: desvío de
        # 0.1px). Lo que estaba mal era el eje vertical y la proporción —
        # ver _MARKER_SIZE / _EMOJI_Y_OFFSET arriba. Un emoji asimétrico como
        # 🚩 (asta a la izquierda, bandera colgando a la derecha) igual va a
        # verse corrido en horizontal, porque SU PROPIO glyph no está
        # centrado en la fuente: conviene usar emoji redondos/simétricos.
        with_emoji = sub[sub["emoji"].fillna("") != ""]
        if not with_emoji.empty:
            emoji_formatted = with_emoji["time_sec"].apply(format_time)
            fig.add_trace(go.Scatter(
                x=with_emoji["time_sec"], y=[y + _EMOJI_Y_OFFSET] * len(with_emoji),
                mode="text",
                text=with_emoji["emoji"],
                textposition="middle center",
                textfont=dict(size=_EMOJI_SIZE),
                customdata=list(zip(with_emoji["id"], with_emoji["time_sec"], emoji_formatted)),
                hovertemplate="%{text} — %{customdata[2]}<extra></extra>",
                showlegend=False,
            ))

    fig.add_vline(x=current_time, line=dict(color="#ffd166", dash="dash", width=2))

    # Marcas del eje en mm:ss (misma format_time que "Editar eventos"), en
    # vez de segundos crudos — más fácil de leer contra un partido de 40 min.
    max_t = max(float(events_df["time_sec"].max()), current_time, 1.0)
    tickvals = _nice_time_ticks(max_t)

    fig.update_layout(
        # Estos valores no son decorativos: _EMOJI_Y_OFFSET se calcula a
        # partir de ellos (altura, márgenes y rango de Y). Si cambian acá,
        # tienen que cambiar en las constantes de arriba.
        yaxis=dict(range=list(_Y_RANGE), tickvals=[-1, 1], ticktext=["Visitante", "Local"],
                   showgrid=False, zeroline=True, zerolinecolor=style["zero"]),
        xaxis=dict(title="Momento del partido (mm:ss)", showgrid=True, gridcolor=style["grid"],
                   tickmode="array", tickvals=tickvals, ticktext=[format_time(t) for t in tickvals]),
        height=_CHART_HEIGHT, margin=dict(l=60, r=10, t=_CHART_MARGIN_T, b=_CHART_MARGIN_B),
        plot_bgcolor=style["bg"], paper_bgcolor=style["bg"], font=dict(color=style["font"]),
    )
    return fig


def _render_events_timeline(events_df: pd.DataFrame, current_time: float) -> None:
    """
    Local arriba / Visitante abajo, línea vertical en el segundo actual.
    Al clickear un punto, saltamos current_time a ese evento (ver la nota
    sobre `_pending_seek_time` en main.py: no se puede reasignar acá mismo
    porque el slider ya se instanció más arriba en esta misma corrida).
    """
    if events_df.empty:
        st.caption("Todavía no hay eventos tagueados para este partido.")
        return

    style = _CHART_STYLE[st.session_state.get("theme_mode", "dark")]
    fig = _build_timeline_figure(events_df, current_time, style)

    selection = st.plotly_chart(
        fig, use_container_width=True, on_select="rerun",
        selection_mode="points", key="events_timeline",
    )

    points = selection.selection.get("points", []) if selection else []
    if points:
        _request_seek(float(points[0]["customdata"][1]))


# ── Comparativa por tipo de evento (Plotly) ─────────────────────
def _render_events_comparison(events_df: pd.DataFrame) -> None:
    """Barras agrupadas Local vs Visitante: cuántas veces se tagueó cada tipo de evento."""
    if events_df.empty:
        st.caption("Todavía no hay eventos tagueados para este partido.")
        return

    style = _CHART_STYLE[st.session_state.get("theme_mode", "dark")]
    counts = events_df.groupby(["tag_type", "team"]).size().reset_index(name="count")

    fig = go.Figure()
    for team_key in ("home", "away"):
        sub = counts[counts["team"] == team_key]
        if sub.empty:
            continue
        fig.add_trace(go.Bar(
            x=sub["tag_type"], y=sub["count"],
            name=TEAM_LABELS[team_key],
            marker_color=TEAM_COLORS[team_key],
        ))

    fig.update_layout(
        barmode="group",
        height=240, margin=dict(l=40, r=10, t=10, b=40),
        plot_bgcolor=style["bg"], paper_bgcolor=style["bg"], font=dict(color=style["font"]),
        xaxis=dict(gridcolor=style["grid"]),
        yaxis=dict(title="Cantidad", gridcolor=style["grid"], zerolinecolor=style["zero"]),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
    )
    st.plotly_chart(fig, use_container_width=True, key="events_comparison")


# ── Editar / eliminar eventos (tarjetas + modales) ──────────────
@st.dialog("Editar evento")
def _edit_event_dialog(event: dict) -> None:
    # El tipo del evento puede haber sido borrado/renombrado desde que se
    # tageó (events.tag_type es texto libre, sin FK a event_types — ver
    # decisión de diseño). Si ya no está entre los tipos activos, se agrega
    # como opción extra para no romper el dropdown ni forzar un cambio.
    options = [et["name"] for et in get_all_event_types()]
    if event["tag_type"] not in options:
        options = options + [event["tag_type"]]
    tag_type = st.selectbox("Evento", options, index=options.index(event["tag_type"]), filter_mode=None)
    team = st.selectbox(
        "Equipo", TEAM_OPTIONS, index=TEAM_OPTIONS.index(event["team"]),
        format_func=lambda t: TEAM_LABELS[t], filter_mode=None,
    )
    time_sec = st.number_input("Segundo", min_value=0.0, step=1.0, value=float(event["time_sec"]))

    col_save, col_cancel = st.columns(2)
    if col_save.button("Guardar", use_container_width=True, type="primary"):
        update_event(int(event["id"]), tag_type, float(time_sec), team)
        st.rerun()
    if col_cancel.button("Cancelar", use_container_width=True):
        st.rerun()


@st.dialog("Eliminar evento")
def _delete_event_dialog(event: dict) -> None:
    st.write(
        f"¿Seguro que querés eliminar **{event['tag_type']}** "
        f"({TEAM_LABELS[event['team']]}, {format_time(event['time_sec'])})?"
    )
    col_confirm, col_cancel = st.columns(2)
    if col_confirm.button("Eliminar", use_container_width=True, type="primary"):
        delete_event(int(event["id"]))
        st.rerun()
    if col_cancel.button("Cancelar", use_container_width=True):
        st.rerun()


# ── Gestión de tipos de evento (botones configurables) ──────────
# Un único @st.dialog con "vistas" internas (lista / editar / eliminar)
# controladas por session_state, en vez de tres diálogos separados que se
# abren uno desde el otro: confirmado que Streamlit no permite eso — abrir
# un @st.dialog desde dentro de otro ya abierto no tira error, pero cierra
# todo en silencio (probado con AppTest antes de programar esto).
def _render_edit_type_view(type_id: int) -> None:
    event_type = next((t for t in get_all_event_types() if t["id"] == type_id), None)
    if event_type is None:  # lo borraron desde otra sesión mientras tanto
        st.session_state.pop("_editing_type_id", None)
        st.rerun()
        return

    name = st.text_input("Nombre", value=event_type["name"])
    emoji = st.text_input("Emoji (opcional)", value=event_type["emoji"], max_chars=4, placeholder="⚽")
    scope = st.selectbox(
        "Aparece para", SCOPE_OPTIONS, index=SCOPE_OPTIONS.index(event_type["scope"]),
        format_func=lambda s: SCOPE_LABELS[s], filter_mode=None,
    )
    col_save, col_cancel = st.columns(2)
    if col_save.button("Guardar", use_container_width=True, type="primary"):
        ok, msg = update_event_type(type_id, name, scope, emoji)
        if ok:
            st.session_state.pop("_editing_type_id", None)
            st.rerun()
        else:
            st.error(msg)
    if col_cancel.button("Volver", use_container_width=True):
        st.session_state.pop("_editing_type_id", None)
        st.rerun()


def _render_delete_type_view(type_id: int) -> None:
    event_type = next((t for t in get_all_event_types() if t["id"] == type_id), None)
    if event_type is None:
        st.session_state.pop("_deleting_type_id", None)
        st.rerun()
        return

    st.write(f'¿Seguro que querés eliminar "{event_type["name"]}"?')
    st.caption("Los eventos ya tagueados con este nombre no se modifican ni se borran — solo deja de aparecer como botón.")
    col_confirm, col_cancel = st.columns(2)
    if col_confirm.button("Eliminar", use_container_width=True, type="primary"):
        delete_event_type(type_id)
        st.session_state.pop("_deleting_type_id", None)
        st.rerun()
    if col_cancel.button("Volver", use_container_width=True):
        st.session_state.pop("_deleting_type_id", None)
        st.rerun()


def _render_type_list_view() -> None:
    col_header, col_new = st.columns([4, 1])
    col_header.markdown("**Tipos de evento**")
    # st.popover en vez de un segundo st.dialog: confirmado con AppTest que
    # Streamlit no permite anidar dialogs (tira StreamlitInvalidLayoutContextError),
    # pero un popover sí puede vivir adentro de un dialog ya abierto.
    #
    # Sin use_container_width (antes estiraba el botón al ancho de la
    # columna angosta y "Nuevo tipo" se cortaba en "..."). La flechita ⌄
    # es parte fija del widget, sin parámetro para sacarla — el CSS de
    # abajo apunta al ícono interno por prueba, no pude confirmarlo en un
    # navegador real; si sigue apareciendo, avisame.
    st.markdown(
        '<style>.st-key-new_type_popover button svg { display: none !important; }</style>',
        unsafe_allow_html=True,
    )
    with col_new.popover("➕", key="new_type_popover", help="Crear un tipo de evento nuevo"):
        st.markdown("**Crear tipo nuevo**")
        new_name = st.text_input("Nombre", key="new_event_type_name", placeholder='Ej: "Falta táctica"')
        new_emoji = st.text_input("Emoji (opcional)", key="new_event_type_emoji", max_chars=4, placeholder="⚽")
        new_scope = st.selectbox(
            "Aparece para", SCOPE_OPTIONS, key="new_event_type_scope",
            format_func=lambda s: SCOPE_LABELS[s], filter_mode=None,
        )
        if st.button("Crear", key="create_event_type_btn", type="primary"):
            ok, msg = create_event_type(new_name, new_scope, new_emoji)
            if ok:
                st.success(msg)
                del st.session_state["new_event_type_name"]  # limpia los campos para el próximo
                del st.session_state["new_event_type_emoji"]
                st.rerun()
            else:
                st.error(msg)

    # El orden es por equipo (sort_order_home / sort_order_away), así que la
    # gestión también necesita saber para cuál equipo estás mirando/arrastrando.
    manage_team = st.segmented_control(
        "Equipo",
        options=TEAM_OPTIONS,
        format_func=lambda t: "🔵 Local" if t == "home" else "🔴 Visitante",
        default="home",
        key="manage_types_team",
        label_visibility="collapsed",
    ) or "home"

    types = get_event_types_for_team(manage_team)
    names = [et["name"] for et in types]

    if names:
        st.caption("Arrastrá para reordenar — así van a aparecer los botones de tagueo para este equipo.")
        # sort_items trabaja con strings planos, no con filas con botones —
        # por eso la lista de arrastre (solo nombres) queda separada de las
        # filas de editar/eliminar de abajo, en vez de una sola lista.
        new_order = sort_items(names, direction="vertical", key=f"event_types_sort_{manage_team}")
        if new_order != names:
            reorder_event_types(manage_team, new_order)
            st.rerun()
            return
    else:
        st.caption("Todavía no hay tipos para este equipo.")

    st.divider()
    ring_color = TEAM_COLORS[manage_team]
    for et in types:
        col_info, col_edit, col_delete = st.columns([6, 1, 1])
        if et["emoji"]:
            # Anillo de color detrás del emoji (no se puede trazar el
            # contorno real del glyph — ver la conversación sobre esto).
            col_info.markdown(
                f"<span style='display:inline-flex;align-items:center;justify-content:center;"
                f"width:1.6em;height:1.6em;border-radius:50%;background:{ring_color};"
                f"margin-right:0.4em;font-size:0.95em;'>{et['emoji']}</span>"
                f"**{et['name']}** — {SCOPE_LABELS[et['scope']]}",
                unsafe_allow_html=True,
            )
        else:
            col_info.write(f"**{et['name']}** — {SCOPE_LABELS[et['scope']]}")
        if col_edit.button("", icon=":material/edit:", key=f"edit_type_{et['id']}", use_container_width=True):
            st.session_state["_editing_type_id"] = et["id"]
            st.rerun()
        if col_delete.button("", icon=":material/delete:", key=f"delete_type_{et['id']}", use_container_width=True):
            st.session_state["_deleting_type_id"] = et["id"]
            st.rerun()


def _close_manage_types_dialog() -> None:
    """Callback de on_dismiss: si cierran con la X, hay que apagar la bandera
    de abajo a mano — si no, el diálogo se "reabriría solo" en la próxima
    interacción cualquiera que tenga la app (confirmado: sin esto, cerrar
    con la X no alcanza para que se mantenga cerrado)."""
    st.session_state.pop("_show_manage_types_dialog", None)
    st.session_state.pop("_editing_type_id", None)
    st.session_state.pop("_deleting_type_id", None)


@st.dialog("Gestionar tipos de evento", on_dismiss=_close_manage_types_dialog)
def _manage_event_types_dialog() -> None:
    editing_id = st.session_state.get("_editing_type_id")
    deleting_id = st.session_state.get("_deleting_type_id")

    if editing_id is not None:
        _render_edit_type_view(editing_id)
    elif deleting_id is not None:
        _render_delete_type_view(deleting_id)
    else:
        _render_type_list_view()


def _render_events_cards(events_df: pd.DataFrame) -> None:
    """Una tarjeta por evento — nada de grilla tipo Excel."""
    st.markdown("**Editar eventos**")
    if events_df.empty:
        st.caption("Todavía no hay eventos tagueados para este partido.")
        return

    for _, row in events_df.iterrows():
        event = row.to_dict()
        team_key = event["team"] if event["team"] in TEAM_OPTIONS else "home"

        with st.container(border=True):
            col_info, col_edit, col_delete = st.columns([6, 1, 1])

            card_label = f"{event['tag_type']} · {TEAM_LABELS[team_key]} · {format_time(event['time_sec'])}"
            if col_info.button(card_label, key=f"seek_{event['id']}", type="tertiary", use_container_width=True):
                _request_seek(float(event["time_sec"]))

            if col_edit.button("", icon=":material/edit:", key=f"edit_{event['id']}", use_container_width=True):
                _edit_event_dialog(event)
            if col_delete.button("", icon=":material/delete:", key=f"delete_{event['id']}", use_container_width=True):
                _delete_event_dialog(event)


# ── Componentes de UI ──────────────────────────────────────────
def render_tagging_panel() -> None:
    """Selector de equipo + botones de tagueo one-click + timeline + tarjetas."""
    match_name = st.session_state.get("selected_match", "sin_partido")
    current_time = st.session_state.get("current_time", 0)

    # El fondo depende del equipo ya elegido en la corrida anterior (persiste
    # en session_state por el key="tag_team" del control de más abajo), así
    # el contenedor ya nace pintado del color correcto en esta misma corrida.
    active_team = st.session_state.get("tag_team") or "home"
    _inject_team_background(active_team)

    with st.container(key="tagging_section"):
        col_title, col_manage = st.columns([4, 1])
        col_title.markdown("**Tagueo one-click**")
        # Bandera persistente en vez de "if st.button(...): dialog()": esta
        # segunda forma solo funciona en la corrida inmediatamente después
        # del click — cualquier interacción DENTRO del diálogo (editar,
        # volver) dispara una corrida nueva donde el botón ya no está en
        # True, y el diálogo se cerraría solo. Confirmado con AppTest antes
        # de dejarlo así.
        if col_manage.button("⚙️", key="open_manage_types", use_container_width=True, help="Gestionar tipos de evento"):
            st.session_state["_show_manage_types_dialog"] = True
        if st.session_state.get("_show_manage_types_dialog"):
            _manage_event_types_dialog()

        # Selector de equipo grande y con color propio, para que se note de
        # un vistazo en qué modo está sin frenar el flujo con un paso de
        # confirmación aparte (eso te haría perder la jugada).
        team = st.segmented_control(
            "Equipo",
            options=TEAM_OPTIONS,
            format_func=lambda t: "🔵 LOCAL" if t == "home" else "🔴 VISITANTE",
            default="home",
            key="tag_team",
            label_visibility="collapsed",
        )
        if team is None:  # el usuario puede deseleccionar el segmented_control
            team = "home"
        st.markdown(f"#### Tagueando para: {TEAM_LABELS[team]}")

        event_types = get_event_types_for_team(team)
        if not event_types:
            st.caption("No hay tipos de evento configurados para este equipo — agregá uno con el ⚙️ de arriba.")
        else:
            cols = st.columns(2)
            for i, et in enumerate(event_types):
                if cols[i % 2].button(et["name"], use_container_width=True, key=f"tag_btn_{et['id']}"):
                    saved_time = max(0.0, current_time - TAG_TIME_BUFFER_SEC)
                    save_event(match_name, et["name"], saved_time, team)
                    st.toast(f"Tag guardado: {et['name']} @ {format_time(saved_time)} ({TEAM_LABELS[team]})")
                    st.rerun()

        st.divider()
        events_df = get_events(match_name)

        # Mismo patrón que Métricas/Tagueo en main.py: tabs en vez de
        # apilar los dos gráficos, así no crece la pantalla en vivo.
        tab_timeline, tab_comparison = st.tabs(["Momentos del partido", "Comparativa por tipo"])
        with tab_timeline:
            _render_events_timeline(events_df, current_time)
        with tab_comparison:
            _render_events_comparison(events_df)

        st.divider()
        _render_events_cards(events_df)


def render_semaforo_tab(match_name: str) -> None:
    """
    Formulario de calificación individual post-partido (🔴🟡🟢 por jugador).

    TODO Persona C:
      - Mostrar resumen de calificaciones ya guardadas para este partido
    """
    st.markdown("**Semáforo post-partido**")
    st.caption("Calificación individual — hacé clic para evaluar a cada jugador.")

    roster = load_roster(match_name)
    if all(p["name"].startswith("Jugador #") for p in roster):
        st.caption("⚠️ Nómina no cargada todavía para este partido — mostrando números sueltos (ver data/roster.json).")

    for player in roster:
        n = player["number"]
        col_num, col_btns = st.columns([1, 3])
        col_num.write(f"**#{n}** {player['name']}")
        b1, b2, b3 = col_btns.columns(3)
        if b1.button("🔴", key=f"low_{n}"):
            save_semaforo(match_name, n, "bajo")
        if b2.button("🟡", key=f"mid_{n}"):
            save_semaforo(match_name, n, "regular")
        if b3.button("🟢", key=f"high_{n}"):
            save_semaforo(match_name, n, "destacado")
