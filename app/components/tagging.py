"""
Analizador Táctico — Tagueo one-click y semáforo (Luci)
=========================================================
STUB TEMPORAL — creado por Nico para poder correr la app mientras Luci
desarrolla su módulo. Reemplazar por la implementación real.

Contrato esperado por main.py:
    render_tagging_panel()
    render_semaforo_tab(match_name)
"""
import streamlit as st


def render_tagging_panel() -> None:
    # TODO Luci: botonera de eventos (Salida, Presión, Pelota parada) que
    # exporta clips de 10s a output/clips/.
    st.markdown("**Tagueo** _(en desarrollo — Luci)_")
    st.caption("Stub temporal: la botonera de eventos va acá.")


def render_semaforo_tab(match_name: str) -> None:
    # TODO Luci: semáforo cuali/cuantitativo con histórico en SQLite.
    st.info(f"Semáforo de «{match_name}» en desarrollo (Luci).")
