"""
Mongo-backed caches with an in-memory TTL fallback when MONGO_URI is unset.
Collections: key_health, decomposition_cache, expansion_cache.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Optional

logger = logging.getLogger("mongo_store")

MONGO_URI = os.getenv("MONGO_URI", "").strip()
MONGO_DB = os.getenv("MONGO_DB", "ip_shakti")

_lock = threading.Lock()
_memory: dict[str, dict[str, tuple[float, Any]]] = {
    "key_health": {},
    "decomposition_cache": {},
    "expansion_cache": {},
}

_client = None
_db = None


def _get_db():
    global _client, _db
    if not MONGO_URI:
        return None
    if _db is not None:
        return _db
    try:
        from pymongo import MongoClient
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        _client.admin.command("ping")
        _db = _client[MONGO_DB]
        _db["decomposition_cache"].create_index("expires_at", expireAfterSeconds=0)
        _db["expansion_cache"].create_index("expires_at", expireAfterSeconds=0)
        logger.info("Connected to MongoDB at %s", MONGO_URI.split("@")[-1])
        return _db
    except Exception as e:
        logger.warning("Mongo unavailable (%s); using in-memory TTL cache", e)
        _db = None
        return None


def _mem_get(coll: str, key: str) -> Optional[Any]:
    with _lock:
        row = _memory.get(coll, {}).get(key)
        if not row:
            return None
        expires, value = row
        if expires and expires < time.time():
            _memory[coll].pop(key, None)
            return None
        return value


def _mem_set(coll: str, key: str, value: Any, ttl_s: Optional[int]) -> None:
    expires = (time.time() + ttl_s) if ttl_s else 0.0
    with _lock:
        _memory.setdefault(coll, {})[key] = (expires, value)


def cache_get(collection: str, key: str) -> Optional[Any]:
    db = _get_db()
    if db is None:
        return _mem_get(collection, key)
    try:
        doc = db[collection].find_one({"_id": key})
        if not doc:
            return None
        return doc.get("value")
    except Exception as e:
        logger.warning("Mongo get failed: %s", e)
        return _mem_get(collection, key)


def cache_set(collection: str, key: str, value: Any, ttl_s: Optional[int] = None) -> None:
    import datetime
    db = _get_db()
    if db is None:
        _mem_set(collection, key, value, ttl_s)
        return
    try:
        doc: dict[str, Any] = {"_id": key, "value": value}
        if ttl_s:
            doc["expires_at"] = datetime.datetime.utcnow() + datetime.timedelta(seconds=ttl_s)
        db[collection].replace_one({"_id": key}, doc, upsert=True)
    except Exception as e:
        logger.warning("Mongo set failed: %s", e)
        _mem_set(collection, key, value, ttl_s)


def upsert_key_health(key_id: str, payload: dict) -> None:
    cache_set("key_health", key_id, payload, ttl_s=None)
    db = _get_db()
    if db is None:
        return
    try:
        db["key_health"].replace_one({"_id": key_id}, {"_id": key_id, **payload}, upsert=True)
    except Exception as e:
        logger.warning("key_health persist failed: %s", e)
