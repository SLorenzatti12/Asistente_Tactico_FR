"""
Partidos y tiempos — alta y listado
=====================================
Filmamos un archivo por tiempo: cada video se procesa por separado (su
parquet, calibración, dirección de ataque y equipos) y esta tabla los agrupa
en un partido. El equipo y el estadio se asignan una vez y se copian a los
dos tiempos.

Ejemplos:
    python3 scripts/partidos.py alta "Sportivo vs Crecer 2026-09-27" \\
        --t1 sportivo_crecer_t1 --t2 sportivo_crecer_t2 --estadio "Sportivo Belgrano" --equipo "Primera"
    python3 scripts/partidos.py listar

Los nombres de --t1/--t2 son los de los videos sin extensión (los mismos que
usa el dashboard). Si un tiempo todavía no está filmado o procesado, se puede
dar de alta solo uno y agregar el otro después.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db import estadio_repo, partido_repo, team_repo  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Partidos y sus tiempos",
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)
    alta = sub.add_parser("alta", help="Alta o corrección de un partido")
    alta.add_argument("partido")
    alta.add_argument("--t1", default=None, help="Video del primer tiempo (sin extensión)")
    alta.add_argument("--t2", default=None, help="Video del segundo tiempo (sin extensión)")
    alta.add_argument("--estadio", default=None, help="Estadio (ver scripts/estadios.py): se asigna a los dos tiempos")
    alta.add_argument("--equipo", default=None, help="Equipo/categoría (ver la app): se asigna a los dos tiempos")
    sub.add_parser("listar", help="Lista los partidos y sus tiempos")
    args = parser.parse_args()

    partido_repo.init_partidos_table()
    if args.comando == "listar":
        partidos = partido_repo.list_partidos()
        if not partidos:
            print("No hay partidos cargados.")
        for nombre, tiempos in partidos.items():
            print(f"- {nombre}: " + " · ".join(f"{t['tiempo']}° tiempo = {t['match_name']}" for t in tiempos))
        return

    if not args.t1 and not args.t2:
        sys.exit("[ERROR] Indicá al menos un tiempo: --t1 y/o --t2")
    videos = [v for v in (args.t1, args.t2) if v]
    for tiempo, video in ((1, args.t1), (2, args.t2)):
        if video:
            partido_repo.set_tiempo(video, args.partido, tiempo)
            print(f"✅ {args.partido}: {tiempo}° tiempo = {video}")
    if args.estadio:
        estadio_repo.init_estadios_table()
        estadio = estadio_repo.get_estadio(args.estadio)
        if estadio is None:
            sys.exit(f"[ERROR] No existe el estadio '{args.estadio}' (ver python3 scripts/estadios.py listar)")
        for v in videos:
            estadio_repo.set_match_estadio(v, estadio["id"])
        print(f"   Estadio {args.estadio} asignado a: {', '.join(videos)}")
    if args.equipo:
        team_repo.init_teams_table()
        equipo = next((t for t in team_repo.list_teams() if t["name"] == args.equipo), None)
        if equipo is None:
            sys.exit(f"[ERROR] No existe el equipo '{args.equipo}' (se crean desde la app, panel Partido)")
        for v in videos:
            team_repo.set_match_team(v, equipo["id"])
        print(f"   Equipo {args.equipo} asignado a: {', '.join(videos)}")


if __name__ == "__main__":
    main()
