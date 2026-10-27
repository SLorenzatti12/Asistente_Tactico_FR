"""
Analizador Táctico — Vista "Usuarios" (solo administradores)
==============================================================
Santi. Alta de usuarios, cambio de rol, contraseña nueva y activar o
desactivar, sobre src/db/usuarios_repo.py, y el registro de accesos y
cambios (src/db/registro_repo.py). Siempre queda al menos un
administrador activo (lo controla el repositorio), y un admin no se puede
desactivar ni quitar el rol a sí mismo desde acá, para no quedar afuera a
mitad de la sesión.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.db import registro_repo, usuarios_repo  # noqa: E402

ROLES = usuarios_repo.ROLES
DESCRIPCION_ROLES = {
    "admin": "Todo, incluida esta pantalla de usuarios.",
    "analyst": "Taguea en la Mesa táctica, gestiona partidos, plantel y tipos de evento.",
    "coach": "Ve todo y califica el semáforo. No toca la configuración.",
    "viewer": "Solo mira: no carga ni modifica nada.",
}


def _alta(yo: dict) -> None:
    with st.form("alta_usuario", clear_on_submit=True, border=True):
        st.markdown("**Nuevo usuario**")
        c1, c2 = st.columns(2)
        usuario = c1.text_input("Usuario (para ingresar)", key="alta_usuario_usuario")
        nombre = c2.text_input("Nombre y apellido", key="alta_usuario_nombre")
        rol = st.selectbox("Rol", list(ROLES), format_func=ROLES.get, index=1, key="alta_usuario_rol")
        st.caption(DESCRIPCION_ROLES[rol] if rol else "")
        c3, c4 = st.columns(2)
        contrasena = c3.text_input("Contraseña inicial", type="password", key="alta_usuario_contrasena")
        repetida = c4.text_input("Repetila", type="password", key="alta_usuario_repetida")
        if st.form_submit_button("Crear usuario", type="primary", icon=":material/person_add:"):
            if contrasena != repetida:
                st.error("Las contraseñas no coinciden.")
                return
            try:
                u = usuarios_repo.crear_usuario(usuario, nombre, rol, contrasena, actor=yo)
            except ValueError as e:
                st.error(str(e))
                return
            # Se recarga para que la tabla de arriba ya muestre al usuario nuevo.
            st.toast(f"Usuario '{u['usuario']}' creado ({ROLES[u['rol']]}). Pasale la contraseña por un canal seguro.")
            st.rerun()


def _editar(usuarios: list[dict], yo: dict) -> None:
    with st.container(border=True):
        st.markdown("**Editar usuario**")
        elegido = st.selectbox(
            "Usuario", [u["id"] for u in usuarios],
            format_func=lambda i: next(f"{u['nombre']} ({u['usuario']})" for u in usuarios if u["id"] == i),
            key="editar_usuario_id",
        )
        u = next(x for x in usuarios if x["id"] == elegido)
        es_yo = u["id"] == yo["id"]

        c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
        rol = c1.selectbox("Rol", list(ROLES), format_func=ROLES.get, index=list(ROLES).index(u["rol"]),
                           key=f"editar_rol_{u['id']}", disabled=es_yo,
                           help="No podés cambiar tu propio rol." if es_yo else DESCRIPCION_ROLES[u["rol"]])
        if c2.button("Guardar rol", key=f"guardar_rol_{u['id']}", disabled=es_yo or rol == u["rol"], width="stretch"):
            try:
                usuarios_repo.cambiar_rol(u["id"], rol, actor=yo)
                st.rerun()
            except ValueError as e:
                st.error(str(e))

        c3, c4 = st.columns([2, 1], vertical_alignment="bottom")
        nueva = c3.text_input("Contraseña nueva", type="password", key=f"editar_contrasena_{u['id']}",
                              help="Para cuando alguien se la olvidó. Pasale la nueva por un canal seguro.")
        if c4.button("Poner contraseña", key=f"guardar_contrasena_{u['id']}", disabled=not nueva, width="stretch"):
            try:
                usuarios_repo.cambiar_contrasena(u["id"], nueva, actor=yo)
                st.success("Contraseña actualizada.")
            except ValueError as e:
                st.error(str(e))

        if u["activo"]:
            if st.button("Desactivar usuario", key=f"desactivar_{u['id']}", icon=":material/person_off:",
                         disabled=es_yo, help="No podés desactivarte a vos mismo." if es_yo else
                         "No borra nada: el usuario no puede ingresar hasta que se lo vuelva a activar."):
                try:
                    usuarios_repo.cambiar_activo(u["id"], False, actor=yo)
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        elif st.button("Activar usuario", key=f"activar_{u['id']}", icon=":material/person_check:"):
            usuarios_repo.cambiar_activo(u["id"], True, actor=yo)
            st.rerun()


def render_usuarios(yo: dict) -> None:
    """Vista completa de administración de usuarios."""
    usuarios_repo.init_usuarios_table()
    st.markdown("**Usuarios del dashboard**")
    st.caption("Las cuentas son de esta laptop: funcionan sin internet y no se sincronizan a la nube.")
    usuarios = usuarios_repo.listar()

    col_lista, col_acciones = st.columns([1.4, 1], gap="medium")
    with col_lista:
        tabla = pd.DataFrame([{
            "Usuario": u["usuario"], "Nombre": u["nombre"], "Rol": ROLES[u["rol"]],
            "Estado": "Activo" if u["activo"] else "Desactivado",
            "Último ingreso": (u["ultimo_ingreso"] or "—").replace("T", " "),
        } for u in usuarios])
        st.dataframe(tabla, hide_index=True, width="stretch")
        with st.expander("Qué puede hacer cada rol"):
            for rol, texto in DESCRIPCION_ROLES.items():
                st.markdown(f"- **{ROLES[rol]}:** {texto}")
    with col_acciones:
        _editar(usuarios, yo)
    _alta(yo)
    _registro()


def _registro() -> None:
    """Las últimas acciones registradas: ingresos (también los fallidos),
    salidas, cambios de usuarios y respaldos. No incluye contraseñas."""
    with st.expander("Registro de accesos y cambios"):
        filas = registro_repo.listar(limite=300)
        if not filas:
            st.caption("Todavía no hay nada registrado.")
            return
        st.dataframe(pd.DataFrame([{
            "Fecha": f["fecha"].replace("T", " "),
            "Quién": f["actor"],
            "Acción": registro_repo.ACCIONES.get(f["accion"], f["accion"]),
            "Sobre": f["objetivo"] or "",
            "Detalle": f["detalle"] or "",
        } for f in filas]), hide_index=True, width="stretch", height=320)
        st.caption("Las 300 más recientes. Se guarda en la base local, junto con los usuarios.")
