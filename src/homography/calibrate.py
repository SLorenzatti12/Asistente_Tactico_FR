"""
Analizador Táctico — Módulo de Homografía
==========================================
Convierte coordenadas de píxeles (frame de video) a metros reales
sobre la cancha, usando una calibración manual de 4 puntos.

Flujo:
    1. El usuario hace clic en 4 puntos conocidos de la cancha
       sobre el primer frame del video (ej: las 4 esquinas del área,
       o las 4 esquinas de la cancha si se ven completas)
    2. Se guarda la matriz de homografía en un .json (una vez por video/cámara)
    3. Cualquier coordenada en píxeles del .parquet de detecciones
       se puede transformar a metros usando esa matriz

Uso:
    # Paso 1: calibrar (una vez por video/ángulo de cámara)
    python src/homography/calibrate.py data/videos/partido.mp4

    # Con puntos custom (cuando no se ven las 4 esquinas completas)
    python src/homography/calibrate.py data/videos/partido.mp4 \
        --points mitad_linea_sup,mitad_linea_inf,area_grande_sup_der,area_grande_inf_der

    # Paso 2: aplicar la calibración a las coordenadas ya detectadas
    python src/homography/calibrate.py data/videos/partido.mp4 --apply data/outputs/partido_coords.parquet

    # Auditar una calibración ya guardada (sin recalibrar), opcionalmente en otro frame
    python src/homography/calibrate.py data/videos/partido.mp4 --verificar [--frame 3000]

Control de calidad:
    Toda calibración termina con un control por superposición: se proyectan
    las líneas de la cancha sobre el frame y se mide el error contra las
    líneas de cal reales, LEJOS de los puntos usados para calibrar (cerca de
    ellos la homografía coincide por construcción y el error no dice nada).
    Se guarda <video>_calibracion_control.png y el veredicto queda en el .json:
    "ok", "revisar" o "no_verificable". Ver control_calidad().
    Límites conocidos del control: las líneas muy tenues (noche, lejos de la
    cámara) pueden no detectarse y contar como "sin línea cerca"; y una línea
    proyectada mal puede "encontrar" otra línea real cercana y subestimar su
    error. Por eso la imagen es la referencia final, no solo el número.
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT    = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / "data" / "outputs"

# ── Dimensiones estándar de cancha (metros) ────────────────
FIELD_LENGTH = 105.0
FIELD_WIDTH  = 68.0

# Margen de tolerancia (metros) al filtrar detecciones fuera de la cancha.
# Más chico = más estricto (filtra mejor banco/DTs/árbitros cerca de la línea,
# pero puede descartar jugadores reales cerca del límite si la calibración
# tiene algo de error). Más grande = más permisivo.
OUT_OF_BOUNDS_MARGIN = 1.5

# Puntos de referencia disponibles para calibrar — el usuario elige
# cuáles 4 puede ver claramente en su video (no siempre se ve la cancha entera)
REFERENCE_POINTS = {
    "esquina_sup_izq":      (0.0, 0.0),
    "esquina_sup_der":      (FIELD_LENGTH, 0.0),
    "esquina_inf_izq":      (0.0, FIELD_WIDTH),
    "esquina_inf_der":      (FIELD_LENGTH, FIELD_WIDTH),
    "penal_izq":            (11.0, FIELD_WIDTH / 2),
    "penal_der":            (FIELD_LENGTH - 11.0, FIELD_WIDTH / 2),
    "area_chica_sup_izq":   (0.0, FIELD_WIDTH / 2 - 9.16),
    "area_chica_inf_izq":   (0.0, FIELD_WIDTH / 2 + 9.16),
    "area_grande_sup_izq":  (0.0, FIELD_WIDTH / 2 - 20.16),
    "area_grande_inf_izq":  (0.0, FIELD_WIDTH / 2 + 20.16),
    # Lado derecho (arco derecho) — para cámaras que solo ven la mitad de cancha
    "area_chica_sup_der":   (FIELD_LENGTH, FIELD_WIDTH / 2 - 9.16),
    "area_chica_inf_der":   (FIELD_LENGTH, FIELD_WIDTH / 2 + 9.16),
    "area_grande_sup_der":  (FIELD_LENGTH - 16.5, FIELD_WIDTH / 2 - 20.16),
    "area_grande_inf_der":  (FIELD_LENGTH - 16.5, FIELD_WIDTH / 2 + 20.16),
    "area_grande_borde_der": (FIELD_LENGTH - 16.5, FIELD_WIDTH / 2),
    "centro_cancha":        (FIELD_LENGTH / 2, FIELD_WIDTH / 2),
    "mitad_linea_sup":      (FIELD_LENGTH / 2, 0.0),
    "mitad_linea_inf":      (FIELD_LENGTH / 2, FIELD_WIDTH),
    # Cruces de la línea media con el círculo central (radio 9.15 m): puntos
    # nítidos y casi siempre visibles en planos de transmisión.
    "circulo_mitad_sup":    (FIELD_LENGTH / 2, FIELD_WIDTH / 2 - 9.15),
    "circulo_mitad_inf":    (FIELD_LENGTH / 2, FIELD_WIDTH / 2 + 9.15),
    # Donde el arco del área (radio 9.15 m desde el punto penal, a 11 m del
    # arco) corta la línea del frente del área (a 16.5 m): 5.5 m de distancia
    # horizontal → ± sqrt(9.15² - 5.5²) ≈ ±7.31 m del eje.
    "arco_area_sup_der":    (FIELD_LENGTH - 16.5, FIELD_WIDTH / 2 - 7.31),
    "arco_area_inf_der":    (FIELD_LENGTH - 16.5, FIELD_WIDTH / 2 + 7.31),
    "arco_area_sup_izq":    (16.5, FIELD_WIDTH / 2 - 7.31),
    "arco_area_inf_izq":    (16.5, FIELD_WIDTH / 2 + 7.31),
}
# OJO con la convención de nombres heredada: "area_grande_sup_izq/inf_izq"
# están sobre la LÍNEA DE FONDO (x=0), mientras que "area_grande_sup_der/
# inf_der" son las esquinas del FRENTE del área (x=105-16.5). No se
# renombraron para no romper calibraciones guardadas; el print de la ventana
# muestra la coordenada en metros de cada punto para no confundirse.

DEFAULT_ORDER = ["esquina_sup_izq", "esquina_sup_der", "esquina_inf_izq", "esquina_inf_der"]
RIGHT_HALF_ORDER = ["mitad_linea_sup", "mitad_linea_inf", "area_grande_sup_der", "area_grande_inf_der"]


# ── Control de calidad por superposición (vale para CUALQUIER modo) ───────
# Por qué existe: una homografía se ajusta a los puntos de calibración, así
# que el error medido EN esos puntos siempre da chico, aunque la calibración
# esté mal en el resto de la cancha (nos pasó: RANSAC daba 0.2 m de error y,
# superponiendo las líneas, la línea media quedaba corrida 2-4.5 m). Este
# control mide contra las líneas de cal reales del frame, LEJOS de los puntos
# usados en el ajuste — eso sí es evidencia independiente.

# Medidas reglamentarias de las marcas que se dibujan/verifican (metros).
_AREA_GRANDE_LARGO, _AREA_GRANDE_ANCHO = 16.5, 40.32
_AREA_CHICA_LARGO, _AREA_CHICA_ANCHO = 5.5, 18.32
_RADIO_CIRCULO = 9.15

QC_PASO_MUESTREO_M = 1.0      # cada cuántos metros se muestrea cada línea
# Las muestras más cerca que esto de un punto de ajuste no cuentan: ahí la
# proyección coincide por construcción y mediría el ajuste, no la calidad.
QC_RADIO_EXCLUSION_M = 4.0
# Radio (px) donde se busca la línea de cal real alrededor de cada muestra
# proyectada. Más allá, la muestra cuenta como "sin línea cerca".
QC_RADIO_BUSQUEDA_PX = 40
QC_ERROR_OK_M = 1.0           # error mediano máximo para un veredicto "ok"
QC_ERROR_LINEA_MAX_M = 2.0    # ninguna línea individual puede superar esto
QC_MIN_MUESTRAS_LINEA = 15    # ...si se la pudo verificar con al menos tantas muestras
QC_MIN_MUESTRAS = 30          # menos muestras verificadas que esto → "no verificable"
# Fracción máxima de muestras proyectadas DENTRO del cuadro sin ninguna línea
# real cerca. Si es alta, hay líneas proyectadas donde no hay nada pintado.
QC_MAX_SIN_LINEA = 0.5


def _lineas_cancha() -> dict:
    """Marcas de la cancha como polilíneas en metros (origen esquina sup-izq)."""
    L, W = FIELD_LENGTH, FIELD_WIDTH
    yg1, yg2 = (W - _AREA_GRANDE_ANCHO) / 2, (W + _AREA_GRANDE_ANCHO) / 2
    yc1, yc2 = (W - _AREA_CHICA_ANCHO) / 2, (W + _AREA_CHICA_ANCHO) / 2
    t = np.linspace(0, 2 * np.pi, 120)
    return {
        "banda_lejana":     [(0, 0), (L, 0)],
        "banda_cercana":    [(0, W), (L, W)],
        "fondo_izq":        [(0, 0), (0, W)],
        "fondo_der":        [(L, 0), (L, W)],
        "linea_media":      [(L / 2, 0), (L / 2, W)],
        "circulo_central":  list(zip(L / 2 + _RADIO_CIRCULO * np.cos(t), W / 2 + _RADIO_CIRCULO * np.sin(t))),
        "area_grande_izq":  [(0, yg1), (_AREA_GRANDE_LARGO, yg1), (_AREA_GRANDE_LARGO, yg2), (0, yg2)],
        "area_grande_der":  [(L, yg1), (L - _AREA_GRANDE_LARGO, yg1), (L - _AREA_GRANDE_LARGO, yg2), (L, yg2)],
        "area_chica_izq":   [(0, yc1), (_AREA_CHICA_LARGO, yc1), (_AREA_CHICA_LARGO, yc2), (0, yc2)],
        "area_chica_der":   [(L, yc1), (L - _AREA_CHICA_LARGO, yc1), (L - _AREA_CHICA_LARGO, yc2), (L, yc2)],
    }


def _muestrear(polilinea, paso: float) -> np.ndarray:
    pts = np.asarray(polilinea, dtype=np.float64)
    tramos = []
    for a, b in zip(pts[:-1], pts[1:]):
        n = max(2, int(np.ceil(np.linalg.norm(b - a) / paso)) + 1)
        tramos.append(np.linspace(a, b, n, endpoint=False))
    tramos.append(pts[-1:])
    return np.vstack(tramos)


def _mascara_lineas(frame: np.ndarray) -> np.ndarray:
    """
    Píxeles de líneas de cal: más claros que su entorno (top-hat), poco
    saturados (blanco) y sobre o pegados al pasto. Se descartan manchas
    compactas (jugadores de camiseta clara, pelota) — las líneas son largas.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    tophat = cv2.morphologyEx(v, cv2.MORPH_TOPHAT, kernel)
    # Saturación RELATIVA al pasto de alrededor, no un umbral fijo: con luz
    # artificial amarillenta la cal no es "blanca" (en Sportivo de noche las
    # líneas tienen saturación ~93), pero sigue siendo menos saturada que el
    # pasto que la rodea.
    s_entorno = cv2.blur(s, (31, 31)).astype(np.int16)
    blanco = (tophat > 25) & (s.astype(np.int16) < s_entorno - 15)
    pasto = ((h >= 30) & (h <= 95) & (s > 40) & (v > 40)).astype(np.uint8)
    # Pasto a AMBOS lados: un cierre morfológico "rellena" las líneas finas
    # pintadas sobre el pasto, pero no el borde de un cartel de publicidad
    # (que tiene pasto de un solo lado). Sin esto, el borde inferior de los
    # carteles se confundía con la banda lejana.
    sobre_pasto = cv2.morphologyEx(pasto, cv2.MORPH_CLOSE,
                                   cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))).astype(bool)
    mascara = (blanco & sobre_pasto).astype(np.uint8)
    # Las líneas lejanas y finas salen partidas en pedacitos: se unen antes de filtrar.
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats(mascara, connectivity=8)
    for i in range(1, n):
        largo = max(stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT])
        grosor = stats[i, cv2.CC_STAT_AREA] / largo        # espesor medio aproximado (px)
        # Línea = fina; jugador/pelota = mancha gruesa y corta.
        if largo < 20 or (grosor > 4.5 and largo < 200):
            mascara[etiquetas == i] = 0
    return mascara.astype(bool)


def control_calidad(frame: np.ndarray, H: np.ndarray, puntos_ajuste_m, ruta_png: Path) -> dict:
    """
    Verifica una homografía (píxel → metros) contra las líneas de cal reales.

    Proyecta las marcas de la cancha sobre `frame`, busca la línea real más
    cercana a cada muestra y mide la distancia en metros — EXCLUYENDO las
    muestras cerca de `puntos_ajuste_m` (los puntos usados para calcular H).
    Guarda en `ruta_png` el frame con la superposición: magenta = líneas
    proyectadas; muestras verde/amarillo/rojo según error; azul = proyectada
    en el cuadro sin ninguna línea real cerca; círculo blanco = punto de ajuste.

    Sirve igual para la calibración manual (puntos clickeados) y la
    automática (keypoints inliers): no depende de cómo se obtuvo H.

    Returns:
        dict con `veredicto` ("ok" | "revisar" | "no_verificable"), `motivos`,
        métricas globales y por línea. "ok" solo se da con evidencia: si hay
        pocas líneas visibles para verificar, el veredicto es "no_verificable".
    """
    alto, ancho = frame.shape[:2]
    ajuste = np.asarray(puntos_ajuste_m, dtype=np.float64).reshape(-1, 2)
    Hinv = np.linalg.inv(H)
    # Una homografía vale igual multiplicada por cualquier escalar, NEGATIVO
    # incluido. Se fija el signo para que w>0 en los puntos de ajuste (que
    # seguro están delante de la cámara); si no, "w<=0 = detrás de la cámara"
    # descartaría la cancha entera según cómo vino escalada H.
    ref = ajuste.mean(axis=0) if len(ajuste) else np.array([FIELD_LENGTH / 2, FIELD_WIDTH / 2])
    if (np.r_[ref, 1.0] @ Hinv.T)[2] < 0:
        Hinv = -Hinv
    mascara = _mascara_lineas(frame)
    from scipy.ndimage import distance_transform_edt
    dist_px, (idx_y, idx_x) = distance_transform_edt(~mascara, return_indices=True)

    vis = frame.copy()
    por_linea, errores_m, errores_px = {}, [], []
    n_en_cuadro = n_sin_linea = 0

    for nombre, polilinea in _lineas_cancha().items():
        muestras = _muestrear(polilinea, QC_PASO_MUESTREO_M)
        homog = np.c_[muestras, np.ones(len(muestras))] @ Hinv.T
        delante = homog[:, 2] > 1e-9                     # w<=0: detrás de la cámara
        px = homog[:, :2] / np.where(delante, homog[:, 2], 1)[:, None]

        visibles = [p for p, ok in zip(px, delante) if ok and np.all(np.isfinite(p))]
        if len(visibles) > 1:
            cv2.polylines(vis, [np.array(visibles, np.int32)], False, (255, 0, 255), 2)

        errs = []
        for m, p, ok in zip(muestras, px, delante):
            if not ok or not np.all(np.isfinite(p)):
                continue
            x, y = int(round(p[0])), int(round(p[1]))
            if not (0 <= x < ancho and 0 <= y < alto):
                continue
            if len(ajuste) and np.min(np.linalg.norm(ajuste - m, axis=1)) < QC_RADIO_EXCLUSION_M:
                cv2.circle(vis, (x, y), 2, (160, 160, 160), -1)
                continue
            n_en_cuadro += 1
            d = dist_px[y, x]
            if d > QC_RADIO_BUSQUEDA_PX:
                n_sin_linea += 1
                cv2.drawMarker(vis, (x, y), (255, 128, 0), cv2.MARKER_TILTED_CROSS, 8, 2)
                continue
            real_px = np.array([[[idx_x[y, x], idx_y[y, x]]]], np.float32)
            real_m = cv2.perspectiveTransform(real_px, H).reshape(2)
            e = float(np.linalg.norm(real_m - m))
            errs.append(e)
            errores_px.append(float(d))
            color = (0, 200, 0) if e < 0.5 else (0, 220, 255) if e < 1.5 else (0, 0, 255)
            cv2.circle(vis, (x, y), 3, color, -1)
        if errs:
            por_linea[nombre] = {"muestras": len(errs), "error_mediano_m": round(float(np.median(errs)), 2),
                                 "error_p90_m": round(float(np.percentile(errs, 90)), 2)}
        errores_m.extend(errs)

    for m in ajuste:
        p = cv2.perspectiveTransform(m.reshape(1, 1, 2).astype(np.float32), Hinv).reshape(2)
        if np.all(np.isfinite(p)):
            cv2.circle(vis, (int(p[0]), int(p[1])), 9, (255, 255, 255), 2)

    n_ver = len(errores_m)
    frac_sin_linea = n_sin_linea / n_en_cuadro if n_en_cuadro else 0.0
    resultado = {
        "muestras_verificadas": n_ver,
        "muestras_sin_linea_cerca": n_sin_linea,
        "fraccion_sin_linea_cerca": round(frac_sin_linea, 2),
        "error_mediano_m": round(float(np.median(errores_m)), 2) if n_ver else None,
        "error_p90_m": round(float(np.percentile(errores_m, 90)), 2) if n_ver else None,
        "error_mediano_px": round(float(np.median(errores_px)), 1) if n_ver else None,
        "por_linea": por_linea,
    }
    motivos = []
    if n_ver < QC_MIN_MUESTRAS:
        veredicto = "no_verificable"
        motivos.append(f"solo {n_ver} muestras de línea visibles lejos de los puntos de ajuste "
                       f"(mínimo {QC_MIN_MUESTRAS}) — no hay evidencia de que la calibración sea buena")
    else:
        if resultado["error_mediano_m"] > QC_ERROR_OK_M:
            motivos.append(f"error mediano {resultado['error_mediano_m']} m > {QC_ERROR_OK_M} m")
        # El promedio global puede esconder una línea muy corrida (p.ej. si
        # las bandas encajan bien y dominan la cuenta) — se mira cada una.
        for nombre, m in por_linea.items():
            if m["muestras"] >= QC_MIN_MUESTRAS_LINEA and m["error_mediano_m"] > QC_ERROR_LINEA_MAX_M:
                motivos.append(f"{nombre}: error mediano {m['error_mediano_m']} m (> {QC_ERROR_LINEA_MAX_M} m)")
        if frac_sin_linea > QC_MAX_SIN_LINEA:
            motivos.append(f"{frac_sin_linea:.0%} de las líneas proyectadas dentro del cuadro no tienen "
                           f"ninguna línea real cerca — probablemente quedaron donde no hay nada pintado")
        veredicto = "revisar" if motivos else "ok"
    resultado["veredicto"], resultado["motivos"] = veredicto, motivos

    color_v = {"ok": (0, 200, 0), "revisar": (0, 0, 255), "no_verificable": (0, 165, 255)}[veredicto]
    texto = (f"CONTROL: {veredicto.upper()}  |  error mediano "
             f"{resultado['error_mediano_m']} m  |  sin linea cerca {frac_sin_linea:.0%}  |  n={n_ver}")
    cv2.rectangle(vis, (0, 0), (ancho, 34), (0, 0, 0), -1)
    cv2.putText(vis, texto, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color_v, 2)
    ruta_png.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ruta_png), vis)
    resultado["imagen"] = str(ruta_png)
    return resultado


def imprimir_control(resultado: dict) -> None:
    """Resumen legible del control de calidad por consola."""
    icono = {"ok": "✅", "revisar": "⚠️ ", "no_verificable": "❔"}[resultado["veredicto"]]
    print(f"\n{icono} Control de calidad de la calibración: {resultado['veredicto'].upper()}")
    if resultado["muestras_verificadas"]:
        print(f"   Error contra líneas reales (lejos de los puntos de ajuste): "
              f"mediano {resultado['error_mediano_m']} m, p90 {resultado['error_p90_m']} m "
              f"({resultado['muestras_verificadas']} muestras)")
        for nombre, m in sorted(resultado["por_linea"].items(), key=lambda kv: -kv[1]["error_mediano_m"]):
            print(f"     {nombre:<16} {m['error_mediano_m']:>5} m  (n={m['muestras']})")
    print(f"   Líneas proyectadas sin ninguna línea real cerca: {resultado['fraccion_sin_linea_cerca']:.0%}")
    for motivo in resultado["motivos"]:
        print(f"   - {motivo}")
    print(f"   Superposición guardada en: {resultado['imagen']}")
    if resultado["veredicto"] != "ok":
        print("   Mirá la imagen antes de usar esta calibración.")


class CalibrationUI:
    """Ventana interactiva para marcar puntos de referencia sobre un frame."""

    def __init__(self, frame: np.ndarray, point_names: list):
        self.frame       = frame
        self.display     = frame.copy()
        self.point_names = point_names
        self.clicks      = []

    def _on_mouse(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(self.clicks) < len(self.point_names):
            self.clicks.append((x, y))
            self._redraw()

    def _redraw(self):
        self.display = self.frame.copy()
        for i, (px, py) in enumerate(self.clicks):
            cv2.circle(self.display, (px, py), 6, (0, 0, 255), -1)
            cv2.putText(self.display, str(i + 1), (px + 10, py - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        self._draw_hud()

    def _draw_hud(self):
        h, w = self.display.shape[:2]
        overlay = self.display.copy()
        cv2.rectangle(overlay, (0, 0), (w, 70), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.55, self.display, 0.45, 0, self.display)

        if len(self.clicks) < len(self.point_names):
            next_point = self.point_names[len(self.clicks)]
            msg = f"Clic en: {next_point.replace('_', ' ').upper()}  ({len(self.clicks)}/{len(self.point_names)})"
        else:
            msg = "Listo — presiona ENTER para confirmar, o R para reiniciar"

        cv2.putText(self.display, msg, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
        cv2.putText(self.display, "R: reiniciar   Q: cancelar", (15, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    def run(self):
        window = "Calibracion - Analizador Tactico"
        cv2.namedWindow(window)
        cv2.setMouseCallback(window, self._on_mouse)
        self._redraw()

        while True:
            cv2.imshow(window, self.display)
            key = cv2.waitKey(20) & 0xFF

            if key == ord("q"):
                cv2.destroyAllWindows()
                return None
            elif key == ord("r"):
                self.clicks = []
                self._redraw()
            elif key == 13 and len(self.clicks) == len(self.point_names):
                cv2.destroyAllWindows()
                return self.clicks


def calibrate(video_path: Path, point_names: list = None, frame_idx: int = 0) -> Path:
    """
    Abre el frame `frame_idx` del video (por defecto el primero) y pide clics
    en los puntos de referencia. Guarda la homografía resultante en un .json.
    Conviene elegir un frame con la cámara en su posición más habitual y
    usar puntos que se VEAN (no extrapolar marcas fuera de cuadro).
    """
    point_names = point_names or DEFAULT_ORDER

    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        sys.exit(f"[ERROR] No se pudo leer el frame {frame_idx} de: {video_path}")

    print(f"\nSe abrirá una ventana con el frame {frame_idx}. Hacé clic, en orden, en estos "
          f"{len(point_names)} puntos:")
    for i, name in enumerate(point_names, 1):
        x, y = REFERENCE_POINTS[name]
        print(f"  {i}. {name.replace('_', ' '):<22} (x={x:.2f} m, y={y:.2f} m)")
    print("\nSi alguno de estos puntos no se ve en tu video, cancelá (Q) y volvé a")
    print("llamar a calibrate() pasando otra lista de puntos que sí se vean")
    print("(ver REFERENCE_POINTS en este archivo para las opciones disponibles).\n")
    input("Presioná ENTER para abrir la ventana...")

    ui = CalibrationUI(frame, point_names)
    pixel_points = ui.run()

    if pixel_points is None:
        sys.exit("[INFO] Calibración cancelada.")

    real_points = [REFERENCE_POINTS[name] for name in point_names]

    src = np.array(pixel_points, dtype=np.float32)
    dst = np.array(real_points, dtype=np.float32)
    H, status = cv2.findHomography(src, dst, method=0)

    if H is None:
        sys.exit("[ERROR] No se pudo calcular la homografía. Revisá que los 4 puntos no sean colineales.")

    # Residuo por punto: con más de 4 puntos, un clic mal hecho se nota como
    # un residuo mucho mayor que el resto. (Esto NO mide la calidad de la
    # calibración — mide si los clics son consistentes entre sí. La calidad
    # la mide control_calidad(), lejos de estos puntos.)
    if len(point_names) > 4:
        proy = cv2.perspectiveTransform(src.reshape(-1, 1, 2), H).reshape(-1, 2)
        residuos = np.linalg.norm(proy - dst, axis=1)
        print("\nResiduo por punto clickeado (consistencia entre clics):")
        for name, r in zip(point_names, residuos):
            aviso = "  ← ¿clic corrido? revisalo" if r > 1.0 else ""
            print(f"   {name:<22} {r:5.2f} m{aviso}")

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUTS / f"{video_path.stem}_homography.json"

    # Control de calidad contra las líneas reales del mismo frame. No bloquea
    # el guardado (el usuario decide), pero el veredicto queda en el .json y
    # se imprime fuerte si no es "ok".
    control = control_calidad(frame, H, real_points, OUTPUTS / f"{video_path.stem}_calibracion_control.png")

    calibration = {
        "video": video_path.name,
        "frame": frame_idx,
        "point_names": point_names,
        "pixel_points": pixel_points,
        "real_points": real_points,
        "homography_matrix": H.tolist(),
        "control_calidad": control,
    }
    with open(out_path, "w") as f:
        json.dump(calibration, f, indent=2)

    print(f"\n✅ Calibración guardada en: {out_path.name}")
    print("   Podés reusarla para todos los videos grabados desde la misma cámara/posición.")
    imprimir_control(control)
    return out_path


def verificar_calibracion(video_path: Path, homography_path: Path, frame_idx: int = None) -> dict:
    """
    Corre el control de calidad sobre una calibración YA guardada, sin
    recalibrar. Por defecto usa el frame con el que se calibró (o el 0 si el
    .json es anterior a que se guardara ese dato). Útil para auditar
    calibraciones viejas, y con `frame_idx` para ver si siguen valiendo más
    adelante en el video (p.ej. si la cámara se movió).
    """
    with open(homography_path) as f:
        calib = json.load(f)
    idx = frame_idx if frame_idx is not None else calib.get("frame", 0)
    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        sys.exit(f"[ERROR] No se pudo leer el frame {idx} de: {video_path}")
    ruta_png = homography_path.parent / f"{homography_path.stem.replace('_homography', '')}_calibracion_control_f{idx}.png"
    control = control_calidad(frame, np.array(calib["homography_matrix"], dtype=np.float64),
                              calib["real_points"], ruta_png)
    print(f"\nCalibración: {homography_path.name}  (puntos: {', '.join(calib['point_names'])})  — frame {idx}")
    imprimir_control(control)
    return control


def apply_homography(coords_path: Path, homography_path: Path) -> Path:
    """
    Aplica una calibración guardada a un .parquet de coordenadas en píxeles,
    agregando columnas field_x, field_y en metros reales.

    Filtra detecciones que caen fuera de la cancha (con margen OUT_OF_BOUNDS_MARGIN)
    para descartar banco, cuerpo técnico, árbitros de línea fuera de juego, etc.
    """
    with open(homography_path) as f:
        calib = json.load(f)
    H = np.array(calib["homography_matrix"], dtype=np.float64)

    df = pd.read_parquet(coords_path)

    points = df[["cx", "feet_y"]].to_numpy(dtype=np.float32).reshape(-1, 1, 2)
    transformed = cv2.perspectiveTransform(points, H).reshape(-1, 2)

    df["field_x"] = transformed[:, 0].round(2)
    df["field_y"] = transformed[:, 1].round(2)

    margin = OUT_OF_BOUNDS_MARGIN
    in_bounds = (
        (df["field_x"] >= -margin) & (df["field_x"] <= FIELD_LENGTH + margin) &
        (df["field_y"] >= -margin) & (df["field_y"] <= FIELD_WIDTH + margin)
    )
    n_out = (~in_bounds).sum()
    n_total = len(df)

    # Filtramos las detecciones fuera de cancha del resultado final
    df_filtered = df[in_bounds].copy()

    if n_out > 0:
        pct = n_out / n_total * 100
        print(f"[INFO] {n_out} detecciones ({pct:.1f}%) descartadas por caer fuera de la cancha")
        print(f"       (margen: {margin}m — filtra banco/cuerpo técnico/árbitros fuera de juego).")
        if pct > 15:
            print("        Este porcentaje es alto — revisá la calibración, puede haber puntos mal marcados.")

    out_path = coords_path.parent / f"{coords_path.stem}_field.parquet"
    df_filtered.to_parquet(out_path, index=False)

    print(f"\n✅ Coordenadas de cancha exportadas: {out_path.name}")
    print(f"   Nuevas columnas: field_x, field_y (metros, origen en esquina sup-izquierda)")
    print(f"   {len(df_filtered)} de {n_total} detecciones conservadas.")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analizador Táctico — Calibración de homografía",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python src/homography/calibrate.py data/videos/partido.mp4

  python src/homography/calibrate.py data/videos/partido.mp4 --apply data/outputs/partido_coords.parquet

  python src/homography/calibrate.py data/videos/partido.mp4 \\
      --points mitad_linea_sup,mitad_linea_inf,area_grande_sup_der,area_grande_inf_der

  python src/homography/calibrate.py data/videos/partido.mp4 --verificar --frame 3000
        """,
    )
    parser.add_argument("video", type=str, help="Ruta al video .mp4 (para calibrar) o de referencia")
    parser.add_argument("--apply", type=str, default=None,
                         help="Ruta a un .parquet de coordenadas — si se pasa, aplica la calibración "
                              "existente en vez de abrir la ventana de calibración")
    parser.add_argument("--points", type=str, default=None,
                         help="Lista de puntos a usar para calibrar, separados por coma "
                              "(ver REFERENCE_POINTS en este archivo).")
    parser.add_argument("--verificar", action="store_true",
                         help="Corre el control de calidad sobre la calibración ya guardada de este "
                              "video, sin recalibrar")
    parser.add_argument("--frame", type=int, default=None,
                         help="Frame sobre el cual calibrar (default: 0) o, con --verificar, sobre el "
                              "cual verificar (default: el frame con el que se calibró)")
    args = parser.parse_args()

    video_path = Path(args.video)
    if not video_path.exists():
        sys.exit(f"[ERROR] Video no encontrado: {video_path}")

    if args.verificar:
        homography_path = OUTPUTS / f"{video_path.stem}_homography.json"
        if not homography_path.exists():
            sys.exit(f"[ERROR] No hay calibración guardada para este video: {homography_path.name}")
        verificar_calibracion(video_path, homography_path, args.frame)
    elif args.apply:
        coords_path = Path(args.apply)
        if not coords_path.exists():
            sys.exit(f"[ERROR] Archivo de coordenadas no encontrado: {coords_path}")
        homography_path = OUTPUTS / f"{video_path.stem}_homography.json"
        if not homography_path.exists():
            sys.exit(f"[ERROR] No hay calibración guardada para este video.\n"
                      f"  Corré primero: python src/homography/calibrate.py {video_path}")
        apply_homography(coords_path, homography_path)
    else:
        point_names = args.points.split(",") if args.points else None
        if point_names:
            invalid = [p for p in point_names if p not in REFERENCE_POINTS]
            if invalid:
                sys.exit(f"[ERROR] Puntos no reconocidos: {invalid}\n"
                          f"  Opciones válidas: {list(REFERENCE_POINTS.keys())}")
        calibrate(video_path, point_names=point_names, frame_idx=args.frame or 0)
