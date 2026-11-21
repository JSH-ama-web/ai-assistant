"""(보너스) MCP 서버 — 배포된 FastAPI 를 외부 클라이언트(Claude Desktop 등)에서 도구로 호출.

웹 채팅의 Function Calling 과 '같은 기능'을 MCP 도구로 노출한다.
MCP 서버는 DB/키에 직접 접근하지 않고 REST API 만 호출하므로 키는 Render 에만 존재한다.

실행:
    pip install -r requirements.txt
    API_BASE_URL=https://<your-api>.onrender.com python server.py      # stdio 모드

Claude Desktop 설정(claude_desktop_config.json) 예시는 README 참고.
"""
from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

API = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
mcp = FastMCP("workout-assistant")


def _call(method: str, path: str, **kwargs):
    # Render 무료 티어 콜드스타트 대비 넉넉한 타임아웃
    with httpx.Client(timeout=90) as client:
        res = client.request(method, API + path, **kwargs)
        res.raise_for_status()
        return res.json()


@mcp.tool()
def get_data_summary() -> dict:
    """전체 운동 기록의 기간, 개수, 합계/평균/최대/최소, 최근 14일 추세를 조회한다."""
    return _call("GET", "/api/data/summary")


@mcp.tool()
def get_statistics() -> dict:
    """요일별 평균, 월별 합계, 중앙값, 표준편차, 최장 연속 기록, 종목(메모)별 횟수를 조회한다."""
    stats = _call("GET", "/api/data/statistics")
    stats.pop("moving_average_7", None)
    return stats


@mcp.tool()
def query_data(start_date: str | None = None, end_date: str | None = None,
               memo_keyword: str | None = None, limit: int = 31) -> dict:
    """기간(YYYY-MM-DD)·메모 키워드로 개별 기록을 조회한다."""
    params = {k: v for k, v in {"start": start_date, "end": end_date}.items() if v}
    items = _call("GET", "/api/data", params=params)
    if memo_keyword:
        items = [i for i in items if memo_keyword in (i.get("memo") or "")]
    values = [i["value"] for i in items]
    return {"matched": len(items), "total": round(sum(values), 2),
            "records": [{"date": i["date"], "value": i["value"], "memo": i.get("memo", "")}
                        for i in items[-max(1, min(limit, 60)):]]}


@mcp.tool()
def add_record(date: str, value: float, memo: str = "") -> dict:
    """운동 기록 1건을 추가한다. date=YYYY-MM-DD, value=분."""
    return _call("POST", "/api/data", json={"date": date, "value": value, "memo": memo})


@mcp.tool()
def list_conversations(limit: int = 5) -> list:
    """웹 서비스에 저장된 최근 대화 목록(제목·미리보기)을 조회한다."""
    return _call("GET", "/api/conversations")[:limit]


@mcp.tool()
def ask_assistant(question: str) -> dict:
    """웹 서비스의 AI 비서(/api/chat)에게 질문한다. 서버 측 도구 호출 내역도 함께 반환."""
    res = _call("POST", "/api/chat", json={"message": question, "use_tools": True})
    return {"reply": res["reply"], "tool_calls": res.get("tool_calls", []),
            "conversation_id": res["conversation_id"]}


if __name__ == "__main__":
    mcp.run()
