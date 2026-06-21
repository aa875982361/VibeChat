from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


class Settings:
    @property
    def openai_api_key(self) -> str:
        return os.getenv("OPENAI_API_KEY", "")

    @property
    def openai_model(self) -> str:
        return os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    @property
    def openai_moderation_model(self) -> str:
        return os.getenv("OPENAI_MODERATION_MODEL", "omni-moderation-latest")

    @property
    def db_path(self) -> str:
        default_path = ROOT_DIR / "vibechat.db"
        return os.getenv("VIBECHAT_DB_PATH", str(default_path))

    @property
    def frontend_origin(self) -> str:
        return os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")


settings = Settings()

