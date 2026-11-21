"""FastAPI 진입점.  실행: uvicorn main:app --reload"""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import chat, conversations, data
from app.services import llm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

app = FastAPI(
    title="내 데이터를 아는 AI 비서 API",
    description="시계열 데이터 CRUD · 요약 · 대화 기록 · 컨텍스트 주입 AI 채팅",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",   # Vercel 프리뷰 배포 허용
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(data.router)
app.include_router(conversations.router)
app.include_router(chat.router)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    # 내부 오류 메시지(키, 스택 등)는 노출하지 않는다
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "서버 내부 오류가 발생했습니다."})


@app.get("/", tags=["health"])
def root():
    return {"service": "AI 비서 API", "docs": "/docs", "health": "/health"}


@app.get("/health", tags=["health"], summary="헬스 체크 (콜드스타트 깨우기용, AI 설정 진단)")
def health():
    # 키 값은 노출하지 않고 설정 여부·주소·모델만 보여 준다
    return {"status": "ok", "ai": llm.config()}
