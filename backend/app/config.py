from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


class Settings:
    @property
    def ai_provider(self) -> str:
        return os.getenv("AI_PROVIDER", "openai").lower()

    @property
    def llm_api_key(self) -> str:
        if self.ai_provider == "deepseek":
            return os.getenv("DEEPSEEK_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
        return os.getenv("OPENAI_API_KEY", "")

    @property
    def llm_base_url(self) -> str:
        if self.ai_provider == "deepseek":
            return os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        return os.getenv("OPENAI_BASE_URL", "")

    @property
    def llm_model(self) -> str:
        if self.ai_provider == "deepseek":
            return os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        return os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

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
