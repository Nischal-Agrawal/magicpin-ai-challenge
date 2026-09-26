"""Unified context store with in-memory caching and SQLite persistence."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from app.storage import Storage

class ContextStore:
    def __init__(self, storage: Storage):
        self.storage = storage
        self._cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._seed_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._load_from_storage()
        self._load_seeds_if_available()

    def _load_seeds_if_available(self) -> None:
        import json
        from pathlib import Path
        root = Path("dataset")
        cust_path = root / "customers_seed.json"
        if cust_path.exists():
            try:
                with open(cust_path, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                    for c in cdata.get("customers", []):
                        cid = c.get("customer_id")
                        if cid:
                            self._seed_cache[("customer", cid)] = {
                                "version": 0,
                                "payload": c,
                                "delivered_at": "2026-04-26T00:00:00Z"
                            }
            except Exception:
                pass
        merch_path = root / "merchants_seed.json"
        if merch_path.exists():
            try:
                with open(merch_path, "r", encoding="utf-8") as f:
                    mdata = json.load(f)
                    for m in mdata.get("merchants", []):
                        mid = m.get("merchant_id")
                        if mid:
                            self._seed_cache[("merchant", mid)] = {
                                "version": 0,
                                "payload": m,
                                "delivered_at": "2026-04-26T00:00:00Z"
                            }
            except Exception:
                pass
        cat_dir = root / "categories"
        if cat_dir.exists():
            for cfile in cat_dir.glob("*.json"):
                try:
                    with open(cfile, "r", encoding="utf-8") as f:
                        cpayload = json.load(f)
                        cslug = cpayload.get("slug") or cfile.stem
                        if cslug:
                            self._seed_cache[("category", cslug)] = {
                                "version": 0,
                                "payload": cpayload,
                                "delivered_at": "2026-04-26T00:00:00Z"
                            }
                except Exception:
                    pass

    def _load_from_storage(self) -> None:
        for scope in ["category", "merchant", "customer", "trigger"]:
            items = self.storage.get_all_contexts_by_scope(scope)
            for cid, data in items.items():
                self._cache[(scope, cid)] = data

    def push(
        self, scope: str, context_id: str, version: int, payload: Dict[str, Any], delivered_at: Optional[str] = None
    ) -> Tuple[bool, str, int]:
        """
        Store context version atomically.
        Returns (accepted, ack_or_reason, current_version).
        """
        key = (scope, context_id)
        cur = self._cache.get(key)
        if cur and cur["version"] >= version:
            return False, "stale_version", cur["version"]

        accepted, cur_ver, msg = self.storage.save_context(scope, context_id, version, payload, delivered_at)
        if accepted:
            self._cache[key] = {
                "version": version,
                "payload": payload,
                "delivered_at": delivered_at or datetime.now(timezone.utc).isoformat(),
            }
            return True, msg, version
        return False, msg, cur_ver

    def get(self, scope: str, context_id: str) -> Optional[Dict[str, Any]]:
        key = (scope, context_id)
        if key in self._cache:
            return self._cache[key]["payload"]
        data = self.storage.get_context(scope, context_id)
        if data:
            self._cache[key] = data
            return data["payload"]
        if key in self._seed_cache:
            return self._seed_cache[key]["payload"]
        return None

    def get_version(self, scope: str, context_id: str) -> Optional[int]:
        key = (scope, context_id)
        if key in self._cache:
            return self._cache[key]["version"]
        data = self.storage.get_context(scope, context_id)
        if data:
            self._cache[key] = data
            return data["version"]
        if key in self._seed_cache:
            return self._seed_cache[key]["version"]
        return None

    def counts(self) -> Dict[str, int]:
        c = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        for (scope, _) in self._cache.keys():
            if scope in c:
                c[scope] += 1
        return c

    def clear(self) -> int:
        count = len(self._cache)
        self._cache.clear()
        self.storage.wipe_all()
        return count
