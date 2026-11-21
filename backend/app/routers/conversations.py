from fastapi import APIRouter, Depends, HTTPException, status

from ..database import Repository, get_repo
from ..schemas import ConversationCreate, ConversationDetail, ConversationListItem
from ..services import conversation_service

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.post("", response_model=ConversationDetail, status_code=status.HTTP_201_CREATED,
             summary="대화 저장")
def save_conversation(payload: ConversationCreate, repo: Repository = Depends(get_repo)):
    msgs = [m.model_dump() for m in payload.messages]
    return conversation_service.create_conversation(repo, msgs, payload.title)


@router.get("", response_model=list[ConversationListItem],
            summary="대화 목록 조회 (messages 미포함 — 상세는 GET /{id})")
def list_conversations(repo: Repository = Depends(get_repo)):
    return conversation_service.list_conversations(repo)


@router.get("/{conv_id}", response_model=ConversationDetail, summary="특정 대화 전체 메시지 조회")
def get_conversation(conv_id: str, repo: Repository = Depends(get_repo)):
    conv = conversation_service.get_conversation(repo, conv_id)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "대화를 찾을 수 없습니다.")
    return conv


@router.delete("/{conv_id}", summary="대화 삭제")
def delete_conversation(conv_id: str, repo: Repository = Depends(get_repo)):
    if not conversation_service.delete_conversation(repo, conv_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "대화를 찾을 수 없습니다.")
    return {"deleted": True, "id": conv_id}
