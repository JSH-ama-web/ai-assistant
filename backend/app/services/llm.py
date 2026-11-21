"""AI 호출 클라이언트 — 코디세이 AI Gateway(copa.codyssey.kr) 기본, 표준 라이브러리(urllib)만 사용.

환경 변수
  AI_API_KEY    : 코디세이 콘솔에서 발급한 키 (필수)
  AI_BASE_URL   : Gateway 주소, 기본 https://copa.codyssey.kr (끝에 /v1 이 있어도 됨)
  AI_MODEL      : 모델 이름, 기본 claude-haiku-4
  AI_API_FORMAT : 비우면 Anthropic 방식 → 404/405 시 OpenAI 호환 방식으로 자동 전환
                  'anthropic' / 'openai' 로 고정 가능

도구 호출(Function Calling)은 두 형식 모두 지원한다.
  - Anthropic : tools[{name, description, input_schema}] → content 의 tool_use 블록 → tool_result 로 응답
  - OpenAI    : tools[{type:function, function}] → message.tool_calls → role=tool 메시지로 응답
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Callable

from ..config import settings

logger = logging.getLogger(__name__)
TIMEOUT = 50

_resolved_format: str | None = None   # 자동 감지 결과 캐시 (첫 성공 형식)


class LLMError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def config() -> dict:
    """키 값은 노출하지 않는 진단용 정보 (/health 에서 사용)."""
    return {"api_key_set": bool(settings.ai_api_key), "base_url": settings.ai_base_url,
            "model": settings.ai_model, "format": settings.ai_api_format or f"auto({_resolved_format or 'anthropic'})"}


def _url(path: str) -> str:
    base = settings.ai_base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return base + path


def _post(url: str, body: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"content-type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        return json.loads(res.read().decode("utf-8"))


def _explain(e: urllib.error.HTTPError) -> LLMError:
    try:
        detail = e.read().decode(errors="ignore")[:300]
    except Exception:
        detail = ""
    logger.warning("AI Gateway HTTP %s: %s", e.code, detail)
    if e.code in (401, 403):
        return LLMError(502, f"AI 인증 실패({e.code}): AI_API_KEY 를 확인하세요.")
    if e.code == 404:
        return LLMError(502, f"AI 주소나 모델 이름이 올바르지 않습니다(404). AI_BASE_URL·AI_MODEL='{settings.ai_model}' 확인")
    if e.code == 429:
        return LLMError(429, "AI 사용량 한도를 초과했습니다(429). 잠시 후 다시 시도하세요.")
    return LLMError(502, f"AI API 오류({e.code})")


# ── Anthropic Messages 형식 ───────────────────────────
def _anthropic_loop(system, messages, tools, run_tool, rounds):
    a_tools = [{"name": t["function"]["name"], "description": t["function"]["description"],
                "input_schema": t["function"]["parameters"]} for t in tools]
    msgs = [{"role": m["role"], "content": m["content"]} for m in messages]
    logs = []
    for r in range(rounds + 1):
        body = {"model": settings.ai_model, "max_tokens": settings.ai_max_tokens,
                "temperature": 0.4, "system": system, "messages": msgs}
        if a_tools:
            body["tools"] = a_tools
            if r == rounds:                       # 마지막 라운드는 반드시 텍스트로 답하게
                body["tool_choice"] = {"type": "none"}
        out = _post(_url("/v1/messages"), body,
                    {"x-api-key": settings.ai_api_key, "anthropic-version": "2023-06-01"})
        blocks = out.get("content", [])
        uses = [b for b in blocks if b.get("type") == "tool_use"]
        if not uses:
            return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip(), logs
        msgs.append({"role": "assistant", "content": blocks})
        results = []
        for u in uses:
            args = u.get("input") or {}
            logs.append(_log(u["name"], args))
            results.append({"type": "tool_result", "tool_use_id": u["id"],
                            "content": run_tool(u["name"], args)})
        msgs.append({"role": "user", "content": results})
    return "", logs


# ── OpenAI 호환 형식 ─────────────────────────────────
def _openai_loop(system, messages, tools, run_tool, rounds):
    msgs = [{"role": "system", "content": system}] + \
           [{"role": m["role"], "content": m["content"]} for m in messages]
    logs = []
    for r in range(rounds + 1):
        body = {"model": settings.ai_model, "max_tokens": settings.ai_max_tokens,
                "temperature": 0.4, "messages": msgs}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "none" if r == rounds else "auto"
        out = _post(_url("/v1/chat/completions"), body,
                    {"Authorization": f"Bearer {settings.ai_api_key}"})
        msg = out["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            return (msg.get("content") or "").strip(), logs
        msgs.append({"role": "assistant", "content": msg.get("content"), "tool_calls": calls})
        for c in calls:
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            logs.append(_log(c["function"]["name"], args))
            msgs.append({"role": "tool", "tool_call_id": c["id"],
                         "content": run_tool(c["function"]["name"], args)})
    return "", logs


def _log(name: str, args: dict) -> dict:
    return {"name": name, "arguments": {k: v for k, v in args.items() if k != "reason"},
            "reason": str(args.get("reason", ""))}


def chat(system: str, messages: list[dict], tools: list[dict] | None,
         run_tool: Callable[[str, dict], str], max_rounds: int = 3) -> tuple[str, list[dict]]:
    """system + 대화(messages: role/content 문자열) → (최종 답변, 도구 호출 기록).

    tools 는 OpenAI 스키마로 받아 형식에 맞게 변환한다. run_tool(name, args) 는 JSON 문자열을 반환.
    """
    global _resolved_format
    if not settings.ai_api_key:
        raise LLMError(503, "AI_API_KEY 가 설정되지 않았습니다.")
    tools = tools or []
    fmt = settings.ai_api_format or _resolved_format or "anthropic"
    try:
        try:
            if fmt == "openai":
                result = _openai_loop(system, messages, tools, run_tool, max_rounds)
            else:
                result = _anthropic_loop(system, messages, tools, run_tool, max_rounds)
        except urllib.error.HTTPError as e:
            # 형식 자동 감지: Anthropic 경로가 없으면 OpenAI 호환으로 한 번 전환
            if settings.ai_api_format or fmt != "anthropic" or e.code not in (404, 405):
                raise
            logger.info("Anthropic 형식 %s → OpenAI 호환 형식으로 전환", e.code)
            fmt = "openai"
            result = _openai_loop(system, messages, tools, run_tool, max_rounds)
        _resolved_format = fmt
        return result
    except urllib.error.HTTPError as e:
        raise _explain(e) from e
    except urllib.error.URLError as e:
        raise LLMError(502, f"AI 서버 연결 실패: {e.reason}") from e
    except TimeoutError as e:
        raise LLMError(504, "AI 응답 시간이 초과됐습니다.") from e
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        raise LLMError(502, "AI 응답 형식을 해석하지 못했습니다. AI_API_FORMAT 설정을 확인하세요.") from e
