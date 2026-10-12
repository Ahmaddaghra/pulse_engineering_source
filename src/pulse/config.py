import os
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    database_url: str = "postgresql+psycopg://pulse:pulse@localhost:5432/pulse"
    object_root: Path = Path("artifacts")
    live_enabled: bool = False
    api_token: str = ""
    audit_token: str = ""
    lease_seconds: int = Field(default=30, ge=1, le=300)
    max_attempts: int = Field(default=4, ge=1, le=10)

    @classmethod
    def from_env(cls) -> "Settings":
        values = {
            name: os.environ[f"PULSE_{name.upper()}"]
            for name in cls.model_fields
            if f"PULSE_{name.upper()}" in os.environ
        }
        return cls.model_validate(values)
