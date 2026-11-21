from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from ..database import Repository, get_repo
from ..schemas import ChatRequest, ChatResponse
from ..services import chat_service

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse,
             summary="AI 대화 (요약 컨텍스트 주입 + 도구 호출 + 자동 저장)")
async def chat(payload: ChatRequest, repo: Repository = Depends(get_repo)):
    try:
        # AI Gateway(urllib)·Firestore 호출은 동기 → 스레드풀에서 실행해 이벤트 루프를 막지 않는다
        return await run_in_threadpool(chat_service.chat, repo, payload.message,
                                       payload.conversation_id, payload.use_tools)
    except chat_service.ChatError as exc:
        raise HTTPException(exc.status, exc.message) from exc
