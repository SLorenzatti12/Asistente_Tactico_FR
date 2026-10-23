"""
Analizador Táctico — Vista de Patrones Tácticos Detectados
============================================================
Vista "Patrones" del encabezado: consume src/analysis/tactical_patterns.py
para el dashboard. Presenta cada caso como "momento para revisar", con
redacción orientada al DT, desglose técnico y botones de timestamp para
revisar la jugada exacta en el video. La severidad solo ORDENA la lista y
se muestra como dato técnico: no hay etiquetas ni filtro por severidad,
porque los casos revisados contra video con severidad máxima resultaron
falsos positivos o leves (ver docs/context/decisiones.md).

Metodología:
  El sistema mide desviación posicional geométrica, no intención táctica.
  Las detecciones se comunican siempre como SEÑALES PARA REVISAR EN VIDEO,
  nunca como diagnósticos definitivos.
"""

import html
import sys
from pathlib import Path
import pandas as pd
import streamlit as st

# Importar funciones de análisis táctico
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.analysis.tactical_patterns import (
    detectar_fases,
    asignar_lineas,
    detectar_patrones,
)
from src.analysis.lados import control_entre_tiempos
from components.tagging import format_time
from theme import TEAM_COLORS, TEAM_LABELS

# Nombres amigables para los patrones
PATRON_TITULOS = {
    "desconectado": "Más despegado de su línea que sus compañeros",
    "no_achica": "Atrás del avance de su línea cuando el equipo sube",
    "bloque_estirado": "Bloque estirado en transición",
    "cobertura_lateral": "Retardo en basculación lateral",
}


@st.cache_data(show_spinner="Analizando patrones tácticos en el partido…")
def _calcular_patrones_cached(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
    """
    Ejecuta el pipeline de 3 pasos (fases -> líneas -> patrones).
    Devuelve (patrones_df, patrones_no_evaluados, avisos).
    """
    if "team" not in df.columns or df["team"].dropna().empty:
        return pd.DataFrame(), [], ["Falta la columna 'team' en el archivo."]

    try:
        fases = detectar_fases(df)
        lineas = asignar_lineas(df)
        patrones = detectar_patrones(df, fases, lineas)

        no_evaluados = patrones.attrs.get("patrones_no_evaluados", [])
        avisos = patrones.attrs.get("avisos", [])
        return patrones, no_evaluados, avisos
    except Exception as e:
        return pd.DataFrame(), [], [f"Error al calcular patrones: {str(e)}"]


@st.cache_data(show_spinner=False, max_entries=8)
def _control_tiempos_cached(match_name: str, _df: pd.DataFrame, firma: tuple) -> dict | None:
    """control_entre_tiempos() cacheado por partido y por la fecha de los dos
    parquets (`firma`): si se reprocesa cualquiera de los tiempos, se recalcula."""
    return control_entre_tiempos(match_name, _df)


def _firma_tiempos(match_name: str) -> tuple:
    outputs = _ROOT / "data" / "outputs"
    rutas = sorted(outputs.glob(f"{match_name}_coords_field.parquet"))
    try:
        from src.db import partido_repo
        otro = partido_repo.otro_tiempo(match_name)
        if otro:
            rutas += sorted(outputs.glob(f"{otro['match_name']}_coords_field.parquet"))
    except Exception:
        pass
    return tuple((r.name, r.stat().st_mtime) for r in rutas)


# Estilo del mockup (mockup/styles.css: .patrones-hero-banner, .pattern-card).
# Usa los tokens --at-* que define main.py; los colores de equipo salen de
# theme.TEAM_COLORS. Atado a clases propias y a los contenedores con key
# "patron_*", no a data-testid internos de Streamlit.
_ESTILOS = """
<style>
.at-hero { background: var(--at-surface-1, #121519); border: 1px solid var(--at-border, #242a35);
           border-radius: 12px; padding: 18px 22px; display: flex; flex-direction: column; gap: 6px; }
.at-hero h2 { font-size: 1.05rem; letter-spacing: 0.08em; margin: 0; padding: 0; }
.at-hero p { color: var(--at-text-2, #9aa4b2); font-size: 0.9rem; margin: 0; max-width: 90ch; }
.at-card-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }
.at-card-type { font-family: var(--at-mono, monospace); font-size: 0.7rem; color: var(--at-text-2, #9aa4b2); }
.at-card-team { font-size: 0.75rem; font-weight: 700; padding: 2px 10px; border-radius: 999px; border: 1px solid; }
.at-card-title { font-size: 1.05rem; font-weight: 700; margin: 2px 0 0; }
.at-card-track { font-family: var(--at-mono, monospace); font-size: 0.75rem; color: var(--at-text-3, #626c7a); }
.at-card-text { font-size: 0.9rem; color: var(--at-text-1, #f0f3f6); }
.at-card-box { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px 16px;
               background: var(--at-surface-2, #181c22); border: 1px solid var(--at-border, #242a35);
               border-radius: 8px; padding: 10px 12px; }
.at-card-box .k { font-size: 0.68rem; color: var(--at-text-3, #626c7a); text-transform: uppercase; letter-spacing: 0.06em; }
.at-card-box .v { font-family: var(--at-mono, monospace); font-size: 0.85rem; color: var(--at-text-1, #f0f3f6); }
.at-card-ev { font-size: 0.72rem; color: var(--at-text-3, #626c7a); text-transform: uppercase; letter-spacing: 0.06em; }
</style>
"""

_HERO = """
<div class="at-hero">
  <h2>MOMENTOS PARA REVISAR</h2>
  <p>Señales que surgen de desviaciones geométricas respecto a la línea de compañeros:
  <strong>no son diagnósticos definitivos</strong>. Un jugador despegado de su línea puede estar
  desmarcándose para recibir, haciendo una marca personal o basculando bien. Revisá siempre la
  jugada en video antes de sacar conclusiones.</p>
</div>
"""


def _html_tarjeta(row, titulo: str, team_label: str, team_color: str) -> str:
    """Parte fija de la tarjeta de un patrón (sin los botones, que son widgets)."""
    valores = []
    if row["patron"] == "desconectado":
        exceso_pct = int((row["valor_tecnico"] - 1.0) * 100) if row["valor_tecnico"] > 1.0 else 0
        valores.append(("Desvío sobre su línea", f"+{exceso_pct}%"))
    elif row["patron"] == "no_achica":
        valores.append(("Déficit de avance", f"{row['valor_tecnico']} m"))
    valores.append(("Ocurrencias", f"{row['n_ocurrencias']}"))
    # La severidad solo ordena la lista (ver decisiones.md): va como dato técnico.
    valores.append(("Orden (severidad)", f"{row['severidad']:.2f}"))
    candidatos = row.get("posible_mismo_jugador_que", [])
    if candidatos:
        valores.append(("Posible mismo jugador", ", ".join(f"track {c}" for c in candidatos)))
    caja = "".join(f'<div><div class="k">{k}</div><div class="v">{v}</div></div>' for k, v in valores)
    return f"""
<div class="at-card-head">
  <span class="at-card-type">Para revisar · <code>{row['patron']}</code></span>
  <span class="at-card-team" style="color:{team_color}; border-color:{team_color}">{team_label}</span>
</div>
<div class="at-card-title">{html.escape(titulo)}</div>
<div class="at-card-track">Track #{row['track_id']}</div>
<div class="at-card-text">{html.escape(str(row['descripcion']))}</div>
<div class="at-card-box">{caja}</div>
"""


def _ir_a(t: float) -> None:
    """Pide el salto a la Mesa táctica (main.py aplica `_pending_seek_time`)."""
    st.session_state["_pending_seek_time"] = float(t)


def render_tactical_patterns_tab(df: pd.DataFrame) -> None:
    """Renderiza el contenido de la vista de Patrones Tácticos."""
    st.html(_ESTILOS)
    st.html(_HERO)

    if "team" not in df.columns or df["team"].dropna().empty:
        st.warning(
            "⚠️ Este partido no tiene asignación de equipos (`team`).\n\n"
            "La detección de fases y líneas defensivas requiere diferenciar Local y Visitante. "
            "Corré primero:\n"
            "```bash\npython3 src/analysis/team_assignment.py <video.mp4> <coords.parquet>\n```"
        )
        return

    # Segundo tiempo de un partido: los equipos tienen que haber cambiado de
    # lado respecto del primero. Si no, no se muestran patrones de este tiempo.
    match_name = st.session_state.get("selected_match")
    control = _control_tiempos_cached(match_name, df, _firma_tiempos(match_name)) if match_name else None
    if control is not None:
        texto = (f"{control['tiempo_actual']}° tiempo de «{control['partido']}» "
                 f"(el otro: {control['otro_video']}): {control['motivo']}.")
        if control["ok"]:
            st.caption(f"✅ {texto}")
        elif control["tiempo_actual"] == 2:
            st.error(f"{texto} No se calculan patrones de este tiempo hasta resolverlo.")
            return
        else:
            st.warning(texto)

    patrones, no_evaluados, avisos = _calcular_patrones_cached(df)

    # Avisos de inferencia de dirección si los hubiera
    if avisos:
        for aviso in avisos:
            st.caption(f"⚠️ _{aviso}_")

    # Filtro por equipo (no por severidad: la severidad solo ordena la lista)
    equipo_filtro = st.segmented_control(
        "Equipo",
        options=["todos", "home", "away"],
        format_func=lambda x: "Ambos equipos" if x == "todos" else TEAM_LABELS.get(x, x),
        default="todos",
        key="filtro_equipo_patrones",
    )

    # Filtrar resultados. detectar_patrones ya los devuelve ordenados por
    # severidad, de más a menos señal: ese es el único uso de la severidad acá.
    df_filtrado = patrones.copy()
    if not df_filtrado.empty and equipo_filtro not in (None, "todos"):
        df_filtrado = df_filtrado[df_filtrado["team"] == equipo_filtro]

    # Sin patrones detectados
    if df_filtrado.empty:
        if patrones.empty:
            st.success("✅ No se detectaron desajustes tácticos sostenidos en este clip.")
        else:
            st.caption("No hay momentos para revisar de este equipo.")

        if no_evaluados:
            with st.expander("ℹ️ Patrones no evaluados (datos insuficientes)", expanded=False):
                st.caption(
                    "El sistema exige un mínimo de fases u observaciones independientes para "
                    "no reportar una casualidad como si fuera una tendencia. En este clip:"
                )
                for item in no_evaluados:
                    st.markdown(f"- {item}")
        return

    # Tarjetas en grilla de dos columnas, ordenadas de más a menos señal
    st.markdown(f"**Momentos para revisar ({len(df_filtrado)})**")

    filas = list(df_filtrado.iterrows())
    for i in range(0, len(filas), 2):
        columnas = st.columns(2)
        for col, (_, row) in zip(columnas, filas[i:i + 2]):
            team_key = row["team"]
            clave = f"{row['patron']}_{row['track_id']}"
            with col, st.container(border=True, key=f"patron_{clave}"):
                st.html(_html_tarjeta(row, PATRON_TITULOS.get(row["patron"], row["patron"]),
                                      TEAM_LABELS.get(team_key, team_key), TEAM_COLORS.get(team_key, "#ffffff")))
                # Evidencia: cada botón lleva a la Mesa táctica en ese instante
                evidencia = row.get("evidencia_seg", [])[:6]
                if evidencia:
                    st.html('<div class="at-card-ev">Evidencia en video</div>')
                    with st.container(horizontal=True, gap="small"):
                        for j, (t_ini, _t_fin) in enumerate(evidencia):
                            st.button(
                                format_time(t_ini), key=f"btn_seek_{clave}_{j}",
                                icon=":material/play_arrow:", type="primary" if j == 0 else "secondary",
                                on_click=_ir_a, args=(t_ini,),
                                help="Ver la jugada en la Mesa táctica (video y cancha).",
                            )

    # Sección de información de patrones no evaluados
    if no_evaluados:
        with st.expander("ℹ️ Patrones no evaluados (criterios de evidencia)", expanded=False):
            st.caption(
                "Para no generar falsos positivos con clips cortos, se requiere una cantidad mínima "
                "de fases de juego evaluables. En este clip:"
            )
            for item in no_evaluados:
                st.markdown(f"- {item}")
