"""data 컬렉션 CRUD."""
from __future__ import annotations

from datetime import date as Date

from ..database import DATA_COLLECTION, Repository, now_iso
from ..schemas import DataCreate, DataUpdate


def _sort_key(item: dict) -> tuple:
    return (item.get("date", ""), item.get("created_at") or "")


def list_data(repo: Repository, start: Date | None = None, end: Date | None = None,
              limit: int | None = None) -> list[dict]:
    items = sorted(repo.list(DATA_COLLECTION), key=_sort_key)
    if start:
        items = [i for i in items if i["date"] >= start.isoformat()]
    if end:
        items = [i for i in items if i["date"] <= end.isoformat()]
    if limit:
        items = items[-limit:]
    return items


def create_data(repo: Repository, payload: DataCreate) -> dict:
    ts = now_iso()
    doc = {"date": payload.date.isoformat(), "value": payload.value, "memo": payload.memo,
           "created_at": ts, "updated_at": ts}
    return repo.add(DATA_COLLECTION, doc)


def update_data(repo: Repository, doc_id: str, payload: DataUpdate) -> dict | None:
    changes = payload.model_dump(exclude_none=True)
    if "date" in changes:
        changes["date"] = changes["date"].isoformat()
    if "memo" in changes:
        changes["memo"] = changes["memo"].strip()
    changes["updated_at"] = now_iso()
    return repo.update(DATA_COLLECTION, doc_id, changes)


def delete_data(repo: Repository, doc_id: str) -> bool:
    return repo.delete(DATA_COLLECTION, doc_id)
