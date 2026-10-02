from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

def _database_url() -> str:
    url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://nmtpl_app:CHANGE_ME@127.0.0.1:5432/nmtpl_ops",
    ).strip()
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url

@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "NMTPL - site Thakurani IOM")
    env: str = os.getenv("APP_ENV", "development")
    host: str = os.getenv("APP_HOST", "0.0.0.0")
    port: int = int(os.getenv("APP_PORT", "8000"))
    timezone: str = os.getenv("APP_TIMEZONE", "Asia/Kolkata")
    database_url: str = _database_url()

settings = Settings()
