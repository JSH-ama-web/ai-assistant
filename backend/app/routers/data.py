from datetime import date as Date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..database import Repository, get_repo
from ..schemas import DataCreate, DataItem, DataUpdate, Statistics, Summary
from ..services import data_service, summary_service

router = APIRouter(prefix="/api/data", tags=["data"])


# 고정 경로(/summary, /statistics)는 /{id} 보다 먼저 선언한다.
@router.get("/summary", response_model=Summary, summary="데이터 요약 (프롬프트 주입용)")
def get_summary(repo: Repository = Depends(get_repo)):
    return summary_service.compute_summary(data_service.list_data(repo))


@router.get("/statistics", response_model=Statistics, summary="(보너스) 확장 통계")
def get_statistics(repo: Repository = Depends(get_repo)):
    return summary_service.compute_statistics(data_service.list_data(repo))


@router.get("", response_model=list[DataItem], summary="데이터 목록 조회 (날짜 오름차순)")
def list_data(
    start: Date | None = Query(None, description="시작일 YYYY-MM-DD"),
    end: Date | None = Query(None, description="종료일 YYYY-MM-DD"),
    limit: int | None = Query(None, ge=1, le=5000, description="최근 N개만"),
    repo: Repository = Depends(get_repo),
):
    if start and end and start > end:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "start 가 end 보다 늦습니다.")
    return data_service.list_data(repo, start, end, limit)


@router.post("", response_model=DataItem, status_code=status.HTTP_201_CREATED, summary="새 데이터 추가")
def create_data(payload: DataCreate, repo: Repository = Depends(get_repo)):
    return data_service.create_data(repo, payload)


@router.put("/{doc_id}", response_model=DataItem, summary="데이터 수정")
def update_data(doc_id: str, payload: DataUpdate, repo: Repository = Depends(get_repo)):
    if not payload.model_dump(exclude_none=True):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "수정할 필드가 없습니다.")
    updated = data_service.update_data(repo, doc_id, payload)
    if updated is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "데이터를 찾을 수 없습니다.")
    return updated


@router.delete("/{doc_id}", summary="데이터 삭제")
def delete_data(doc_id: str, repo: Repository = Depends(get_repo)):
    if not data_service.delete_data(repo, doc_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "데이터를 찾을 수 없습니다.")
    return {"deleted": True, "id": doc_id}
