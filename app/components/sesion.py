"""
Analizador Táctico — Sesión: ingreso, usuario actual y permisos
=================================================================
Santi. Login local (sin internet) sobre src/db/usuarios_repo.py: la
pantalla de ingreso, el usuario de la sesión y el menú del usuario en el
encabezado (cambiar contraseña, salir).

La sesión vive en st.session_state (una por pestaña del navegador): al
recargar la página hay que volver a ingresar. En cada corrida el usuario se
relee de la base, así que si el admin lo desactiva o le cambia el rol, el
cambio aplica en la próxima interacción.
"""

import sys
import time
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.db import usuarios_repo  # noqa: E402

_CLAVE = "usuario_id"


def usuario_actual() -> dict | None:
    """El usuario de esta sesión (activo), o None si no ingresó."""
    usuario_id = st.session_state.get(_CLAVE)
    if usuario_id is None:
        return None
    usuario = usuarios_repo.obtener(usuario_id)
    if usuario is None or not usuario["activo"]:
        st.session_state.pop(_CLAVE, None)
        return None
    return usuario


def puede(permiso: str) -> bool:
    """¿El usuario de esta sesión tiene este permiso? (ver usuarios_repo.PERMISOS)."""
    usuario = usuario_actual()
    return usuario is not None and usuarios_repo.puede(usuario["rol"], permiso)


def nombre_rol(rol: str) -> str:
    return usuarios_repo.ROLES.get(rol, rol)


def render_login(html_marca: str) -> None:
    """Pantalla de ingreso. Si las credenciales son correctas, inicia la sesión
    y vuelve a correr la app."""
    usuarios_repo.init_usuarios_table()
    st.html('<div style="height: 12vh"></div>')
    _, centro, _ = st.columns([1, 1.1, 1])
    with centro:
        st.html(html_marca)
        if not usuarios_repo.hay_usuarios():
            st.info(
                "Todavía no hay usuarios. Creá el primer administrador desde la terminal:\n\n"
                "```\npython3 scripts/usuarios.py crear <usuario> --nombre \"Nombre Apellido\" --rol admin\n```"
            )
            return
        with st.form("login", border=True):
            st.markdown("**Ingresar**")
            usuario = st.text_input("Usuario", key="login_usuario")
            contrasena = st.text_input("Contraseña", type="password", key="login_contrasena")
            enviar = st.form_submit_button("Ingresar", type="primary", width="stretch")
        if enviar:
            u = usuarios_repo.verificar(usuario, contrasena)
            if u is None:
                time.sleep(0.5)   # frena intentos repetidos sin molestar al que se equivocó una vez
                st.error("Usuario o contraseña incorrectos, o el usuario está desactivado.")
                return
            st.session_state[_CLAVE] = u["id"]
            st.rerun()


def _cerrar_sesion() -> None:
    st.session_state.pop(_CLAVE, None)
    st.session_state.pop("_ver_usuarios", None)


def render_menu_usuario(usuario: dict) -> None:
    """Menú del encabezado: nombre y rol, cambiar contraseña y salir."""
    with st.popover(usuario["nombre"].split()[0], icon=":material/account_circle:", width="stretch"):
        st.markdown(f"**{usuario['nombre']}**")
        st.caption(f"{usuario['usuario']} · {nombre_rol(usuario['rol'])}")
        with st.form("cambiar_contrasena", border=False, clear_on_submit=True):
            st.markdown("Cambiar contraseña")
            actual = st.text_input("Contraseña actual", type="password")
            nueva = st.text_input("Contraseña nueva", type="password")
            repetida = st.text_input("Repetí la nueva", type="password")
            if st.form_submit_button("Guardar contraseña"):
                if usuarios_repo.verificar(usuario["usuario"], actual) is None:
                    st.error("La contraseña actual no es correcta.")
                elif nueva != repetida:
                    st.error("Las contraseñas nuevas no coinciden.")
                else:
                    try:
                        usuarios_repo.cambiar_contrasena(usuario["id"], nueva)
                        st.success("Contraseña actualizada.")
                    except ValueError as e:
                        st.error(str(e))
        if usuarios_repo.puede(usuario["rol"], "administrar_usuarios"):
            st.button("Usuarios", icon=":material/group:", width="stretch", key="abrir_usuarios",
                      on_click=lambda: st.session_state.update(_ver_usuarios=True))
        st.button("Salir", icon=":material/logout:", on_click=_cerrar_sesion, width="stretch", key="salir")
