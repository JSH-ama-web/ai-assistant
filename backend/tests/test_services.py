"""서비스 계층 테스트 — Firebase·AI 키 없이 실행 가능 (메모리 저장소 + 가짜 코디세이 Gateway).

실행: python tests/test_services.py   (또는 pytest)
"""
import csv
import json
import sys
from pathlib import Path
import io
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pydantic import ValidationError  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import MemoryRepository, set_repo  # noqa: E402
from app.schemas import ChatRequest, DataCreate, DataUpdate  # noqa: E402
from app.services import (chat_service, conversation_service, data_service,  # noqa: E402
                          llm, summary_service, tools)


def seeded_repo():
    repo = MemoryRepository()
    with (ROOT / "data" / "workout_log.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            data_service.create_data(repo, DataCreate(date=r["date"], value=float(r["value"]), memo=r["memo"]))
    set_repo(repo)
    return repo


class FakeGateway:
    """코디세이 Gateway 흉내. 1번째 호출: query_data 도구 요청 → 2번째: 최종 답변.
    mode='anthropic' | 'openai' | 'openai_only'(Anthropic 경로 404 → 자동 전환 확인)"""
    def __init__(self, mode="anthropic"):
        self.mode, self.calls = mode, []

    def __call__(self, url, body, headers):
        if self.mode == "openai_only" and url.endswith("/v1/messages"):
            raise urllib.error.HTTPError(url, 404, "not found", {}, io.BytesIO(b"no route"))
        self.calls.append((url, body, headers))
        args = {"reason": "'이번 달' 기록이 필요함", "start_date": "2026-11-01", "end_date": "2026-11-30"}
        first = len(self.calls) == 1 and body.get("tools")
        if url.endswith("/v1/messages"):
            if first:
                return {"content": [{"type": "text", "text": "확인해 볼게요."},
                                    {"type": "tool_use", "id": "tu_1", "name": "query_data", "input": args}]}
            return {"content": [{"type": "text", "text": "이번 달 합계는 ...분이에요."}]}
        if first:
            return {"choices": [{"message": {"content": None, "tool_calls": [
                {"id": "call_1", "type": "function",
                 "function": {"name": "query_data", "arguments": json.dumps(args)}}]}}]}
        return {"choices": [{"message": {"content": "이번 달 합계는 ...분이에요."}}]}


def use_gateway(mode="anthropic", fmt=""):
    fake = FakeGateway(mode)
    llm._post = fake
    llm._resolved_format = None
    object.__setattr__(settings, "ai_api_key", "test-key")
    object.__setattr__(settings, "ai_api_format", fmt)
    return fake


def test_validation():
    for bad in [{"date": "2026-13-01", "value": 1}, {"date": "2026-11-01", "value": -1},
                {"date": "2026-11-01", "value": float("inf")}, {"date": "2026-11-01", "value": 1, "memo": "x" * 201}]:
        try:
            DataCreate(**bad)
            raise AssertionError(f"검증 실패해야 함: {bad}")
        except ValidationError:
            pass
    try:
        ChatRequest(message="   ")
        raise AssertionError("빈 메시지 통과")
    except ValidationError:
        pass


def test_crud_and_summary():
    repo = seeded_repo()
    items = data_service.list_data(repo)
    assert len(items) >= 100
    s = summary_service.compute_summary(items)
    assert s["count"] == len(items) and s["metrics"]["max"] >= s["metrics"]["average"]
    new = data_service.create_data(repo, DataCreate(date="2026-11-21", value=200, memo="테스트"))
    assert summary_service.compute_summary(data_service.list_data(repo))["metrics"]["max"] == 200
    upd = data_service.update_data(repo, new["id"], DataUpdate(value=10))
    assert upd["value"] == 10 and upd["memo"] == "테스트"
    assert data_service.delete_data(repo, new["id"]) is True
    assert data_service.delete_data(repo, new["id"]) is False
    assert data_service.update_data(repo, "nope", DataUpdate(value=1)) is None
    st = summary_service.compute_statistics(data_service.list_data(repo))
    assert set(st["weekday_average"]) <= set("월화수목금토일") and st["monthly"]
    assert summary_service.compute_summary([])["count"] == 0


def test_tools():
    repo = seeded_repo()
    r = tools.run_tool(repo, "query_data", {"start_date": "2026-11-01", "memo_keyword": "복싱"})
    assert r["matched"] > 0 and all("복싱" in x["memo"] for x in r["records"])
    assert "error" in tools.run_tool(repo, "unknown", {})
    assert tools.run_tool(repo, "get_statistics", {}).get("moving_average_7") is None


def test_chat_flow_anthropic():
    repo = seeded_repo()
    fake = use_gateway("anthropic")
    res = chat_service.chat(repo, "이번 달 운동량 어때?")
    url, body, headers = fake.calls[0]
    assert url == "https://copa.codyssey.kr/v1/messages" and headers["x-api-key"] == "test-key"
    assert "[사용자 데이터 요약]" in body["system"] and "총 레코드: 180개" in body["system"]  # 컨텍스트 주입
    assert body["max_tokens"] > 0 and body["tools"][0]["input_schema"]                    # 비용 제한·도구 변환
    second = fake.calls[1][1]["messages"]
    assert second[-1]["content"][0]["type"] == "tool_result"                              # 도구 결과 전달
    assert res["tool_calls"][0]["name"] == "query_data" and res["tool_calls"][0]["reason"]
    assert "reason" not in res["tool_calls"][0]["arguments"]
    conv = conversation_service.get_conversation(repo, res["conversation_id"])
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]                # 자동 저장
    assert conv["messages"][1]["tool_calls"][0]["name"] == "query_data"
    # 이어서 대화 → 같은 문서에 추가 + 이력 반영, 도구 끔
    fake2 = use_gateway("anthropic")
    chat_service.chat(repo, "그럼 지난달은?", res["conversation_id"], use_tools=False)
    assert len(conversation_service.get_conversation(repo, res["conversation_id"])["messages"]) == 4
    b = fake2.calls[0][1]
    assert len(b["messages"]) == 3 and b["messages"][0]["role"] == "user" and "tools" not in b
    assert all(isinstance(m["content"], str) for m in b["messages"])                      # tool_calls 는 이력에서 제외
    lst = conversation_service.list_conversations(repo)
    assert lst[0]["message_count"] == 4 and "messages" not in lst[0]
    try:
        chat_service.chat(repo, "hi", "missing-id")
        raise AssertionError("404 이어야 함")
    except chat_service.NotFound:
        pass


def test_chat_flow_openai_fallback():
    repo = seeded_repo()
    fake = use_gateway("openai_only")          # /v1/messages 404 → /v1/chat/completions 자동 전환
    res = chat_service.chat(repo, "이번 달 운동량 어때?")
    assert fake.calls[0][0].endswith("/v1/chat/completions")
    assert fake.calls[0][2]["Authorization"] == "Bearer test-key"
    assert fake.calls[0][1]["messages"][0]["role"] == "system"
    assert fake.calls[1][1]["messages"][-1]["role"] == "tool"
    assert res["tool_calls"][0]["name"] == "query_data" and res["reply"]
    assert llm._resolved_format == "openai"


def test_llm_errors():
    repo = seeded_repo()
    use_gateway()
    object.__setattr__(settings, "ai_api_key", "")
    try:
        chat_service.chat(repo, "hi")
        raise AssertionError("키 없으면 503")
    except chat_service.ChatError as e:
        assert e.status == 503
    use_gateway()
    def unauthorized(url, body, headers):
        raise urllib.error.HTTPError(url, 401, "unauthorized", {}, io.BytesIO(b"bad key"))
    llm._post = unauthorized
    try:
        chat_service.chat(repo, "hi")
        raise AssertionError("401 → 502")
    except chat_service.ChatError as e:
        assert e.status == 502 and "AI_API_KEY" in e.message
    assert "test-key" not in json.dumps(llm.config())                                    # 키 비노출


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("✓", name)
    print("모든 테스트 통과")
