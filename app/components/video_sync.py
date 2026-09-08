"""
Analizador Táctico — Reproductor de video sincronizado (CCv2)
==================================================================
Santi — Reemplaza a st.video() en la pestaña "Análisis": expone el
tiempo real de reproducción a Python, para que el mapa 2D (map_view.py)
y el panel de métricas se actualicen solos en vez de quedarse fijos en
current_time = 0 como pasaba con st.video().

Por qué un componente custom
------------------------------
st.video() no expone su tiempo de reproducción — no hay forma de leer
"en qué segundo va" desde Python. Se resuelve con un componente CCv2
(Custom Components v2) que embebe un <video> HTML real: un timer en JS
sondea `video.currentTime` unas pocas veces por segundo y lo manda a
Python con `setStateValue()`.

Nota de versión: la implementación "clásica" de este patrón usa
`streamlit.components.v1.html()` + `Streamlit.setComponentValue()`
(postMessage). Esa API es v1, está deprecada, y esta skill del proyecto
la prohíbe para código nuevo — acá se usa `st.components.v2.component()`
(inline, sin build ni carpeta de proyecto aparte), que es la forma
soportada de lograr lo mismo.

Cómo se sirve el video
------------------------
El archivo vive en data/outputs/ (fuera de app/), y Streamlit solo puede
servir estáticos desde app/static/ (con server.enableStaticServing=true
en .streamlit/config.toml). _asegurar_video_estatico() expone el video
ahí con un HARDLINK (mismo inodo — no duplica los ~90MB en disco) y solo
cae a copiarlo si el filesystem no soporta hardlinks.

⚠️ app/static/ se genera sola, en tiempo de ejecución — no es código
fuente. Está en .gitignore: si te aparece en `git status`, es esperable,
no hay que agregarla.
"""

import os
import shutil
from pathlib import Path

import streamlit as st

_APP_DIR = Path(__file__).resolve().parent.parent  # app/
_STATIC_VIDEOS_DIR = _APP_DIR / "static" / "videos"

# Cada cuánto el JS sondea video.currentTime y (si cambió) avisa a Python.
# 4 Hz alcanza para que el mapa se sienta "en vivo"; 30 fps (cada frame de
# video) dispararía 7-8x más reruns sin ninguna ganancia perceptible en un
# mapa 2D de posiciones — se nota tan fluido a 4Hz como a 30fps.
INTERVALO_SONDEO_MS = 250

# Diferencia mínima (segundos) para considerar que el tiempo "cambió de
# verdad" y vale la pena avisarle a Python. Filtra el jitter de punto
# flotante del propio <video> y evita reruns de más con el video pausado.
_UMBRAL_CAMBIO_SEG = 0.05


_HTML = """
<div id="video-sync-wrap">
  <video id="video-sync-el" controls playsinline></video>
</div>
"""

# `var(--st-*, fallback)` — toma el tema activo de Streamlit (el mismo que
# define .streamlit/config.toml / app/theme.py) en vez de hardcodear los
# colores acá de nuevo; el fallback es el mismo valor por si el componente
# se usara alguna vez fuera de este tema.
_CSS = """
#video-sync-wrap {
  border-radius: var(--st-base-radius, 8px);
  overflow: hidden;
  border: 1px solid var(--st-border-color, #2a2f3a);
  background: var(--st-secondary-background-color, #181c25);
  line-height: 0;   /* <video> es inline por default: sin esto queda un hueco de unos px abajo */
}
#video-sync-el {
  display: block;
  width: 100%;
  background: #000;
}
"""

# Recordatorio (ver docstring del módulo): SOLO API v2 acá.
# setTriggerValue(...) sí — Streamlit.setComponentValue(...) NO.
#
# TRIGGER y no STATE a propósito: un trigger se resetea a None apenas se lo
# lee, así que Python puede distinguir "el video acaba de mandar un tiempo
# nuevo en ESTA corrida" (valor presente) de "esta corrida la disparó otra
# cosa" (valor None) — el slider manual, un tag, cualquier otro widget. Con
# STATE no se puede distinguir eso: el último valor mandado queda pegado y
# se reafirma en cada rerun del fragmento, así lo haya disparado el video o
# no, y termina pisando el slider manual apenas se lo toca (ver docstring
# de render_video_sincronizado).
_JS = """
export default function (component) {
  const { data, parentElement, setTriggerValue } = component
  const video = parentElement.querySelector("#video-sync-el")
  if (!video) return

  // Hidratación: solo se toca el <video> si la URL realmente cambió (p.ej.
  // el usuario eligió otro partido). Si se reasignara "src" en cada
  // re-render del componente —que puede pasar varias veces por segundo
  // mientras el video corre— se reiniciaría la reproducción todo el tiempo.
  const nextSrc = data?.src ?? ""
  if (video.getAttribute("src") !== nextSrc) {
    video.setAttribute("src", nextSrc)
  }

  // El timer se crea UNA sola vez por instancia del componente, no en cada
  // re-render (que Streamlit dispara cada vez que este mismo componente
  // llama a setTriggerValue — si se recreara el interval acá adentro,
  // nunca se estabilizaría). Se guarda en el propio parentElement para que
  // sobreviva a los re-renders y no choque con otras instancias del mismo
  // componente si hubiera más de una en la página.
  if (!parentElement._videoSyncTimer) {
    const intervaloMs = data?.intervaloMs ?? 250
    const umbralSeg = data?.umbralSeg ?? 0.05
    let ultimoEnviado = null

    parentElement._videoSyncTimer = setInterval(() => {
      const t = video.currentTime
      if (ultimoEnviado === null || Math.abs(t - ultimoEnviado) > umbralSeg) {
        ultimoEnviado = t
        setTriggerValue("tick", t)
      }
    }, intervaloMs)
  }

  // Se llama cuando Streamlit desmonta esta instancia del todo (no en cada
  // re-render) — ver "Frontend renderer lifecycle" de la guía de CCv2.
  return () => {
    if (parentElement._videoSyncTimer) {
      clearInterval(parentElement._videoSyncTimer)
      parentElement._videoSyncTimer = null
    }
  }
}
"""

# Se registra UNA sola vez, a nivel de módulo (no adentro de la función que
# se llama por cada partido) — así no se re-registra el componente en cada
# rerun. render_video_sincronizado() de más abajo es la API pública.
_COMPONENT = st.components.v2.component(
    "video_sync",
    html=_HTML,
    css=_CSS,
    js=_JS,
)


def _asegurar_video_estatico(video_path: Path) -> str | None:
    """
    Expone `video_path` bajo app/static/videos/ y devuelve la URL relativa
    que puede usar un <video src=...>. None si el archivo de origen no existe.

    Usa un hardlink (mismo inodo, no duplica el video en disco) y cae a
    copiarlo solo si el filesystem no lo permite (por ejemplo, si
    app/static/ y data/outputs/ terminaran en discos/volúmenes distintos).
    Es barata de llamar seguido: si el destino ya existe y su mtime
    coincide con el del original, no vuelve a tocar el disco.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        return None

    _STATIC_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    destino = _STATIC_VIDEOS_DIR / video_path.name

    origen_mtime = video_path.stat().st_mtime
    if not destino.exists() or destino.stat().st_mtime != origen_mtime:
        if destino.exists():
            destino.unlink()
        try:
            os.link(video_path, destino)
        except OSError:
            shutil.copyfile(video_path, destino)
        os.utime(destino, (origen_mtime, origen_mtime))

    return f"app/static/videos/{video_path.name}"


def render_video_sincronizado(video_path: Path, key: str) -> float | None:
    """
    Reproductor de video que expone su tiempo de reproducción a Python.

    Reemplaza a st.video() en el flujo de la pestaña "Análisis": a
    diferencia de st.video(), esta función devuelve el segundo actual de
    reproducción, actualizado ~4 veces por segundo mientras el video corre
    (play), quieto mientras está pausado, y saltando al instante correcto
    apenas el usuario arrastra la barra de progreso del navegador (seek) —
    en los tres casos porque lee directamente `video.currentTime` del
    elemento <video> real, no un cronómetro aparte.

    Args:
        video_path: ruta al .mp4 a reproducir.
        key: key único de Streamlit — usar uno distinto por partido
            (p. ej. f"video_{nombre_partido}") para que cambiar de partido
            monte una instancia nueva del componente, no reutilice estado
            del video anterior.

    Returns:
        El segundo de reproducción que el video acaba de reportar (float),
        SOLO en la corrida donde lo reportó — en cualquier otra corrida
        (el usuario tocó el slider manual, un botón de tagueo, cambió de
        partido, lo que sea) devuelve None. Esto es a propósito: es lo que
        le permite al caller (ver _panel_sincronizado en main.py) escribir
        simplemente "si no es None, lo pisa"; el resto de las corridas no
        toca current_time y deja que gane el valor que haya puesto el
        slider — sin este contrato, el video reafirmaría su último tiempo
        conocido en CADA rerun y el slider manual nunca podría ganarle.

        También devuelve None si `video_path` no existe. El caller es
        responsable de chequear eso aparte para decidir si avisarle al
        usuario (ver main.py) — esta función no distingue "no existe" de
        "no hay tick nuevo" porque, para lo único que le importa al caller
        (¿toco current_time o no?), es la misma respuesta: no.
    """
    src = _asegurar_video_estatico(video_path)
    if src is None:
        return None

    resultado = _COMPONENT(
        key=key,
        data={"src": src, "intervaloMs": INTERVALO_SONDEO_MS, "umbralSeg": _UMBRAL_CAMBIO_SEG},
        on_tick_change=lambda: None,
    )
    return resultado.tick
