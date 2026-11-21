"""환경 변수 로딩. 키 값은 코드에 두지 않고 모두 환경 변수에서 읽는다."""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _split(value: str) -> list[str]:
    return [v.strip().rstrip("/") for v in value.split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    # 코디세이 AI Gateway (copa.codyssey.kr)
    ai_api_key: str = os.getenv("AI_API_KEY", "").strip()
    ai_base_url: str = os.getenv("AI_BASE_URL", "").strip() or "https://copa.codyssey.kr"
    ai_model: str = os.getenv("AI_MODEL", "").strip() or "claude-haiku-4"
    ai_api_format: str = os.getenv("AI_API_FORMAT", "").strip().lower()   # ''(자동) | anthropic | openai
    ai_max_tokens: int = int(os.getenv("AI_MAX_TOKENS", "500"))
    chat_history_limit: int = int(os.getenv("CHAT_HISTORY_LIMIT", "10"))

    firebase_json: str = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
    firebase_path: str = os.getenv("FIREBASE_CREDENTIALS_PATH", "")
    use_memory_db: bool = os.getenv("USE_MEMORY_DB", "false").lower() == "true"

    # 데이터 설명 (프롬프트·요약에 표시)
    data_label: str = os.getenv("DATA_LABEL", "일일 운동 시간")
    data_unit: str = os.getenv("DATA_UNIT", "분")

    allowed_origins: list[str] = field(
        default_factory=lambda: _split(
            os.getenv("ALLOWED_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500")
        )
    )


settings = Settings()
