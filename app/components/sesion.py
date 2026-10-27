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

Inactividad: después de INACTIVIDAD_MAX_MIN minutos sin usar el dashboard,
la sesión se cierra. Cuenta como uso cualquier corrida que pase por
usuario_actual(), incluido el video reproduciéndose (cada avance del video
actualiza la cancha). vigilar_inactividad() revisa cada minuto, para que
una laptop desatendida no quede con el partido a la vista hasta que alguien
la toque.

Ingresos fallidos: el bloqueo lo decide usuarios_repo.verificar (por nombre
de usuario, contando en el registro de accesos).
"""

import sys
import time
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.db import registro_repo, respaldo, usuarios_repo  # noqa: E402

_CLAVE = "usuario_id"
_ACTIVIDAD = "_ultima_actividad"
INACTIVIDAD_MAX_MIN = 30


def _vencida() -> bool:
    ultima = st.session_state.get(_ACTIVIDAD)
    return ultima is not None and time.time() - ultima > INACTIVIDAD_MAX_MIN * 60


def usuario_actual() -> dict | None:
    """El usuario de esta sesión (activo), o None si no ingresó, lo
    desactivaron o la sesión venció por inactividad. Cada llamada cuenta
    como actividad."""
    usuario_id = st.session_state.get(_CLAVE)
    if usuario_id is None:
        return None
    usuario = usuarios_repo.obtener(usuario_id)
    if usuario is None or not usuario["activo"]:
        _cerrar_sesion()
        return None
    if _vencida():
        registro_repo.registrar("sesion_vencida", usuario, objetivo=usuario["usuario"],
                                detalle=f"{INACTIVIDAD_MAX_MIN} min sin actividad")
        _cerrar_sesion()
        st.session_state["_aviso_login"] = "La sesión se cerró por inactividad. Volvé a ingresar."
        return None
    st.session_state[_ACTIVIDAD] = time.time()
    return usuario


@st.fragment(run_every=60)
def vigilar_inactividad() -> None:
    """Cada minuto, si la sesión venció, redibuja la app (que muestra el
    ingreso). No llama a usuario_actual(), para no contar como actividad."""
    if st.session_state.get(_CLAVE) is not None and _vencida():
        st.rerun(scope="app")


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
        aviso = st.session_state.pop("_aviso_login", None)
        if aviso:
            st.info(aviso, icon=":material/schedule:")
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
            try:
                u = usuarios_repo.verificar(usuario, contrasena)
            except usuarios_repo.IngresoBloqueado as e:
                st.error(str(e))
                return
            if u is None:
                time.sleep(0.5)   # frena intentos repetidos sin molestar al que se equivocó una vez
                st.error("Usuario o contraseña incorrectos, o el usuario está desactivado.")
                return
            st.session_state[_CLAVE] = u["id"]
            st.session_state[_ACTIVIDAD] = time.time()
            _respaldo_diario()
            st.rerun()


def _respaldo_diario() -> None:
    """Al ingresar, si el último respaldo automático tiene más de un día, hace
    otro (la base y las calibraciones pesan pocos MB: tarda menos de un
    segundo). Si falla, avisa pero no impide entrar."""
    try:
        respaldo.respaldo_si_corresponde()
    except Exception as e:  # noqa: BLE001 — un respaldo fallido no puede dejar afuera al usuario
        st.toast(f"No se pudo hacer el respaldo diario de la base: {e}", icon=":material/warning:")


def _cerrar_sesion() -> None:
    st.session_state.pop(_CLAVE, None)
    st.session_state.pop(_ACTIVIDAD, None)
    st.session_state.pop("_ver_usuarios", None)


def _salir(usuario: dict) -> None:
    registro_repo.registrar("salida", usuario, objetivo=usuario["usuario"])
    _cerrar_sesion()


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
                if not usuarios_repo.comprobar_contrasena(usuario["id"], actual):
                    st.error("La contraseña actual no es correcta.")
                elif nueva != repetida:
                    st.error("Las contraseñas nuevas no coinciden.")
                else:
                    try:
                        usuarios_repo.cambiar_contrasena(usuario["id"], nueva, actor=usuario)
                        st.success("Contraseña actualizada.")
                    except ValueError as e:
                        st.error(str(e))
        if usuarios_repo.puede(usuario["rol"], "administrar_usuarios"):
            st.button("Usuarios", icon=":material/group:", width="stretch", key="abrir_usuarios",
                      on_click=lambda: st.session_state.update(_ver_usuarios=True))
        st.button("Salir", icon=":material/logout:", on_click=_salir, args=(usuario,), width="stretch", key="salir")
