"""
Analizador Táctico — Plantel del equipo
==========================================
Nico — alta/baja del plantel de un equipo. Se carga UNA SOLA VEZ por
equipo (no por partido, no hay que retipear nombres cada semana) y se
reutiliza en el semáforo de todos los partidos de ese equipo — ver
app/components/team_selector.py para cómo se asigna un equipo a un
partido. Persiste en SQLite local (tabla `roster`, ver
src/db/roster_repo.py) y se sincroniza a Supabase (tabla `players`) con
scripts/sync_to_cloud.py.

Rediseño (27/10/2026, Santi con el OK de Nico): vista propia "Plantel"
(dentro de Semáforo, ver semaforo_view.py), con:
- elegir el equipo, o crear uno nuevo;
- la plantilla como planilla editable: apellido, nombre y dorsal
  (opcional), con agregar, corregir y sacar filas, y "Guardar cambios";
- importar la plantilla del club desde un CSV (apellido, nombre[, dorsal]).

Sin el permiso `gestionar_plantel` (cuerpo técnico, solo lectura) se ve la
lista sin editar; el permiso se vuelve a chequear acá adentro. Cada alta,
corrección y baja queda en el registro de accesos, con quién la hizo: son
datos personales de los jugadores (ver la sección 5.2 del informe).
"""
import io
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# src/ es hermano de app/, no un subdirectorio — no queda en sys.path solo
# por correr `streamlit run app/main.py` (a diferencia de components/, que
# sí queda porque Streamlit agrega el directorio del script principal).
_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from db import roster_repo as repo, team_repo  # noqa: E402
from components.sesion import puede, usuario_actual  # noqa: E402
# Por src.db (no db): el mismo módulo que usa sesion.py.
from src.db import registro_repo  # noqa: E402

_COLUMNAS = ["Apellido", "Nombre", "Dorsal"]


def _dorsal(valor) -> int | None:
    if valor is None or pd.isna(valor) or str(valor).strip() == "":
        return None
    numero = int(float(valor))
    if not 0 <= numero <= 99:
        raise ValueError(f"Dorsal fuera de rango: {numero} (va de 0 a 99).")
    return numero


def _texto(valor) -> str:
    return "" if valor is None or pd.isna(valor) else str(valor).strip()


def cambios_plantel(originales: list[dict], editado: pd.DataFrame) -> dict:
    """Compara el plantel guardado con la planilla editada.

    `originales`: filas de roster_repo.list_players_raw. `editado`: el
    DataFrame del editor, con columnas id, Apellido, Nombre, Dorsal (id
    vacío en las filas nuevas). Devuelve {"altas", "ediciones", "bajas",
    "errores"}; las filas nuevas sin nada escrito se ignoran.
    """
    por_id = {p["id"]: p for p in originales}
    altas, ediciones, errores = [], [], []
    vistos = set()
    for i, fila in editado.reset_index(drop=True).iterrows():
        apellido, nombre = _texto(fila.get("Apellido")), _texto(fila.get("Nombre"))
        pid = fila.get("id")
        pid = None if pid is None or pd.isna(pid) else int(pid)
        if pid is None and not apellido and not nombre and _texto(fila.get("Dorsal")) == "":
            continue   # fila nueva vacía
        try:
            dorsal = _dorsal(fila.get("Dorsal"))
        except (ValueError, TypeError) as e:
            errores.append(f"Fila {i + 1}: {e}")
            continue
        if not apellido:
            errores.append(f"Fila {i + 1}: falta el apellido.")
            continue
        if pid is None:
            altas.append({"apellido": apellido, "nombre": nombre, "dorsal": dorsal})
            continue
        vistos.add(pid)
        antes = por_id.get(pid)
        if antes and (antes.get("apellido") or "", antes.get("nombre") or "", antes.get("jersey_number")) != \
                (apellido, nombre, dorsal):
            ediciones.append({"id": pid, "apellido": apellido, "nombre": nombre, "dorsal": dorsal, "antes": antes})
    bajas = [p for pid, p in por_id.items() if pid not in vistos]
    return {"altas": altas, "ediciones": ediciones, "bajas": bajas, "errores": errores}


def _aplicar(team_id: int, cambios: dict) -> None:
    yo = usuario_actual()
    for a in cambios["altas"]:
        repo.add_player(team_id, a["apellido"], a["nombre"], a["dorsal"])
        registro_repo.registrar("plantel_alta", yo, objetivo=repo.nombre_completo(a["nombre"], a["apellido"]),
                                detalle=f"dorsal {a['dorsal'] if a['dorsal'] is not None else '-'} · equipo {team_id}")
    for e in cambios["ediciones"]:
        repo.update_player(e["id"], e["apellido"], e["nombre"], e["dorsal"])
        antes = e["antes"]
        registro_repo.registrar(
            "plantel_edicion", yo, objetivo=repo.nombre_completo(e["nombre"], e["apellido"]),
            detalle=f"{antes['full_name']} #{antes['jersey_number'] if antes['jersey_number'] is not None else '-'} → "
                    f"{repo.nombre_completo(e['nombre'], e['apellido'])} "
                    f"#{e['dorsal'] if e['dorsal'] is not None else '-'} · equipo {team_id}")
    for b in cambios["bajas"]:
        repo.remove_player(b["id"])
        registro_repo.registrar("plantel_baja", yo, objetivo=b["full_name"],
                                detalle=f"dorsal {b['jersey_number'] if b['jersey_number'] is not None else '-'} "
                                        f"· equipo {team_id}")


def leer_csv(contenido: bytes) -> pd.DataFrame:
    """Plantilla del club desde un CSV (separado por coma o punto y coma),
    con columnas apellido y nombre, y opcionalmente dorsal (en cualquier
    orden, sin importar mayúsculas ni tildes en el encabezado)."""
    df = pd.read_csv(io.BytesIO(contenido), sep=None, engine="python", dtype=str)
    normal = {c: c.strip().lower().replace("ú", "u").replace("í", "i") for c in df.columns}
    df = df.rename(columns=normal)
    if "apellido" not in df.columns:
        raise ValueError("El CSV tiene que tener una columna 'apellido' (y 'nombre'; 'dorsal' es opcional).")
    return pd.DataFrame({
        "id": None,
        "Apellido": df["apellido"],
        "Nombre": df["nombre"] if "nombre" in df.columns else "",
        "Dorsal": df["dorsal"] if "dorsal" in df.columns else None,
    })


def _tabla(jugadores: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([{"id": p["id"], "Apellido": p.get("apellido") or "", "Nombre": p.get("nombre") or "",
                          "Dorsal": p["jersey_number"]} for p in jugadores],
                        columns=["id", *_COLUMNAS]).astype({"Dorsal": "Int64"})


def _elegir_equipo(equipo_por_defecto: int | None, editable: bool) -> int | None:
    equipos = team_repo.list_teams()
    col_eq, col_nuevo = st.columns([3, 1], vertical_alignment="bottom")
    if editable:
        with col_nuevo.popover("Nuevo equipo", icon=":material/add:", width="stretch"):
            nombre = st.text_input("Nombre del equipo o categoría", key="plantel_nuevo_equipo",
                                   placeholder="Ej.: Sportivo Belgrano — Reserva")
            if st.button("Crear equipo", key="plantel_crear_equipo", type="primary"):
                if not nombre.strip():
                    st.warning("Escribí un nombre.")
                else:
                    nuevo = team_repo.create_team(nombre.strip())
                    registro_repo.registrar("equipo_creado", usuario_actual(), objetivo=nombre.strip())
                    st.session_state["plantel_equipo"] = nuevo
                    st.rerun()
    if not equipos:
        col_eq.info("Todavía no hay equipos. Creá uno con «Nuevo equipo».")
        return None
    ids = [e["id"] for e in equipos]
    if st.session_state.get("plantel_equipo") not in ids:
        st.session_state["plantel_equipo"] = equipo_por_defecto if equipo_por_defecto in ids else ids[0]
    return col_eq.selectbox("Equipo", ids, key="plantel_equipo",
                            format_func=lambda i: next(e["name"] for e in equipos if e["id"] == i))


def render_plantel(equipo_por_defecto: int | None = None, solo_lectura: bool = False) -> None:
    """Vista del plantel: elegir o crear el equipo y editar su plantilla."""
    repo.init_roster_table()
    editable = not solo_lectura and puede("gestionar_plantel")
    team_id = _elegir_equipo(equipo_por_defecto, editable)
    if team_id is None:
        return
    jugadores = repo.list_players_raw(team_id)

    if not editable:
        st.caption("Solo lectura: tu rol no modifica el plantel.")
        if jugadores:
            tabla = _tabla(jugadores).drop(columns="id")
            tabla["Dorsal"] = tabla["Dorsal"].map(lambda d: "—" if pd.isna(d) else str(d))
            st.dataframe(tabla, hide_index=True, width="stretch")
        else:
            st.info("Todavía no hay jugadores cargados para este equipo.")
        return

    st.caption("La plantilla se carga una vez por equipo y se usa en el semáforo de todos sus partidos. "
               "Editá las celdas, agregá filas al final o seleccioná filas y borralas; después, «Guardar cambios».")
    clave = f"plantel_editor_{team_id}_{st.session_state.get('_plantel_version', 0)}"
    editado = st.data_editor(
        _tabla(jugadores), key=clave, num_rows="dynamic", hide_index=True, width="stretch",
        column_config={
            "id": None,
            "Apellido": st.column_config.TextColumn("Apellido", required=True, max_chars=60),
            "Nombre": st.column_config.TextColumn("Nombre", max_chars=60),
            "Dorsal": st.column_config.NumberColumn("Dorsal", min_value=0, max_value=99, step=1,
                                                    help="Opcional"),
        },
    )
    cambios = cambios_plantel(jugadores, editado)
    for error in cambios["errores"]:
        st.error(error)
    resumen = [f"{len(cambios[k])} {t}" for k, t in (("altas", "nuevos"), ("ediciones", "corregidos"),
                                                       ("bajas", "a sacar")) if cambios[k]]
    col_guardar, col_resumen = st.columns([1, 3], vertical_alignment="center")
    if col_guardar.button("Guardar cambios", type="primary", icon=":material/save:", key="plantel_guardar",
                          disabled=not resumen or bool(cambios["errores"]), width="stretch"):
        _aplicar(team_id, cambios)
        st.session_state["_plantel_version"] = st.session_state.get("_plantel_version", 0) + 1
        st.toast("Plantel guardado: " + ", ".join(resumen))
        st.rerun()
    col_resumen.caption("Cambios sin guardar: " + ", ".join(resumen) if resumen else f"{len(jugadores)} jugadores.")

    with st.expander("Importar la plantilla desde un CSV"):
        st.caption("Columnas: apellido, nombre y (opcional) dorsal, separadas por coma o punto y coma. "
                   "Desde Excel: Archivo → Guardar como → CSV. Se agregan al plantel; no se borra a nadie.")
        archivo = st.file_uploader("Archivo CSV", type=["csv"], key=f"plantel_csv_{team_id}",
                                   label_visibility="collapsed")
        if archivo is not None:
            try:
                importados = cambios_plantel([], leer_csv(archivo.getvalue()))
            except (ValueError, pd.errors.ParserError) as e:
                st.error(f"No se pudo leer el CSV: {e}")
                return
            ya = {(p.get("apellido") or "").lower() + "|" + (p.get("nombre") or "").lower() for p in jugadores}
            nuevos = [a for a in importados["altas"] if f"{a['apellido'].lower()}|{a['nombre'].lower()}" not in ya]
            for error in importados["errores"]:
                st.error(error)
            st.write(f"{len(nuevos)} jugadores para agregar"
                     + (f" ({len(importados['altas']) - len(nuevos)} ya estaban)" if len(nuevos) < len(importados["altas"]) else ""))
            if nuevos and st.button(f"Agregar {len(nuevos)} jugadores", key="plantel_importar", type="primary"):
                _aplicar(team_id, {"altas": nuevos, "ediciones": [], "bajas": []})
                st.session_state["_plantel_version"] = st.session_state.get("_plantel_version", 0) + 1
                st.toast(f"Importados {len(nuevos)} jugadores")
                st.rerun()
