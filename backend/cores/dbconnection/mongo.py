from __future__ import annotations

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database

from cores.config import DB_ACC, DB_HTTP, DB_NAME, DB_PAS, DB_PORT


def _build_mongo_uri() -> str:
    if DB_ACC and DB_PAS:
        return f"mongodb://{DB_ACC}:{DB_PAS}@{DB_HTTP}:{DB_PORT}/{DB_NAME}?authSource=admin"
    return f"mongodb://{DB_HTTP}:{DB_PORT}/{DB_NAME}"


MONGO_URI = _build_mongo_uri()
client = MongoClient(MONGO_URI, tz_aware=True)


def get_db() -> Database:
    return client[DB_NAME]


def ensure_indexes(db: Database):
    db.app_config.create_index([("_key", ASCENDING)], unique=True)

    db.kvm_sources.create_index([("name", ASCENDING)])
    db.kvm_sources.create_index([("enabled", ASCENDING)])

    db.screen_groups.create_index([("source_id", ASCENDING), ("monitor_key", ASCENDING)])
    db.screen_groups.create_index([("source_id", ASCENDING), ("name", ASCENDING)])

    db.snapshots.create_index([("source_id", ASCENDING), ("monitor_key", ASCENDING), ("created_at", DESCENDING)])
    db.snapshots.create_index([("source_id", ASCENDING), ("monitor_key", ASCENDING), ("image_hash", ASCENDING)])
    db.snapshots.create_index([("screen_group_id", ASCENDING), ("created_at", DESCENDING)])

    db.screen_entities.create_index([("screen_group_id", ASCENDING), ("entity_key", ASCENDING)], unique=True)
    db.screen_entities.create_index([("screen_group_id", ASCENDING), ("display_name", ASCENDING)])

    db.entity_logs.create_index([("entity_id", ASCENDING), ("recorded_at", DESCENDING)])
    db.entity_logs.create_index([("entity_id", ASCENDING), ("metric", ASCENDING), ("recorded_at", DESCENDING)])
    db.entity_logs.create_index([("entity_id", ASCENDING), ("value_type", ASCENDING), ("recorded_at", DESCENDING)])
    db.entity_logs.create_index([("snapshot_id", ASCENDING)])

    db.snapshot_jobs.create_index([("status", ASCENDING)])
    db.snapshot_jobs.create_index([("created_at", DESCENDING)])
    db.snapshot_jobs.create_index([("updated_at", DESCENDING)])
