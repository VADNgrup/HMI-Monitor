import threading
from datetime import timedelta
from pathlib import Path

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Body
from fastapi.responses import FileResponse

from cores.dbconnection.mongo import get_db
from cores.pipeline import (
    backfill_old_data,
    create_source,
    get_queue_stats,
    get_screen_preview,
    get_source_or_none,
    get_timeseries,
    latest_snapshots,
    list_entities,
    list_logs,
    list_screens,
    process_single_snapshot,
    serialize_source,
)
from cores.schemas import SourceCreate, SourceUpdate
from utils.common import now_utc
from cores.helpers.helpers_basic_crud import crud

router = APIRouter(prefix="/api", tags=["kvm-ocr"])


@router.get("/kvm-sources")
def list_sources():
    db = get_db()
    sources = list(db.kvm_sources.find().sort("_id", 1))
    return [serialize_source(src) for src in sources]


@router.post("/kvm-sources")
def create_kvm_source(payload: SourceCreate):
    db = get_db()
    source_id = create_source(db, payload.model_dump())
    return {"id": source_id}


@router.patch("/kvm-sources/{source_id}/toggle")
def toggle_source(source_id: str, enabled: bool):
    db = get_db()
    source = get_source_or_none(db, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    update: dict = {"enabled": enabled, "updated_at": now_utc()}
    # When enabling, reset last_polled_at so the poll loop picks it up immediately
    if enabled:
        update["last_polled_at"] = None
    db.kvm_sources.update_one({"_id": source["_id"]}, {"$set": update})
    updated = db.kvm_sources.find_one({"_id": source["_id"]})
    return serialize_source(updated)


@router.put("/kvm-sources/{source_id}")
def update_kvm_source(source_id: str, payload: SourceUpdate):
    db = get_db()
    source = get_source_or_none(db, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    update_fields = payload.model_dump(exclude_none=True)
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    update_fields["updated_at"] = now_utc()
    db.kvm_sources.update_one({"_id": source["_id"]}, {"$set": update_fields})
    updated = db.kvm_sources.find_one({"_id": source["_id"]})
    return serialize_source(updated)


@router.delete("/kvm-sources/{source_id}")
def delete_kvm_source(source_id: str):
    db = get_db()
    source = get_source_or_none(db, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    db.kvm_sources.delete_one({"_id": source["_id"]})
    return {"ok": True}


def _run_once_worker(source_id_str: str):
    """Runs in a background thread so the API returns instantly."""
    from bson import ObjectId
    db = get_db()
    source = db.kvm_sources.find_one({"_id": ObjectId(source_id_str)})
    if not source:
        return
    for monitor_key in source.get("monitor_keys") or ["default"]:
        try:
            process_single_snapshot(db, source, monitor_key)
        except Exception:
            pass
    db.kvm_sources.update_one(
        {"_id": source["_id"]},
        {"$set": {"last_polled_at": now_utc(), "updated_at": now_utc()}},
    )


@router.post("/kvm-sources/{source_id}/run-once")
def run_once(source_id: str, bg: BackgroundTasks):
    db = get_db()
    source = get_source_or_none(db, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    bg.add_task(_run_once_worker, source_id)
    return {"ok": True, "detail": "Snapshot job queued in background."}


@router.get("/screens")
def get_screens(source_id: str):
    db = get_db()
    source = get_source_or_none(db, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return list_screens(db, source_id)


@router.get("/screens/{screen_group_id}/preview")
def screen_preview(screen_group_id: str):
    """Return latest snapshot info + image url for the screen group."""
    db = get_db()
    preview = get_screen_preview(db, screen_group_id)
    if not preview:
        raise HTTPException(status_code=404, detail="No snapshots for this screen")
    return preview


@router.get("/entities")
def get_entities(screen_group_id: str):
    """List entities for a screen group, including their metrics summary."""
    db = get_db()
    return list_entities(db, screen_group_id)


@router.get("/snapshots/{snapshot_id}/image")
def get_snapshot_image(snapshot_id: str):
    """Serve the raw PNG snapshot image."""
    db = get_db()
    try:
        snap = db.snapshots.find_one({"_id": ObjectId(snapshot_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid snapshot id")
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    path = snap.get("image_path")
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="Snapshot image file missing")
    return FileResponse(path, media_type="image/png")


@router.post("/screens/{screen_id}/toggle-ignore")
def toggle_screen_ignore(screen_id: str, payload: dict = Body(...)):
    db = get_db()
    ignored = payload.get("ignored", False)
    try:
        oid = ObjectId(screen_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid screen id")
    
    db.screen_groups.update_one(
        {"_id": oid},
        {"$set": {"ignored": bool(ignored), "updated_at": now_utc()}}
    )
    return {"ok": True, "ignored": ignored}


@router.get("/logs")
def get_logs(
    screen_group_id: str,
    hours: int = Query(default=24, ge=1, le=168),
    entity_ids: str | None = Query(default=None, description="Comma-separated entity IDs"),
    limit: int = Query(default=500, ge=1, le=5000),
):
    db = get_db()
    since = now_utc() - timedelta(hours=hours)
    eids = [eid.strip() for eid in entity_ids.split(",") if eid.strip()] if entity_ids else None
    return list_logs(db, screen_group_id=screen_group_id, since=since, entity_ids=eids, limit=limit)


@router.get("/timeseries")
def timeseries(
    screen_group_id: str,
    hours: int = Query(default=24, ge=1, le=168),
    entity_ids: str | None = Query(default=None, description="Comma-separated entity IDs"),
):
    db = get_db()
    since = now_utc() - timedelta(hours=max(1, min(168, hours)))
    eids = [eid.strip() for eid in entity_ids.split(",") if eid.strip()] if entity_ids else None
    return get_timeseries(db, screen_group_id=screen_group_id, since=since, entity_ids=eids)


@router.get("/snapshots/latest")
def get_latest_snapshots(source_id: str, limit: int = Query(default=20, ge=1, le=100)):
    db = get_db()
    source = get_source_or_none(db, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return latest_snapshots(db, source_id=source_id, limit=limit)


@router.delete("/entities/{entity_id}")
def delete_entity(entity_id: str):
    db = get_db()
    try:
        oid = ObjectId(entity_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid entity id")
    db.screen_entities.delete_one({"_id": oid})
    # Also delete logs for this entity
    db.entity_logs.delete_many({"entity_id": oid})
    return {"ok": True}


@router.post("/entities/batch-delete")
def batch_delete_entities(payload: dict = Body(...)):
    db = get_db()
    entity_ids = payload.get("entity_ids", [])
    if not isinstance(entity_ids, list):
        raise HTTPException(status_code=400, detail="entity_ids must be a list")
    
    oids = []
    for eid in entity_ids:
        try:
            oids.append(ObjectId(eid))
        except Exception:
            continue
    if not oids:
        return {"ok": True, "deleted": 0}

    res_entities = db.screen_entities.delete_many({"_id": {"$in": oids}})
    db.entity_logs.delete_many({"entity_id": {"$in": oids}})
    return {"ok": True, "deleted": res_entities.deleted_count}


@router.get("/queue")
def get_queue():
    db = get_db()
    return get_queue_stats(db)


@router.post("/backfill")
def run_backfill():
    """Migrate old entity_logs/screen_entities to the new metrics schema."""
    db = get_db()
    stats = backfill_old_data(db)
    return {"ok": True, **stats}


@router.post("/entities")
def create_entity(payload: dict = Body(...)):
    db = get_db()
    group_id = payload.get("screen_group_id")
    if not group_id:
        raise HTTPException(400, "Missing screen_group_id")
    entity = {
        "screen_group_id": ObjectId(group_id),
        "entity_key": payload.get("display_name"),
        "display_name": payload.get("display_name"),
        "entity_type": payload.get("entity_type", "sensor"),
        "region": payload.get("region", "center"),
        "metrics": payload.get("metrics", {}),
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "last_seen_at": now_utc()
    }
    entity["_id"] = crud.insert_one(db, "screen_entities", entity)
    entity["screen_group_id"] = str(entity["screen_group_id"])
    return entity

@router.put("/entities/{entity_id}")
def update_entity(entity_id: str, payload: dict = Body(...)):
    db = get_db()
    update_data = {
        "display_name": payload.get("display_name"),
        "entity_type": payload.get("entity_type"),
        "region": payload.get("region", "center"),
        "metrics": payload.get("metrics", {}),
        "updated_at": now_utc()
    }
    crud.update_by_id(db, "screen_entities", entity_id, update_data)
    schema = crud.find_by_id(db, "screen_entities", entity_id)
    schema["_id"] = str(schema["_id"])
    schema["screen_group_id"] = str(schema["screen_group_id"])
    return {"ok": True, "entity": schema}

@router.delete("/entities/{entity_id}")
def delete_entity(entity_id: str):
    db = get_db()
    crud.delete_by_id(db, "screen_entities", entity_id)
    db.entity_logs.delete_many({"entity_id": ObjectId(entity_id)})
    return {"ok": True}
