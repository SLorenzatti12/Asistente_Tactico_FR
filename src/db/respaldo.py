"""
Respaldo y restauración de los datos que no se pueden regenerar
=================================================================
Santi. Un respaldo es una carpeta `respaldo_AAAAMMDD-HHMMSS/` con:

- `analizador.sqlite` — copia de la base local, hecha con la API de backup
  de SQLite (copia consistente aunque el dashboard esté abierto): usuarios,
  registro de accesos, eventos tagueados, semáforo, plantel, equipos,
  estadios, partidos.
- `calibracion/` — los JSON de `data/calibracion/` y los de
  `data/outputs/` (calibraciones, puntos, verificación de cámara): rehacerlos
  es trabajo manual.
- `outputs/` — los parquets de coordenadas (`*_coords.parquet` y
  `*_coords_field.parquet`, unos MB por partido): rehacerlos lleva ~80 min de
  inferencia por partido de 90 min.
- `manifiesto.json` — fecha, motivo, filas por tabla y SHA-256 de cada
  archivo, para verificar el respaldo antes de restaurarlo.

Los videos quedan afuera (cientos de MB, y el original lo tiene el club).

Dónde: por defecto `data/respaldos/` (misma laptop: protege de un error, de
un archivo corrupto o de una base borrada, no de perder el disco). Para
guardarlo en otro lugar, `--destino` en scripts/respaldo.py o la variable
de entorno ANALIZADOR_DIR_RESPALDOS (p.ej. un pendrive o una carpeta
sincronizada).

Automático: al ingresar al dashboard, si el último respaldo de la carpeta
por defecto tiene más de RESPALDO_CADA_HORAS, se hace otro; se conservan
los últimos CONSERVAR.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from src.db import registro_repo

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "db" / "analizador.sqlite"
DIR_CALIBRACION = ROOT / "data" / "calibracion"
DIR_OUTPUTS = ROOT / "data" / "outputs"

RESPALDO_CADA_HORAS = 24
CONSERVAR = 14
_PREFIJO = "respaldo_"
_FORMATO = "%Y%m%d-%H%M%S"


def dir_respaldos() -> Path:
    return Path(os.environ.get("ANALIZADOR_DIR_RESPALDOS") or ROOT / "data" / "respaldos")


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _filas_por_tabla(ruta_db: Path) -> dict[str, int]:
    conn = sqlite3.connect(f"file:{ruta_db}?mode=ro", uri=True)
    try:
        tablas = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        # Los nombres salen de sqlite_master, no de un dato del usuario.
        return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tablas}
    finally:
        conn.close()


def _integridad(ruta_db: Path) -> str:
    conn = sqlite3.connect(f"file:{ruta_db}?mode=ro", uri=True)
    try:
        return conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()


def _copiar_base(origen: Path, destino: Path) -> None:
    """Copia consistente con la API de backup de SQLite (no un cp del archivo:
    si la base se está escribiendo, un cp puede quedar a medias)."""
    src = sqlite3.connect(origen)
    dst = sqlite3.connect(destino)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _archivos_a_respaldar() -> list[tuple[Path, str]]:
    """(archivo de origen, ruta dentro del respaldo)."""
    archivos = []
    if DIR_CALIBRACION.exists():
        archivos += [(p, f"calibracion/{p.relative_to(DIR_CALIBRACION)}")
                     for p in sorted(DIR_CALIBRACION.rglob("*.json"))]
    if DIR_OUTPUTS.exists():
        archivos += [(p, f"calibracion/outputs/{p.name}") for p in sorted(DIR_OUTPUTS.glob("*.json"))]
        archivos += [(p, f"outputs/{p.name}") for p in sorted(DIR_OUTPUTS.glob("*_coords.parquet"))]
        archivos += [(p, f"outputs/{p.name}") for p in sorted(DIR_OUTPUTS.glob("*_coords_field.parquet"))]
    return archivos


def crear_respaldo(destino: Path | None = None, motivo: str = "manual",
                   actor: dict | str | None = None) -> Path:
    """Crea un respaldo y lo verifica. Devuelve la carpeta creada."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No existe la base {DB_PATH}")
    base = Path(destino) if destino else dir_respaldos()
    base.mkdir(parents=True, exist_ok=True)
    carpeta = base / f"{_PREFIJO}{datetime.now().strftime(_FORMATO)}"
    n = 1
    while carpeta.exists():   # dos respaldos en el mismo segundo
        carpeta = base / f"{_PREFIJO}{datetime.now().strftime(_FORMATO)}_{n}"
        n += 1
    temporal = carpeta.with_name(carpeta.name + ".incompleto")
    temporal.mkdir()
    try:
        _copiar_base(DB_PATH, temporal / "analizador.sqlite")
        manifiesto = {
            "fecha": datetime.now().isoformat(timespec="seconds"),
            "motivo": motivo,
            "origen": str(ROOT),
            "tablas": _filas_por_tabla(temporal / "analizador.sqlite"),
            "archivos": {},
        }
        for origen, rel in _archivos_a_respaldar():
            destino_archivo = temporal / rel
            destino_archivo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origen, destino_archivo)
        for archivo in sorted(temporal.rglob("*")):
            if archivo.is_file():
                manifiesto["archivos"][archivo.relative_to(temporal).as_posix()] = {
                    "sha256": _sha256(archivo), "bytes": archivo.stat().st_size}
        (temporal / "manifiesto.json").write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False))
        problemas = verificar_respaldo(temporal)
        if problemas:
            raise RuntimeError("El respaldo recién creado no verifica: " + "; ".join(problemas))
        # Recién completo y verificado toma su nombre final: una carpeta
        # "respaldo_..." nunca queda a medias.
        temporal.rename(carpeta)
    except BaseException:
        shutil.rmtree(temporal, ignore_errors=True)
        raise
    registro_repo.registrar("respaldo_creado", actor, objetivo=carpeta.name,
                            detalle=f"{motivo} · {carpeta.parent}")
    return carpeta


def verificar_respaldo(carpeta: Path) -> list[str]:
    """Lista de problemas (vacía si el respaldo está bien): archivos que
    faltan o cambiaron, base corrupta o con otras filas que las anotadas."""
    carpeta = Path(carpeta)
    ruta_manifiesto = carpeta / "manifiesto.json"
    if not ruta_manifiesto.exists():
        return ["no tiene manifiesto.json"]
    manifiesto = json.loads(ruta_manifiesto.read_text())
    problemas = []
    for rel, info in manifiesto["archivos"].items():
        archivo = carpeta / rel
        if not archivo.exists():
            problemas.append(f"falta {rel}")
        elif _sha256(archivo) != info["sha256"]:
            problemas.append(f"{rel} cambió (SHA-256 distinto)")
    base = carpeta / "analizador.sqlite"
    if base.exists():
        integridad = _integridad(base)
        if integridad != "ok":
            problemas.append(f"la base no pasa integrity_check: {integridad}")
        elif _filas_por_tabla(base) != manifiesto["tablas"]:
            problemas.append("la base tiene otras filas que las anotadas en el manifiesto")
    else:
        problemas.append("falta analizador.sqlite")
    return problemas


def listar_respaldos(base: Path | None = None) -> list[Path]:
    """Respaldos completos de la carpeta, del más viejo al más nuevo."""
    base = Path(base) if base else dir_respaldos()
    if not base.exists():
        return []
    return sorted(p for p in base.iterdir()
                  if p.is_dir() and p.name.startswith(_PREFIJO) and not p.name.endswith(".incompleto"))


def restaurar(carpeta: Path, con_archivos: bool = False, actor: dict | str | None = None) -> Path:
    """Vuelve la base (y, con `con_archivos`, las calibraciones y los
    parquets) al estado del respaldo. Antes verifica el respaldo y hace uno
    del estado actual, para poder deshacer. Devuelve ese respaldo previo."""
    carpeta = Path(carpeta)
    problemas = verificar_respaldo(carpeta)
    if problemas:
        raise RuntimeError("El respaldo no verifica, no se restaura: " + "; ".join(problemas))
    previo = crear_respaldo(motivo=f"antes de restaurar {carpeta.name}", actor=actor)
    # La API de backup escribe sobre la base viva de forma consistente.
    _copiar_base(carpeta / "analizador.sqlite", DB_PATH)
    if con_archivos:
        for rel in json.loads((carpeta / "manifiesto.json").read_text())["archivos"]:
            if rel.startswith("calibracion/outputs/"):
                destino = DIR_OUTPUTS / Path(rel).name
            elif rel.startswith("calibracion/"):
                destino = DIR_CALIBRACION / rel.removeprefix("calibracion/")
            elif rel.startswith("outputs/"):
                destino = DIR_OUTPUTS / Path(rel).name
            else:
                continue
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(carpeta / rel, destino)
    registro_repo.registrar("respaldo_restaurado", actor, objetivo=carpeta.name,
                            detalle="base y archivos" if con_archivos else "solo la base")
    return previo


def podar(base: Path | None = None, conservar: int = CONSERVAR) -> list[Path]:
    """Borra los respaldos más viejos de la carpeta, dejando los últimos
    `conservar`. Devuelve los borrados."""
    respaldos = listar_respaldos(base)
    viejos = respaldos[:-conservar] if conservar > 0 else respaldos
    for p in viejos:
        shutil.rmtree(p)
    return viejos


def respaldo_si_corresponde() -> Path | None:
    """El respaldo automático: si el último de la carpeta por defecto tiene
    más de RESPALDO_CADA_HORAS (o no hay ninguno), hace uno y poda."""
    if not DB_PATH.exists():
        return None
    existentes = listar_respaldos()
    if existentes:
        ultimo = datetime.strptime(existentes[-1].name.removeprefix(_PREFIJO)[:15], _FORMATO)
        if datetime.now() - ultimo < timedelta(hours=RESPALDO_CADA_HORAS):
            return None
    carpeta = crear_respaldo(motivo="automático al ingresar", actor="sistema")
    podar()
    return carpeta
