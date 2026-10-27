"""
Usuarios del dashboard — alta y mantenimiento por consola
===========================================================
El primer administrador se crea acá; después, el admin da de alta y
administra al resto desde la vista "Usuarios" del dashboard. Las
contraseñas se piden por teclado (nunca como argumento, para que no queden
en el historial de la terminal).

Ejemplos:
    python3 scripts/usuarios.py crear santi --nombre "Santiago Lorenzatti" --rol admin
    python3 scripts/usuarios.py listar
    python3 scripts/usuarios.py contrasena santi        # si alguien se olvidó la suya (y lo desbloquea)
    python3 scripts/usuarios.py registro                # últimos accesos y cambios

Roles: admin, analyst (analista), coach (cuerpo técnico), viewer (solo lectura).
"""

import argparse
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db import registro_repo, usuarios_repo  # noqa: E402


def _pedir_contrasena() -> str:
    while True:
        c1 = getpass.getpass("Contraseña: ")
        error = usuarios_repo.validar_contrasena(c1)
        if error:
            print(f"  {error}")
            continue
        if getpass.getpass("Repetila: ") != c1:
            print("  No coinciden, probá de nuevo.")
            continue
        return c1


def main() -> None:
    parser = argparse.ArgumentParser(description="Usuarios del dashboard",
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)
    crear = sub.add_parser("crear", help="Alta de un usuario")
    crear.add_argument("usuario")
    crear.add_argument("--nombre", required=True)
    crear.add_argument("--rol", default="admin", choices=list(usuarios_repo.ROLES))
    sub.add_parser("listar", help="Lista los usuarios")
    registro = sub.add_parser("registro", help="Últimos accesos y cambios")
    registro.add_argument("-n", type=int, default=40, help="Cuántas filas (default 40)")
    contrasena = sub.add_parser("contrasena", help="Pone una contraseña nueva")
    contrasena.add_argument("usuario")
    args = parser.parse_args()

    usuarios_repo.init_usuarios_table()
    if args.comando == "registro":
        for f in reversed(registro_repo.listar(limite=args.n)):
            print(f"{f['fecha'].replace('T', ' ')}  {f['actor']:<14} "
                  f"{registro_repo.ACCIONES.get(f['accion'], f['accion']):<42} {f['objetivo'] or '':<16} {f['detalle'] or ''}")
        return
    if args.comando == "listar":
        usuarios = usuarios_repo.listar()
        if not usuarios:
            print("No hay usuarios. Creá el primer admin con: python3 scripts/usuarios.py crear <usuario> --nombre \"...\"")
        for u in usuarios:
            estado = "activo" if u["activo"] else "desactivado"
            print(f"- {u['usuario']:<16} {u['nombre']:<28} {usuarios_repo.ROLES[u['rol']]:<16} {estado:<12} "
                  f"último ingreso: {u['ultimo_ingreso'] or '—'}")
        return

    if args.comando == "crear":
        try:
            u = usuarios_repo.crear_usuario(args.usuario, args.nombre, args.rol, _pedir_contrasena())
        except ValueError as e:
            sys.exit(f"[ERROR] {e}")
        print(f"✅ Usuario '{u['usuario']}' creado ({usuarios_repo.ROLES[u['rol']]}).")
        return

    u = usuarios_repo.obtener_por_usuario(args.usuario)
    if u is None:
        sys.exit(f"[ERROR] No existe el usuario '{args.usuario}'.")
    usuarios_repo.cambiar_contrasena(u["id"], _pedir_contrasena())
    print(f"✅ Contraseña de '{u['usuario']}' actualizada.")


if __name__ == "__main__":
    main()
