"""
Procedencia de las salidas del pipeline
=========================================
Santi (09/11/2026). Cada parquet que escribe una etapa del pipeline guarda de
dónde viene: qué script lo hizo, con qué parámetros, en qué commit del código y
con qué versiones de las librerías, y la procedencia de su entrada bajo la
clave "origen". La cadena llega hasta el SHA-256 del video original, así que se
puede demostrar qué video y qué código produjeron un resultado, y volver a
correrlo igual (surgió de un peritaje simulado; ver decisiones.md,
"Procedencia de las salidas del pipeline").

La metadata va en el esquema del parquet, bajo la clave b"analizador" (JSON),
junto a la que ya guarda pandas (b"pandas" y b"PANDAS_ATTRS"), que se conserva:
los datos y `df.attrs` quedan iguales a los de `df.to_parquet`. Un parquet
anterior a esto no tiene la clave: `leer_meta` devuelve None.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
CLAVE = b"analizador"
LIBRERIAS = ("inference", "inference-sdk", "inference-models", "supervision", "pandas", "pyarrow", "numpy")
_BLOQUE = 8 * 1024 * 1024


def sha256_archivo(path, progreso: bool = True) -> str:
    """SHA-256 del archivo, leído por bloques (los videos pesan GB)."""
    path = Path(path)
    total = path.stat().st_size
    h = hashlib.sha256()
    barra = None
    if progreso and total > 50 * 1024 * 1024:
        from tqdm import tqdm
        barra = tqdm(total=total, unit="B", unit_scale=True, desc=f"SHA-256 {path.name}")
    with open(path, "rb") as f:
        while bloque := f.read(_BLOQUE):
            h.update(bloque)
            if barra is not None:
                barra.update(len(bloque))
    if barra is not None:
        barra.close()
    return h.hexdigest()


def info_archivo(path, progreso: bool = True) -> dict:
    """Nombre, ruta relativa al repo, tamaño y SHA-256 de un archivo."""
    path = Path(path).resolve()
    try:
        ruta = str(path.relative_to(ROOT))
    except ValueError:
        ruta = str(path)
    return {"nombre": path.name, "ruta": ruta, "bytes": path.stat().st_size,
            "sha256": sha256_archivo(path, progreso)}


def info_git() -> dict:
    """Commit actual y si hay cambios sin commitear en archivos versionados
    (los archivos sin seguimiento, como los datos, no cuentan)."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    try:
        return {"commit": git("rev-parse", "HEAD"),
                "dirty": bool(git("status", "--porcelain", "--untracked-files=no"))}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def versiones_librerias() -> dict:
    out = {"python": sys.version.split()[0]}
    for nombre in LIBRERIAS:
        try:
            out[nombre] = importlib_metadata.version(nombre)
        except importlib_metadata.PackageNotFoundError:
            out[nombre] = None
    return out


def meta_base(script, parametros: dict | None = None) -> dict:
    """Lo que toda salida registra: script, parámetros, fecha UTC, código y librerías."""
    script = Path(script).resolve()
    try:
        script = script.relative_to(ROOT)
    except ValueError:
        pass
    return {
        "script": str(script),
        "fecha_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git": info_git(),
        "versiones": versiones_librerias(),
        "parametros": parametros or {},
    }


def meta_de_entrada(path) -> dict:
    """Para la clave "origen" de una salida: el archivo de entrada (con su
    SHA-256) y la procedencia que trae, o None si es anterior a esto."""
    return {"archivo": info_archivo(path, progreso=False), "procedencia": leer_meta(path)}


def escribir_parquet_con_meta(df: pd.DataFrame, path, meta: dict) -> None:
    """Como `df.to_parquet(path, index=False)`, más la metadata de procedencia
    en el esquema (clave b"analizador")."""
    table = pa.Table.from_pandas(df, preserve_index=False)
    md = dict(table.schema.metadata or {})
    if df.attrs:   # lo mismo que hace pandas en to_parquet, para que read_parquet devuelva los attrs
        md[b"PANDAS_ATTRS"] = json.dumps(df.attrs).encode()
    md[CLAVE] = json.dumps(meta, ensure_ascii=False, default=str).encode()
    pq.write_table(table.replace_schema_metadata(md), path)


def leer_meta(path) -> dict | None:
    """La procedencia guardada en el parquet, o None si no tiene."""
    md = pq.read_schema(path).metadata or {}
    return json.loads(md[CLAVE]) if CLAVE in md else None
