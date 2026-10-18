"""
Lado de la cancha de cada equipo: cambio de lado dentro de un video, e
inversión entre el primer y el segundo tiempo
========================================================================
La dirección de ataque nunca se asume igual para los dos tiempos: cada
tiempo es un video propio y su dirección se calcula sobre ese video
(tactical_patterns._direccion_ataque). Este módulo agrega dos controles.

Señal: en cada ventana de tiempo, la mediana de field_x de los jugadores de
campo de cada equipo (por color de camiseta, que es confiable). Cada equipo
se para, en conjunto, más cerca de su propio arco, así que el signo de
(home − away) dice de qué lado está cada uno. Medido:
  - dentro de un mismo tiempo el signo no cambia: 100% de las ventanas de 2
    min en sportivo_crop3 (27 min) y de 5 s en partido_clip2, siempre a 4 m
    o más del cero;
  - en un video simulado con los dos tiempos (sportivo_crop3 + una copia
    espejada) el signo se invierte justo en el cambio de lado.

1. detectar_cambio_de_lado(df): ¿este video tiene los dos tiempos juntos?
   Si sí, tactical_patterns frena (no calcula una sola dirección para los
   dos) y team_assignment no asigna arqueros por geometría. Hay que cortar
   el video con scripts/cortar_video.py.
2. verificar_inversion(df_t1, df_t2): entre tiempos, cada equipo tiene que
   haber cambiado de lado. Si no, o las etiquetas home/away se cruzaron
   entre tiempos o algo salió mal: no se calculan patrones del segundo.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

VENTANA_LADO_SEG = 120         # ventana para medir el lado (se achica en clips cortos)
MIN_VENTANAS_LADO = 10         # ...para tener al menos tantas ventanas
MIN_DIF_LADO_M = 2.0           # |home − away| menor a esto: ventana ambigua, no cuenta
# Un cambio de lado tiene que sostenerse: al menos tantas ventanas seguidas del
# signo contrario (con ventanas de 2 min, 4 min) — una ventana suelta no alcanza.
MIN_VENTANAS_SOSTENIDO = 2


def lado_por_ventana(df: pd.DataFrame) -> pd.DataFrame:
    """Por ventana: inicio (s), diferencia home − away de la mediana de field_x
    (m) y su signo (+1 / −1, o 0 si es ambigua o falta un equipo)."""
    columnas = ["desde", "dif_m", "signo"]
    if df.empty or "team" not in df.columns or "field_x" not in df.columns:
        return pd.DataFrame(columns=columnas)
    jug = df[(df["class_name"] == "player") & df["team"].isin(["home", "away"])]
    if jug.empty:
        return pd.DataFrame(columns=columnas)
    duracion = float(jug["time_sec"].max() - jug["time_sec"].min())
    ventana = min(VENTANA_LADO_SEG, max(duracion / MIN_VENTANAS_LADO, 1.0))
    v = ((jug["time_sec"] - jug["time_sec"].min()) // ventana).astype(int)
    piv = jug.groupby([v, "team"])["field_x"].median().unstack()
    if not {"home", "away"} <= set(piv.columns):
        return pd.DataFrame(columns=columnas)
    dif = (piv["home"] - piv["away"]).dropna()
    signo = np.where(dif.abs() >= MIN_DIF_LADO_M, np.sign(dif), 0).astype(int)
    return pd.DataFrame({"desde": jug["time_sec"].min() + dif.index * ventana,
                         "dif_m": dif.round(1).to_numpy(), "signo": signo})


def lado_del_video(df: pd.DataFrame) -> int:
    """Signo dominante de home − away en todo el video (+1, −1, o 0 si no se sabe)."""
    s = lado_por_ventana(df)["signo"]
    s = s[s != 0]
    if s.empty:
        return 0
    return int(np.sign(s.sum())) if s.sum() != 0 else 0


def detectar_cambio_de_lado(df: pd.DataFrame) -> dict | None:
    """
    None si los equipos se mantienen del mismo lado todo el video. Si hay un
    cambio sostenido (MIN_VENTANAS_SOSTENIDO ventanas seguidas de cada signo,
    a los dos lados del cambio), devuelve {"t": segundo aproximado del
    cambio, "antes": signo, "despues": signo, "ventanas": tabla}.
    """
    tabla = lado_por_ventana(df)
    s = tabla[tabla["signo"] != 0].reset_index(drop=True)
    if len(s) < 2 * MIN_VENTANAS_SOSTENIDO:
        return None
    # Rachas de signo constante
    rachas = (s["signo"] != s["signo"].shift()).cumsum()
    largas = [g for _, g in s.groupby(rachas) if len(g) >= MIN_VENTANAS_SOSTENIDO]
    for a, b in zip(largas[:-1], largas[1:]):
        if a["signo"].iat[0] != b["signo"].iat[0]:
            return {"t": float(b["desde"].iat[0]), "antes": int(a["signo"].iat[0]),
                    "despues": int(b["signo"].iat[0]), "ventanas": tabla}
    return None


def mensaje_cambio_de_lado(cambio: dict) -> str:
    t = cambio["t"]
    return (f"Los equipos cambian de lado cerca del {int(t // 60)}:{int(t % 60):02d}: este video parece "
            f"tener los dos tiempos. La dirección de ataque no se puede asumir igual para los dos — cortalo "
            f"con scripts/cortar_video.py y procesá cada tiempo por separado.")


def verificar_inversion(df_t1: pd.DataFrame, df_t2: pd.DataFrame) -> dict:
    """
    ¿Los equipos cambiaron de lado entre el primer y el segundo tiempo?
    {"ok": bool, "lado_t1", "lado_t2", "motivo"}. ok=False si el lado no se
    invierte o no se puede saber en alguno de los dos.
    """
    l1, l2 = lado_del_video(df_t1), lado_del_video(df_t2)
    if l1 == 0 or l2 == 0:
        return {"ok": False, "lado_t1": l1, "lado_t2": l2,
                "motivo": "no se pudo determinar de qué lado jugó cada equipo en alguno de los dos tiempos"}
    if l1 == l2:
        return {"ok": False, "lado_t1": l1, "lado_t2": l2,
                "motivo": ("los equipos aparecen del MISMO lado en los dos tiempos: o las etiquetas "
                           "local/visitante se cruzaron entre tiempos, o hay un error en la asignación de "
                           "equipos o en la calibración. Revisalo antes de analizar el segundo tiempo")}
    return {"ok": True, "lado_t1": l1, "lado_t2": l2, "motivo": "los equipos cambiaron de lado, como corresponde"}


def control_entre_tiempos(match_name: str, df: pd.DataFrame, outputs_dir: Path | None = None) -> dict | None:
    """
    Si `match_name` es un tiempo de un partido registrado (src/db/partido_repo.py)
    y el otro tiempo ya está procesado, verifica que los equipos hayan cambiado
    de lado entre los dos. None si no aplica (video suelto, o falta el otro).
    Devuelve el resultado de verificar_inversion() más "tiempo_actual" y
    "otro_video".
    """
    import sys
    raiz = Path(__file__).resolve().parents[2]
    if str(raiz) not in sys.path:
        sys.path.insert(0, str(raiz))
    from src.db import partido_repo

    partido_repo.init_partidos_table()
    propio, otro = partido_repo.get_tiempo(match_name), partido_repo.otro_tiempo(match_name)
    if propio is None or otro is None:
        return None
    ruta_otro = (outputs_dir or raiz / "data" / "outputs") / f"{otro['match_name']}_coords_field.parquet"
    if not ruta_otro.exists():
        return None
    df_otro = pd.read_parquet(ruta_otro)
    if "team" not in df_otro.columns:
        return None
    df_t1, df_t2 = (df, df_otro) if propio["tiempo"] == 1 else (df_otro, df)
    resultado = verificar_inversion(df_t1, df_t2)
    resultado.update({"tiempo_actual": propio["tiempo"], "otro_video": otro["match_name"],
                      "partido": propio["partido"]})
    return resultado
