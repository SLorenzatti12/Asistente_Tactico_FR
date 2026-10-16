"""
Estadios y medidas de cancha — alta, listado y asignación a partidos
=====================================================================
Las medidas se cargan una vez por estadio (tabla `estadios`, ver
src/db/estadio_repo.py) y calibrate.py las copia a cada calibración.

Ejemplos:
    # Alta (o corrección) de un estadio — marcas omitidas = reglamentarias
    python scripts/estadios.py alta "Sportivo Belgrano" --largo 100 --ancho 70
    python scripts/estadios.py alta "Sportivo Belgrano" --largo 100 --ancho 70 --area-chica-largo 6

    python scripts/estadios.py listar

    # Qué estadio corresponde a un partido (match_name = nombre del video sin extensión)
    python scripts/estadios.py asignar sportivo_crop3 "Sportivo Belgrano"

Corregir las medidas de un estadio NO cambia las calibraciones ya hechas
(guardan una copia): hay que volver a calibrar y a correr --apply.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db import estadio_repo as repo  # noqa: E402
from src.homography.medidas_cancha import descripcion  # noqa: E402

MARCAS = ("area_grande_largo", "area_grande_ancho", "area_chica_largo", "area_chica_ancho",
          "radio_circulo", "distancia_penal")


def main() -> None:
    parser = argparse.ArgumentParser(description="Estadios y medidas de cancha",
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)

    alta = sub.add_parser("alta", help="Alta o corrección de un estadio")
    alta.add_argument("nombre")
    alta.add_argument("--largo", type=float, required=True, help="Largo de la cancha, arco a arco (m)")
    alta.add_argument("--ancho", type=float, required=True, help="Ancho de la cancha, lateral a lateral (m)")
    for marca in MARCAS:
        alta.add_argument(f"--{marca.replace('_', '-')}", type=float, default=None,
                          help="(m) — omitido: reglamentaria")

    sub.add_parser("listar", help="Lista los estadios cargados")

    asignar = sub.add_parser("asignar", help="Asigna un estadio a un partido")
    asignar.add_argument("match_name", help="Nombre del partido (el del video, sin extensión)")
    asignar.add_argument("estadio")

    args = parser.parse_args()
    repo.init_estadios_table()

    if args.comando == "alta":
        marcas = {m: getattr(args, m) for m in MARCAS if getattr(args, m) is not None}
        previo = repo.get_estadio(args.nombre)
        repo.upsert_estadio(args.nombre, args.largo, args.ancho, **marcas)
        estadio = repo.get_estadio(args.nombre)
        print(f"✅ {'Actualizado' if previo else 'Creado'}: {descripcion(estadio['medidas'])}")
        if previo and previo["medidas"] != estadio["medidas"]:
            print("   Las calibraciones ya hechas en este estadio guardaron las medidas viejas: "
                  "volvé a calibrar y a correr --apply para usar las nuevas.")
    elif args.comando == "listar":
        estadios = repo.list_estadios()
        if not estadios:
            print("No hay estadios cargados. Alta: python scripts/estadios.py alta <nombre> --largo L --ancho A")
        for e in estadios:
            marcas = {k: v for k, v in e["medidas"].items() if k not in ("largo", "ancho", "estadio")}
            extra = f"  marcas no reglamentarias: {marcas}" if marcas else ""
            print(f"- {descripcion(e['medidas'])}{extra}")
    elif args.comando == "asignar":
        estadio = repo.get_estadio(args.estadio)
        if estadio is None:
            sys.exit(f"[ERROR] No existe el estadio '{args.estadio}'. Listado: python scripts/estadios.py listar")
        repo.set_match_estadio(args.match_name, estadio["id"])
        print(f"✅ {args.match_name} → {descripcion(estadio['medidas'])}")


if __name__ == "__main__":
    main()
