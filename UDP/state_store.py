"""Persistent application state with MongoDB and local JSON support."""

import json
import os
from pathlib import Path
from typing import Any

from pymongo import MongoClient


BASE_DIR = Path(__file__).resolve().parent
STATE_FILES = {
    "accounts": BASE_DIR / "accounts.json",
    "token_cache": BASE_DIR / "token_cache.json",
    "devices": BASE_DIR / "devices.json",
}


class StateStore:
    def __init__(self) -> None:
        self._collection = None
        self._client = None

    def initialize(self) -> None:
        uri = os.environ.get("MONGODB_URI", "").strip()
        required = os.environ.get("REQUIRE_MONGODB", "false").lower() == "true"
        if not uri:
            if required:
                raise RuntimeError("MONGODB_URI is required for this deployment")
            return

        self._client = MongoClient(uri, serverSelectionTimeoutMS=10000)
        self._client.admin.command("ping")
        database_name = os.environ.get("MONGODB_DATABASE", "f4x_udp").strip() or "f4x_udp"
        self._collection = self._client[database_name]["app_state"]

        for key, path in STATE_FILES.items():
            if self._collection.find_one({"_id": key}, {"_id": 1}) is not None:
                continue
            try:
                with path.open("r", encoding="utf-8") as state_file:
                    value = json.load(state_file)
            except (OSError, json.JSONDecodeError):
                continue
            self.save(key, value)

    def load(self, key: str, default: Any) -> Any:
        if self._collection is None:
            path = STATE_FILES.get(key)
            if path is None or not path.exists():
                return default
            try:
                with path.open("r", encoding="utf-8") as state_file:
                    return json.load(state_file)
            except (OSError, json.JSONDecodeError):
                return default

        document = self._collection.find_one({"_id": key}, {"value": 1})
        return document.get("value", default) if document else default

    def save(self, key: str, value: Any) -> None:
        if self._collection is None:
            path = STATE_FILES.get(key)
            if path is None:
                raise KeyError(f"Unknown state key: {key}")
            temporary_path = path.with_suffix(path.suffix + ".tmp")
            with temporary_path.open("w", encoding="utf-8") as state_file:
                json.dump(value, state_file, indent=2, default=self._json_default)
            os.replace(temporary_path, path)
            return

        self._collection.replace_one({"_id": key}, {"_id": key, "value": value}, upsert=True)

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, (bytes, bytearray)):
            return {"__bytes_hex__": bytes(value).hex()}
        raise TypeError(f"Type {type(value)} is not JSON serializable")


state_store = StateStore()
