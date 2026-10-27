"""
Verificar la seguridad de la nube (Supabase) después de correr db/rls_cloud.sql
================================================================================
Comprueba, contra el proyecto real:

  1. Con la clave PÚBLICA (SUPABASE_KEY): no se puede leer ninguna tabla, ni
     insertar, ni listar o subir videos al bucket `match-videos`.
  2. Con la clave SECRETA (SUPABASE_SECRET_KEY): se leen todas las tablas
     (lo que usa el sync).

Si con la clave pública algo SÍ se pudo escribir (RLS sin aplicar), lo borra
enseguida con la clave secreta y lo informa como FALLA.

    python3 scripts/verificar_rls.py

Sale con código 1 si hay alguna FALLA. Necesita internet y las dos claves en
el .env (ver .env.example).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db.supabase_client import SupabaseConfigError, get_client, get_client_publico  # noqa: E402

TABLAS = ["clubs", "users", "teams", "players", "matches", "match_videos",
          "calibrations", "tracking_outputs", "events", "player_ratings", "match_metrics"]
BUCKET = "match-videos"
MARCA = "__prueba_rls__"


def verificar(publico, secreto) -> list[tuple[str, bool, str]]:
    """Lista de (control, ok, detalle)."""
    res = []

    for tabla in TABLAS:
        try:
            filas = publico.table(tabla).select("*").limit(1).execute().data
            res.append((f"pública no lee {tabla}", not filas,
                        "devolvió filas: RLS no aplicada" if filas else "0 filas"))
        except Exception as e:  # noqa: BLE001 — permiso denegado es el resultado esperado
            res.append((f"pública no lee {tabla}", True, f"rechazado ({_corto(e)})"))

    try:
        creado = publico.table("clubs").insert({"name": MARCA}).execute().data
        if creado:
            secreto.table("clubs").delete().eq("name", MARCA).execute()
        res.append(("pública no inserta en clubs", not creado,
                    "INSERTÓ (borrado con la clave secreta): RLS no aplicada" if creado else "sin filas"))
    except Exception as e:  # noqa: BLE001
        res.append(("pública no inserta en clubs", True, f"rechazado ({_corto(e)})"))

    try:
        objetos = publico.storage.from_(BUCKET).list()
        res.append(("pública no lista videos", not objetos,
                    f"listó {len(objetos)} objetos" if objetos else "0 objetos"))
    except Exception as e:  # noqa: BLE001
        res.append(("pública no lista videos", True, f"rechazado ({_corto(e)})"))

    ruta = f"{MARCA}/prueba.txt"
    try:
        publico.storage.from_(BUCKET).upload(ruta, b"prueba", {"content-type": "text/plain"})
        secreto.storage.from_(BUCKET).remove([ruta])
        res.append(("pública no sube videos", False, "SUBIÓ un archivo (borrado con la clave secreta)"))
    except Exception as e:  # noqa: BLE001
        res.append(("pública no sube videos", True, f"rechazado ({_corto(e)})"))

    for tabla in TABLAS:
        try:
            secreto.table(tabla).select("*").limit(1).execute()
            res.append((f"secreta lee {tabla}", True, "ok"))
        except Exception as e:  # noqa: BLE001
            res.append((f"secreta lee {tabla}", False, _corto(e)))
    return res


def _corto(e: Exception) -> str:
    return str(e).replace("\n", " ")[:90]


def main() -> None:
    try:
        publico, secreto = get_client_publico(), get_client()
    except SupabaseConfigError as e:
        sys.exit(f"[ERROR] {e}")
    resultados = verificar(publico, secreto)
    for control, ok, detalle in resultados:
        print(f"{'OK   ' if ok else 'FALLA'} {control:<34} {detalle}")
    fallas = [r for r in resultados if not r[1]]
    print(f"\n{len(resultados) - len(fallas)} de {len(resultados)} controles OK.")
    if fallas:
        sys.exit(1)


if __name__ == "__main__":
    main()
