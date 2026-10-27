"""
Respaldo de la base local, las calibraciones y los parquets de coordenadas
===========================================================================
El dashboard ya hace uno automático al ingresar si el último tiene más de un
día (en data/respaldos/). Este script es para hacerlos a mano, guardarlos en
otro lugar, verificarlos y restaurarlos. Detalle en src/db/respaldo.py.

Ejemplos:
    python3 scripts/respaldo.py crear
    python3 scripts/respaldo.py crear --destino /Volumes/PENDRIVE/respaldos   # en otro disco
    python3 scripts/respaldo.py listar
    python3 scripts/respaldo.py verificar data/respaldos/respaldo_20261027-101500
    python3 scripts/respaldo.py restaurar data/respaldos/respaldo_20261027-101500
    python3 scripts/respaldo.py restaurar <respaldo> --con-archivos   # también calibraciones y parquets

Antes de restaurar: cerrar el dashboard. La restauración verifica el
respaldo y hace otro del estado actual, para poder deshacerla.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db import respaldo  # noqa: E402


def _resumen(carpeta: Path) -> str:
    m = json.loads((carpeta / "manifiesto.json").read_text())
    mb = sum(a["bytes"] for a in m["archivos"].values()) / 1e6
    filas = sum(m["tablas"].values())
    return f"{carpeta.name}  {m['motivo']:<40} {len(m['archivos']):>3} archivos  {mb:6.1f} MB  {filas} filas"


def main() -> None:
    parser = argparse.ArgumentParser(description="Respaldo de los datos locales",
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)
    crear = sub.add_parser("crear", help="Crea un respaldo y lo verifica")
    crear.add_argument("--destino", type=Path, help=f"Carpeta donde guardarlo (default: {respaldo.dir_respaldos()})")
    listar = sub.add_parser("listar", help="Lista los respaldos de una carpeta")
    listar.add_argument("--carpeta", type=Path)
    verificar = sub.add_parser("verificar", help="Verifica un respaldo (SHA-256, integridad y filas)")
    verificar.add_argument("respaldo", type=Path)
    restaurar = sub.add_parser("restaurar", help="Vuelve los datos al estado de un respaldo")
    restaurar.add_argument("respaldo", type=Path)
    restaurar.add_argument("--con-archivos", action="store_true",
                           help="Restaurar también calibraciones y parquets (si no, solo la base)")
    restaurar.add_argument("--si", action="store_true", help="No pedir confirmación")
    args = parser.parse_args()

    if args.comando == "crear":
        carpeta = respaldo.crear_respaldo(args.destino, motivo="manual")
        print(f"✅ {_resumen(carpeta)}\n   en {carpeta.parent}")
        return

    if args.comando == "listar":
        respaldos = respaldo.listar_respaldos(args.carpeta)
        if not respaldos:
            print("No hay respaldos en", args.carpeta or respaldo.dir_respaldos())
        for carpeta in respaldos:
            print(_resumen(carpeta))
        return

    if args.comando == "verificar":
        problemas = respaldo.verificar_respaldo(args.respaldo)
        if problemas:
            sys.exit("[ERROR] " + "\n[ERROR] ".join(problemas))
        print(f"✅ Verifica: {_resumen(args.respaldo)}")
        return

    que = "la base, las calibraciones y los parquets" if args.con_archivos else "la base"
    if not args.si:
        r = input(f"Se va a reemplazar {que} por el contenido de {args.respaldo.name}. "
                  "¿El dashboard está cerrado y querés seguir? [s/N] ")
        if r.strip().lower() not in ("s", "si", "sí"):
            sys.exit("Cancelado.")
    try:
        previo = respaldo.restaurar(args.respaldo, con_archivos=args.con_archivos)
    except RuntimeError as e:
        sys.exit(f"[ERROR] {e}")
    print(f"✅ Restaurado {args.respaldo.name} ({que}).\n"
          f"   El estado anterior quedó en {previo} — para deshacer, restaurá ese.")


if __name__ == "__main__":
    main()
