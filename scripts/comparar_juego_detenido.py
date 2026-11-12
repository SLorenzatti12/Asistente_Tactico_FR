"""
Compara el "posible juego detenido" estimado (src/analysis/estado_juego.py)
con las paradas tagueadas a mano con el botón "Juego detenido".

    python3 scripts/comparar_juego_detenido.py sportivo_crop3
    python3 scripts/comparar_juego_detenido.py sportivo_crop3 --hasta 13:30    # solo lo tagueado
    python3 scripts/comparar_juego_detenido.py sportivo_crop3 --umbral-ms 1.2 --duracion-min-seg 10

Segundo a segundo, dentro del tramo evaluado: qué parte del tiempo detenido
real marca el detector (cobertura) y qué parte de lo que marca era realmente
juego detenido (precisión). Además, lista las paradas que se le escapan y lo
que marca de más, para revisarlo en el video. Solo lee: no cambia nada.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analysis.estado_juego import PARAMETROS_POR_DEFECTO, detectar_juego_detenido, velocidad_colectiva  # noqa: E402

DB = ROOT / "data" / "db" / "analizador.sqlite"


def _segundos(texto: str) -> float:
    partes = [float(p) for p in texto.split(":")]
    return partes[0] * 60 + partes[1] if len(partes) == 2 else partes[0]


def _mmss(s: float) -> str:
    return f"{int(s // 60)}:{int(s % 60):02d}"


def _mascara(intervalos, segundos: np.ndarray) -> np.ndarray:
    m = np.zeros(len(segundos), dtype=bool)
    for a, b in intervalos:
        m |= (segundos >= a) & (segundos < b)
    return m


def main() -> None:
    parser = argparse.ArgumentParser(description="Paradas tagueadas contra el juego detenido estimado")
    parser.add_argument("clip", help="Nombre del video (p. ej. sportivo_crop3)")
    parser.add_argument("--desde", default=None, help="Comienzo del tramo evaluado (mm:ss). Default: el del video")
    parser.add_argument("--hasta", default=None, help="Fin del tramo evaluado (mm:ss). Default: el del video")
    for clave, valor in PARAMETROS_POR_DEFECTO.items():
        if clave != "fraccion_min_momento":
            parser.add_argument(f"--{clave.replace('_', '-')}", type=type(valor), default=valor)
    args = parser.parse_args()

    conn = sqlite3.connect(DB)
    try:
        tagueadas = conn.execute("SELECT inicio_sec, fin_sec FROM paradas WHERE match_name = ? AND fin_sec IS NOT NULL "
                                 "ORDER BY inicio_sec", (args.clip,)).fetchall()
        abiertas = conn.execute("SELECT COUNT(*) FROM paradas WHERE match_name = ? AND fin_sec IS NULL",
                                (args.clip,)).fetchone()[0]
    except sqlite3.OperationalError:
        sys.exit("[ERROR] Todavía no hay tabla de paradas: abrí el dashboard una vez y tagueá con «Juego detenido».")
    finally:
        conn.close()
    if not tagueadas:
        sys.exit(f"[ERROR] {args.clip} no tiene paradas tagueadas (cerradas).")

    df = pd.read_parquet(ROOT / "data" / "outputs" / f"{args.clip}_coords_field.parquet")
    parametros = {k: getattr(args, k) for k in PARAMETROS_POR_DEFECTO if k != "fraccion_min_momento"}
    curva = velocidad_colectiva(df, parametros)
    estimadas = detectar_juego_detenido(df, parametros, curva)
    estimadas = list(zip(estimadas["inicio"], estimadas["fin"]))

    desde = _segundos(args.desde) if args.desde else float(curva["time_sec"].min())
    hasta = _segundos(args.hasta) if args.hasta else float(curva["time_sec"].max())
    # Solo los segundos con curva (fuera quedan los tramos sin calibración válida).
    con_dato = np.unique(np.floor(curva["time_sec"].to_numpy()))
    seg = con_dato[(con_dato >= desde) & (con_dato < hasta)] + 0.5
    real, marcado = _mascara(tagueadas, seg), _mascara(estimadas, seg)

    print(f"\n{args.clip}: {_mmss(desde)}–{_mmss(hasta)} · umbral {parametros['umbral_ms']} m/s durante "
          f"≥{parametros['duracion_min_seg']:g} s")
    if abiertas:
        print(f"⚠️  {abiertas} parada(s) sin cerrar: no cuentan.")
    print(f"Tagueado: {len(tagueadas)} paradas, {real.sum()} s ({100 * real.mean():.0f}% del tramo)")
    print(f"Estimado: {len(estimadas)} intervalos, {marcado.sum()} s ({100 * marcado.mean():.0f}% del tramo)")
    if real.any():
        print(f"Cobertura (del tiempo detenido real, cuánto marca): {100 * (real & marcado).sum() / real.sum():.0f}%")
    if marcado.any():
        print(f"Precisión (de lo que marca, cuánto era juego detenido): {100 * (real & marcado).sum() / marcado.sum():.0f}%")

    print("\nParadas tagueadas y cuánto de cada una marca el detector:")
    for a, b in tagueadas:
        if b <= desde or a >= hasta:
            continue
        m = (seg >= a) & (seg < b)
        cubierto = marcado[m].mean() if m.any() else 0
        nota = "corta: el detector pide ≥" + f"{parametros['duracion_min_seg']:g} s" if b - a < parametros["duracion_min_seg"] else ""
        print(f"  {_mmss(a)}–{_mmss(b)} ({b - a:.0f} s): {100 * cubierto:.0f}% {nota}")
    print("\nIntervalos estimados que no coinciden con ninguna parada tagueada (menos de la mitad):")
    for a, b in estimadas:
        if b <= desde or a >= hasta:
            continue
        m = (seg >= a) & (seg < b)
        if m.any() and real[m].mean() < 0.5:
            print(f"  {_mmss(a)}–{_mmss(b)} ({b - a:.0f} s): {100 * real[m].mean():.0f}% tagueado como detenido")


if __name__ == "__main__":
    main()
