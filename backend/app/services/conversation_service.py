"""conversations 컬렉션 — 대화 저장/목록/상세/삭제/이어쓰기."""
from __future__ import annotations

from ..database import CONVERSATION_COLLECTION, Repository, now_iso


def _title_from(messages: list[dict]) -> str:
    first_user = next((m["content"] for m in messages if m["role"] == "user"), "새 대화")
    first_user = " ".join(first_user.split())
    return first_user[:30] + ("…" if len(first_user) > 30 else "")


def _stamp(messages: list[dict]) -> list[dict]:
    ts = now_iso()
    out = []
    for m in messages:
        msg = {"role": m["role"], "content": m["content"], "created_at": m.get("created_at") or ts}
        if m.get("tool_calls"):
            msg["tool_calls"] = m["tool_calls"]
        out.append(msg)
    return out


def create_conversation(repo: Repository, messages: list[dict], title: str | None = None) -> dict:
    ts = now_iso()
    msgs = _stamp(messages)
    doc = {"title": (title or "").strip() or _title_from(msgs), "messages": msgs,
           "created_at": ts, "updated_at": ts}
    return repo.add(CONVERSATION_COLLECTION, doc)


def append_messages(repo: Repository, conv_id: str, messages: list[dict]) -> dict | None:
    conv = repo.get(CONVERSATION_COLLECTION, conv_id)
    if conv is None:
        return None
    merged = conv.get("messages", []) + _stamp(messages)
    return repo.update(CONVERSATION_COLLECTION, conv_id,
                       {"messages": merged, "updated_at": now_iso()})


def list_conversations(repo: Repository) -> list[dict]:
    """목록: messages 는 빼고 개수·미리보기만 (응답 가벼움 유지). 최신 수정순."""
    out = []
    for c in repo.list(CONVERSATION_COLLECTION):
        msgs = c.get("messages", [])
        last = msgs[-1]["content"] if msgs else ""
        out.append({"id": c["id"], "title": c.get("title", "제목 없음"),
                    "message_count": len(msgs), "preview": last[:60],
                    "created_at": c.get("created_at"), "updated_at": c.get("updated_at")})
    return sorted(out, key=lambda x: x.get("updated_at") or "", reverse=True)


def get_conversation(repo: Repository, conv_id: str) -> dict | None:
    return repo.get(CONVERSATION_COLLECTION, conv_id)


def delete_conversation(repo: Repository, conv_id: str) -> bool:
    return repo.delete(CONVERSATION_COLLECTION, conv_id)
