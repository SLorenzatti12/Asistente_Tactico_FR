"""
Analizador Táctico — Detección de patrones tácticos por jugador
====================================================================
Módulo de análisis en 3 pasos, pensado para leerse en ese orden:

    fases  = detectar_fases(df)              # ¿el bloque de cada equipo avanza o repliega, y cuándo?
    lineas = asignar_lineas(df)               # ¿en qué línea juega cada jugador, en cada frame?
    patrones = detectar_patrones(df, fases, lineas)   # señales por jugador, con evidencia

Qué mide "fase" acá (y qué NO mide)
--------------------------------------
No hay detección de posesión de pelota confiable en este pipeline — la
clase `ball` tiene recall bajo, así que no se puede saber con confianza
quién tiene la pelota en cada instante. `detectar_fases` NO mide ataque/
defensa en el sentido de posesión: mide si el CENTROIDE del bloque de un
equipo avanza o retrocede sobre el eje X. Es una proxy geométrica del
posicionamiento del equipo, no del juego con pelota — un equipo puede
empujar la línea sin tener la pelota (presión alta) o replegarse
teniéndola (bloque bajo buscando de contra). Los patrones que dependen de
"fase de ataque"/"fase defensiva" heredan esta limitación: miden si un
jugador acompaña el movimiento de bloque de su equipo, no si ataca o
defiende en sentido futbolístico estricto.

Qué patrones se implementan acá, y cuáles no (y por qué)
------------------------------------------------------------
De los cuatro patrones evaluados, se implementan DOS con buena base de
datos (`desconectado`, `no_achica`) y se dejan DOS marcados como no
implementados (`no_repliega`, `cobertura_banda`) — ver sus docstrings
para el detalle. En criollo: con clips de 27-45 segundos, un partido
típico contiene 0-1 eventos reales de cambio de fase (verificado a mano
sobre partido_clip2: ~30s de bloque estable, un único avance sostenido de
~10s, repliegue parcial). Eso alcanza para detectar la fase en sí, pero
NO alcanza para hablar de una "tendencia" de un jugador puntual en esa
única fase — es una observación, no un patrón repetido. `no_achica` se
implementa igual, pero con un freno explícito: si el equipo no acumuló un
mínimo de fases de ataque independientes (MIN_FASES_ATAQUE), no emite una
severidad para sus jugadores — el resultado queda registrado como "datos
insuficientes" en vez de un número que parezca confiable sin serlo.
`desconectado`, en cambio, no depende de fases: usa el clip completo
(cientos de frames por jugador) como muestra, así que es la señal más
sólida de las cuatro.

Este mismo motivo es por el que el club aportando partidos completos (no
solo clips) cambia el panorama: con más minutos por jugador hay más
eventos de fase para promediar, y ahí sí valen la pena `no_repliega` y
`cobertura_banda` — quedan con un esqueleto (NotImplementedError) a
propósito, no lo hicimos por falta de tiempo, sino porque implementarlos
hoy daría una falsa sensación de precisión.

El wording importa
--------------------
Las descripciones de detectar_patrones están escritas para un DT, no
para un ingeniero: "tendencia a jugar separado de su línea", no "z-score
de distancia al centroide = 2.3". El número técnico va aparte, en la
columna `valor_tecnico` — ahí si conviene ser preciso, para quien quiera
auditar el número. Y ningún patrón se afirma como verdad absoluta: son
señales estadísticas sobre datos con tracking fragmentado y homografía
imperfecta, así que el wording usa siempre "posible"/"tendencia a", nunca
una afirmación categórica.

LIMITACIÓN CONOCIDA — dirección de ataque depende del arquero
------------------------------------------------------------------
Todo lo que usa "profundidad ajustada por sentido de ataque" (fases,
líneas, no_achica) depende de _direccion_ataque(), que necesita saber
qué arco defiende cada equipo. El camino confiable es la posición
promedio del arquero propio — pero el arquero es una clase minoritaria y
a veces el modelo casi no lo detecta como tal (en partido_clip2, el
arquero de un equipo tuvo apenas 9 detecciones en 45s, por debajo de
MIN_MUESTRAS_ARQUERO_DIRECCION=10, disperso en 5 track_ids distintos —
ruido, no un arquero real trackeado). Cuando eso pasa para UN equipo y
el OTRO sí tiene arquero confiable, la dirección del que falta queda
FORZADA por descarte (solo hay 2 arcos) — ese camino es seguro. El
riesgo real es que NINGÚN equipo tenga arquero confiable: ahí se cae a
comparar el field_x promedio de jugadores de campo entre los dos
equipos, una inferencia bastante más débil (asume que el que jugó más
retrasado en promedio durante TODO el clip es el que defiende ese lado,
lo cual puede no cumplirse en un clip corto o con posesión muy desigual)
y sin forma de detectar sola si se equivocó. Por eso detectar_fases() y
asignar_lineas() dejan un aviso explícito en `.attrs["avisos"]` (y
detectar_patrones() lo hereda) cada vez que se resuelve por ese camino —
revisar contra el video antes de confiar en esos equipos.

LIMITACIÓN CONCEPTUAL — posición no es intención
------------------------------------------------------
Validamos los primeros resultados de este módulo contra video, con un DT
mirando las jugadas — y los tres casos de severidad máxima resultaron ser
falsos positivos, los tres por el mismo motivo de fondo: el sistema mide
DESVIACIÓN POSICIONAL, no INTENCIÓN TÁCTICA. Un jugador puede alejarse de
su línea o no acompañar una subida por razones perfectamente correctas
que la geometría, sola, no puede distinguir de un problema real:

  - Se abre de su línea para desmarcarse y recibir un pase — no es que
    esté desordenado, está generando un pase.
  - Sale de su posición porque está haciendo marca personal sobre un
    rival — dejar la línea ES la jugada correcta ahí.
  - No sube en una única subida del equipo por la basculación normal del
    juego (un lateral que se queda cubriendo mientras el otro ataca, por
    ejemplo) — "1 de 4" no es una tendencia, es una jugada puntual.

Ninguna cantidad de ajuste de umbrales resuelve esto de raíz: no hay
información de intención en el tracking posicional. Lo que SÍ se puede
hacer — y es lo que hace este módulo desde esta validación — es subir el
listón de EVIDENCIA todo lo posible: exigir que un comportamiento se
repita en la mayoría de las oportunidades reales que tuvo (no una vez),
y que una desviación sea sostenida en el tiempo (no un tramo aislado que
coincide con una jugada puntual). Eso reduce falsos positivos, pero no
los elimina — sigue siendo perfectamente posible que un marcador personal
consistente a lo largo de todo un partido dispare `desconectado` con
severidad alta, porque su posición SÍ es consistentemente distinta a la
de su línea, aunque sea la jugada correcta.

Por eso, y esto no es negociable en el wording de las descripciones: los
patrones de este módulo son SEÑALES PARA REVISAR EN VIDEO, nunca
diagnósticos. El umbral de evidencia es alto justamente porque el costo
de un falso positivo (decirle a un DT que un jugador tiene un problema
que no tiene) es alto, y no hay forma de que el sistema se autocorrija:
necesita un par de ojos mirando la jugada, siempre.

Uso por consola:
    python src/analysis/tactical_patterns.py data/outputs/partido_clip2_coords_field.parquet
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# MAX_SPEED_MS: mismo techo de velocidad humana que usa player_stats.py
# para filtrar saltos de posición imposibles — se reutiliza acá para decidir
# si el salto entre el fin de un track y el comienzo de otro es plausible
# para una misma persona (ver detectar_candidatos_fusion).
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from src.analysis.player_stats import MAX_SPEED_MS  # noqa: E402

# ── Fases de juego ───────────────────────────────────────────
# Ventana por defecto para medir la tendencia del centroide (segundos).
VENTANA_FASE_SEG_DEFAULT = 2.0

# Mínimo de jugadores de un equipo visibles en un frame para confiar en su
# centroide — con menos, un par de detecciones perdidas mueven el promedio
# más de lo que se movió el bloque real.
MIN_JUGADORES_CENTROIDE = 4

# Mínimo de detecciones de arquero para confiar en su posición promedio al
# inferir hacia dónde ataca su equipo (ver _direccion_ataque).
MIN_MUESTRAS_ARQUERO_DIRECCION = 10

# Velocidad mínima (m/s) del centroide, sostenida durante VENTANA_FASE_SEG,
# para considerar que el bloque avanza ("ataque") o retrocede ("defensa").
# Calibrado a mano sobre partido_clip2: el tramo "estable" del clip (30s)
# tiene un drift de centroide de ruido ~0.1 m/s; el único avance de bloque
# real del clip fue de ~1.1-1.7 m/s. 0.3 m/s separa limpio ruido de señal
# en ese caso concreto — con más partidos convendría revisar este número.
UMBRAL_AVANCE_MS = 0.3

# Magnitud mínima de velocidad, en ambos lados de una reversión de signo,
# para calificarla de "transición" (cambio abrupto) en vez de ruido.
UMBRAL_TRANSICION_MS = 0.3

# ── Líneas ───────────────────────────────────────────────────
# Mínimo de jugadores de un equipo, con team asignado, en un frame, para
# repartirlos en 3 líneas con algo de sentido (con menos, "tercios" da
# grupos de 0-1 jugador, una foto demasiado pobre para decir nada).
MIN_JUGADORES_LINEA = 4

# ── Patrón: desconectado ─────────────────────────────────────
# Mínimo de frames válidos (con línea y equipo asignado) para calcular la
# desviación media de un track con algo de estabilidad. 30 frames (~1s)
# resultó insuficiente en la práctica: dejaba pasar fragmentos de track
# muy cortos cuya única aparición podía coincidir con un instante atípico
# del bloque (verificado a mano sobre partido_clip2: un track de 52 frames
# salía con un exceso de 2x solo por mala suerte de timing). 150 frames
# (~5s a 30fps) filtra esos fragmentos sin perder a los jugadores reales.
MIN_FRAMES_PATRON = 150

# Mínimo de OTROS jugadores en la misma línea del equipo (excluyendo al
# candidato) para tener una mediana de referencia con sentido.
MIN_JUGADORES_LINEA_COMPARACION = 2

# Exceso relativo mínimo sobre la mediana de su línea para considerar que
# hay señal de desconexión. Se calibró a mano sobre partido_clip2: la
# desviación de profundidad DENTRO de una misma línea es una distribución
# continua y bastante amplia, no bimodal (grupos de 4-7 jugadores, sin un
# salto claro entre "normal" y "atípico") — con 0.25 quedaba marcado casi
# un tercio del plantel, incluyendo diferencias que son variación normal
# de juego, no una tendencia. 0.5 (hay que superar a su línea en un 50%
# largo) aísla un núcleo bastante más chico y estable ante cambios de
# parámetros — sigue siendo una lectura con cautela sobre un solo clip,
# no una certeza.
UMBRAL_DESCONEXION_MIN = 0.5

# Exceso relativo que se mapea a severidad máxima (1.0 = duplicar la
# distancia típica de su línea ya es severidad 1.0).
UMBRAL_SEVERIDAD_MAX_DESCONEXION = 1.0

# Duración mínima (segundos) de un tramo por-encima-del-umbral para contarlo
# como una "ocurrencia" de desconexión — descarta parpadeos de 1-2 frames.
SEGMENTO_DESCONEXION_MIN_SEG = 1.0

# Proporción mínima del tiempo en cancha que el track tiene que pasar por
# encima del umbral instantáneo para que la desconexión cuente como
# SOSTENIDA, no como tramos aislados. Se calibró contra 2 falsos positivos
# confirmados por un DT mirando el video sobre partido_clip2: un jugador
# que se abre para recibir un pase y otro que hace marca personal tenían
# proporción 0.58 y 0.59 — se despegan de su línea la mayor parte del
# partido, pero por motivos tácticamente correctos, no por desorden. Un
# umbral de "más de la mitad" (0.5) los habría dejado pasar igual; 0.70 los
# excluye con margen. Esto NO resuelve el problema de fondo (posición no
# es intención — ver LIMITACIÓN CONOCIDA en el docstring del módulo), pero
# sí exige mucha más evidencia antes de reportar algo.
PROPORCION_MIN_DESCONEXION = 0.70

# ── Patrón: no_achica ─────────────────────────────────────────
# Mínimo de fases de ataque INDEPENDIENTES que tiene que haber tenido el
# equipo en el clip (y que tiene que haber podido evaluarse en CADA
# jugador candidato — ver el chequeo por-track más abajo) para siquiera
# hablar de una tendencia. Subido de 2 a 4 tras validar contra video: con
# 2, un solo evento coincidente ya alcanzaba para "confirmar" un patrón —
# nada distingue eso de una casualidad. Con 4, hace falta que el
# comportamiento se repita en al menos 3 (ver PROPORCION_MIN_NO_ACHICA)
# de 4+ subidas realmente independientes — mucho más difícil de explicar
# por azar. Con clips de 27-45s esto en la práctica deja a la mayoría de
# los equipos (y a veces a todos) sin evaluar — es el comportamiento
# esperado, no un error: significa que no hay evidencia suficiente, y
# es preferible decir eso a inventar una tendencia de una sola subida.
MIN_FASES_ATAQUE = 4

# Proporción mínima de las subidas evaluadas (para ESE jugador puntual, no
# el total del equipo) en las que tiene que repetirse el déficit para
# reportarlo. "Más de la mitad": con MIN_FASES_ATAQUE=4, hacen falta al
# menos 3 de 4 — "1 de 4" (25%) o "2 de 4" (exactamente la mitad, no más)
# ya no alcanzan. Encontramos casos "1 de 4" reportados antes de este
# cambio que, validados contra el video, resultaron ser basculación
# normal del equipo, no una falla del jugador — de ahí la exigencia.
PROPORCION_MIN_NO_ACHICA = 0.5

# Duración mínima (segundos) de una fase de ataque para que cuente como
# una fase real y no un cruce de umbral de 1-2 frames.
SEGMENTO_ATAQUE_MIN_SEG = 1.0

# Mínimo de frames de un track DENTRO de una fase de ataque para incluirlo
# en la comparación de esa fase puntual (si el track casi no aparece en
# esa fase, su desplazamiento medido no significa nada).
MIN_FRAMES_EN_FASE = 3

# Déficit mínimo (metros, respecto al desplazamiento de su línea) durante
# una fase de ataque para contarla como ocurrencia de no_achica.
UMBRAL_NO_ACHICA_M = 3.0

# Déficit promedio (metros) que se mapea a severidad máxima.
UMBRAL_SEVERIDAD_MAX_NO_ACHICA_M = 8.0

# ── Candidatos a "mismo jugador, track distinto" ──────────────
# ByteTrack pierde la identidad de un jugador (oclusión, cruce, salir de
# cuadro) y le asigna un track_id nuevo al reaparecer — a veces incluso
# ANTES de soltar el anterior, con un instante de solapamiento (ver
# MAX_SOLAPAMIENTO_FUSION_SEG). detectar_candidatos_fusion() NO fusiona
# nada: señala pares de tracks candidatos a ser la misma persona, para
# que quien lea el resultado decida — fusionar mal (dos jugadores
# distintos mezclados en uno) es peor que no fusionar, porque contamina
# en silencio las stats de los dos y es difícil de notar después.

# Ventana máxima (segundos) entre que un track TERMINA y otro EMPIEZA
# para considerarlos candidatos — un hueco más largo que esto es más
# probable que sea una sustitución real o dos jugadores distintos que
# casualmente pasaron por zonas parecidas en momentos distintos.
MAX_GAP_FUSION_SEG = 3.0

# Solapamiento máximo (segundos) tolerado en el otro sentido — el track
# "siguiente" puede haber empezado un poco ANTES de que el "previo"
# termine (el hand-off de ByteTrack no es instantáneo). Calibrado sobre
# el caso confirmado a mano en partido_clip2 (track 21 → 74): se
# solapan 0.30s en la misma posición (13cm de diferencia) antes de que
# el tracker suelte el ID viejo.
MAX_SOLAPAMIENTO_FUSION_SEG = 1.0

# Piso de tiempo (segundos) para calcular la "velocidad necesaria" —
# evita que un gap casi nulo (el caso de solapamiento de arriba) dispare
# una velocidad absurdamente alta solo por dividir por un número casi
# cero; con un gap real de 0.30s como el de 21→74, este piso ni entra en
# juego (no lo achica), pero protege el caso límite de gap≈0.
MIN_DT_FUSION_SEG = 0.1


# ── Helpers de dirección y validación ─────────────────────────
def _validar_columnas(df: pd.DataFrame, requeridas: set, quien: str) -> None:
    faltantes = requeridas - set(df.columns)
    if faltantes:
        raise ValueError(f"{quien}: al DataFrame le faltan columnas requeridas: {sorted(faltantes)}")


def _direccion_ataque(df: pd.DataFrame) -> tuple:
    """
    Sentido de ataque de cada equipo: +1 si ataca hacia field_x creciente,
    -1 si ataca hacia field_x decreciente. Se resuelve en tres pasos, del
    más confiable al menos confiable:

      1. Por arquero propio: si el equipo tiene arquero con team asignado
         y suficientes detecciones, su posición promedio delata el arco
         que defiende (y por lo tanto hacia dónde ataca su equipo). No
         necesita al rival — funciona incluso con un solo equipo detectado.
      2. Forzado por descarte: si el OTRO equipo ya se resolvió por
         arquero propio y solo hay 2 equipos, el que falta ataca
         necesariamente para el lado contrario (solo hay 2 arcos en una
         cancha). No se re-deriva por separado — evitar que un segundo
         cálculo independiente (paso 3) alguna vez discrepe del primero
         sin que nadie se entere.
      3. Fallback por comparación entre equipos: si NINGÚN equipo tiene
         arquero confiable, se compara el field_x promedio de jugadores
         de campo entre los dos equipos (el que tenga el promedio más
         bajo defiende cerca de x=0). Es el camino menos confiable — ver
         la LIMITACIÓN CONOCIDA en el docstring del módulo.

    Asume que el clip no cruza un entretiempo (no hay cambio de lado
    dentro del mismo video) — mismo supuesto que team_assignment.py.

    Returns:
        (direccion, metodo):
          - direccion: dict {team: +1 | -1}. Puede venir incompleto (o
            vacío) si no hay información suficiente para algún equipo.
          - metodo: dict {team: "arquero" | "forzado" | "promedio"} — de
            qué paso salió cada signo. Ver _avisos_direccion() para
            convertir esto en un aviso legible cuando corresponda.
    """
    personas = df[df["class_name"].isin(("player", "goalkeeper")) & df["team"].notna()]
    if personas.empty:
        return {}, {}

    equipos = list(personas["team"].unique())
    direccion: dict = {}
    metodo: dict = {}

    # Paso 1: arquero propio, equipo por equipo — no depende del rival.
    arqueros = personas[personas["class_name"] == "goalkeeper"]
    centro_observado = df["field_x"].median()  # "mitad de cancha" según lo que se ve en ESTE clip
    for team in equipos:
        x_arq = arqueros.loc[arqueros["team"] == team, "field_x"]
        if len(x_arq) >= MIN_MUESTRAS_ARQUERO_DIRECCION:
            direccion[team] = +1 if x_arq.mean() < centro_observado else -1
            metodo[team] = "arquero"

    # Paso 2: forzado por descarte — solo tiene sentido con exactamente
    # 2 equipos y exactamente uno sin resolver.
    faltantes = [t for t in equipos if t not in direccion]
    if len(equipos) == 2 and len(faltantes) == 1 and len(direccion) == 1:
        team_faltante = faltantes[0]
        team_conocido = next(iter(direccion))
        direccion[team_faltante] = -direccion[team_conocido]
        metodo[team_faltante] = "forzado"
        faltantes = []

    # Paso 3: fallback por comparación de jugadores de campo entre equipos.
    if faltantes:
        jugadores = personas[personas["class_name"] == "player"]
        x_prom = jugadores.groupby("team")["field_x"].mean()
        if len(x_prom) >= 2:
            equipo_x0 = x_prom.idxmin()
            equipo_x105 = x_prom.idxmax()
            for team, signo in ((equipo_x0, +1), (equipo_x105, -1)):
                if team not in direccion:
                    direccion[team] = signo
                    metodo[team] = "promedio"

    return direccion, metodo


def _avisos_direccion(metodo: dict) -> list:
    """
    Traduce el `metodo` de _direccion_ataque() a avisos legibles — solo
    para el camino "promedio" (el forzado por descarte no se avisa: está
    anclado por el arquero del rival, es seguro). Ver LIMITACIÓN CONOCIDA
    en el docstring del módulo.
    """
    equipos_promedio = sorted(t for t, m in metodo.items() if m == "promedio")
    if not equipos_promedio:
        return []
    return [
        f"Dirección de ataque de {equipos_promedio} inferida por comparación de "
        f"posición promedio entre equipos — ningún equipo tuvo arquero detectado "
        f"con suficiente confianza para anclarla (ver MIN_MUESTRAS_ARQUERO_DIRECCION "
        f"en tactical_patterns.py). Es el camino menos confiable: no hay forma de "
        f"detectar sola si se equivocó. Revisar contra el video antes de confiar en "
        f"los patrones de estos equipos."
    ]


def _segmentos_contiguos(frames, tiempos, mascara, min_duracion_seg: float) -> list:
    """
    A partir de una secuencia ordenada (frames, tiempos, máscara booleana),
    devuelve los intervalos [t_inicio, t_fin] de corridas contiguas con
    máscara=True, descartando las más cortas que min_duracion_seg.

    "Contiguos" respeta huecos reales en los datos: si el paso entre dos
    frames consecutivos es mucho mayor al paso típico de la serie (un
    tramo sin datos, no un frame de por medio), se corta la corrida en vez
    de puentearla — si no, un hueco de varios segundos podría maquillarse
    como parte de un tramo largo.
    """
    frames = np.asarray(frames)
    tiempos = np.asarray(tiempos, dtype=float)
    mascara = np.asarray(mascara, dtype=bool)
    n = len(frames)
    if n == 0:
        return []
    if n == 1:
        return [(float(tiempos[0]), float(tiempos[0]))] if mascara[0] and min_duracion_seg <= 0 else []

    pasos = np.diff(frames.astype(float))
    paso_tipico = np.median(pasos) if len(pasos) else 1.0
    if paso_tipico <= 0:
        paso_tipico = 1.0
    hueco = np.concatenate([[True], pasos > paso_tipico * 1.5])
    cambio_mascara = np.concatenate([[True], mascara[1:] != mascara[:-1]])
    grupo_id = np.cumsum(hueco | cambio_mascara)

    segmentos = []
    for _, idx in pd.Series(np.arange(n)).groupby(grupo_id):
        i0, i1 = int(idx.iloc[0]), int(idx.iloc[-1])
        if not mascara[i0]:
            continue
        t_ini, t_fin = float(tiempos[i0]), float(tiempos[i1])
        if (t_fin - t_ini) >= min_duracion_seg:
            segmentos.append((t_ini, t_fin))
    return segmentos


def _calificador(severidad: float) -> str:
    """Traduce una severidad [0,1] a un adjetivo de lectura futbolística."""
    if severidad >= 0.66:
        return "marcada"
    if severidad >= 0.33:
        return "moderada"
    return "leve"


def _formatear_evidencia(segmentos: list, maximo: int = 3) -> str:
    """Los primeros `maximo` segmentos como texto 'mm:ss-mm:ss', para el CLI."""
    def mmss(seg):
        return f"{int(seg // 60)}:{seg % 60:04.1f}"

    partes = [f"{mmss(a)}-{mmss(b)}" for a, b in segmentos[:maximo]]
    extra = f" (+{len(segmentos) - maximo} más)" if len(segmentos) > maximo else ""
    return ", ".join(partes) + extra


# ── Paso 1: fases de juego ────────────────────────────────────
def detectar_fases(df: pd.DataFrame, ventana_seg: float = VENTANA_FASE_SEG_DEFAULT) -> pd.DataFrame:
    """
    Clasifica, frame a frame y por equipo, si el bloque avanza ("ataque"),
    retrocede ("defensa"), tiene un cambio brusco de sentido ("transicion")
    o no muestra una tendencia clara ("estable") — ver el docstring del
    módulo para la limitación de fondo (esto es geometría de bloque, no
    posesión de pelota).

    Se agrega una 5ta categoría, "sin_datos", para frames donde no hay
    ventana suficiente para calcular una velocidad confiable (bordes del
    clip, o tramos con menos de MIN_JUGADORES_CENTROIDE visibles) — se
    prefirió ser explícito ahí antes que forzarlos a "estable".

    Args:
        df: detecciones con frame, time_sec, class_name, team, field_x.
        ventana_seg: ventana (segundos) para medir la tendencia del centroide.

    Returns:
        DataFrame con columnas: frame, time_sec, team, centroide_x, fase.
        Vacío (mismas columnas) si no hay datos suficientes — sin lanzar
        excepción — por ejemplo con un solo equipo detectado y sin arquero
        para orientar su sentido de ataque. En `.attrs["avisos"]` queda
        registrado si la dirección de algún equipo se resolvió por el
        camino menos confiable (ver LIMITACIÓN CONOCIDA en el docstring
        del módulo) — vale la pena chequearlo incluso cuando el resultado
        no viene vacío.
    """
    _validar_columnas(df, {"frame", "time_sec", "class_name", "team", "field_x"}, "detectar_fases")

    columnas_salida = ["frame", "time_sec", "team", "centroide_x", "fase"]
    vacio = pd.DataFrame(columns=columnas_salida)
    if df.empty:
        return vacio

    personas = df[df["class_name"].isin(("player", "goalkeeper")) & df["team"].notna()]
    if personas.empty:
        return vacio

    direccion, metodo = _direccion_ataque(df)
    if not direccion:
        return vacio
    avisos = _avisos_direccion(metodo)

    tiempos_unicos = np.sort(df["time_sec"].dropna().unique())
    dt = float(np.median(np.diff(tiempos_unicos))) if tiempos_unicos.size >= 2 else 0.0
    if dt <= 0:
        return vacio
    ventana_frames = max(3, round(ventana_seg / dt))

    tiempo_por_frame = df.groupby("frame")["time_sec"].first()
    resultados = []

    for team, sub_team in personas.groupby("team"):
        if team not in direccion:
            continue

        conteo = sub_team.groupby("frame").size()
        centroide = sub_team.groupby("frame")["field_x"].mean()
        centroide = centroide[conteo >= MIN_JUGADORES_CENTROIDE].sort_index()
        if len(centroide) < ventana_frames * 2:
            continue  # muy pocos frames confiables para este equipo

        centroide_firmado = centroide * direccion[team]
        suave = centroide_firmado.rolling(
            ventana_frames, center=True, min_periods=max(3, ventana_frames // 2)
        ).median()

        desplazamiento = suave - suave.shift(ventana_frames)
        velocidad = desplazamiento / ventana_seg
        velocidad_previa = velocidad.shift(ventana_frames)

        tiene_dato = velocidad.notna()
        fase = pd.Series("sin_datos", index=suave.index, dtype=object)
        fase[tiene_dato] = "estable"
        fase[tiene_dato & (velocidad >= UMBRAL_AVANCE_MS)] = "ataque"
        fase[tiene_dato & (velocidad <= -UMBRAL_AVANCE_MS)] = "defensa"

        es_transicion = (
            velocidad.notna() & velocidad_previa.notna()
            & (np.sign(velocidad) != np.sign(velocidad_previa))
            & (velocidad.abs() > UMBRAL_TRANSICION_MS)
            & (velocidad_previa.abs() > UMBRAL_TRANSICION_MS)
        )
        fase[es_transicion] = "transicion"  # el cambio abrupto pisa a las demás categorías

        parcial = pd.DataFrame({
            "frame": centroide.index,
            "team": team,
            "centroide_x": centroide.values,
            "fase": fase.values,
        })
        parcial["time_sec"] = parcial["frame"].map(tiempo_por_frame)
        resultados.append(parcial)

    if not resultados:
        return vacio
    resultado = (
        pd.concat(resultados, ignore_index=True)[columnas_salida]
        .sort_values(["team", "frame"])
        .reset_index(drop=True)
    )
    resultado.attrs["avisos"] = avisos
    return resultado


# ── Paso 2: líneas ─────────────────────────────────────────────
def asignar_lineas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clasifica a cada jugador de campo (no arqueros) en una línea —
    "defensa" / "mediocampo" / "ataque" — según su posición relativa
    DENTRO DE SU PROPIO EQUIPO, en cada frame. No usa tercios fijos de
    cancha: un central sigue siendo central aunque su equipo esté
    empujado en campo rival — lo que importa es su rango (percentil) de
    profundidad respecto a sus compañeros en ese instante, ajustado por
    el sentido de ataque del equipo.

    Los arqueros quedan afuera de esta clasificación a propósito (no son
    una "línea" en este esquema); sus filas quedan con línea NaN, igual
    que árbitro y pelota.

    Args:
        df: detecciones con frame, track_id, class_name, team, field_x.

    Returns:
        Copia de `df` con una columna `linea` nueva (NaN donde no aplica
        o no hay suficientes compañeros ese frame para repartir en 3
        grupos con sentido — ver MIN_JUGADORES_LINEA). En
        `.attrs["avisos"]` queda registrado si la dirección de algún
        equipo se resolvió por el camino menos confiable — ver
        LIMITACIÓN CONOCIDA en el docstring del módulo.
    """
    _validar_columnas(df, {"frame", "track_id", "class_name", "team", "field_x"}, "asignar_lineas")

    resultado = df.copy()
    resultado["linea"] = pd.Series([pd.NA] * len(resultado), index=resultado.index, dtype=object)
    if resultado.empty:
        return resultado

    direccion, metodo = _direccion_ataque(resultado)
    resultado.attrs["avisos"] = _avisos_direccion(metodo)
    if not direccion:
        return resultado  # no se pudo orientar ningún equipo (ver _direccion_ataque)

    jugadores = resultado[
        (resultado["class_name"] == "player")
        & resultado["team"].notna()
        & resultado["team"].isin(direccion.keys())
    ]
    if jugadores.empty:
        return resultado

    for (frame, team), sub in jugadores.groupby(["frame", "team"]):
        if len(sub) < MIN_JUGADORES_LINEA:
            continue
        x_ajustado = sub["field_x"] * direccion[team]  # mayor = más adelantado
        rangos = x_ajustado.rank(pct=True, method="first")
        lineas = pd.cut(
            rangos, bins=[0, 1 / 3, 2 / 3, 1.0001],
            labels=["defensa", "mediocampo", "ataque"], include_lowest=True,
        )
        resultado.loc[sub.index, "linea"] = lineas.astype(object).values

    return resultado


# ── Paso 3: patrones ───────────────────────────────────────────
def _desviacion_linea_por_frame(jugadores: pd.DataFrame, direccion: dict) -> pd.Series:
    """
    Para cada jugador, en cada frame, cuánto se aparta (metros, sobre el
    eje de profundidad) del promedio de SUS COMPAÑEROS DE LÍNEA en ese
    mismo frame — centroide de la línea "leave-one-out" (sin contarse a
    sí mismo, por la misma razón que en team_assignment.py: si no, un
    jugador que se aleja arrastra un poco su propia referencia).

    Deliberadamente NO es distancia euclidiana 2D al centroide del EQUIPO
    (la primera versión probada): esa confundía "jugar ancho por rol" —
    un lateral o extremo bien plantado en la banda — con "estar
    desconectado". Verificado a mano sobre partido_clip2: los dos casos
    más "alejados" por distancia 2D eran extremos con desvío estándar de
    field_y de apenas 0.4m — posición perfectamente estable, no errática,
    simplemente ancha. Mirar solo profundidad, y dentro de la propia
    línea, evita ese sesgo: todos los de una línea ya comparten un rango
    de profundidad similar por construcción (así arma las líneas
    asignar_lineas), así que lo que sobresale acá es una diferencia de
    profundidad real dentro de esa línea, no una diferencia de banda.

    Requiere al menos 2 compañeros de línea (mismo equipo, misma línea)
    en el frame, y sentido de ataque conocido para ese equipo; si no, NaN.
    """
    resultado = pd.Series(np.nan, index=jugadores.index, dtype=float)
    for (_frame, team, _linea), sub in jugadores.groupby(["frame", "team", "linea"], observed=True):
        n = len(sub)
        if n < 2 or team not in direccion:
            continue
        x_ajustado = (sub["field_x"] * direccion[team]).to_numpy()
        x_loo = (x_ajustado.sum() - x_ajustado) / (n - 1)
        resultado.loc[sub.index] = np.abs(x_ajustado - x_loo)
    return resultado


def _detectar_desconectado(lineas: pd.DataFrame, fases: pd.DataFrame) -> tuple:
    """Implementa el patrón 'desconectado' — ver detectar_patrones()."""
    filas = []
    no_evaluados = []

    jugadores = lineas[
        (lineas["class_name"] == "player") & lineas["team"].notna() & lineas["linea"].notna()
    ].copy()
    if jugadores.empty:
        return pd.DataFrame(), ["desconectado: sin jugadores con equipo y línea asignados."]

    # Se excluyen los frames en fase "transición": ahí el bloque no se mueve
    # como un cuerpo rígido a propósito (una reversión rápida hace que unos
    # jugadores reaccionen antes que otros, sin que eso sea un problema de
    # nadie) — verificado a mano sobre partido_clip2, donde buena parte de
    # la "evidencia" de desconexión de varios jugadores DISTINTOS coincidía
    # con la única transición de fase del clip, no con un patrón individual
    # sostenido. Sin este filtro, un evento de equipo se mal-lee como una
    # característica de cada jugador por separado.
    if not fases.empty:
        fase_por_team_frame = fases.set_index(["team", "frame"])["fase"]
        claves = pd.MultiIndex.from_arrays([jugadores["team"], jugadores["frame"]])
        fase_actual = fase_por_team_frame.reindex(claves).to_numpy()
        jugadores = jugadores[fase_actual != "transicion"]
        if jugadores.empty:
            return pd.DataFrame(), ["desconectado: todos los frames disponibles caían en fase de transición."]

    direccion, _metodo = _direccion_ataque(lineas)
    jugadores["desviacion_linea"] = _desviacion_linea_por_frame(jugadores, direccion)
    jugadores = jugadores.dropna(subset=["desviacion_linea"])
    if jugadores.empty:
        return pd.DataFrame(), ["desconectado: sin sentido de ataque conocido para evaluar la profundidad."]

    # línea "predominante" de cada track: la más frecuente en sus frames.
    linea_por_track = jugadores.groupby("track_id")["linea"].agg(lambda s: s.mode().iat[0])
    team_por_track = jugadores.groupby("track_id")["team"].first()
    n_frames_por_track = jugadores.groupby("track_id")["desviacion_linea"].count()
    media_por_track = jugadores.groupby("track_id")["desviacion_linea"].mean()

    tracks_validos = n_frames_por_track[n_frames_por_track >= MIN_FRAMES_PATRON].index
    if len(tracks_validos) == 0:
        return pd.DataFrame(), [
            f"desconectado: ningún track llegó a {MIN_FRAMES_PATRON} frames válidos."
        ]

    for (team, linea), tracks_grupo in (
        pd.DataFrame({"team": team_por_track, "linea": linea_por_track})
        .loc[tracks_validos]
        .groupby(["team", "linea"])
    ):
        candidatos = tracks_grupo.index.tolist()
        if len(candidatos) < MIN_JUGADORES_LINEA_COMPARACION + 1:
            no_evaluados.append(
                f"desconectado: {team}/{linea} tiene solo {len(candidatos)} track(s) "
                f"con datos suficientes — se necesitan al menos {MIN_JUGADORES_LINEA_COMPARACION + 1}."
            )
            continue

        for track_id in candidatos:
            otros = [t for t in candidatos if t != track_id]
            mediana_referencia = media_por_track.loc[otros].median()
            valor = media_por_track.loc[track_id]
            if mediana_referencia <= 0:
                continue
            exceso_relativo = (valor - mediana_referencia) / mediana_referencia
            if exceso_relativo <= UMBRAL_DESCONEXION_MIN:
                continue

            sub_track = jugadores[jugadores["track_id"] == track_id].sort_values("frame")
            umbral_instantaneo = mediana_referencia * (1 + UMBRAL_DESCONEXION_MIN)
            segmentos = _segmentos_contiguos(
                sub_track["frame"].to_numpy(),
                sub_track["time_sec"].to_numpy(),
                (sub_track["desviacion_linea"] > umbral_instantaneo).to_numpy(),
                SEGMENTO_DESCONEXION_MIN_SEG,
            )
            if not segmentos:
                continue  # exceso en el promedio, pero sin un tramo sostenido concreto que mostrar

            # Exigir que la desviación sea SOSTENIDA, no tramos aislados que
            # coincidan con un desmarque puntual o una marca personal — ver
            # PROPORCION_MIN_DESCONEXION.
            duracion_desviado = sum(fin - ini for ini, fin in segmentos)
            duracion_en_cancha = sub_track["time_sec"].iloc[-1] - sub_track["time_sec"].iloc[0]
            proporcion_desviado = duracion_desviado / duracion_en_cancha if duracion_en_cancha > 0 else 0.0
            if proporcion_desviado <= PROPORCION_MIN_DESCONEXION:
                continue

            severidad = float(np.clip(exceso_relativo / UMBRAL_SEVERIDAD_MAX_DESCONEXION, 0.0, 1.0))
            calif = _calificador(severidad)
            filas.append({
                "track_id": track_id,
                "team": team,
                "patron": "desconectado",
                "severidad": round(severidad, 2),
                "valor_tecnico": round(valor / mediana_referencia, 2),
                "n_ocurrencias": len(segmentos),
                "evidencia_seg": segmentos,
                "descripcion": (
                    f"Tendencia {calif} a despegarse en profundidad del resto de su línea "
                    f"de forma sostenida ({proporcion_desviado:.0%} del tiempo en cancha) "
                    f"— posible desconexión del bloque. Revisar en video: puede ser un "
                    f"problema real o un movimiento correcto (desmarque, marca personal) "
                    f"que este análisis no puede distinguir por sí solo."
                ),
            })

    return pd.DataFrame(filas), no_evaluados


def _detectar_no_achica(lineas: pd.DataFrame, fases: pd.DataFrame) -> tuple:
    """Implementa el patrón 'no_achica' — ver detectar_patrones()."""
    filas = []
    no_evaluados = []

    if fases.empty:
        return pd.DataFrame(), ["no_achica: no hay fases detectadas (ver detectar_fases)."]

    direccion, _metodo = _direccion_ataque(lineas)
    jugadores = lineas[
        (lineas["class_name"] == "player") & lineas["team"].notna() & lineas["linea"].notna()
    ]
    if jugadores.empty or not direccion:
        return pd.DataFrame(), ["no_achica: sin jugadores con equipo/línea, o sin sentido de ataque definido."]

    for team, fases_team in fases.groupby("team"):
        if team not in direccion:
            continue
        fases_team = fases_team.sort_values("frame")
        segmentos_ataque = _segmentos_contiguos(
            fases_team["frame"].to_numpy(),
            fases_team["time_sec"].to_numpy(),
            (fases_team["fase"] == "ataque").to_numpy(),
            SEGMENTO_ATAQUE_MIN_SEG,
        )

        if len(segmentos_ataque) < MIN_FASES_ATAQUE:
            no_evaluados.append(
                f"no_achica: {team} tuvo {len(segmentos_ataque)} fase(s) de ataque de "
                f"{SEGMENTO_ATAQUE_MIN_SEG:.0f}s+ en el clip — se necesitan al menos "
                f"{MIN_FASES_ATAQUE} para no evaluar sobre una sola observación."
            )
            continue

        jugadores_team = jugadores[jugadores["team"] == team]
        linea_por_track = jugadores_team.groupby("track_id")["linea"].agg(lambda s: s.mode().iat[0])

        # deficit[track_id] = lista de (t_ini, t_fin, deficit_m) por fase con déficit real.
        deficit_por_track: dict = {tid: [] for tid in linea_por_track.index}
        fases_evaluadas_por_track: dict = {tid: 0 for tid in linea_por_track.index}

        for t_ini, t_fin in segmentos_ataque:
            ventana = jugadores_team[
                (jugadores_team["time_sec"] >= t_ini) & (jugadores_team["time_sec"] <= t_fin)
            ]
            if ventana.empty:
                continue

            desplazamiento = {}
            for track_id, sub in ventana.groupby("track_id"):
                if len(sub) < MIN_FRAMES_EN_FASE:
                    continue
                sub = sub.sort_values("frame")
                dx = (sub["field_x"].iloc[-1] - sub["field_x"].iloc[0]) * direccion[team]
                desplazamiento[track_id] = dx

            for track_id, dx_jugador in desplazamiento.items():
                linea = linea_por_track.get(track_id)
                pares_linea = [
                    dx for tid, dx in desplazamiento.items()
                    if tid != track_id and linea_por_track.get(tid) == linea
                ]
                if len(pares_linea) < MIN_JUGADORES_LINEA_COMPARACION:
                    continue
                fases_evaluadas_por_track[track_id] = fases_evaluadas_por_track.get(track_id, 0) + 1
                dx_linea_prom = float(np.mean(pares_linea))
                deficit = dx_linea_prom - dx_jugador
                if deficit > UMBRAL_NO_ACHICA_M:
                    deficit_por_track.setdefault(track_id, []).append((t_ini, t_fin, deficit))

        for track_id, ocurrencias in deficit_por_track.items():
            if not ocurrencias:
                continue

            total_fases = fases_evaluadas_por_track.get(track_id, 0)
            # Oportunidades mínimas PARA ESTE JUGADOR (no solo para el equipo):
            # un track puede haber estado en cancha en menos subidas que el
            # total del equipo (entró/salió del cuadro, fragmentación).
            if total_fases < MIN_FASES_ATAQUE:
                continue
            # Proporción de repetición: "1 de 4" o "2 de 4" no alcanzan — ver
            # PROPORCION_MIN_NO_ACHICA. Sin esto, una sola subida coincidente
            # (basculación normal, no una falla del jugador) ya reportaba.
            if len(ocurrencias) <= total_fases * PROPORCION_MIN_NO_ACHICA:
                continue

            segmentos = [(a, b) for a, b, _ in ocurrencias]
            deficit_prom = float(np.mean([d for _, _, d in ocurrencias]))
            severidad = float(np.clip(deficit_prom / UMBRAL_SEVERIDAD_MAX_NO_ACHICA_M, 0.0, 1.0))
            calif = _calificador(severidad)
            filas.append({
                "track_id": track_id,
                "team": team,
                "patron": "no_achica",
                "severidad": round(severidad, 2),
                "valor_tecnico": round(deficit_prom, 1),
                "n_ocurrencias": len(ocurrencias),
                "evidencia_seg": segmentos,
                "descripcion": (
                    f"Tendencia {calif} a no acompañar el avance de su línea cuando "
                    f"el equipo sube — posible falta de achique. Se repite en "
                    f"{len(ocurrencias)} de las {total_fases} subidas evaluadas "
                    f"— revisar en video antes de concluir nada, puede ser "
                    f"basculación normal del equipo."
                ),
            })

    return pd.DataFrame(filas), no_evaluados


# ── Candidatos a "mismo jugador, track distinto" ──────────────
def detectar_candidatos_fusion(df: pd.DataFrame, max_gap_seg: float = MAX_GAP_FUSION_SEG) -> pd.DataFrame:
    """
    Señala pares de track_id que, por continuidad espacio-temporal,
    PODRÍAN ser la misma persona con la identidad perdida y reasignada
    por ByteTrack — NO los fusiona. Ver la sección "Candidatos a 'mismo
    jugador, track distinto'" más arriba en este archivo para el motivo:
    fusionar mal es peor que no fusionar, así que esto se queda en avisar.

    Un par (A, B) es candidato si, TODOS a la vez:
      1. Mismo `team`.
      2. B empieza cerca en el tiempo de donde A termina: el hueco entre
         que A termina y B empieza está entre -MAX_SOLAPAMIENTO_FUSION_SEG
         (B pudo empezar un poco ANTES de que A termine — el hand-off de
         ByteTrack no es instantáneo) y +max_gap_seg (un hueco real, hasta
         donde se considera plausible que sea una pérdida de tracking y no
         una sustitución o dos jugadores distintos sin relación).
      3. El salto de posición es físicamente plausible: la distancia entre
         la última posición de A y la primera de B, dividida por el tiempo
         transcurrido (con un piso de MIN_DT_FUSION_SEG para no dividir
         por casi cero), no supera MAX_SPEED_MS — el mismo techo de
         velocidad humana que usa player_stats.py para filtrar saltos
         imposibles.

    Deliberadamente NO usa `linea` como filtro — puede ser ruidosa justo
    en el borde de un track corto (pocos frames para calcular una moda
    confiable). Si `lineas` está disponible, conviene mirar a mano la
    línea de cada candidato antes de decidir si son la misma persona.

    Args:
        df: detecciones con track_id, team, class_name, frame, time_sec,
            field_x, field_y.
        max_gap_seg: hueco máximo (segundos) para considerar candidatos.

    Returns:
        DataFrame con una fila por par candidato — track_id_previo,
        track_id_siguiente, team, gap_seg (negativo = solapamiento),
        distancia_m, velocidad_necesaria_ms. Puede haber más de un
        candidato para el mismo track de cualquiera de los dos lados; no
        se fuerza una relación 1 a 1, eso también queda para quien lo
        revise. Vacío (mismas columnas) si no hay pares candidatos o no
        hay datos suficientes.
    """
    _validar_columnas(
        df, {"track_id", "team", "class_name", "frame", "time_sec", "field_x", "field_y"},
        "detectar_candidatos_fusion",
    )

    columnas_salida = [
        "track_id_previo", "track_id_siguiente", "team",
        "gap_seg", "distancia_m", "velocidad_necesaria_ms",
    ]
    vacio = pd.DataFrame(columns=columnas_salida)
    if df.empty:
        return vacio

    personas = df[df["class_name"].isin(("player", "goalkeeper")) & df["team"].notna()]
    if personas.empty:
        return vacio

    extremos = (
        personas.sort_values("frame")
        .groupby("track_id")
        .agg(
            team=("team", "first"),
            t_ini=("time_sec", "first"), t_fin=("time_sec", "last"),
            x_ini=("field_x", "first"), x_fin=("field_x", "last"),
            y_ini=("field_y", "first"), y_fin=("field_y", "last"),
        )
    )

    filas = []
    for team, grupo in extremos.groupby("team"):
        tracks = grupo.index.tolist()
        for a in tracks:
            fin_a = grupo.loc[a, "t_fin"]
            for b in tracks:
                if a == b:
                    continue
                gap = grupo.loc[b, "t_ini"] - fin_a
                if gap < -MAX_SOLAPAMIENTO_FUSION_SEG or gap > max_gap_seg:
                    continue
                dx = grupo.loc[b, "x_ini"] - grupo.loc[a, "x_fin"]
                dy = grupo.loc[b, "y_ini"] - grupo.loc[a, "y_fin"]
                distancia = float(np.hypot(dx, dy))
                dt_efectivo = max(abs(gap), MIN_DT_FUSION_SEG)
                velocidad = distancia / dt_efectivo
                if velocidad <= MAX_SPEED_MS:
                    filas.append({
                        "track_id_previo": a,
                        "track_id_siguiente": b,
                        "team": team,
                        "gap_seg": round(float(gap), 2),
                        "distancia_m": round(distancia, 2),
                        "velocidad_necesaria_ms": round(float(velocidad), 2),
                    })

    if not filas:
        return vacio
    return (
        pd.DataFrame(filas)[columnas_salida]
        .sort_values(["track_id_previo", "gap_seg"])
        .reset_index(drop=True)
    )


def detectar_patrones(df: pd.DataFrame, fases: pd.DataFrame, lineas: pd.DataFrame) -> pd.DataFrame:
    """
    Corre los patrones implementados (desconectado, no_achica) y devuelve
    una fila por (track_id, patrón detectado) — solo para las combinaciones
    donde hubo señal real y datos suficientes para confiar en ella. Si un
    patrón no se pudo evaluar para algún equipo (datos insuficientes), no
    se inventa una fila — queda registrado en
    `resultado.attrs["patrones_no_evaluados"]` (lista de strings), para
    quien quiera saber por qué falta algo sin que rompa el flujo normal.

    `lineas` (la salida de asignar_lineas) ya es un superset de `df` — se
    reciben los tres parámetros por prolijidad de API, pero la función
    trabaja principalmente sobre `lineas` y `fases`.

    Columnas del resultado:
        track_id, team, patron, severidad (0-1), valor_tecnico (el número
        crudo detrás de la severidad — su significado depende del patrón,
        ver abajo), n_ocurrencias, evidencia_seg (lista de (t_ini, t_fin)
        en segundos — para poder llevar al usuario a ese momento del
        video), descripcion (redactada para un DT, nunca como verdad
        absoluta), posible_mismo_jugador_que (lista de otros track_id que
        detectar_candidatos_fusion() marcó como candidatos a ser la misma
        persona que este — vacía si no hay ninguno; ver esa función para
        el criterio. NO están fusionados, es solo un aviso).

        valor_tecnico por patrón:
          - desconectado: cuántas veces su desvío de profundidad respecto
            al resto de su línea fue el de un compañero típico de esa
            línea (1.8 = un 80% más que lo típico). No es distancia
            euclidiana al centroide del equipo — ver el docstring de
            _desviacion_linea_por_frame() para por qué.
          - no_achica: déficit promedio en metros respecto al
            desplazamiento de su línea, en las subidas donde se repitió.

    Devuelve un DataFrame vacío (con las columnas de arriba) si no hubo
    ninguna detección — no es un error, es el resultado normal de un
    clip sin señales claras. Además de `.attrs["patrones_no_evaluados"]`,
    deja `.attrs["avisos"]` (dirección de ataque resuelta por el camino
    menos confiable — ver LIMITACIÓN CONOCIDA del módulo) y
    `.attrs["candidatos_fusion"]` (la tabla completa de
    detectar_candidatos_fusion(), con gap/distancia/velocidad — la
    columna `posible_mismo_jugador_que` es un resumen de esto mismo).
    """
    columnas_salida = [
        "track_id", "team", "patron", "severidad", "valor_tecnico",
        "n_ocurrencias", "evidencia_seg", "descripcion", "posible_mismo_jugador_que",
    ]

    partes = []
    no_evaluados = []

    parte, msgs = _detectar_desconectado(lineas, fases)
    if not parte.empty:
        partes.append(parte)
    no_evaluados.extend(msgs)

    parte, msgs = _detectar_no_achica(lineas, fases)
    if not parte.empty:
        partes.append(parte)
    no_evaluados.extend(msgs)

    candidatos = detectar_candidatos_fusion(df)
    relacionados: dict = {}
    for fila in candidatos.itertuples(index=False):
        relacionados.setdefault(fila.track_id_previo, set()).add(fila.track_id_siguiente)
        relacionados.setdefault(fila.track_id_siguiente, set()).add(fila.track_id_previo)

    if not partes:
        resultado = pd.DataFrame(columns=columnas_salida)
    else:
        resultado = pd.concat(partes, ignore_index=True)
        resultado["posible_mismo_jugador_que"] = resultado["track_id"].map(
            lambda tid: sorted(relacionados.get(tid, []))
        )
        resultado = (
            resultado[columnas_salida]
            .sort_values("severidad", ascending=False)
            .reset_index(drop=True)
        )

    # avisos de dirección: se juntan los de fases/lineas (ya calculados ahí)
    # sin duplicar mensajes idénticos.
    avisos_vistos = dict.fromkeys(
        list(fases.attrs.get("avisos", [])) + list(lineas.attrs.get("avisos", []))
    )
    resultado.attrs["avisos"] = list(avisos_vistos)
    resultado.attrs["patrones_no_evaluados"] = no_evaluados
    resultado.attrs["candidatos_fusion"] = candidatos
    return resultado


# ── Esqueletos documentados — no implementados a propósito ────
def no_repliega(*_args, **_kwargs):
    """
    NO IMPLEMENTADO A PROPÓSITO.

    Mide la latencia de un jugador para volver a su posición esperada
    respecto a su línea cuando arranca una fase defensiva. Necesita dos
    cosas que hoy no son confiables con clips de 27-45s:

      1. Un inicio de fase defensiva bien definido — con un solo evento
         de cambio de fase por clip (ver docstring del módulo), no hay
         forma de aislar "el momento en que empezó a defender" de forma
         robusta; cualquier medición sería sobre una única observación.
      2. Un modelo de "posición esperada" al replegarse — no es un dato
         que se pueda leer directo de la trayectoria, hay que definirlo
         (¿respecto a dónde estaba su línea en el momento previo? ¿a un
         promedio histórico del equipo?), y construir ese modelo ad hoc
         para una sola observación por clip no vale la pena.

    Con partidos completos (varias fases defensivas por partido, no una),
    esto pasa a ser implementable con una base de datos real. El club se
    ofreció a aportarlos — este lugar queda marcado para cuando lleguen.
    """
    raise NotImplementedError(
        "no_repliega: requiere múltiples fases defensivas por jugador para "
        "distinguir una tendencia real de una observación puntual — no "
        "disponible con clips de 27-45s (ver el docstring de esta función "
        "y el del módulo). Pendiente de partidos completos."
    )


def cobertura_banda(*_args, **_kwargs):
    """
    NO IMPLEMENTADO A PROPÓSITO.

    Mide, para jugadores de banda, cuánto retroceden respecto al bloque en
    fase defensiva. Además de heredar la fragilidad de no_repliega (fases
    defensivas limpias, poco confiables en un clip corto), necesita una
    clasificación lateral (banda vs. central) que asignar_lineas() NO
    hace hoy — esa función solo separa por profundidad (eje X: defensa/
    mediocampo/ataque), no por banda (eje Y). Construir esa clasificación
    ad hoc para un solo patrón, sobre clips de un único evento de fase,
    daría una señal de baja confianza.

    Con partidos completos vale la pena sumar la clasificación lateral y
    retomar esto — este lugar queda marcado para cuando lleguen.
    """
    raise NotImplementedError(
        "cobertura_banda: requiere clasificación lateral (banda/central, "
        "no implementada en asignar_lineas) y fases defensivas limpias, "
        "ninguna de las dos confiable con clips de 27-45s. Pendiente de "
        "partidos completos."
    )


# ── CLI ──────────────────────────────────────────────────────
def _subidas_por_equipo(fases: pd.DataFrame) -> dict:
    """Cuántas fases de ataque de SEGMENTO_ATAQUE_MIN_SEG+ tuvo cada equipo — para el resumen del CLI."""
    resultado = {}
    if fases.empty:
        return resultado
    for team, fases_team in fases.groupby("team"):
        fases_team = fases_team.sort_values("frame")
        segmentos = _segmentos_contiguos(
            fases_team["frame"].to_numpy(), fases_team["time_sec"].to_numpy(),
            (fases_team["fase"] == "ataque").to_numpy(), SEGMENTO_ATAQUE_MIN_SEG,
        )
        resultado[team] = len(segmentos)
    return resultado


def _imprimir_resumen_sin_patrones(fases: pd.DataFrame) -> None:
    """
    Explica por qué no se reportó nada — con clips de 27-45s, este es el
    resultado ESPERABLE (ver LIMITACIÓN CONOCIDA en el docstring del
    módulo), no un fracaso del análisis.
    """
    print("No se detectaron patrones con evidencia suficiente.")
    subidas = _subidas_por_equipo(fases)
    if subidas:
        print("\nSubidas de bloque evaluadas por equipo (ver detectar_fases):")
        for team, n in sorted(subidas.items()):
            print(f"  {team}: {n} subida(s) de {SEGMENTO_ATAQUE_MIN_SEG:.0f}s+")
    print(
        f"\nPara reportar `no_achica` en un jugador hacen falta al menos "
        f"{MIN_FASES_ATAQUE} subidas evaluadas PARA ESE jugador, con el déficit "
        f"repetido en más de la mitad de ellas (no una sola coincidencia). Para "
        f"`desconectado` hace falta una desviación sostenida en más del "
        f"{PROPORCION_MIN_DESCONEXION:.0%} del tiempo que el jugador está en cancha, "
        f"no tramos aislados. Con un clip corto es normal no juntar esa evidencia — "
        f"es preferible no decir nada a inventar una tendencia."
    )


def _imprimir_patrones(patrones: pd.DataFrame) -> None:
    if patrones.empty:
        return

    for _, fila in patrones.iterrows():
        print(f"\n● track {fila.track_id} ({fila.team}) — {fila.patron}  "
              f"[severidad {fila.severidad:.2f}, {len(fila.evidencia_seg)} ocurrencia(s)]")
        print(f"  {fila.descripcion}")
        print(f"  técnico: valor_tecnico={fila.valor_tecnico}")
        print(f"  evidencia: {_formatear_evidencia(fila.evidencia_seg)}")
        if fila.posible_mismo_jugador_que:
            tracks = ", ".join(str(t) for t in fila.posible_mismo_jugador_que)
            print(f"  ⚠️  posible el mismo jugador que track(s): {tracks} "
                  f"(no fusionado — ver detectar_candidatos_fusion)")


def _imprimir_candidatos_fusion(candidatos: pd.DataFrame) -> None:
    if candidatos.empty:
        print("(sin candidatos a fusión)")
        return
    for fila in candidatos.itertuples(index=False):
        solapa = "se solapan" if fila.gap_seg < 0 else "hueco de"
        print(f"  track {fila.track_id_previo} → track {fila.track_id_siguiente} "
              f"({fila.team}): {solapa} {abs(fila.gap_seg):.2f}s, "
              f"{fila.distancia_m:.2f}m ({fila.velocidad_necesaria_ms:.2f} m/s necesarios)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analizador Táctico — Detección de patrones tácticos por jugador",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplo:
  python src/analysis/tactical_patterns.py data/outputs/partido_clip2_coords_field.parquet
        """,
    )
    parser.add_argument("parquet", type=str,
                        help="Ruta al .parquet de coordenadas — necesita columna `team` "
                             "(ver src/analysis/team_assignment.py)")
    parser.add_argument("--ventana-fase", type=float, default=VENTANA_FASE_SEG_DEFAULT,
                        help=f"Ventana (segundos) para detectar fases (default: {VENTANA_FASE_SEG_DEFAULT})")
    args = parser.parse_args()

    ruta = Path(args.parquet)
    if not ruta.exists():
        sys.exit(f"[ERROR] Parquet no encontrado: {ruta}")

    df = pd.read_parquet(ruta)
    if "team" not in df.columns:
        sys.exit(
            "[ERROR] Este parquet no tiene columna `team`. Corré primero:\n"
            f"  python src/analysis/team_assignment.py <video> {ruta}"
        )

    print(f"\n🧭 Patrones tácticos — {ruta.name}")
    print("=" * 78)

    fases = detectar_fases(df, ventana_seg=args.ventana_fase)
    print(f"Fases detectadas: {len(fases)} (frame, equipo) evaluados")
    if not fases.empty:
        print(fases["fase"].value_counts().to_string())

    lineas = asignar_lineas(df)
    n_con_linea = lineas["linea"].notna().sum()
    print(f"\nFilas con línea asignada: {n_con_linea} / {len(lineas)}")

    patrones = detectar_patrones(df, fases, lineas)

    avisos = patrones.attrs.get("avisos", [])
    if avisos:
        print("\n🚩 AVISOS — dirección de ataque resuelta por el camino menos confiable:")
        for msg in avisos:
            print(f"  - {msg}")

    print("\n" + "=" * 78)
    if patrones.empty:
        _imprimir_resumen_sin_patrones(fases)
    else:
        print("Patrones detectados:")
        _imprimir_patrones(patrones)

    print("\n" + "=" * 78)
    print("Candidatos a 'mismo jugador, track distinto' (no fusionados):")
    _imprimir_candidatos_fusion(patrones.attrs.get("candidatos_fusion", pd.DataFrame()))

    no_evaluados = patrones.attrs.get("patrones_no_evaluados", [])
    if no_evaluados:
        print("\n⚠️  Patrones no evaluados por falta de datos:")
        for msg in no_evaluados:
            print(f"  - {msg}")
