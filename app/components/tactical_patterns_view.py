"""
Analizador Táctico — Vista de Patrones Tácticos Detectados
============================================================
Pestaña "⚠️ Patrones tácticos": consume src/analysis/tactical_patterns.py
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


def render_tactical_patterns_tab(df: pd.DataFrame) -> None:
    """Renderiza el contenido de la pestaña de Patrones Tácticos."""
    st.markdown("### ⚠️ Patrones tácticos y desajustes posicionales")

    # Banner metodológico para el cuerpo técnico
    st.info(
        "💡 **Nota para el cuerpo técnico:** Estas señales surgen de desviaciones "
        "geométricas estadísticas respecto a la línea de compañeros — **no son diagnósticos definitivos**. "
        "Un jugador despegado de su línea puede estar ejecutando un desmarque para recibir, "
        "una marca personal sobre un rival o una basculación correcta. "
        "Revisá siempre la jugada en video antes de sacar conclusiones.",
        icon="📋",
    )

    if "team" not in df.columns or df["team"].dropna().empty:
        st.warning(
            "⚠️ Este partido no tiene asignación de equipos (`team`).\n\n"
            "La detección de fases y líneas defensivas requiere diferenciar Local y Visitante. "
            "Corré primero:\n"
            "```bash\npython3 src/analysis/team_assignment.py <video.mp4> <coords.parquet>\n```"
        )
        return

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

    # Renderizar tarjetas
    st.markdown(f"**Momentos para revisar ({len(df_filtrado)}):**")

    for _, row in df_filtrado.iterrows():
        team_key = row["team"]
        team_label = TEAM_LABELS.get(team_key, team_key)
        team_color = TEAM_COLORS.get(team_key, "#ffffff")
        titulo_patron = PATRON_TITULOS.get(row["patron"], row["patron"])

        with st.container(border=True):
            col_header, col_team = st.columns([3, 1])
            with col_header:
                st.markdown(
                    f"**🔎 Para revisar** · `{row['patron']}` — "
                    f"**Track #{row['track_id']}**",
                )
                st.markdown(f"#### {titulo_patron}")
            with col_team:
                st.markdown(
                    f"<div style='text-align: right; color: {team_color}; font-weight: 700;'>"
                    f"{team_label}</div>",
                    unsafe_allow_html=True,
                )

            st.write(row["descripcion"])

            # Métricas técnicas de soporte
            c_val, c_ocurr, c_sev, c_fusion = st.columns([1, 1, 1, 2])
            if row["patron"] == "desconectado":
                exceso_pct = int((row["valor_tecnico"] - 1.0) * 100) if row["valor_tecnico"] > 1.0 else 0
                c_val.metric("Desvío s/ línea", f"+{exceso_pct}%", help="Exceso sobre la distancia típica de su línea.")
            elif row["patron"] == "no_achica":
                c_val.metric("Déficit de avance", f"{row['valor_tecnico']} m", help="Metros por detrás del desplazamiento de su línea.")

            c_ocurr.metric("Ocurrencias", f"{row['n_ocurrencias']}", help="Segmentos donde se repitió el comportamiento.")
            c_sev.metric(
                "Severidad", f"{row['severidad']:.2f}",
                help="Dato técnico: solo ordena la lista. No mide qué tan grave es: los casos "
                     "revisados en video con severidad máxima resultaron falsos positivos o leves.",
            )

            candidatos = row.get("posible_mismo_jugador_que", [])
            if candidatos:
                c_fusion.caption(f"🔗 Posible mismo jugador que track(s): {candidatos}")

            # Botones con evidencia temporal para saltar al video
            evidencia = row.get("evidencia_seg", [])
            if evidencia:
                st.markdown("**Evidencia en video (hacé clic para ir a ese instante):**")
                cols_ev = st.columns(min(len(evidencia), 6))
                for i, (t_ini, t_fin) in enumerate(evidencia[:6]):
                    btn_label = f"▶ {format_time(t_ini)}"
                    if cols_ev[i].button(btn_label, key=f"btn_seek_{row['patron']}_{row['track_id']}_{i}", width="stretch"):
                        st.session_state["_pending_seek_time"] = float(t_ini)
                        st.toast(f"Tiempo fijado en {format_time(t_ini)} — pasá a la pestaña '📊 Análisis' para reproducir.")
                        st.rerun()

    # Sección de información de patrones no evaluados
    if no_evaluados:
        with st.expander("ℹ️ Patrones no evaluados (criterios de evidencia)", expanded=False):
            st.caption(
                "Para no generar falsos positivos con clips cortos, se requiere una cantidad mínima "
                "de fases de juego evaluables. En este clip:"
            )
            for item in no_evaluados:
                st.markdown(f"- {item}")
