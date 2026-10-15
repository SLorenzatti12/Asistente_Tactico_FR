"""
Analizador Táctico — Registro de la ruta del video del partido
==================================================
Nico — hace explícita en SQLite la ruta local del video crudo de cada
partido (tabla `match_videos`, ver src/db/video_repo.py), para que
scripts/sync_to_cloud.py sepa qué archivo subir a Supabase Storage cuando
haya internet.

Ojo: acá solo se REGISTRA la ruta y se muestra el estado de subida. La
subida en sí no corre desde este componente — es una operación pesada (el
archivo puede pesar cientos de MB) y correrla dentro del ciclo de request
de Streamlit congelaría la interfaz. Se dispara aparte, cuando hay
internet, con:

    python scripts/sync_to_cloud.py <nombre_del_partido>
"""
import sys
from pathlib import Path

import streamlit as st

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from db import video_repo as repo  # noqa: E402


def render_video_registry(match_name: str, default_path: Path) -> None:
    repo.init_video_table()
    registrado = repo.get_video(match_name)
    ruta_actual = registrado["local_path"] if registrado else str(default_path)

    with st.expander("🎥 Video del partido (ruta local y estado de subida)"):
        nueva_ruta = st.text_input(
            "Ruta del archivo de video en esta computadora",
            value=ruta_actual,
            key=f"video_path_{match_name}",
        )
        col_guardar, col_estado = st.columns([1, 3])
        if col_guardar.button("💾 Guardar ruta", key=f"video_save_{match_name}"):
            if not nueva_ruta.strip():
                st.warning("Ingresá una ruta.")
            else:
                repo.set_video_path(match_name, nueva_ruta.strip())
                st.toast("Ruta guardada")
                st.rerun()

        with col_estado:
            if registrado is None:
                st.caption("Todavía no se guardó la ruta de este video.")
            elif not Path(registrado["local_path"]).exists():
                st.warning(f"No se encuentra el archivo en «{registrado['local_path']}».")
            elif registrado["synced_at"]:
                fecha = registrado["synced_at"][:16].replace("T", " ")
                st.success(f"✅ Subido a la nube el {fecha}.")
            else:
                st.info(
                    "⏳ Pendiente de subir. Con internet, correr:\n\n"
                    f"`python scripts/sync_to_cloud.py {match_name}`"
                )
