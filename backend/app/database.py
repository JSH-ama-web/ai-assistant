"""Firestore 연동 계층.

- FirestoreRepository : 운영용 (Firebase Admin SDK)
- MemoryRepository    : Firebase 키 없이 로컬 테스트할 때만 사용 (USE_MEMORY_DB=true)

서비스 계층은 Repository 인터페이스(list/get/add/update/delete)만 사용하므로
DB 구현이 바뀌어도 서비스/라우터 코드는 그대로 유지된다.
"""
from __future__ import annotations

import base64
import copy
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol

from .config import settings

logger = logging.getLogger(__name__)

DATA_COLLECTION = "data"
CONVERSATION_COLLECTION = "conversations"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Repository(Protocol):
    def list(self, collection: str) -> list[dict[str, Any]]: ...
    def get(self, collection: str, doc_id: str) -> dict[str, Any] | None: ...
    def add(self, collection: str, data: dict[str, Any]) -> dict[str, Any]: ...
    def update(self, collection: str, doc_id: str, data: dict[str, Any]) -> dict[str, Any] | None: ...
    def delete(self, collection: str, doc_id: str) -> bool: ...


class MemoryRepository:
    def __init__(self) -> None:
        self._store: dict[str, dict[str, dict[str, Any]]] = {}

    def _col(self, name: str) -> dict[str, dict[str, Any]]:
        return self._store.setdefault(name, {})

    def list(self, collection):
        return [{"id": k, **copy.deepcopy(v)} for k, v in self._col(collection).items()]

    def get(self, collection, doc_id):
        doc = self._col(collection).get(doc_id)
        return {"id": doc_id, **copy.deepcopy(doc)} if doc else None

    def add(self, collection, data):
        doc_id = uuid.uuid4().hex[:20]
        self._col(collection)[doc_id] = copy.deepcopy(data)
        return {"id": doc_id, **copy.deepcopy(data)}

    def update(self, collection, doc_id, data):
        col = self._col(collection)
        if doc_id not in col:
            return None
        col[doc_id].update(copy.deepcopy(data))
        return {"id": doc_id, **copy.deepcopy(col[doc_id])}

    def delete(self, collection, doc_id):
        return self._col(collection).pop(doc_id, None) is not None


class FirestoreRepository:
    def __init__(self) -> None:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            firebase_admin.initialize_app(_load_credentials(credentials))
        self._db = firestore.client()

    def list(self, collection):
        return [{"id": d.id, **d.to_dict()} for d in self._db.collection(collection).stream()]

    def get(self, collection, doc_id):
        snap = self._db.collection(collection).document(doc_id).get()
        return {"id": snap.id, **snap.to_dict()} if snap.exists else None

    def add(self, collection, data):
        _, ref = self._db.collection(collection).add(data)
        return {"id": ref.id, **data}

    def update(self, collection, doc_id, data):
        ref = self._db.collection(collection).document(doc_id)
        if not ref.get().exists:
            return None
        ref.update(data)
        snap = ref.get()
        return {"id": snap.id, **snap.to_dict()}

    def delete(self, collection, doc_id):
        ref = self._db.collection(collection).document(doc_id)
        if not ref.get().exists:
            return False
        ref.delete()
        return True


def _load_credentials(credentials):
    """FIREBASE_SERVICE_ACCOUNT_JSON(JSON 문자열 또는 base64) → 없으면 파일 경로."""
    raw = settings.firebase_json.strip()
    if raw:
        if not raw.startswith("{"):
            raw = base64.b64decode(raw).decode("utf-8")
        info = json.loads(raw)
        # Render 등에서 줄바꿈이 \\n 으로 이스케이프된 경우 복원
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")
        return credentials.Certificate(info)
    if settings.firebase_path:
        return credentials.Certificate(settings.firebase_path)
    raise RuntimeError(
        "Firebase 자격 증명이 없습니다. FIREBASE_SERVICE_ACCOUNT_JSON 또는 "
        "FIREBASE_CREDENTIALS_PATH 를 설정하세요. (로컬 테스트는 USE_MEMORY_DB=true)"
    )


_repo: Repository | None = None


def get_repo() -> Repository:
    global _repo
    if _repo is None:
        if settings.use_memory_db:
            logger.warning("USE_MEMORY_DB=true → 메모리 저장소 사용 (재시작 시 데이터 사라짐)")
            _repo = MemoryRepository()
        else:
            _repo = FirestoreRepository()
    return _repo


def set_repo(repo: Repository) -> None:
    """테스트용 주입."""
    global _repo
    _repo = repo
