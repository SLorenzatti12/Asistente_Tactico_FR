"""
Sincronizar SQLite local con Supabase — Nico
===============================================
Correr manualmente cuando hay internet (después del partido / en el club),
NO durante el procesamiento en cancha.

    python scripts/sync_to_cloud.py --all
    python scripts/sync_to_cloud.py "belgrano_vs_rival_2026-09-14"

Requiere SUPABASE_URL y SUPABASE_KEY configuradas — ver .env.example.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from db.sync import sync_all, sync_match  # noqa: E402
from db.supabase_client import SupabaseConfigError  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("match_name", nargs="?", help="Nombre del partido a sincronizar")
    parser.add_argument("--all", action="store_true", help="Sincronizar todos los partidos con datos locales")
    args = parser.parse_args()

    if not args.all and not args.match_name:
        parser.error("Pasá un match_name o usá --all")

    try:
        if args.all:
            resumen = sync_all()
            plantel = resumen.pop("plantel", {})
            for team_name, r in plantel.items():
                print(f"Plantel «{team_name}»: {r['jugadores_subidos']} jugadores, "
                      f"{r['jugadores_borrados']} bajas replicadas")
            if not resumen:
                print("No hay partidos con datos locales todavía.")
                return
            for match_name, r in resumen.items():
                video = "video subido" if r["video_subido"] else "sin video pendiente"
                print(f"{match_name}: {r['events_subidos']} eventos, "
                      f"{r['ratings_subidos']} calificaciones, {video}")
        else:
            r = sync_match(args.match_name)
            video = "video subido" if r["video_subido"] else "sin video pendiente"
            print(f"{args.match_name}: {r['events_subidos']} eventos, "
                  f"{r['ratings_subidos']} calificaciones, {video}")
    except SupabaseConfigError as e:
        print(f"⚠️  {e}")
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"⚠️  {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
