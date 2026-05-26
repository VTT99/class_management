from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    duckdb_file: Path = Field(default=Path("data/tutorial_center.duckdb"), alias="DUCKDB_FILE")
    google_service_account_file: Path = Field(
        default=Path("secrets/service_account.json"),
        alias="GOOGLE_SERVICE_ACCOUNT_FILE",
    )
    google_calendar_id: str = Field(default="", alias="GOOGLE_CALENDAR_ID")
    google_sheets_spreadsheet_id: str = Field(default="", alias="GOOGLE_SHEETS_SPREADSHEET_ID")
    timezone: str = Field(default="Asia/Hong_Kong", alias="TIMEZONE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    api_bearer_token: str = Field(default="", alias="API_BEARER_TOKEN")
    root_path: str = Field(default="", alias="ROOT_PATH")
    serve_frontend: bool = Field(default=True, alias="SERVE_FRONTEND")
    allowed_origins: str = Field(
        default="http://127.0.0.1:8000,http://localhost:8000",
        alias="ALLOWED_ORIGINS",
    )

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def duckdb_path(self) -> Path:
        return self._resolve(self.duckdb_file)

    @property
    def google_service_account_path(self) -> Path:
        return self._resolve(self.google_service_account_file)

    @staticmethod
    def _resolve(p: Path) -> Path:
        return p if p.is_absolute() else REPO_ROOT / p


@lru_cache
def get_settings() -> Settings:
    return Settings()
