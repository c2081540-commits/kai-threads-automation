from dataclasses import dataclass
import os

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return False

load_dotenv()


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    threads_user_id: str = os.getenv("THREADS_USER_ID", "")
    threads_access_token: str = os.getenv("THREADS_ACCESS_TOKEN", "")
    threads_api_version: str = os.getenv("THREADS_API_VERSION", "v1.0")
    timezone: str = os.getenv("TIMEZONE", "Asia/Tokyo")
    auto_publish: bool = _bool("AUTO_PUBLISH")
    auto_analyze: bool = _bool("AUTO_ANALYZE")
    database_path: str = os.getenv("DATABASE_PATH", "data/tarot_growth.db")
    min_body_length: int = int(os.getenv("MIN_BODY_LENGTH", "80"))
    max_body_length: int = int(os.getenv("MAX_BODY_LENGTH", "500"))
    duplicate_threshold: float = float(os.getenv("DUPLICATE_THRESHOLD", "0.72"))
    exploration_rate: float = float(os.getenv("EXPLORATION_RATE", "0.25"))
    image_base_url: str = os.getenv("IMAGE_BASE_URL", "")
    content_queue_path: str = os.getenv(
        "CONTENT_QUEUE_PATH", "data/content_queue.json"
    )


settings = Settings()
