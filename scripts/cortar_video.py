"""
Corta un video que tiene los dos tiempos en <video>_t1.mp4 y <video>_t2.mp4,
en el minuto que se indique. Filmamos un archivo por tiempo, así que esto es
para el caso excepcional en que llega un solo archivo con todo: cada tiempo
se procesa después por separado (la dirección de ataque nunca se asume igual
para los dos). Si se procesa un video con los dos tiempos sin cortarlo,
tactical_patterns frena al detectar que los equipos cambian de lado.

Uso:
    python3 scripts/cortar_video.py data/videos/partido_completo.mp4 --en 47:30

Corta sin reencodear (segundos, sin pérdida): el corte cae en el keyframe
más cercano, así que cada parte puede empezar o terminar un par de segundos
antes o después — se informan los tiempos reales. Con --exacto reencodea
(H.264, CRF 18) y corta en el segundo pedido; tarda bastante más.
Después: registrar el partido con scripts/partidos.py.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _segundos(texto: str) -> float:
    if ":" in texto:
        partes = [float(p) for p in texto.split(":")]
        return sum(v * 60 ** i for i, v in enumerate(reversed(partes)))
    return float(texto)


def _duracion(ruta: Path) -> float:
    salida = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                             "-of", "default=nw=1:nk=1", str(ruta)], capture_output=True, text=True)
    return float(salida.stdout.strip())


def _fmt(seg: float) -> str:
    return f"{int(seg // 60)}:{seg % 60:04.1f}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Corta un video en primer y segundo tiempo",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("video")
    ap.add_argument("--en", required=True, help="Dónde cortar: m:ss, h:mm:ss o segundos")
    ap.add_argument("--salida-dir", default=None, help="Carpeta de salida (default: la del video)")
    ap.add_argument("--exacto", action="store_true", help="Reencodear para cortar en el segundo exacto")
    a = ap.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("[ERROR] Hace falta ffmpeg: brew install ffmpeg")
    video = Path(a.video)
    if not video.exists():
        sys.exit(f"[ERROR] No existe {video}")
    corte = _segundos(a.en)
    total = _duracion(video)
    if not 0 < corte < total:
        sys.exit(f"[ERROR] El corte ({_fmt(corte)}) tiene que estar dentro del video (dura {_fmt(total)})")
    destino = Path(a.salida_dir) if a.salida_dir else video.parent
    destino.mkdir(parents=True, exist_ok=True)
    t1, t2 = destino / f"{video.stem}_t1.mp4", destino / f"{video.stem}_t2.mp4"
    for ruta in (t1, t2):
        if ruta.exists():
            sys.exit(f"[ERROR] Ya existe {ruta}: movelo o borralo antes de cortar de nuevo")

    codec = (["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "copy"] if a.exacto
             else ["-c", "copy"])
    for ruta, rango in ((t1, ["-t", str(corte)]), (t2, ["-ss", str(corte)])):
        entrada = ["-ss", str(corte), "-i", str(video)] if ruta == t2 else ["-i", str(video)] + rango
        cmd = ["ffmpeg", "-v", "error", "-y"] + entrada + codec + ["-movflags", "+faststart", str(ruta)]
        if subprocess.run(cmd).returncode != 0:
            sys.exit(f"[ERROR] ffmpeg falló al escribir {ruta}")
    d1, d2 = _duracion(t1), _duracion(t2)
    print(f"✅ {t1.name}: 0:00 – {_fmt(d1)}  ({t1.stat().st_size / 1048576:.0f} MB)")
    print(f"✅ {t2.name}: {_fmt(total - d2)} – {_fmt(total)} del original  ({t2.stat().st_size / 1048576:.0f} MB)")
    if not a.exacto and abs(d1 - corte) > 0.5:
        print(f"   El corte cayó en el keyframe más cercano ({_fmt(d1)} en vez de {_fmt(corte)}). "
              f"Con --exacto se corta en el segundo pedido.")
    print("\nSiguiente paso: registrar el partido (python3 scripts/partidos.py alta ...) y procesar cada tiempo.")


if __name__ == "__main__":
    main()
