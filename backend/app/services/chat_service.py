"""POST /api/chat 의 핵심 로직 — 컨텍스트 주입 + (선택) Function Calling + 자동 저장.

흐름
 1) 데이터 요약 조회 (GET /api/data/summary 와 같은 함수)
 2) 요약을 시스템 프롬프트에 삽입
 3) 코디세이 AI Gateway 호출 (필요 시 도구 호출 → 결과를 다시 전달, 최대 3라운드)
 4) user/assistant 메시지를 conversations 에 저장
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..config import settings
from ..database import Repository
from . import conversation_service, data_service, llm, summary_service, tools

MAX_TOOL_ROUNDS = 3
KST = timezone(timedelta(hours=9))


class ChatError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class NotFound(ChatError):
    def __init__(self, message: str):
        super().__init__(404, message)


def build_system_prompt(summary: dict) -> str:
    today = datetime.now(KST).date().isoformat()
    return (
        "당신은 사용자의 개인 데이터를 이해하는 데이터 분석 비서입니다.\n\n"
        "[사용자 데이터 요약]\n"
        f"{summary_service.summary_to_prompt(summary)}\n\n"
        f"오늘 날짜: {today} (Asia/Seoul)\n\n"
        "규칙:\n"
        "- 위 요약과 도구 결과에 있는 숫자만 근거로 답하고, 없는 수치는 지어내지 마세요.\n"
        "- 요약만으로 답할 수 없는 구체적 날짜·요일·종목 질문은 도구를 호출해 확인하세요.\n"
        "- 한국어로 2~5문장, 핵심 수치와 단위를 포함해 친근하게 답하세요.\n"
        "- 데이터가 없거나 부족하면 그 사실을 솔직히 말하세요."
    )


def chat(repo: Repository, message: str, conversation_id: str | None = None,
         use_tools: bool = True) -> dict:
    # 이어서 대화하는 경우 기존 대화 확인
    history: list[dict] = []
    if conversation_id:
        conv = conversation_service.get_conversation(repo, conversation_id)
        if conv is None:
            raise NotFound("대화를 찾을 수 없습니다.")
        history = [{"role": m["role"], "content": m["content"]}
                   for m in conv.get("messages", [])][-settings.chat_history_limit:]
        while history and history[0]["role"] != "user":   # Anthropic 형식은 user 로 시작해야 함
            history.pop(0)

    # 1) 요약 조회  2) 시스템 프롬프트 주입
    summary = summary_service.compute_summary(data_service.list_data(repo))
    system = build_system_prompt(summary)
    messages = [*history, {"role": "user", "content": message}]

    # 3) AI 호출 (+ 도구 호출 루프는 llm 모듈이 형식별로 처리)
    try:
        reply, tool_logs = llm.chat(
            system, messages,
            tools.TOOLS if use_tools else None,
            lambda name, args: tools.to_json(tools.run_tool(repo, name, args)),
            MAX_TOOL_ROUNDS,
        )
    except llm.LLMError as e:
        raise ChatError(e.status, e.message) from e

    if not reply:
        reply = "죄송해요, 답변을 만들지 못했어요. 질문을 조금 바꿔서 다시 시도해 주세요."

    # 4) 자동 저장
    new_msgs = [{"role": "user", "content": message},
                {"role": "assistant", "content": reply, "tool_calls": tool_logs}]
    if conversation_id:
        conversation_service.append_messages(repo, conversation_id, new_msgs)
    else:
        conversation_id = conversation_service.create_conversation(repo, new_msgs)["id"]

    return {"conversation_id": conversation_id, "reply": reply,
            "summary": summary, "tool_calls": tool_logs}
