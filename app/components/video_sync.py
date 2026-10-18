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
El archivo vive en data/outputs/ (fuera de app/). Hay dos caminos, según
el tamaño:

- **Hasta 200 MB:** como estático de Streamlit, desde app/static/ (con
  server.enableStaticServing=true en .streamlit/config.toml).
  _asegurar_video_estatico() lo expone ahí con un HARDLINK (mismo inodo —
  no duplica el video en disco) y solo cae a copiarlo si el filesystem no
  soporta hardlinks. En app/static/videos/ queda SOLO el video del partido
  abierto: Streamlit desactiva todos los estáticos al arrancar si la
  carpeta pasa 1 GB, y llegó a estar en 1.02 GB juntando videos viejos.
- **Más de 200 MB** (un partido de 90 min: ~345 MB en H.264; los 27 min
  de sportivo_crop3 pesan 103 MB): Streamlit responde 404 ("File is too large") a los estáticos
  más grandes que eso. Se sirven desde un servidor local propio
  (_servidor_videos(): Starlette + uvicorn, que ya vienen con Streamlit),
  que arranca solo la primera vez que hace falta y vive mientras viva el
  dashboard. Responde "range requests" (pedir un tramo del archivo), que
  es lo que usa el navegador para adelantar y retroceder sin bajar el
  video entero. Solo sirve los videos que registra esta misma app.

⚠️ app/static/ se genera sola, en tiempo de ejecución — no es código
fuente. Está en .gitignore: si te aparece en `git status`, es esperable,
no hay que agregarla.
"""

import hashlib
import os
import shutil
import socket
import threading
from pathlib import Path

import streamlit as st

_APP_DIR = Path(__file__).resolve().parent.parent  # app/
_STATIC_VIDEOS_DIR = _APP_DIR / "static" / "videos"

# Tamaño máximo que Streamlit sirve como estático (MAX_APP_STATIC_FILE_SIZE en
# streamlit/web/server/starlette/starlette_server_config.py): más grande → 404.
# VIDEO_LIMITE_ESTATICO_MB permite bajarlo para probar el servidor local con un
# video chico (p.ej. `VIDEO_LIMITE_ESTATICO_MB=50 streamlit run app/main.py`).
LIMITE_ESTATICO_BYTES = int(os.environ.get("VIDEO_LIMITE_ESTATICO_MB", "200")) * 1024 * 1024

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

  // Video grande: lo sirve el servidor local (otro puerto, mismo host que la
  // página — así funciona igual si el dashboard se abre desde otra máquina
  // de la red). Video chico: ruta relativa a los estáticos de Streamlit.
  const nextSrc = data?.puerto
    ? `http://${window.location.hostname}:${data.puerto}${data.ruta}`
    : (data?.src ?? "")

  // Hidratación: solo se toca el <video> si la URL realmente cambió (p.ej.
  // el usuario eligió otro partido). Si se reasignara "src" en cada
  // re-render del componente —que puede pasar varias veces por segundo
  // mientras el video corre— se reiniciaría la reproducción todo el tiempo.
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
    _limpiar_estaticos(dejar=destino)

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


def _limpiar_estaticos(dejar: Path | None = None) -> None:
    """Saca de app/static/videos/ todos los videos menos `dejar`. Son
    hardlinks (o copias) de data/outputs/: borrarlos no borra el original, y
    se vuelven a crear solos al abrir ese partido."""
    if not _STATIC_VIDEOS_DIR.exists():
        return
    for archivo in _STATIC_VIDEOS_DIR.iterdir():
        if archivo.is_file() and archivo != dejar:
            archivo.unlink()


class _ServidorVideos:
    """Servidor HTTP local para videos de más de LIMITE_ESTATICO_BYTES.

    Escucha en un puerto libre que elige el sistema, en la misma interfaz
    que el dashboard (server.address, o todas si no está configurada).
    Solo responde por los archivos registrados con registrar(): la URL lleva
    un identificador derivado de la ruta, no la ruta en sí.
    """

    def __init__(self):
        from starlette.applications import Starlette
        from starlette.responses import FileResponse, Response
        from starlette.routing import Route
        import uvicorn

        self._videos: dict[str, Path] = {}

        async def servir(request):
            ruta = self._videos.get(request.path_params["clave"])
            if ruta is None or not ruta.exists():
                return Response("Video no registrado", status_code=404)
            # FileResponse de Starlette responde los "Range" con 206 (tramo
            # del archivo): es lo que permite adelantar/retroceder.
            return FileResponse(ruta, media_type="video/mp4",
                                headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"})

        app = Starlette(routes=[Route("/videos/{clave}/{nombre}", servir)])
        host = st.get_option("server.address") or "0.0.0.0"
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((host, 0))
        self.puerto = self._socket.getsockname()[1]
        servidor = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
        hilo = threading.Thread(target=servidor.run, kwargs={"sockets": [self._socket]},
                                name="servidor-videos", daemon=True)
        hilo.start()

    def registrar(self, video_path: Path) -> str:
        """Devuelve la ruta URL (sin host ni puerto) con que se pide este video."""
        video_path = Path(video_path).resolve()
        clave = hashlib.sha1(str(video_path).encode()).hexdigest()[:16]
        self._videos[clave] = video_path
        return f"/videos/{clave}/{video_path.name}"


@st.cache_resource(show_spinner=False)
def _servidor_videos() -> _ServidorVideos:
    """Uno solo por proceso del dashboard: cache_resource lo comparte entre
    sesiones y sobrevive a los reruns y a la recarga de este módulo."""
    return _ServidorVideos()


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
    video_path = Path(video_path)
    if not video_path.exists():
        return None

    datos = {"intervaloMs": INTERVALO_SONDEO_MS, "umbralSeg": _UMBRAL_CAMBIO_SEG}
    if video_path.stat().st_size <= LIMITE_ESTATICO_BYTES:
        datos["src"] = _asegurar_video_estatico(video_path)
    else:
        _limpiar_estaticos()
        servidor = _servidor_videos()
        datos["puerto"] = servidor.puerto
        datos["ruta"] = servidor.registrar(video_path)

    resultado = _COMPONENT(
        key=key,
        data=datos,
        on_tick_change=lambda: None,
    )
    return resultado.tick
