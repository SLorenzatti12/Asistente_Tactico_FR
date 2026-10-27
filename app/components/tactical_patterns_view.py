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

Criterios propios del club (27/10/2026, ver decisiones.md):
  - Cada momento lo puede calificar el cuerpo técnico después de verlo
    (útil / correcto tácticamente / no se ve en el video, más un
    comentario), en src/db/revision_patrones_repo.py. Es la evidencia para
    ajustar los criterios con datos del club.
  - "Probar otros criterios" recalcula el partido con otros umbrales SIN
    GUARDAR NADA y muestra qué momentos aparecen o desaparecen, y qué había
    dicho el cuerpo técnico de cada uno.
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
    CRITERIOS_POR_DEFECTO,
    criterios_completos,
    detectar_fases,
    asignar_lineas,
    detectar_patrones,
)
from src.analysis.lados import control_entre_tiempos
from src.db import revision_patrones_repo as revisiones
from components.sesion import puede, usuario_actual
from components.tagging import format_time
from theme import TEAM_COLORS, TEAM_LABELS

# Nombres amigables para los patrones
PATRON_TITULOS = {
    "desconectado": "Más despegado de su línea que sus compañeros",
    "no_achica": "Atrás del avance de su línea cuando el equipo sube",
    "bloque_estirado": "Bloque estirado en transición",
    "cobertura_lateral": "Retardo en basculación lateral",
}


def _calcular(df: pd.DataFrame, criterios: dict) -> tuple[pd.DataFrame, list[str], list[str]]:
    if "team" not in df.columns or df["team"].dropna().empty:
        return pd.DataFrame(), [], ["Falta la columna 'team' en el archivo."]
    try:
        fases = detectar_fases(df, umbral_avance_ms=criterios["umbral_avance_ms"])
        lineas = asignar_lineas(df)
        patrones = detectar_patrones(df, fases, lineas, criterios=criterios)
        return patrones, patrones.attrs.get("patrones_no_evaluados", []), patrones.attrs.get("avisos", [])
    except Exception as e:
        return pd.DataFrame(), [], [f"Error al calcular patrones: {str(e)}"]


@st.cache_data(show_spinner="Analizando patrones tácticos en el partido…")
def _calcular_patrones_cached(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
    """
    Ejecuta el pipeline de 3 pasos (fases -> líneas -> patrones) con los
    criterios vigentes. Devuelve (patrones_df, patrones_no_evaluados, avisos).
    """
    return _calcular(df, criterios_completos())


@st.cache_data(show_spinner="Recalculando con los criterios de prueba…", max_entries=12)
def _calcular_con_criterios(df: pd.DataFrame, criterios: tuple) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Lo mismo con otros criterios (tupla de pares, para poder cachear)."""
    return _calcular(df, criterios_completos(dict(criterios)))


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


# ── Revisión del cuerpo técnico ─────────────────────────────────
_ICONO_VEREDICTO = {"util": "👍", "correcto": "✅", "no_se_ve": "🚫"}


def _guardar_revision(match_name: str, momento: dict, criterios: dict, clave: str) -> None:
    """Callback de la calificación y del comentario: guarda los dos juntos
    (la tabla solo agrega filas; vale la última)."""
    usuario = usuario_actual()
    if usuario is None or not puede("revisar_patrones"):
        return
    revisiones.guardar(match_name, momento, st.session_state.get(f"{clave}_veredicto"),
                       st.session_state.get(f"{clave}_comentario"), criterios, usuario["usuario"])


def _render_revision(match_name: str, row: pd.Series, criterios: dict, previa: dict | None, prefijo: str) -> None:
    """Calificación del momento: útil / correcto tácticamente / no se ve, y
    un comentario. Quien no puede revisar ve la última calificación."""
    clave = f"{prefijo}rev_{row['patron']}_{row['track_id']}"
    if not puede("revisar_patrones"):
        if previa and previa["veredicto"]:
            st.caption(f"{_ICONO_VEREDICTO[previa['veredicto']]} {revisiones.VEREDICTOS[previa['veredicto']]} · "
                       f"{previa['created_by'] or 'sin dato'}" + (f" — «{previa['comentario']}»" if previa['comentario'] else ""))
        return
    momento = row.to_dict()
    if f"{clave}_veredicto" not in st.session_state:
        st.session_state[f"{clave}_veredicto"] = previa["veredicto"] if previa else None
    if f"{clave}_comentario" not in st.session_state:
        st.session_state[f"{clave}_comentario"] = (previa or {}).get("comentario") or ""
    st.segmented_control(
        "¿Qué te pareció después de verlo?", list(revisiones.VEREDICTOS),
        format_func=lambda v: f"{_ICONO_VEREDICTO[v]} {revisiones.VEREDICTOS[v]}", key=f"{clave}_veredicto",
        on_change=_guardar_revision, args=(match_name, momento, criterios, clave))
    st.text_input("Comentario (opcional)", key=f"{clave}_comentario", placeholder="Ej.: se abre para recibir, está bien",
                  on_change=_guardar_revision, args=(match_name, momento, criterios, clave))
    if previa:
        st.caption(f"Última revisión: {previa['created_by'] or 'sin dato'} · {previa['created_at'][:16].replace('T', ' ')}")


def _resumen_revisiones(patrones: pd.DataFrame, vigentes: dict) -> str:
    calificados = [vigentes[k]["veredicto"] for k in zip(patrones["patron"], patrones["track_id"])
                   if k in vigentes and vigentes[k]["veredicto"]]
    partes = [f"Revisados **{len(calificados)} de {len(patrones)}**"]
    partes += [f"{_ICONO_VEREDICTO[v]} {revisiones.VEREDICTOS[v]}: {calificados.count(v)}" for v in revisiones.VEREDICTOS]
    return " · ".join(partes)


def _render_lo_que_dijo_el_club() -> None:
    """Acumulado de todos los partidos: la precisión de cada patrón según el
    cuerpo técnico. Es lo que va al informe y lo que justifica un cambio de
    criterio."""
    resumen = revisiones.resumen_por_patron()
    with st.expander("Lo que dijo el cuerpo técnico (todos los partidos)"):
        if not resumen:
            st.caption("Todavía no hay momentos calificados.")
            return
        st.dataframe(pd.DataFrame([{
            "Patrón": PATRON_TITULOS.get(p, p),
            "Calificados": sum(c.values()),
            **{revisiones.VEREDICTOS[v]: c[v] for v in revisiones.VEREDICTOS},
            "% útil": f"{100 * c['util'] / sum(c.values()):.0f}%",
        } for p, c in resumen.items()]), hide_index=True, width="stretch")
        comentarios = revisiones.con_comentario(limite=30)
        if comentarios:
            st.markdown("**Comentarios**")
            for f in comentarios:
                icono = _ICONO_VEREDICTO.get(f["veredicto"], "·")
                st.caption(f"{icono} {f['match_name']} · {PATRON_TITULOS.get(f['patron'], f['patron'])} · "
                           f"track {f['track_id']} — «{f['comentario']}» ({f['created_by'] or 'sin dato'})")


# ── Probar otros criterios (sin guardar nada) ───────────────────
# Cada perilla en unidades de cancha; el valor por defecto es el criterio
# vigente (CRITERIOS_POR_DEFECTO). (clave, etiqueta, ayuda, mín, máx, paso,
# de criterio a perilla, de perilla a criterio)
_PERILLAS = {
    "Desconectado": [
        ("umbral_desconexion", "Cuánto más despegado que su línea (%)",
         "Cuánto más que lo típico de su línea se tiene que separar en profundidad. 50% = una vez y media lo típico.",
         10, 150, 5, lambda v: int(round(v * 100)), lambda x: x / 100),
        ("proporcion_desconexion", "Durante qué parte de su tiempo en cancha (%)",
         "Qué porcentaje de su tiempo en cancha tiene que estar despegado para que cuente.",
         30, 95, 5, lambda v: int(round(v * 100)), lambda x: x / 100),
    ],
    "No achica": [
        ("umbral_no_achica_m", "Metros que se queda atrás de su línea",
         "Cuando el bloque sube, cuántos metros por detrás del avance de su línea cuentan como no achicar.",
         1.0, 10.0, 0.5, lambda v: float(v), float),
        ("min_fases_ataque", "Subidas mínimas para opinar",
         "Cuántas subidas del bloque tiene que haber visto el jugador para decir algo.",
         2, 8, 1, int, int),
        ("proporcion_no_achica", "En más de qué parte de las subidas (%)",
         "Tiene que quedarse atrás en más de este porcentaje de las subidas evaluadas.",
         25, 90, 5, lambda v: int(round(v * 100)), lambda x: x / 100),
    ],
    "Cuándo «sube» el bloque": [
        ("umbral_avance_ms", "Velocidad mínima del bloque (m/s)",
         "A partir de qué velocidad de avance del centro del bloque se considera que el equipo sube.",
         0.1, 1.0, 0.05, lambda v: float(v), float),
    ],
}


def _clave_perilla(nombre: str) -> str:
    return f"perilla_{nombre}"


def _restablecer_perillas() -> None:
    for grupo in _PERILLAS.values():
        for nombre, *_resto, a_perilla, _a_criterio in grupo:
            st.session_state[_clave_perilla(nombre)] = a_perilla(CRITERIOS_POR_DEFECTO[nombre])


def _render_probar_criterios(df: pd.DataFrame, match_name: str, patrones: pd.DataFrame, vigentes: dict) -> None:
    with st.expander("Probar otros criterios (no cambia nada)"):
        st.caption("Recalcula este partido con otros umbrales y muestra qué momentos aparecerían o desaparecerían, "
                   "y qué había dicho el cuerpo técnico de cada uno. **No guarda nada ni cambia lo que ven los demás.** "
                   "Los momentos nuevos se pueden calificar acá mismo, para juntar evidencia antes de cambiar un criterio.")
        if _clave_perilla("umbral_desconexion") not in st.session_state:
            _restablecer_perillas()
        with st.form("probar_criterios", border=False):
            prueba = {}
            for titulo, grupo in _PERILLAS.items():
                st.markdown(f"**{titulo}**")
                cols = st.columns(len(grupo))
                for col, (nombre, etiqueta, ayuda, mn, mx, paso, _a_perilla, a_criterio) in zip(cols, grupo):
                    valor = col.slider(etiqueta, mn, mx, step=paso, key=_clave_perilla(nombre), help=ayuda)
                    prueba[nombre] = a_criterio(valor)
            c1, c2 = st.columns([1, 1])
            probar = c1.form_submit_button("Probar", type="primary", icon=":material/science:", width="stretch")
            c2.form_submit_button("Volver a los criterios actuales", on_click=_restablecer_perillas, width="stretch")
        if not probar and not st.session_state.get("_criterios_probados"):
            return
        if probar:
            st.session_state["_criterios_probados"] = tuple(sorted(prueba.items()))
        criterios_prueba = criterios_completos(dict(st.session_state["_criterios_probados"]))
        cambiados = {k: v for k, v in criterios_prueba.items() if v != CRITERIOS_POR_DEFECTO[k]}
        if not cambiados:
            st.info("Son los criterios actuales: el resultado es el de arriba.")
            return
        nuevos, _no_eval, _avisos = _calcular_con_criterios(df, st.session_state["_criterios_probados"])
        actuales = set(zip(patrones["patron"], patrones["track_id"])) if not patrones.empty else set()
        probados = set(zip(nuevos["patron"], nuevos["track_id"])) if not nuevos.empty else set()
        st.markdown(f"**Con estos criterios: {len(probados)} momentos** (hoy {len(actuales)}) · "
                    f"{len(probados - actuales)} nuevos · {len(actuales - probados)} dejarían de aparecer · "
                    f"{len(probados & actuales)} se mantienen")

        def opinion(clave):
            v = vigentes.get(clave)
            return f"{_ICONO_VEREDICTO[v['veredicto']]} {revisiones.VEREDICTOS[v['veredicto']]}" if v and v["veredicto"] else "sin calificar"
        desaparecen = [k for k in sorted(actuales - probados)]
        if desaparecen:
            st.caption("Dejarían de aparecer: " + "; ".join(
                f"{PATRON_TITULOS.get(p, p)} · track {t} ({opinion((p, t))})" for p, t in desaparecen))
        if nuevos.empty:
            return
        for _, row in nuevos.iterrows():
            clave = (row["patron"], row["track_id"])
            estado = "se mantiene" if clave in actuales else "NUEVO"
            with st.container(border=True, key=f"prueba_{row['patron']}_{row['track_id']}"):
                c_txt, c_ir = st.columns([4, 1], vertical_alignment="center")
                c_txt.markdown(f"**{estado}** · {PATRON_TITULOS.get(row['patron'], row['patron'])} · track {row['track_id']} · "
                               f"{TEAM_LABELS.get(row['team'], row['team'])} · {opinion(clave)}")
                evidencia = row.get("evidencia_seg", [])
                if len(evidencia):
                    c_ir.button(format_time(evidencia[0][0]), key=f"prueba_ir_{row['patron']}_{row['track_id']}",
                                icon=":material/play_arrow:", on_click=_ir_a, args=(evidencia[0][0],), width="stretch")
                if estado == "NUEVO":
                    _render_revision(match_name, row, criterios_prueba, vigentes.get(clave), prefijo="prueba_")


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
    criterios_vigentes = patrones.attrs.get("criterios") or criterios_completos()
    vigentes = revisiones.vigentes(match_name) if match_name else {}

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
        if match_name:
            _render_probar_criterios(df, match_name, patrones, vigentes)
        _render_lo_que_dijo_el_club()

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
    st.caption(_resumen_revisiones(df_filtrado, vigentes))

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
                if match_name:
                    _render_revision(match_name, row, criterios_vigentes,
                                     vigentes.get((row["patron"], row["track_id"])), prefijo="")

    if match_name:
        _render_probar_criterios(df, match_name, patrones, vigentes)
    _render_lo_que_dijo_el_club()

    # Sección de información de patrones no evaluados
    if no_evaluados:
        with st.expander("ℹ️ Patrones no evaluados (criterios de evidencia)", expanded=False):
            st.caption(
                "Para no generar falsos positivos con clips cortos, se requiere una cantidad mínima "
                "de fases de juego evaluables. En este clip:"
            )
            for item in no_evaluados:
                st.markdown(f"- {item}")
