"""
Muestra de dónde viene un parquet del pipeline: la cadena de procedencia que
guarda cada etapa (ver src/utils/procedencia.py), desde este archivo hasta el
SHA-256 del video original.

Uso:
    python3 scripts/ver_procedencia.py data/outputs/<clip>_coords_field_patrones.parquet
    python3 scripts/ver_procedencia.py <archivo.parquet> --json     # la metadata completa
    python3 scripts/ver_procedencia.py <archivo.parquet> --verificar   # recalcula los SHA-256
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.utils.procedencia import leer_meta, sha256_archivo  # noqa: E402


def _git(meta: dict) -> str:
    g = meta.get("git") or {}
    if not g.get("commit"):
        return "sin dato"
    return g["commit"][:12] + (" (con cambios sin commitear)" if g.get("dirty") else "")


def _archivo(info: dict | None) -> str:
    if not info:
        return "sin dato"
    if isinstance(info, str):
        return f"{info} (no estaba en disco al procesar)"
    return f"{info['ruta']} · {info['bytes']:,} bytes · SHA-256 {info['sha256']}"


def _verificar(info) -> str:
    if not isinstance(info, dict):
        return ""
    ruta = ROOT / info["ruta"]
    if not ruta.is_file():
        return "  [no está en disco]"
    return "  [coincide]" if sha256_archivo(ruta) == info["sha256"] else "  [NO COINCIDE: el archivo cambió]"


def _puntos(info: dict) -> str:
    if info.get("archivo_puntos"):
        return _archivo(info["archivo_puntos"])
    origen = info.get("origen_puntos") or {}
    if isinstance(origen, str):
        return origen
    if origen.get("tipo") == "propagada_desde_otro_video":
        return (f"propagada desde {origen.get('video')} (frame {origen.get('frame')}, "
                f"{origen.get('inliers')} coincidencias de registro)")
    return origen.get("tipo") or "sin dato"


def imprimir(meta: dict, nivel: int, verificar: bool, ruta_salida: str | None = None) -> None:
    sangria = "   " * nivel
    print(f"{sangria}▸ {meta.get('script')}  ({meta.get('fecha_utc')} UTC, commit {_git(meta)})")
    parametros = meta.get("parametros") or {}
    if parametros:
        texto = ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in parametros.items()
                          if not isinstance(v, (dict, list)) or len(json.dumps(v)) < 120)
        print(f"{sangria}  parámetros: {texto}")
    for clave, titulo in (("video", "video"), ("calibracion", "calibración")):
        if clave not in meta:
            continue
        info = meta[clave]
        if clave == "calibracion":
            print(f"{sangria}  calibración: {_archivo(info['archivo'])}"
                  f"{_verificar(info['archivo']) if verificar else ''}")
            print(f"{sangria}    puntos: {_puntos(info)}"
                  f"{_verificar(info.get('archivo_puntos')) if verificar else ''}")
            print(f"{sangria}    estadio: {info.get('estadio') or 'sin dato'} · control: {info.get('control_calidad')}"
                  f" · tramos: {len(info.get('tramos') or [])} · excluidos: "
                  + (", ".join(f"{e['desde']:g}–{e['hasta']:g} s" for e in info.get("excluir") or []) or "ninguno")
                  + " · sin calibración válida: "
                  + (", ".join(f"{t['desde']:g}–{t['hasta']:g} s" for t in info.get("tramos_no_validos") or [])
                     or "ninguno"))
        else:
            print(f"{sangria}  {titulo}: {_archivo(info)}{_verificar(info) if verificar else ''}")
    if meta.get("versiones") and nivel == 0:
        print(f"{sangria}  librerías: " + ", ".join(f"{k} {v}" for k, v in meta["versiones"].items() if v))
    origen = meta.get("origen")
    if origen:
        if origen["archivo"]["ruta"] == ruta_salida:
            # Etapas que reescriben su entrada (team_assignment): el hash es el
            # de la versión anterior del mismo archivo, que ya no existe.
            nota = "  [es este mismo archivo antes de que esta etapa lo reescribiera]"
        else:
            nota = _verificar(origen["archivo"]) if verificar else ""
        print(f"{sangria}  entrada: {_archivo(origen['archivo'])}{nota}")
        if origen.get("procedencia"):
            imprimir(origen["procedencia"], nivel + 1, verificar, origen["archivo"]["ruta"])
        else:
            print(f"{sangria}     ⚠️  esa entrada no tiene procedencia (es anterior al registro): la cadena se corta acá")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cadena de procedencia de un parquet del pipeline")
    parser.add_argument("parquet", type=str)
    parser.add_argument("--json", action="store_true", help="Imprime la metadata completa en JSON")
    parser.add_argument("--verificar", action="store_true",
                        help="Recalcula el SHA-256 de los archivos que siguen en disco y avisa si cambiaron")
    args = parser.parse_args()

    ruta = Path(args.parquet)
    if not ruta.is_file():
        sys.exit(f"[ERROR] No existe: {ruta}")
    meta = leer_meta(ruta)
    if meta is None:
        print(f"⚠️  {ruta.name} no tiene procedencia: es anterior al registro (09/11/2026) "
              "o no lo escribió el pipeline. Se puede leer igual, pero no se sabe de dónde viene.")
        return
    if args.json:
        print(json.dumps(meta, indent=2, ensure_ascii=False))
        return
    print(f"Procedencia de {ruta.name} (de este archivo hacia el video original):\n")
    try:
        ruta_relativa = str(ruta.resolve().relative_to(ROOT))
    except ValueError:
        ruta_relativa = None
    imprimir(meta, 0, args.verificar, ruta_relativa)


if __name__ == "__main__":
    main()
