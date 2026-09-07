"""
Analizador Táctico — Descarga de videos de YouTube
===================================================
Descarga un partido desde YouTube en 720p (ideal para YOLOv8).
El video queda en data/videos/ listo para procesar.

Uso:
    python scripts/download_video.py "https://youtube.com/watch?v=..."
    python scripts/download_video.py "https://youtube.com/watch?v=..." --start 00:05:00 --duration 00:10:00
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT        = Path(__file__).resolve().parent.parent
VIDEOS_DIR  = ROOT / "data" / "videos"

# Tip para conseguir videos de fondo (cámara de arco):
# Buscar en YouTube: "fútbol amateur cámara aérea fondo" / "football end zone camera"
# Cualquier video con la cámara fija en altura desde un extremo sirve para testear


def _add_duration(start: str, duration: str) -> str:
    """Suma start + duration (ambos HH:MM:SS) y devuelve el tiempo final HH:MM:SS."""
    def to_seconds(t: str) -> int:
        h, m, s = (int(x) for x in t.split(":"))
        return h * 3600 + m * 60 + s

    total = to_seconds(start) + to_seconds(duration)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def download(url: str, out_dir: Path, start: str = None, duration: str = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # Formato: 720p mp4 — balance calidad/velocidad de inferencia
    fmt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]"

    cmd = [
        "yt-dlp",
        url,
        "--format", fmt,
        "--output", str(out_dir / "%(title).60s.%(ext)s"),  # max 60 chars en nombre
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--no-warnings",
    ]

    # Recorte opcional: útil para testear solo los primeros 10 minutos
    # yt-dlp espera el formato "*inicio-fin" (ambos tiempos absolutos, no una duración)
    if start or duration:
        real_start = start or "00:00:00"
        if duration:
            real_end = _add_duration(real_start, duration)
            section = f"*{real_start}-{real_end}"
        else:
            section = f"*{real_start}-inf"  # sin duration: desde el start hasta el final
        cmd += ["--download-sections", section, "--force-keyframes-at-cuts"]
        print(f"[INFO] Recortando: desde {real_start} hasta {real_end if duration else 'el final'}")

    print(f"[INFO] URL: {url}")
    print(f"[INFO] Destino: {out_dir}")
    print("[INFO] Resolución: 720p mp4\n")

    result = subprocess.run(cmd, check=False)

    if result.returncode != 0:
        print("\n[ERROR] Falló la descarga.")
        print("  ¿Está instalado yt-dlp? → pip install yt-dlp")
        print("  ¿El video es público/accesible?")
        sys.exit(1)

    print(f"\n[OK] Video guardado en: {out_dir}")
    print("[OK] Listo para correr: python src/detection/run_inference.py <ruta_al_video>")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Descarga videos de YouTube para el Analizador Táctico",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Partido completo
  python scripts/download_video.py "https://youtube.com/watch?v=XXXX"

  # Solo los primeros 10 minutos (más rápido para testear)
  python scripts/download_video.py "https://youtube.com/watch?v=XXXX" --start 00:00:00 --duration 00:10:00

  # Desde el minuto 45 (segundo tiempo)
  python scripts/download_video.py "https://youtube.com/watch?v=XXXX" --start 00:45:00 --duration 00:45:00
        """,
    )
    parser.add_argument("url",        type=str, help="URL del video de YouTube")
    parser.add_argument("--start",    type=str, default=None, help="Inicio del recorte (HH:MM:SS)")
    parser.add_argument("--duration", type=str, default=None, help="Duración del recorte (HH:MM:SS)")
    args = parser.parse_args()

    download(args.url, VIDEOS_DIR, args.start, args.duration)
