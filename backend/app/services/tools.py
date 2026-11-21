"""(보너스) Function Calling 도구 정의와 실행기.

AI(코디세이 Gateway의 Claude)가 필요할 때 내부 기능을 '도구'로 호출한다.
스키마는 OpenAI 형식으로 정의하고, llm.py 가 Anthropic 형식(input_schema)으로 변환해 보낸다. 모든 도구는 reason 인자를 필수로 받아
"어떤 근거로 이 도구를 골랐는지"를 남기고, 채팅 응답의 tool_calls 로 프론트에 보여준다.
같은 함수들을 MCP 서버(mcp_server/server.py)도 REST API 를 통해 노출한다.
"""
from __future__ import annotations

import json
from datetime import date as Date

from ..database import Repository
from . import conversation_service, data_service, summary_service

_REASON = {"type": "string",
           "description": "이 도구를 호출하는 근거 — 사용자 질문의 어떤 부분 때문에 필요한지 한 문장"}

TOOLS = [
    {"type": "function", "function": {
        "name": "get_data_summary",
        "description": "전체 데이터의 기간, 개수, 합계/평균/최대/최소, 최근 14일 트렌드를 조회한다. "
                       "시스템 프롬프트의 요약보다 최신 값이 필요하거나 데이터를 방금 수정했을 때 사용.",
        "parameters": {"type": "object", "properties": {"reason": _REASON},
                       "required": ["reason"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "get_statistics",
        "description": "요일별 평균, 월별 합계/평균, 중앙값, 표준편차, 최장 연속 기록, 메모(종목)별 횟수를 조회한다. "
                       "'무슨 요일에 많이', '월별 비교', '어떤 운동을 제일 많이' 같은 질문에 사용.",
        "parameters": {"type": "object", "properties": {"reason": _REASON},
                       "required": ["reason"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "query_data",
        "description": "특정 기간 또는 메모 키워드의 개별 기록을 조회한다. "
                       "'이번 달', '지난주', '11월 3일', '복싱한 날' 처럼 구체적 날짜/항목이 필요한 질문에 사용.",
        "parameters": {"type": "object", "properties": {
            "reason": _REASON,
            "start_date": {"type": "string", "description": "YYYY-MM-DD (포함)"},
            "end_date": {"type": "string", "description": "YYYY-MM-DD (포함)"},
            "memo_keyword": {"type": "string", "description": "메모에 포함된 키워드"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 60, "default": 31}},
            "required": ["reason"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "list_conversations",
        "description": "이전에 저장된 대화 목록(제목, 미리보기)을 조회한다. '전에 뭐 물어봤지?' 같은 질문에 사용.",
        "parameters": {"type": "object", "properties": {
            "reason": _REASON,
            "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5}},
            "required": ["reason"], "additionalProperties": False}}},
]


def _parse_date(value: str | None) -> Date | None:
    if not value:
        return None
    try:
        return Date.fromisoformat(value)
    except ValueError:
        return None


def run_tool(repo: Repository, name: str, args: dict) -> dict:
    """도구 실행. 결과는 JSON 직렬화 가능한 dict, 실패 시 {'error': ...}."""
    try:
        if name == "get_data_summary":
            return summary_service.compute_summary(data_service.list_data(repo))
        if name == "get_statistics":
            stats = summary_service.compute_statistics(data_service.list_data(repo))
            stats.pop("moving_average_7", None)  # 토큰 절약
            return stats
        if name == "query_data":
            items = data_service.list_data(repo, _parse_date(args.get("start_date")),
                                           _parse_date(args.get("end_date")))
            kw = (args.get("memo_keyword") or "").strip()
            if kw:
                items = [i for i in items if kw in (i.get("memo") or "")]
            limit = max(1, min(int(args.get("limit") or 31), 60))
            values = [i["value"] for i in items]
            return {
                "matched": len(items),
                "total": round(sum(values), 2),
                "average": round(sum(values) / len(values), 2) if values else None,
                "records": [{"date": i["date"], "value": i["value"], "memo": i.get("memo", "")}
                            for i in items[-limit:]],
                "truncated": len(items) > limit,
            }
        if name == "list_conversations":
            limit = max(1, min(int(args.get("limit") or 5), 20))
            return {"conversations": [{"title": c["title"], "preview": c["preview"],
                                       "updated_at": c["updated_at"]}
                                      for c in conversation_service.list_conversations(repo)[:limit]]}
        return {"error": f"알 수 없는 도구: {name}"}
    except Exception as exc:  # 도구 실패가 전체 채팅을 멈추지 않도록
        return {"error": str(exc)}


def to_json(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, default=str)
