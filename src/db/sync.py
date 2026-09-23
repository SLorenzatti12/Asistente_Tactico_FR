"""
Sync SQLite local → Supabase — Nico
=====================================
Una sola dirección (local → nube), manual, pensado para correr cuando hay
conexión a internet (después del partido, en el club, en casa) — NO se
ejecuta automáticamente ni es requisito para tagear/calificar en cancha.

Sincroniza tres cosas, en este orden:

  1. Plantel de cada equipo (mirror completo — ver sync_roster_for_team).
  2. Video del partido, si hay uno registrado sin subir (archivo real, a
     un bucket privado de Supabase Storage).
  3. Eventos y calificaciones de semáforo del partido.

Uso: ver scripts/sync_to_cloud.py (CLI). Programáticamente:

    from db.sync import sync_match, sync_all
    resumen = sync_match("belgrano_vs_rival_2026-09-14")
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from . import local as loc
from . import roster_repo, team_repo, video_repo
from .supabase_client import get_client

# Mapeo directo de rating local -> check constraint de player_ratings.rating
_VALID_RATINGS = {"bajo", "regular", "destacado"}

# Bucket de Supabase Storage donde se suben los videos crudos — PRIVADO
# (Dashboard → Storage → New bucket, "Public bucket" desactivado). Hay que
# crearlo a mano una sola vez por proyecto de Supabase — ver
# docs/context/8-base-de-datos-hibrida.md.
_VIDEO_BUCKET = "match-videos"


def _get_or_create_match(client, match_name: str, team_id: str | None = None) -> str:
    """Busca la fila de `matches` por local_key; si no existe, la crea con
    los datos mínimos. Devuelve el id (uuid) de la fila en Supabase."""
    res = client.table("matches").select("id").eq("local_key", match_name).execute()
    if res.data:
        match_id = res.data[0]["id"]
        if team_id:
            client.table("matches").update({"team_id": team_id}).eq("id", match_id).execute()
        return match_id

    insert_res = (
        client.table("matches")
        .insert({"local_key": match_name, "status": "processed", "team_id": team_id})
        .execute()
    )
    return insert_res.data[0]["id"]


def _get_or_create_team(client, team_name: str) -> str:
    """Busca la fila de `teams` por nombre; si no existe, la crea."""
    res = client.table("teams").select("id").eq("name", team_name).execute()
    if res.data:
        return res.data[0]["id"]

    insert_res = client.table("teams").insert({"name": team_name}).execute()
    return insert_res.data[0]["id"]


def sync_roster_for_team(client, team: dict) -> dict:
    """Sincroniza el plantel local de un equipo como un mirror completo:
    sube (upsert) los jugadores vigentes y BORRA en la nube los que ya no
    están en la lista local (bajas físicas locales se replican como bajas
    físicas en la nube). No hay tracking incremental fila por fila porque
    el plantel es chico (~20-30 jugadores) — resincronizar todo es barato
    y así una baja no necesita un mecanismo aparte de "pendiente de borrar".
    """
    team_id_cloud = _get_or_create_team(client, team["name"])

    jugadores = roster_repo.list_players_raw(team["id"])
    local_ids_vigentes = set()
    for p in jugadores:
        row = {
            "team_id": team_id_cloud,
            "local_id": p["id"],
            "jersey_number": p["jersey_number"],
            "full_name": p["full_name"],
            "active": True,
        }
        client.table("players").upsert(row, on_conflict="team_id,local_id").execute()
        local_ids_vigentes.add(p["id"])

    existentes = (
        client.table("players").select("id,local_id").eq("team_id", team_id_cloud).execute()
    )
    a_borrar = [
        row["id"] for row in existentes.data
        if row["local_id"] is not None and row["local_id"] not in local_ids_vigentes
    ]
    if a_borrar:
        client.table("players").delete().in_("id", a_borrar).execute()

    return {"jugadores_subidos": len(local_ids_vigentes), "jugadores_borrados": len(a_borrar)}


def sync_all_rosters() -> dict[str, dict]:
    """Sincroniza el plantel de todos los equipos locales."""
    team_repo.init_teams_table()
    roster_repo.init_roster_table()
    client = get_client()
    return {team["name"]: sync_roster_for_team(client, team) for team in team_repo.list_teams()}


def _upload_video(client, match_name: str, local_path: str) -> str:
    """Sube el archivo de video al bucket privado de Supabase Storage y
    devuelve el path del objeto dentro del bucket (NO una URL pública —
    el bucket es privado; reproducirlo desde otro lado requiere generar
    un signed URL en el momento, eso queda fuera de este script)."""
    path = Path(local_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encuentra el video: {local_path}")

    storage_path = f"{match_name}/{path.name}"
    client.storage.from_(_VIDEO_BUCKET).upload(
        storage_path,
        path.read_bytes(),
        {"content-type": "video/mp4", "upsert": "true"},
    )
    return storage_path


def sync_match(match_name: str) -> dict:
    """Sincroniza el video, los eventos y las calificaciones de un
    partido puntual.

    Devuelve un resumen: {"video_subido": bool, "events_subidos": N,
    "ratings_subidos": M}.
    """
    loc.ensure_sync_columns()
    client = get_client()

    equipo_local = team_repo.get_match_team(match_name)
    team_id_cloud = _get_or_create_team(client, equipo_local["team_name"]) if equipo_local else None
    match_id = _get_or_create_match(client, match_name, team_id_cloud)
    now_iso = datetime.now(timezone.utc).isoformat()

    # ── Video ────────────────────────────────────────────────────────
    video_subido = False
    video_row = video_repo.get_video(match_name)
    if video_row and not video_row["synced_at"]:
        storage_path = _upload_video(client, match_name, video_row["local_path"])
        client.table("match_videos").upsert(
            {"match_id": match_id, "local_id": video_row["id"], "storage_url": storage_path},
            on_conflict="match_id,local_id",
        ).execute()
        video_repo.mark_synced(match_name, storage_path, now_iso)
        video_subido = True

    # ── Eventos ──────────────────────────────────────────────────────
    pending_events = loc.get_unsynced_events(match_name)
    synced_event_ids = []
    for ev in pending_events:
        row = {
            "match_id": match_id,
            "local_id": ev["id"],
            "tag_type": ev["tag_type"],
            "time_sec": ev["time_sec"],
            "team_side": ev.get("team"),
        }
        # upsert por (match_id, local_id) para poder re-correr el sync sin
        # duplicar si algo falla a mitad de camino.
        client.table("events").upsert(row, on_conflict="match_id,local_id").execute()
        synced_event_ids.append(ev["id"])
    loc.mark_events_synced(synced_event_ids, now_iso)

    # ── Semáforo / calificaciones ────────────────────────────────────
    pending_ratings = loc.get_unsynced_ratings(match_name)
    synced_rating_ids = []
    for rating in pending_ratings:
        if rating["rating"] not in _VALID_RATINGS:
            continue  # dato corrupto/legacy — no lo sube, no lo marca sincronizado
        row = {
            "match_id": match_id,
            "local_id": rating["id"],
            "player_number": rating["player_number"],
            "rating": rating["rating"],
        }
        client.table("player_ratings").upsert(row, on_conflict="match_id,local_id").execute()
        synced_rating_ids.append(rating["id"])
    loc.mark_ratings_synced(synced_rating_ids, now_iso)

    return {
        "video_subido": video_subido,
        "events_subidos": len(synced_event_ids),
        "ratings_subidos": len(synced_rating_ids),
    }


def sync_all() -> dict:
    """Sincroniza el plantel de todos los equipos y todos los partidos
    con datos locales."""
    resumen = {"plantel": sync_all_rosters()}
    for match_name in loc.list_match_names():
        resumen[match_name] = sync_match(match_name)
    return resumen
