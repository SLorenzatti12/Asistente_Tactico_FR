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
    # Paso 1: calibrar (una vez por video/ángulo de cámara). Con --estadio se
    # usan las medidas reales de esa cancha (ver scripts/estadios.py); sin él,
    # las del estadio ya asignado al partido o, si no hay, 105×68.
    python src/homography/calibrate.py data/videos/partido.mp4 --estadio "Sportivo Belgrano"

    # Con puntos custom (cuando no se ven las 4 esquinas completas)
    python src/homography/calibrate.py data/videos/partido.mp4 \
        --points mitad_linea_sup,mitad_linea_inf,area_grande_sup_der,area_grande_inf_der

    # Paso 2: aplicar la calibración a las coordenadas ya detectadas
    python src/homography/calibrate.py data/videos/partido.mp4 --apply data/outputs/partido_coords.parquet

    # Calibrar con puntos medidos fuera de la ventana (archivo .json, ver calibrar_desde_archivo)
    python src/homography/calibrate.py data/videos/partido.mp4 --puntos-archivo data/calibracion/partido_puntos.json

    # Auditar una calibración ya guardada (sin recalibrar), opcionalmente en otro frame
    python src/homography/calibrate.py data/videos/partido.mp4 --verificar [--frame 3000]

Control de calidad:
    Toda calibración termina con un control por superposición: se proyectan
    las líneas de la cancha sobre el frame y se mide el error contra las
    líneas de cal reales, LEJOS de los puntos usados para calibrar (cerca de
    ellos la homografía coincide por construcción y el error no dice nada).
    Se guarda <video>_calibracion_control.png y el veredicto queda en el .json:
    "ok", "revisar" o "no_verificable". Ver control_calidad().
    Las marcas que no se ven en el cuadro (banda tapada por carteles, líneas
    muy tenues) quedan como "no verificadas" — en gris en la imagen — y no
    cuentan ni a favor ni en contra. Una marca que se ve pero está corrida más
    de 4 m sí cuenta como falla (se la busca, paralela, en una banda ancha).
    Límites: lo que no se ve no se puede verificar, y una línea proyectada mal
    puede "encontrar" otra línea real cercana y subestimar su error. Por eso
    la imagen es la referencia final, no solo el número.
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.homography.medidas_cancha import (  # noqa: E402
    ANCHO_ARCO, CLAVE_ATTRS, MEDIDAS_REGLAMENTARIAS, completar_medidas, descripcion, offset_medialuna,
)

# ── Dimensiones de cancha (metros) ─────────────────────────
# Las reales vienen del estadio (ver medidas_cancha.py); estas son las
# reglamentarias, que se usan cuando no hay estadio asignado.
FIELD_LENGTH = MEDIDAS_REGLAMENTARIAS["largo"]
FIELD_WIDTH  = MEDIDAS_REGLAMENTARIAS["ancho"]

# Margen de tolerancia (metros) al filtrar detecciones fuera de la cancha.
# Más chico = más estricto (filtra mejor banco/DTs/árbitros cerca de la línea,
# pero puede descartar jugadores reales cerca del límite si la calibración
# tiene algo de error). Más grande = más permisivo.
OUT_OF_BOUNDS_MARGIN = 1.5

# Puntos de referencia disponibles para calibrar — el usuario elige
# cuáles puede ver claramente en su video (no siempre se ve la cancha entera).
# Dependen de las medidas de la cancha: ver puntos_referencia().
def puntos_referencia(medidas: dict | None = None) -> dict:
    """Coordenadas en metros de cada punto de referencia, para las medidas
    de cancha dadas (None → reglamentarias, 105×68)."""
    m = completar_medidas(medidas)
    L, W = m["largo"], m["ancho"]
    ag_l, ag_a = m["area_grande_largo"], m["area_grande_ancho"]
    ac_l, ac_a, r = m["area_chica_largo"], m["area_chica_ancho"], m["radio_circulo"]
    medialuna = offset_medialuna(m)
    return {
        "esquina_sup_izq":      (0.0, 0.0),
        "esquina_sup_der":      (L, 0.0),
        "esquina_inf_izq":      (0.0, W),
        "esquina_inf_der":      (L, W),
        "penal_izq":            (m["distancia_penal"], W / 2),
        "penal_der":            (L - m["distancia_penal"], W / 2),
        "area_chica_sup_izq":   (0.0, W / 2 - ac_a / 2),
        "area_chica_inf_izq":   (0.0, W / 2 + ac_a / 2),
        "area_grande_sup_izq":  (0.0, W / 2 - ag_a / 2),
        "area_grande_inf_izq":  (0.0, W / 2 + ag_a / 2),
        # Lado derecho (arco derecho) — para cámaras que solo ven la mitad de cancha
        "area_chica_sup_der":   (L, W / 2 - ac_a / 2),
        "area_chica_inf_der":   (L, W / 2 + ac_a / 2),
        "area_grande_sup_der":  (L - ag_l, W / 2 - ag_a / 2),
        "area_grande_inf_der":  (L - ag_l, W / 2 + ag_a / 2),
        "area_grande_borde_der": (L - ag_l, W / 2),
        "centro_cancha":        (L / 2, W / 2),
        "mitad_linea_sup":      (L / 2, 0.0),
        "mitad_linea_inf":      (L / 2, W),
        # Cruces de la línea media con el círculo central: puntos nítidos y
        # casi siempre visibles en planos de transmisión.
        "circulo_mitad_sup":    (L / 2, W / 2 - r),
        "circulo_mitad_inf":    (L / 2, W / 2 + r),
        # Donde la medialuna del área (radio r desde el punto penal) corta la
        # línea del frente del área: ±7.31 m del eje con medidas reglamentarias.
        "arco_area_sup_der":    (L - ag_l, W / 2 - medialuna),
        "arco_area_inf_der":    (L - ag_l, W / 2 + medialuna),
        "arco_area_sup_izq":    (ag_l, W / 2 - medialuna),
        "arco_area_inf_izq":    (ag_l, W / 2 + medialuna),
        # Base de cada poste (donde toca el pasto, sobre la línea de fondo):
        # bien definida aunque las líneas estén gastadas. "sup" = poste del
        # lado de la banda lejana (y chica), "inf" = del lado de la cercana.
        "poste_sup_izq":        (0.0, W / 2 - ANCHO_ARCO / 2),
        "poste_inf_izq":        (0.0, W / 2 + ANCHO_ARCO / 2),
        "poste_sup_der":        (L, W / 2 - ANCHO_ARCO / 2),
        "poste_inf_der":        (L, W / 2 + ANCHO_ARCO / 2),
        # Esquinas del FRENTE del área chica (las "area_chica_*" de arriba
        # están sobre la línea de fondo).
        "area_chica_frente_sup_izq": (ac_l, W / 2 - ac_a / 2),
        "area_chica_frente_inf_izq": (ac_l, W / 2 + ac_a / 2),
        "area_chica_frente_sup_der": (L - ac_l, W / 2 - ac_a / 2),
        "area_chica_frente_inf_der": (L - ac_l, W / 2 + ac_a / 2),
    }


# Con las medidas reglamentarias: para validar nombres y compatibilidad.
REFERENCE_POINTS = puntos_referencia()
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

QC_PASO_MUESTREO_M = 1.0      # cada cuántos metros se muestrea cada línea
# Las muestras más cerca que esto de un punto de ajuste no cuentan: ahí la
# proyección coincide por construcción y mediría el ajuste, no la calidad.
QC_RADIO_EXCLUSION_M = 4.0
# Distancia (en la CANCHA, no en píxeles) a la que se busca la línea real a
# cada lado de la marca proyectada. Antes era un radio fijo de 40 px: en la
# zona lejana de una cámara baja eso son ~13 m y enganchaba bordes de carteles.
QC_RADIO_BUSQUEDA_M = 4.0
QC_BUSQUEDA_MAX_PX = 60       # ...pero nunca más de esto por lado (en la zona cercana 4 m son muchos px)
QC_TOPHAT_MIN = 8             # altura mínima de una cresta de línea (top-hat del brillo, 0-255)
QC_PROMINENCIA = 5            # cuánto tiene que bajar el top-hat a cada lado de la cresta
QC_SATURACION_RELATIVA = 8    # la línea tiene que ser al menos esto menos saturada que el pasto de alrededor
# Una marca es "visible" (y entra en el veredicto) si se encuentra la línea
# real en al menos esta fracción de sus muestras dentro del cuadro, y en al
# menos QC_MIN_MUESTRAS_VISIBLE. Si no, se informa como "no verificada".
QC_MIN_SOPORTE = 0.3
QC_MIN_MUESTRAS_VISIBLE = 8
QC_MIN_LINEAS_VERIFICADAS = 3 # menos líneas verificadas que esto → "no verificable"
# "No se ve" vs "está corrida": si cerca de la proyección no hay línea, se
# busca en una banda ANCHA una línea PARALELA a la proyectada (orientación
# local de la imagen). Si aparece, la marca sí se ve pero la calibración la
# proyecta corrida → falla. Sin esto, una calibración corrida más de
# QC_RADIO_BUSQUEDA_M quedaba como "no verificada" y el control daba OK
# (pasaba con la calibración vieja de sportivo_crop3, banda cercana 6 m corrida).
QC_RADIO_AMPLIO_M = 15.0
QC_BUSQUEDA_AMPLIA_MAX_PX = 150
# En la banda ancha solo cuentan líneas casi paralelas a la proyectada (así no
# se engancha una línea que cruza). Tolerancia amplia a propósito: una
# calibración mala también ROTA las líneas — con los clics de sportivo_crop3
# la línea media proyectada quedaba girada ~20° respecto de la real.
QC_TOLERANCIA_ANGULO = 35.0
# Las muestras "lejos" de una marca son una línea real (y no enganches al
# azar) si su distancia a la marca cambia suave de una muestra a la vecina.
QC_SUAVIDAD_LEJOS_M = 0.75
QC_MIN_FRACCION_LEJOS = 0.15
QC_ERROR_OK_M = 1.0           # error mediano máximo para un veredicto "ok"
QC_ERROR_LINEA_MAX_M = 2.0    # ninguna línea individual puede superar esto
QC_MIN_MUESTRAS_LINEA = 15    # ...si se la pudo verificar con al menos tantas muestras
QC_MIN_MUESTRAS = 30          # menos muestras verificadas que esto → "no verificable"
# Fracción máxima de muestras de las líneas VERIFICADAS sin la línea real
# encontrada (las no verificadas no cuentan acá: ver control_calidad).
QC_MAX_SIN_LINEA = 0.5


def _lineas_cancha(medidas: dict | None = None) -> dict:
    """Marcas de la cancha como polilíneas en metros (origen esquina sup-izq)."""
    m = completar_medidas(medidas)
    L, W = m["largo"], m["ancho"]
    ag_l, ac_l, r = m["area_grande_largo"], m["area_chica_largo"], m["radio_circulo"]
    yg1, yg2 = (W - m["area_grande_ancho"]) / 2, (W + m["area_grande_ancho"]) / 2
    yc1, yc2 = (W - m["area_chica_ancho"]) / 2, (W + m["area_chica_ancho"]) / 2
    t = np.linspace(0, 2 * np.pi, 120)
    return {
        "banda_lejana":     [(0, 0), (L, 0)],
        "banda_cercana":    [(0, W), (L, W)],
        "fondo_izq":        [(0, 0), (0, W)],
        "fondo_der":        [(L, 0), (L, W)],
        "linea_media":      [(L / 2, 0), (L / 2, W)],
        "circulo_central":  list(zip(L / 2 + r * np.cos(t), W / 2 + r * np.sin(t))),
        "area_grande_izq":  [(0, yg1), (ag_l, yg1), (ag_l, yg2), (0, yg2)],
        "area_grande_der":  [(L, yg1), (L - ag_l, yg1), (L - ag_l, yg2), (L, yg2)],
        "area_chica_izq":   [(0, yc1), (ac_l, yc1), (ac_l, yc2), (0, yc2)],
        "area_chica_der":   [(L, yc1), (L - ac_l, yc1), (L - ac_l, yc2), (L, yc2)],
    }


def _muestrear(polilinea, paso: float) -> np.ndarray:
    pts = np.asarray(polilinea, dtype=np.float64)
    tramos = []
    for a, b in zip(pts[:-1], pts[1:]):
        n = max(2, int(np.ceil(np.linalg.norm(b - a) / paso)) + 1)
        tramos.append(np.linspace(a, b, n, endpoint=False))
    tramos.append(pts[-1:])
    return np.vstack(tramos)


def _mapas_lineas(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Tres mapas para buscar líneas de cal:
      - `tophat`: cuánto más claro es cada píxel que su entorno (top-hat del
        brillo). Una línea es una cresta en este mapa.
      - `candidato`: dónde PUEDE haber una línea: menos saturado que el pasto
        de alrededor y con pasto a ambos lados.
      - `direccion`: ángulo (rad) de la dirección local de la línea, del
        tensor de estructura del top-hat — para exigir que la línea
        encontrada sea paralela a la marca proyectada.
    Saturación RELATIVA al pasto, no un umbral fijo: con luz amarillenta la
    cal no es "blanca" (en Sportivo de noche tiene saturación ~93), pero sigue
    siendo menos saturada que el pasto. Pasto a AMBOS lados (cierre
    morfológico): rellena las líneas finas pintadas sobre el pasto, pero no el
    borde de un cartel, que tiene pasto de un solo lado — sin esto, la base de
    los carteles se confundía con la banda lejana.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    tophat = cv2.morphologyEx(v, cv2.MORPH_TOPHAT,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))).astype(np.float32)
    s_entorno = cv2.blur(s, (31, 31)).astype(np.int16)
    menos_saturado = s.astype(np.int16) < s_entorno - QC_SATURACION_RELATIVA
    pasto = ((h >= 30) & (h <= 95) & (s > 40) & (v > 40)).astype(np.uint8)
    sobre_pasto = cv2.morphologyEx(pasto, cv2.MORPH_CLOSE,
                                   cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))).astype(bool)
    gx = cv2.Sobel(tophat, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(tophat, cv2.CV_32F, 0, 1, ksize=3)
    jxx = cv2.GaussianBlur(gx * gx, (0, 0), 2.0)
    jyy = cv2.GaussianBlur(gy * gy, (0, 0), 2.0)
    jxy = cv2.GaussianBlur(gx * gy, (0, 0), 2.0)
    normal = 0.5 * np.arctan2(2 * jxy, jxx - jyy)          # dirección de máximo cambio = normal a la línea
    return tophat, menos_saturado & sobre_pasto, normal + np.pi / 2


def _buscar_cresta(tophat: np.ndarray, candidato: np.ndarray, p: np.ndarray, p_menos: np.ndarray,
                   p_mas: np.ndarray, direccion: np.ndarray | None = None,
                   dir_esperada: np.ndarray | None = None) -> np.ndarray | None:
    """
    Busca una línea de cal a lo largo del segmento p_menos → p_mas (la
    perpendicular a la línea proyectada en p, ± QC_RADIO_BUSQUEDA_M en la
    cancha). Devuelve el píxel (sub-píxel) de la cresta más cercana a p, o
    None si no hay ninguna: una cresta es un máximo local del top-hat, sobre
    un píxel candidato, con altura y prominencia mínimas. Con `direccion`
    (mapa de _mapas_lineas) y `dir_esperada` (vector unitario en píxeles), la
    línea en la cresta además tiene que ser paralela a la esperada.
    """
    largo = float(np.linalg.norm(p_mas - p_menos))
    if largo < 1:
        return None
    n = int(np.ceil(largo / 0.5)) + 1                       # una muestra cada medio píxel
    ts = np.linspace(0.0, 1.0, n)
    pts = p_menos[None, :] + ts[:, None] * (p_mas - p_menos)[None, :]
    alto, ancho = tophat.shape
    dentro = (pts[:, 0] >= 0) & (pts[:, 0] <= ancho - 1) & (pts[:, 1] >= 0) & (pts[:, 1] <= alto - 1)
    if dentro.sum() < 5:
        return None
    mapa_x = pts[:, 0].astype(np.float32).reshape(1, -1)
    mapa_y = pts[:, 1].astype(np.float32).reshape(1, -1)
    perfil = cv2.remap(tophat, mapa_x, mapa_y, cv2.INTER_LINEAR, borderValue=0).ravel()
    xi = np.clip(np.round(pts[:, 0]).astype(int), 0, ancho - 1)
    yi = np.clip(np.round(pts[:, 1]).astype(int), 0, alto - 1)
    valido = dentro & candidato[yi, xi] & (perfil >= QC_TOPHAT_MIN)
    k = 6                                                   # ±3 px para medir la prominencia
    picos = []
    for i in range(1, n - 1):
        if not valido[i] or perfil[i] < perfil[i - 1] or perfil[i] < perfil[i + 1]:
            continue
        izq, der = perfil[max(i - k, 0):i], perfil[i + 1:i + 1 + k]
        if len(izq) == 0 or len(der) == 0:
            continue
        # Cresta, no escalón: tiene que bajar a AMBOS lados.
        if perfil[i] - izq.min() < QC_PROMINENCIA or perfil[i] - der.min() < QC_PROMINENCIA:
            continue
        if direccion is not None and dir_esperada is not None:
            ang = direccion[yi[i], xi[i]]
            coseno = abs(np.cos(ang) * dir_esperada[0] + np.sin(ang) * dir_esperada[1])
            if coseno < np.cos(np.deg2rad(QC_TOLERANCIA_ANGULO)):
                continue
        picos.append(i)
    if not picos:
        return None
    t_p = float(np.dot(p - p_menos, p_mas - p_menos) / largo ** 2)
    i = min(picos, key=lambda j: abs(ts[j] - t_p))
    a, b, c = perfil[i - 1], perfil[i], perfil[i + 1]
    den = a - 2 * b + c
    desplazamiento = 0.5 * (a - c) / den if den != 0 else 0.0   # vértice de la parábola, sub-píxel
    return pts[i] + desplazamiento * (pts[1] - pts[0])


def _distancia_a_polilinea(punto: np.ndarray, polilinea: np.ndarray) -> float:
    a, b = polilinea[:-1], polilinea[1:]
    ab = b - a
    t = np.clip(np.einsum("ij,ij->i", punto - a, ab) / np.maximum(np.einsum("ij,ij->i", ab, ab), 1e-12), 0, 1)
    return float(np.min(np.linalg.norm(a + t[:, None] * ab - punto, axis=1)))


def control_calidad(frame: np.ndarray, H: np.ndarray, puntos_ajuste_m, ruta_png: Path,
                    medidas: dict | None = None) -> dict:
    """
    Verifica una homografía (píxel → metros) contra las líneas de cal reales.

    Para cada muestra de cada marca proyectada (cada QC_PASO_MUESTREO_M),
    busca una línea real sobre la perpendicular, a ± QC_RADIO_BUSQUEDA_M en
    la cancha (ver _buscar_cresta), y mide en metros la distancia entre la
    línea encontrada y la marca. Las muestras a menos de QC_RADIO_EXCLUSION_M
    de los puntos de ajuste no cuentan: ahí la proyección coincide por
    construcción.

    Líneas que no se ven: una marca con menos de QC_MIN_SOPORTE de sus
    muestras con línea real encontrada (o menos de QC_MIN_MUESTRAS_VISIBLE) se
    informa como NO VERIFICADA y no entra en el veredicto. Antes contaba como
    error: en sportivo_crop3 la banda lejana no se ve (la tapan los carteles)
    y el control la "medía" contra la base de los carteles con 7-12 m de
    error; las líneas tenues del lado izquierdo no las detectaba y sumaban al
    "% sin línea cerca".

    Límite, a propósito explícito: una marca proyectada a MÁS de
    QC_RADIO_BUSQUEDA_M de su línea real tampoco encuentra nada y queda "no
    verificada" en vez de fallar. Por eso el veredicto exige al menos
    QC_MIN_LINEAS_VERIFICADAS líneas verificadas, lista las no verificadas,
    y la imagen las muestra en gris: una zona entera sin verificar se ve.

    Guarda en `ruta_png` el frame con la superposición: magenta = marca
    proyectada y verificada; muestras verde/amarillo/rojo según error; cruz
    azul = muestra de una línea verificada sin línea real encontrada (jugador
    encima, tramo borrado); gris = marca no verificada; círculo blanco = punto
    de ajuste. `medidas`: las de la cancha (ver medidas_cancha.py); None → 105×68.

    Returns:
        dict con `veredicto` ("ok" | "revisar" | "no_verificable"), `motivos`,
        métricas globales (solo líneas verificadas), `por_linea` (verificadas)
        y `lineas_no_verificadas` (nombre → soporte).
    """
    alto, ancho = frame.shape[:2]
    ajuste = np.asarray(puntos_ajuste_m, dtype=np.float64).reshape(-1, 2)
    Hinv = np.linalg.inv(H)
    # Una homografía vale igual multiplicada por cualquier escalar, NEGATIVO
    # incluido. Se fija el signo para que w>0 en los puntos de ajuste (que
    # seguro están delante de la cámara); si no, "w<=0 = detrás de la cámara"
    # descartaría la cancha entera según cómo vino escalada H.
    m_cancha = completar_medidas(medidas)
    ref = ajuste.mean(axis=0) if len(ajuste) else np.array([m_cancha["largo"] / 2, m_cancha["ancho"] / 2])
    if (np.r_[ref, 1.0] @ Hinv.T)[2] < 0:
        Hinv = -Hinv
    tophat, candidato, direccion = _mapas_lineas(frame)

    def a_px(puntos_m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        homog = np.c_[puntos_m, np.ones(len(puntos_m))] @ Hinv.T
        delante = homog[:, 2] > 1e-9                       # w<=0: detrás de la cámara
        return homog[:, :2] / np.where(delante, homog[:, 2], 1)[:, None], delante

    vis = frame.copy()
    por_linea, no_verificadas = {}, {}
    errores_m, errores_por_linea, dibujo = [], {}, {}
    n_en_cuadro_ver = n_sin_linea_ver = 0

    for nombre, polilinea in _lineas_cancha(m_cancha).items():
        poli = np.asarray(polilinea, dtype=np.float64)
        muestras = _muestrear(poli, QC_PASO_MUESTREO_M)
        tangente = np.gradient(muestras, axis=0)
        tangente /= np.maximum(np.linalg.norm(tangente, axis=1, keepdims=True), 1e-12)
        normal = np.c_[-tangente[:, 1], tangente[:, 0]]
        px, delante = a_px(muestras)
        px_menos, ok_m = a_px(muestras - QC_RADIO_BUSQUEDA_M * normal)
        px_mas, ok_p = a_px(muestras + QC_RADIO_BUSQUEDA_M * normal)
        px_menos_a, _ = a_px(muestras - QC_RADIO_AMPLIO_M * normal)
        px_mas_a, _ = a_px(muestras + QC_RADIO_AMPLIO_M * normal)
        px_adelante, _ = a_px(muestras + 0.5 * tangente)      # para la dirección de la marca en píxeles

        marcas, errs, lejos, idx_lejos, n_en_cuadro = [], [], [], [], 0
        for i, m in enumerate(muestras):
            if not (delante[i] and ok_m[i] and ok_p[i]) or not np.all(np.isfinite(px[i])):
                continue
            x, y = px[i]
            if not (0 <= x < ancho and 0 <= y < alto):
                continue
            if len(ajuste) and np.min(np.linalg.norm(ajuste - m, axis=1)) < QC_RADIO_EXCLUSION_M:
                marcas.append(("ajuste", px[i], None))
                continue
            n_en_cuadro += 1
            # Ventana de búsqueda acotada en píxeles: en la zona cercana 4 m
            # pueden ser cientos de píxeles y atravesar otras líneas.
            d_menos, d_mas = px_menos[i] - px[i], px_mas[i] - px[i]
            for d in (d_menos, d_mas):
                largo = np.linalg.norm(d)
                if largo > QC_BUSQUEDA_MAX_PX:
                    d *= QC_BUSQUEDA_MAX_PX / largo
            dir_px = px_adelante[i] - px[i]
            dir_px = dir_px / max(np.linalg.norm(dir_px), 1e-9)
            hallado = _buscar_cresta(tophat, candidato, px[i], px[i] + d_menos, px[i] + d_mas)
            if hallado is None:
                # ¿No se ve, o está más lejos? Banda ancha, solo paralelas.
                a_menos, a_mas = px_menos_a[i] - px[i], px_mas_a[i] - px[i]
                for d in (a_menos, a_mas):
                    largo = np.linalg.norm(d)
                    if np.isfinite(largo) and largo > QC_BUSQUEDA_AMPLIA_MAX_PX:
                        d *= QC_BUSQUEDA_AMPLIA_MAX_PX / largo
                lejano = None
                if np.all(np.isfinite(a_menos)) and np.all(np.isfinite(a_mas)):
                    lejano = _buscar_cresta(tophat, candidato, px[i], px[i] + a_menos, px[i] + a_mas,
                                            direccion, dir_px)
                if lejano is not None:
                    real_m = cv2.perspectiveTransform(lejano.reshape(1, 1, 2).astype(np.float32), H).reshape(2)
                    e = _distancia_a_polilinea(real_m.astype(np.float64), poli)
                    if e > QC_RADIO_BUSQUEDA_M:
                        lejos.append(e)
                        idx_lejos.append(i)
                        marcas.append(("lejos", px[i], e))
                        continue
                marcas.append(("sin_linea", px[i], None))
                continue
            real_m = cv2.perspectiveTransform(hallado.reshape(1, 1, 2).astype(np.float32), H).reshape(2)
            e = _distancia_a_polilinea(real_m.astype(np.float64), poli)
            errs.append(e)
            marcas.append(("medida", px[i], e))

        soporte = len(errs) / n_en_cuadro if n_en_cuadro else 0.0
        frac_lejos = len(lejos) / n_en_cuadro if n_en_cuadro else 0.0
        visible = len(errs) >= QC_MIN_MUESTRAS_VISIBLE and soporte >= QC_MIN_SOPORTE
        # Las muestras "lejos" forman una línea real si su error cambia suave
        # entre muestras vecinas (los enganches al azar saltan).
        saltos = [abs(lejos[k + 1] - lejos[k]) for k in range(len(lejos) - 1) if idx_lejos[k + 1] == idx_lejos[k] + 1]
        lejos_coherente = (len(lejos) >= QC_MIN_MUESTRAS_VISIBLE and frac_lejos >= QC_MIN_FRACCION_LEJOS
                           and len(saltos) >= QC_MIN_MUESTRAS_VISIBLE // 2
                           and float(np.median(saltos)) <= QC_SUAVIDAD_LEJOS_M)
        # Visible pero corrida: la línea real aparece, coherente, más lejos que cerca.
        corrida = lejos_coherente and len(lejos) > len(errs)
        if corrida:
            visible = True
        dibujo[nombre] = (muestras, px, delante, visible, marcas)
        if corrida:
            por_linea[nombre] = {"muestras": len(errs) + len(lejos), "soporte": round(soporte + frac_lejos, 2),
                                 "error_mediano_m": round(float(np.median(errs + lejos)), 2),
                                 "error_p90_m": round(float(np.percentile(errs + lejos, 90)), 2),
                                 "corrida": True, "fraccion_lejos": round(frac_lejos, 2)}
            errores_m.extend(errs + lejos)
            n_en_cuadro_ver += n_en_cuadro
            n_sin_linea_ver += n_en_cuadro - len(errs) - len(lejos)
        elif visible:
            por_linea[nombre] = {"muestras": len(errs), "soporte": round(soporte, 2),
                                 "error_mediano_m": round(float(np.median(errs)), 2),
                                 "error_p90_m": round(float(np.percentile(errs, 90)), 2),
                                 "fraccion_lejos": round(frac_lejos, 2) if lejos_coherente else 0.0}
            errores_m.extend(errs)
            n_en_cuadro_ver += n_en_cuadro
            n_sin_linea_ver += n_en_cuadro - len(errs)
        elif n_en_cuadro:
            no_verificadas[nombre] = {"muestras_en_cuadro": n_en_cuadro, "soporte": round(soporte, 2),
                                      "fraccion_lejos": round(frac_lejos, 2)}

    # ── Dibujo ──
    for nombre, (muestras, px, delante, visible, marcas) in dibujo.items():
        visibles = [p for p, ok in zip(px, delante) if ok and np.all(np.isfinite(p))]
        if len(visibles) > 1:
            color = (255, 0, 255) if visible else (150, 150, 150)
            cv2.polylines(vis, [np.array(visibles, np.int32)], False, color, 2 if visible else 1)
        for tipo, p, e in marcas:
            x, y = int(round(p[0])), int(round(p[1]))
            if tipo == "ajuste":
                cv2.circle(vis, (x, y), 2, (160, 160, 160), -1)
            elif not visible:
                continue
            elif tipo == "sin_linea":
                cv2.drawMarker(vis, (x, y), (255, 128, 0), cv2.MARKER_TILTED_CROSS, 8, 2)
            elif tipo == "lejos":
                cv2.drawMarker(vis, (x, y), (0, 0, 255), cv2.MARKER_SQUARE, 8, 2)
            else:
                color = (0, 200, 0) if e < 0.5 else (0, 220, 255) if e < 1.5 else (0, 0, 255)
                cv2.circle(vis, (x, y), 3, color, -1)
        if not visible and nombre in no_verificadas:
            en_cuadro = [p for t, p, _ in marcas if t != "ajuste"]
            if en_cuadro:
                p = en_cuadro[len(en_cuadro) // 2]
                cv2.putText(vis, f"{nombre}: no se ve", (int(p[0]) + 4, int(p[1]) - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
    for m in ajuste:
        p = cv2.perspectiveTransform(m.reshape(1, 1, 2).astype(np.float32), Hinv).reshape(2)
        if np.all(np.isfinite(p)):
            cv2.circle(vis, (int(p[0]), int(p[1])), 9, (255, 255, 255), 2)

    n_ver = len(errores_m)
    frac_sin_linea = n_sin_linea_ver / n_en_cuadro_ver if n_en_cuadro_ver else 0.0
    resultado = {
        "muestras_verificadas": n_ver,
        "lineas_verificadas": sorted(por_linea),
        "fraccion_sin_linea_cerca": round(frac_sin_linea, 2),  # solo dentro de las líneas verificadas
        "error_mediano_m": round(float(np.median(errores_m)), 2) if n_ver else None,
        "error_p90_m": round(float(np.percentile(errores_m, 90)), 2) if n_ver else None,
        "por_linea": por_linea,
        "lineas_no_verificadas": no_verificadas,
        "parametros": {"radio_busqueda_m": QC_RADIO_BUSQUEDA_M, "min_soporte": QC_MIN_SOPORTE},
    }
    motivos = []
    if n_ver < QC_MIN_MUESTRAS or len(por_linea) < QC_MIN_LINEAS_VERIFICADAS:
        veredicto = "no_verificable"
        motivos.append(f"solo {len(por_linea)} líneas verificables con {n_ver} muestras lejos de los puntos "
                       f"de ajuste (mínimo {QC_MIN_LINEAS_VERIFICADAS} líneas y {QC_MIN_MUESTRAS} muestras) — "
                       f"no hay evidencia suficiente de que la calibración sea buena")
    else:
        if resultado["error_mediano_m"] > QC_ERROR_OK_M:
            motivos.append(f"error mediano {resultado['error_mediano_m']} m > {QC_ERROR_OK_M} m")
        # El promedio global puede esconder una línea muy corrida (p.ej. si
        # las bandas encajan bien y dominan la cuenta) — se mira cada una.
        for nombre, m in por_linea.items():
            if m.get("corrida"):
                motivos.append(f"{nombre}: la línea real se ve, pero a {m['error_mediano_m']} m de donde se "
                               f"proyecta (más de {QC_RADIO_BUSQUEDA_M} m)")
            elif m["muestras"] >= QC_MIN_MUESTRAS_LINEA and m["error_mediano_m"] > QC_ERROR_LINEA_MAX_M:
                motivos.append(f"{nombre}: error mediano {m['error_mediano_m']} m (> {QC_ERROR_LINEA_MAX_M} m)")
            elif m.get("fraccion_lejos", 0) >= QC_MIN_FRACCION_LEJOS:
                motivos.append(f"{nombre}: en el {m['fraccion_lejos']:.0%} de sus muestras la línea real está "
                               f"a más de {QC_RADIO_BUSQUEDA_M} m de donde se proyecta")
        if frac_sin_linea > QC_MAX_SIN_LINEA:
            motivos.append(f"{frac_sin_linea:.0%} de las muestras de las líneas verificadas no encuentran la "
                           f"línea real — la proyección está corrida o hay mucha oclusión")
        veredicto = "revisar" if motivos else "ok"
    resultado["veredicto"], resultado["motivos"] = veredicto, motivos

    color_v = {"ok": (0, 200, 0), "revisar": (0, 0, 255), "no_verificable": (0, 165, 255)}[veredicto]
    texto = (f"CONTROL: {veredicto.upper()}  |  error mediano {resultado['error_mediano_m']} m  |  "
             f"{len(por_linea)} lineas verificadas, {len(no_verificadas)} no se ven (gris)  |  n={n_ver}")
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
            print(f"     {nombre:<16} {m['error_mediano_m']:>5} m  (n={m['muestras']}, "
                  f"línea encontrada en el {m['soporte']:.0%} de sus muestras)")
    no_ver = resultado.get("lineas_no_verificadas") or {}
    if no_ver:
        print("   No verificadas (no se ven en el cuadro, o están a más de "
              f"{resultado.get('parametros', {}).get('radio_busqueda_m', QC_RADIO_BUSQUEDA_M)} m de donde se proyectan):")
        for nombre, d in no_ver.items():
            print(f"     {nombre:<16} línea encontrada en el {d['soporte']:.0%} de {d['muestras_en_cuadro']} muestras")
    for motivo in resultado["motivos"]:
        print(f"   - {motivo}")
    print(f"   Superposición guardada en: {resultado['imagen']}")
    if resultado["veredicto"] != "ok":
        print("   Mirá la imagen antes de usar esta calibración.")
    elif no_ver:
        print("   Mirá la imagen: las zonas de las líneas no verificadas no tienen evidencia a favor ni en contra.")


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


def calibrate(video_path: Path, point_names: list = None, frame_idx: int = 0,
              medidas: dict | None = None) -> Path:
    """
    Abre el frame `frame_idx` del video (por defecto el primero) y pide clics
    en los puntos de referencia. Guarda la homografía resultante en un .json.
    Conviene elegir un frame con la cámara en su posición más habitual y
    usar puntos que se VEAN (no extrapolar marcas fuera de cuadro).

    `medidas`: las de la cancha (ver medidas_cancha.py; None → 105×68). Se
    guarda una COPIA en el .json, que es la que usan --apply y --verificar.
    """
    point_names = point_names or DEFAULT_ORDER
    medidas = completar_medidas(medidas)
    puntos = puntos_referencia(medidas)

    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        sys.exit(f"[ERROR] No se pudo leer el frame {frame_idx} de: {video_path}")

    print(f"\nCancha: {descripcion(medidas)}")
    print(f"Se abrirá una ventana con el frame {frame_idx}. Hacé clic, en orden, en estos "
          f"{len(point_names)} puntos:")
    for i, name in enumerate(point_names, 1):
        x, y = puntos[name]
        print(f"  {i}. {name.replace('_', ' '):<22} (x={x:.2f} m, y={y:.2f} m)")
    print("\nSi alguno de estos puntos no se ve en tu video, cancelá (Q) y volvé a")
    print("llamar a calibrate() pasando otra lista de puntos que sí se vean")
    print("(ver REFERENCE_POINTS en este archivo para las opciones disponibles).\n")
    input("Presioná ENTER para abrir la ventana...")

    ui = CalibrationUI(frame, point_names)
    pixel_points = ui.run()

    if pixel_points is None:
        sys.exit("[INFO] Calibración cancelada.")

    return _guardar_calibracion(video_path, frame, frame_idx, point_names, pixel_points, medidas,
                                origen={"tipo": "clics_manuales"})


def calibrar_desde_archivo(video_path: Path, archivo_puntos: Path, medidas: dict | None = None) -> Path:
    """
    Calibra con puntos leídos de un .json en vez de clics. Para puntos
    medidos con más precisión que un clic (p.ej. intersecciones de líneas
    ajustadas al sub-píxel sobre la imagen) y, más adelante, para el modo
    semiautomático. En la zona lejana de una cámara baja 1 px de alto puede
    ser ~0.3 m: con clics en la ventana reducida no se llega a esa precisión.

    Formato del archivo:
        {
          "video": "sportivo_crop3.mp4",              # opcional, se avisa si no coincide
          "frame": 4500,                              # frame sobre el que se midió
          "origen": "ajuste_de_lineas",               # cómo se obtuvieron los puntos
          "descripcion": "texto libre",               # opcional
          "puntos": [
            {"nombre": "circulo_mitad_sup", "px": [880.3, 100.7],
             "metodo": "elipse del círculo ∩ recta de la línea media"},   # "metodo" opcional
            ...
          ]
        }
    El .json de la calibración deja registrado ese origen (no "clics_manuales").
    """
    with open(archivo_puntos) as f:
        datos = json.load(f)
    if datos.get("video") and datos["video"] != video_path.name:
        print(f"[AVISO] El archivo de puntos es de '{datos['video']}' y se está calibrando '{video_path.name}'.")
    puntos_archivo = datos.get("puntos") or []
    point_names = [p["nombre"] for p in puntos_archivo]
    invalidos = [n for n in point_names if n not in REFERENCE_POINTS]
    if invalidos or len(point_names) < 4:
        sys.exit(f"[ERROR] {archivo_puntos}: hacen falta al menos 4 puntos con nombres válidos. "
                 f"No reconocidos: {invalidos}\n  Opciones válidas: {list(REFERENCE_POINTS.keys())}")
    if "frame" not in datos:
        sys.exit(f"[ERROR] {archivo_puntos}: falta \"frame\" (el frame sobre el que se midieron los puntos).")
    frame_idx = int(datos["frame"])
    pixel_points = [[float(v) for v in p["px"]] for p in puntos_archivo]

    medidas = completar_medidas(medidas)
    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        sys.exit(f"[ERROR] No se pudo leer el frame {frame_idx} de: {video_path}")

    print(f"\nCancha: {descripcion(medidas)}")
    print(f"Puntos desde {archivo_puntos} (origen: {datos.get('origen', 'sin especificar')}), frame {frame_idx}")
    origen = {
        "tipo": datos.get("origen", "archivo"),
        "archivo": str(archivo_puntos),
        "descripcion": datos.get("descripcion"),
        "metodo_por_punto": {p["nombre"]: p.get("metodo") for p in puntos_archivo},
    }
    return _guardar_calibracion(video_path, frame, frame_idx, point_names, pixel_points, medidas, origen)


def _guardar_calibracion(video_path: Path, frame: np.ndarray, frame_idx: int, point_names: list,
                         pixel_points: list, medidas: dict, origen: dict) -> Path:
    """Homografía + residuos + control de calidad + .json, igual para clics o archivo.
    `origen` queda en el .json ("origen_puntos"): de dónde salieron los píxeles."""
    puntos = puntos_referencia(medidas)
    real_points = [puntos[name] for name in point_names]

    src = np.array(pixel_points, dtype=np.float32)
    dst = np.array(real_points, dtype=np.float32)
    H, status = cv2.findHomography(src, dst, method=0)

    if H is None:
        sys.exit("[ERROR] No se pudo calcular la homografía. Revisá que los 4 puntos no sean colineales.")

    # Residuo por punto: con más de 4 puntos, un punto mal marcado se nota
    # como un residuo mucho mayor que el resto. (Esto NO mide la calidad de
    # la calibración — mide si los puntos son consistentes entre sí. La
    # calidad la mide control_calidad(), lejos de estos puntos.)
    if len(point_names) > 4:
        proy = cv2.perspectiveTransform(src.reshape(-1, 1, 2), H).reshape(-1, 2)
        residuos = np.linalg.norm(proy - dst, axis=1)
        print("\nResiduo por punto (consistencia entre puntos):")
        for name, r in zip(point_names, residuos):
            aviso = "  ← ¿punto corrido? revisalo" if r > 1.0 else ""
            print(f"   {name:<26} {r:5.2f} m{aviso}")

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUTS / f"{video_path.stem}_homography.json"

    # Control de calidad contra las líneas reales del mismo frame. No bloquea
    # el guardado (el usuario decide), pero el veredicto queda en el .json y
    # se imprime fuerte si no es "ok".
    control = control_calidad(frame, H, real_points, OUTPUTS / f"{video_path.stem}_calibracion_control.png",
                              medidas)

    calibration = {
        "video": video_path.name,
        "frame": frame_idx,
        "point_names": point_names,
        "pixel_points": [list(p) for p in pixel_points],
        "real_points": real_points,
        "origen_puntos": origen,
        "homography_matrix": H.tolist(),
        CLAVE_ATTRS: medidas,
        "control_calidad": control,
    }
    with open(out_path, "w") as f:
        json.dump(calibration, f, indent=2)

    print(f"\n✅ Calibración guardada en: {out_path.name}")
    print("   Podés reusarla para todos los videos grabados desde la misma cámara/posición.")
    imprimir_control(control)
    imprimir_estabilidad(estabilidad_de(video_path, out_path, forzar=True))
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
    medidas = completar_medidas(calib.get(CLAVE_ATTRS))
    control = control_calidad(frame, np.array(calib["homography_matrix"], dtype=np.float64),
                              calib["real_points"], ruta_png, medidas)
    print(f"\nCalibración: {homography_path.name}  (puntos: {', '.join(calib['point_names'])})  — frame {idx}")
    print(f"Cancha: {descripcion(medidas)}")
    imprimir_control(control)
    if frame_idx is None:   # sin --frame: además, ¿la cámara se mantuvo en todo el video?
        imprimir_estabilidad(estabilidad_de(video_path, homography_path))
    return control


# ── ¿La cámara se movió? Estabilidad de la calibración a lo largo del video ─────
# Una calibración vale para UNA posición de cámara. Con cámara "fija" igual se
# mueve: en sportivo_crop3 la cámara derivó ~2 px en los primeros 19 min y a las
# 19:30 saltó ~10 px (un golpe al trípode o un reacomodo). Con la matriz fija,
# desde ahí el error de posición fue de 1.6–1.8 m de mediana y ~3 m en la banda
# lejana, y el control por superposición NO lo detectaba de forma confiable (en
# un video nocturno verifica pocas líneas y su resultado depende de cuáles se
# ven en cada momento). Por eso esto mide directo el movimiento de la cámara:
# registra cada momento contra el frame calibrado (ORB + RANSAC, sobre todo lo
# que tiene textura: tribuna, carteles, líneas) y traduce ese corrimiento a
# metros sobre una grilla de la cancha.
ESTABILIDAD_INTERVALO_SEG = 30     # cada cuánto se mira el video (como máximo)...
ESTABILIDAD_MIN_MUESTRAS = 60      # ...pero al menos tantas veces: en un clip de 45 s, cada 30 s
#                                    eran 3 muestras y se perdía el único tramo válido
ESTABILIDAD_PASO_GRILLA_M = 3.0    # grilla de la cancha sobre la que se mide el error
ESTABILIDAD_MIN_INLIERS = 30       # menos coincidencias → la imagen no es comparable
#                                    (cámara apuntando a otro lado, corte de plano)
ESTABILIDAD_RESOLUCION_SEG = 1.0   # precisión con que se ubica cada cambio
# Criterio "la calibración sigue valiendo": el mismo que el control de calidad
# (QC_ERROR_OK_M de mediana, QC_ERROR_LINEA_MAX_M de p90).
ESTABILIDAD_VERSION = 5            # cambia si cambia el método: invalida el caché


class _Registrador:
    """Compara frames contra el frame calibrado y mide el error en metros que
    produce el corrimiento de la cámara si se usa la matriz fija."""

    def __init__(self, cap: cv2.VideoCapture, calib: dict):
        self.cap = cap
        self.H = np.array(calib["homography_matrix"], dtype=np.float64)
        medidas = completar_medidas(calib.get(CLAVE_ATTRS))
        self.orb = cv2.ORB_create(4000)
        ref = self._leer(calib.get("frame", 0))
        if ref is None:
            raise RuntimeError("No se pudo leer el frame de la calibración")
        self.k_ref, self.d_ref = self.orb.detectAndCompute(cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY), None)
        alto, ancho = ref.shape[:2]
        gx, gy = np.meshgrid(np.arange(1, medidas["largo"], ESTABILIDAD_PASO_GRILLA_M),
                             np.arange(1, medidas["ancho"], ESTABILIDAD_PASO_GRILLA_M))
        campo = np.c_[gx.ravel(), gy.ravel()].astype(np.float32)
        px = cv2.perspectiveTransform(campo.reshape(-1, 1, 2), np.linalg.inv(self.H).astype(np.float32)).reshape(-1, 2)
        dentro = (px[:, 0] >= 0) & (px[:, 0] < ancho) & (px[:, 1] >= 0) & (px[:, 1] < alto)
        self.campo, self.px = campo[dentro], px[dentro]
        self.lejos = self.campo[:, 1] < medidas["ancho"] / 3

    def _leer(self, idx: int):
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = self.cap.read()
        return frame if ok else None

    def medir(self, idx: int) -> dict:
        frame = self._leer(idx)
        if frame is None or self.d_ref is None:
            return {"estado": "sin_comparar", "inliers": 0}
        k, d = self.orb.detectAndCompute(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), None)
        if d is None:
            return {"estado": "sin_comparar", "inliers": 0}
        m = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(self.d_ref, d)
        if len(m) < ESTABILIDAD_MIN_INLIERS:
            return {"estado": "sin_comparar", "inliers": len(m)}
        G, inl = cv2.findHomography(np.float32([self.k_ref[x.queryIdx].pt for x in m]),
                                    np.float32([k[x.trainIdx].pt for x in m]), cv2.RANSAC, 3.0)
        if G is None or int(inl.sum()) < ESTABILIDAD_MIN_INLIERS:
            return {"estado": "sin_comparar", "inliers": 0 if inl is None else int(inl.sum())}
        # Dónde aparece hoy cada punto de la cancha, y qué coordenada le daría la matriz fija.
        px_t = cv2.perspectiveTransform(self.px.reshape(-1, 1, 2), G.astype(np.float32)).reshape(-1, 2)
        medido = cv2.perspectiveTransform(px_t.reshape(-1, 1, 2), self.H.astype(np.float32)).reshape(-1, 2)
        e = np.linalg.norm(medido - self.campo, axis=1)
        mediana, p90 = float(np.median(e)), float(np.percentile(e, 90))
        vale = mediana <= QC_ERROR_OK_M and p90 <= QC_ERROR_LINEA_MAX_M
        return {"estado": "vale" if vale else "no_vale", "inliers": int(inl.sum()),
                "error_mediano_m": round(mediana, 2), "error_p90_m": round(p90, 2),
                "error_banda_lejana_m": round(float(np.median(e[self.lejos])), 2) if self.lejos.any() else None}


def _formato_tiempo(seg: float) -> str:
    return f"{int(seg // 60)}:{seg % 60:04.1f}"


def verificar_estabilidad(video_path: Path, calib: dict,
                          intervalo_seg: float = ESTABILIDAD_INTERVALO_SEG) -> dict:
    """
    Mira el video cada `intervalo_seg` y decide si la calibración sigue
    valiendo ("vale" / "no_vale" / "sin_comparar"). Entre dos muestras de
    estado distinto mira segundo a segundo, para ubicar cada cambio. Devuelve las
    muestras y los tramos en que la matriz NO vale, con su error en metros.
    """
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    reg = _Registrador(cap, calib)
    intervalo_seg = min(intervalo_seg, (n / fps) / ESTABILIDAD_MIN_MUESTRAS) if fps else intervalo_seg
    paso = max(int(round(intervalo_seg * fps)), 1)
    # Siempre se mira también el frame calibrado: ahí la matriz vale por construcción.
    indices = sorted(set(list(range(0, n, paso)) + [n - 1, int(calib.get("frame", 0))]))
    muestras = [{"frame": i, "t": round(i / fps, 1), **reg.medir(i)} for i in indices]

    # Donde dos muestras seguidas difieren, se mira segundo a segundo (no
    # búsqueda binaria: al arrancar el video la cámara puede pasar por varios
    # estados en pocos segundos — en sportivo_crop3, tribuna → cancha → otra vez
    # sin comparar → cancha entre 0 y 8 s — y una bisección se queda con uno).
    resolucion = max(int(round(ESTABILIDAD_RESOLUCION_SEG * fps)), 1)
    finas = []
    for a, b in zip(muestras[:-1], muestras[1:]):
        if a["estado"] != b["estado"]:
            finas += [{"frame": i, "t": round(i / fps, 1), **reg.medir(i)}
                      for i in range(a["frame"] + resolucion, b["frame"], resolucion)]
    cap.release()
    linea = sorted(muestras + finas, key=lambda m: m["frame"])

    # Tramos donde no vale: cada racha de observaciones no-"vale" (desde la
    # primera hasta la siguiente que vuelve a valer, o el final del video).
    duracion = round((n - 1) / fps, 1)
    tramos, actual = [], None
    for m in linea:
        if m["estado"] != "vale":
            if actual is None:
                actual = {"desde": m["t"], "motivo": m["estado"], "obs": []}
            actual["obs"].append(m)
            if m["estado"] == "no_vale":
                actual["motivo"] = "no_vale"   # si hubo movimiento medido, prima sobre "sin comparar"
        elif actual is not None:
            actual["hasta"] = m["t"]; tramos.append(actual); actual = None
    if actual is not None:
        actual["hasta"] = duracion; tramos.append(actual)
    # Tramos separados por un solo paso "válido" son el mismo episodio (con
    # resolución de 1 s, un frame suelto puede caer bien en medio del movimiento).
    unidos = []
    for t in tramos:
        if unidos and t["desde"] - unidos[-1]["hasta"] <= ESTABILIDAD_RESOLUCION_SEG + 0.05:
            unidos[-1]["hasta"] = t["hasta"]; unidos[-1]["obs"] += t["obs"]
            if t["motivo"] == "no_vale":
                unidos[-1]["motivo"] = "no_vale"
        else:
            unidos.append(t)
    tramos = unidos
    cambios = [{"t": t["desde"], "a": t["motivo"]} for t in tramos]
    for t in tramos:
        dentro = [m for m in t.pop("obs") if "error_mediano_m" in m]
        # Típico del tramo (mediana de las observaciones) y pico (el peor instante,
        # p.ej. mientras movían la cámara).
        t["error_mediano_m"] = round(float(np.median([m["error_mediano_m"] for m in dentro])), 2) if dentro else None
        t["error_banda_lejana_m"] = (round(float(np.median([m["error_banda_lejana_m"] or 0 for m in dentro])), 2)
                                     if dentro else None)
        t["error_pico_m"] = max((m["error_mediano_m"] for m in dentro), default=None)
    segundos_no_vale = sum(t["hasta"] - t["desde"] for t in tramos)
    return {"version": ESTABILIDAD_VERSION, "intervalo_seg": round(intervalo_seg, 2), "duracion_seg": duracion,
            "muestras": muestras, "cambios": cambios, "tramos_no_validos": tramos,
            "fraccion_valida": round(1 - segundos_no_vale / duracion, 3) if duracion else 1.0}


def imprimir_estabilidad(r: dict) -> None:
    tramos = r["tramos_no_validos"]
    if not tramos:
        print(f"\n✅ Cámara estable: la calibración vale en todo el video ({_formato_tiempo(r['duracion_seg'])}, "
              f"mirado cada {r['intervalo_seg']:g} s).")
        return
    print(f"\n⚠️  La calibración NO vale en {len(tramos)} tramo(s) — vale en el {r['fraccion_valida']:.0%} del video:")
    for t in tramos:
        dur = t["hasta"] - t["desde"]
        if t["motivo"] == "sin_comparar":
            detalle = "la imagen no se parece al frame calibrado (cámara apuntando a otro lado o corte)"
        else:
            detalle = (f"cámara movida: error de posición típico {t['error_mediano_m']} m"
                       + (f" ({t['error_banda_lejana_m']} m en la banda lejana)" if t["error_banda_lejana_m"] else "")
                       + (f", pico {t['error_pico_m']} m" if t.get("error_pico_m") and t["error_pico_m"] > 2 * (t["error_mediano_m"] or 0) else ""))
        breve = "  (momentáneo)" if dur < r["intervalo_seg"] else ""
        print(f"   {_formato_tiempo(t['desde'])} – {_formato_tiempo(t['hasta'])}: {detalle}{breve}")
    print("   Las coordenadas de esos tramos están corridas. Opciones: recalibrar ese tramo, o descartarlo del análisis.")


def _ruta_estabilidad(homography_path: Path) -> Path:
    return homography_path.parent / f"{homography_path.stem.replace('_homography', '')}_estabilidad_camara.json"


def estabilidad_de(video_path: Path, homography_path: Path, forzar: bool = False) -> dict:
    """verificar_estabilidad() con caché en <video>_estabilidad_camara.json (al
    lado de la calibración, sin modificarla). El caché vale mientras no cambien
    el video, la matriz ni el método."""
    with open(homography_path) as f:
        calib = json.load(f)
    st_video = Path(video_path).stat()
    clave = {"video": Path(video_path).name, "tamano": st_video.st_size, "mtime": st_video.st_mtime,
             "matriz": calib["homography_matrix"], "frame": calib.get("frame", 0), "version": ESTABILIDAD_VERSION}
    ruta = _ruta_estabilidad(homography_path)
    if ruta.exists() and not forzar:
        guardado = json.load(open(ruta))
        if guardado.get("clave") == clave:
            return guardado["resultado"]
    print(f"Verificando la estabilidad de la cámara en {Path(video_path).name} "
          f"(cada {ESTABILIDAD_INTERVALO_SEG} s)...")
    resultado = verificar_estabilidad(video_path, calib)
    with open(ruta, "w") as f:
        json.dump({"clave": clave, "resultado": resultado}, f, indent=1)
    return resultado


def _medidas_para_calibrar(match_name: str, nombre_estadio: str | None) -> dict:
    """
    Medidas a usar al calibrar `match_name`:
      - con `nombre_estadio`: las de ese estadio, y queda asignado al partido;
      - sin él: las del estadio ya asignado al partido (match_estadio);
      - si no hay ninguno: las reglamentarias (105×68), avisando.
    """
    from src.db import estadio_repo
    estadio_repo.init_estadios_table()
    if nombre_estadio:
        estadio = estadio_repo.get_estadio(nombre_estadio)
        if estadio is None:
            sys.exit(f"[ERROR] No existe el estadio '{nombre_estadio}'. Cargalo primero:\n"
                     f"  python scripts/estadios.py alta \"{nombre_estadio}\" --largo <m> --ancho <m>")
        estadio_repo.set_match_estadio(match_name, estadio["id"])
        return completar_medidas(estadio["medidas"])
    estadio = estadio_repo.get_match_estadio(match_name)
    if estadio is not None:
        return completar_medidas(estadio["medidas"])
    print("[AVISO] El partido no tiene estadio asignado: se calibra con la cancha reglamentaria "
          "de 105×68. Si la cancha mide otra cosa, cancelá y pasá --estadio "
          "(ver python scripts/estadios.py listar).")
    return completar_medidas(None)


def _avisar_si_cambio_estadio(match_name: str, medidas_calibracion: dict) -> None:
    """Si el estadio asignado hoy al partido tiene medidas distintas de las
    que guardó la calibración, avisa: las coordenadas saldrían con las viejas."""
    from src.db import estadio_repo
    estadio_repo.init_estadios_table()
    estadio = estadio_repo.get_match_estadio(match_name)
    if estadio is None:
        return
    actuales = completar_medidas(estadio["medidas"])
    if any(abs(actuales[k] - medidas_calibracion[k]) > 1e-6 for k in MEDIDAS_REGLAMENTARIAS):
        print(f"[AVISO] El estadio asignado al partido ahora es {descripcion(actuales)}, pero la "
              f"calibración se hizo con {descripcion(medidas_calibracion)}. Se usan las de la "
              f"calibración; para usar las nuevas, recalibrá.")


def apply_homography(coords_path: Path, homography_path: Path, video_path: Path | None = None) -> Path:
    """
    Aplica una calibración guardada a un .parquet de coordenadas en píxeles,
    agregando columnas field_x, field_y en metros reales.

    Filtra detecciones que caen fuera de la cancha (con margen OUT_OF_BOUNDS_MARGIN)
    para descartar banco, cuerpo técnico, árbitros de línea fuera de juego, etc.

    Las medidas de la cancha salen del .json de la calibración (la copia que
    guardó calibrate(); un .json anterior a eso → 105×68) y se guardan en el
    parquet como metadata: `df.attrs["medidas_cancha"]`, que pandas conserva
    al leer y escribir. Sin columnas nuevas — el contrato del parquet no cambia.

    Antes de aplicar, verifica que la cámara no se haya movido respecto del
    frame calibrado (verificar_estabilidad) y AVISA de los tramos en que la
    matriz no vale; no los descarta. Quedan en
    `df.attrs["calibracion_tramos_no_validos"]` (lista de {desde, hasta,
    motivo, ...} en segundos) para que el análisis pueda excluirlos.
    `video_path`: el video calibrado (default: data/videos/<video del .json>).
    """
    with open(homography_path) as f:
        calib = json.load(f)
    H = np.array(calib["homography_matrix"], dtype=np.float64)
    medidas = completar_medidas(calib.get(CLAVE_ATTRS))
    print(f"Cancha: {descripcion(medidas)}" + ("" if CLAVE_ATTRS in calib else
          "  — la calibración es anterior a las medidas por estadio"))
    _avisar_si_cambio_estadio(homography_path.stem.replace("_homography", ""), medidas)

    if video_path is None:
        video_path = ROOT / "data" / "videos" / calib.get("video", "")
    tramos_no_validos = None
    if Path(video_path).is_file():
        estabilidad = estabilidad_de(video_path, homography_path)
        imprimir_estabilidad(estabilidad)
        tramos_no_validos = estabilidad["tramos_no_validos"]
    else:
        print(f"[AVISO] No encontré el video {video_path}: no se pudo verificar si la cámara se movió.")

    df = pd.read_parquet(coords_path)

    points = df[["cx", "feet_y"]].to_numpy(dtype=np.float32).reshape(-1, 1, 2)
    transformed = cv2.perspectiveTransform(points, H).reshape(-1, 2)

    df["field_x"] = transformed[:, 0].round(2)
    df["field_y"] = transformed[:, 1].round(2)

    margin = OUT_OF_BOUNDS_MARGIN
    in_bounds = (
        (df["field_x"] >= -margin) & (df["field_x"] <= medidas["largo"] + margin) &
        (df["field_y"] >= -margin) & (df["field_y"] <= medidas["ancho"] + margin)
    )
    n_out = (~in_bounds).sum()
    n_total = len(df)

    # Filtramos las detecciones fuera de cancha del resultado final
    df_filtered = df[in_bounds].copy()
    df_filtered.attrs[CLAVE_ATTRS] = medidas
    if tramos_no_validos is not None:
        df_filtered.attrs["calibracion_tramos_no_validos"] = tramos_no_validos

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
    print(f"   Medidas de la cancha guardadas como metadata del parquet: {descripcion(medidas)}")
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

  python src/homography/calibrate.py data/videos/partido.mp4 --estadio "Sportivo Belgrano"

  python src/homography/calibrate.py data/videos/partido.mp4 --puntos-archivo data/calibracion/partido_puntos.json
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
                              "video, sin recalibrar; sin --frame, además verifica si la cámara se "
                              "movió a lo largo de todo el video")
    parser.add_argument("--frame", type=int, default=None,
                         help="Frame sobre el cual calibrar (default: 0) o, con --verificar, sobre el "
                              "cual verificar (default: el frame con el que se calibró)")
    parser.add_argument("--puntos-archivo", type=str, default=None,
                         help="Calibrar con los puntos de este .json en vez de clics (ver "
                              "calibrar_desde_archivo); el frame sale del archivo")
    parser.add_argument("--estadio", type=str, default=None,
                         help="Al calibrar: estadio cuyas medidas usar (ver scripts/estadios.py); queda "
                              "asignado al partido. Sin esto: el estadio ya asignado o, si no hay, 105×68")
    args = parser.parse_args()

    video_path = Path(args.video)
    if args.estadio and (args.apply or args.verificar):
        sys.exit("[ERROR] --estadio va solo al calibrar: --apply y --verificar usan las medidas que "
                 "quedaron guardadas en la calibración. Para cambiarlas, recalibrá con --estadio.")
    if args.puntos_archivo and (args.apply or args.verificar):
        sys.exit("[ERROR] --puntos-archivo es para calibrar; no se combina con --apply ni --verificar.")
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
        apply_homography(coords_path, homography_path, video_path)
    else:
        point_names = args.points.split(",") if args.points else None
        if point_names:
            invalid = [p for p in point_names if p not in REFERENCE_POINTS]
            if invalid:
                sys.exit(f"[ERROR] Puntos no reconocidos: {invalid}\n"
                          f"  Opciones válidas: {list(REFERENCE_POINTS.keys())}")
        medidas = _medidas_para_calibrar(video_path.stem, args.estadio)
        if args.puntos_archivo:
            if point_names or args.frame is not None:
                sys.exit("[ERROR] Con --puntos-archivo, los puntos y el frame salen del archivo: "
                         "no combinar con --points ni --frame.")
            calibrar_desde_archivo(video_path, Path(args.puntos_archivo), medidas)
        else:
            calibrate(video_path, point_names=point_names, frame_idx=args.frame or 0, medidas=medidas)
