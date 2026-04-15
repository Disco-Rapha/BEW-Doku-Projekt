"""Zentrale Settings — liest .env (falls vorhanden) und liefert typisierte Werte."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Repo-Root: zwei Ebenen über dieser Datei (src/bew/config.py -> src/bew -> src -> repo)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Konfiguration aus .env und Umgebung. Felder sind optional, bis Phase 1 Azure nutzt."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Pfade (mit Defaults, relativ zum Repo-Root)
    bew_data_dir: str = "data"
    bew_db_path: str = "db/bew.db"

    # Azure Document Intelligence (Phase 1)
    azure_doc_intel_endpoint: str | None = None
    azure_doc_intel_key: str | None = None

    # Azure OpenAI (Phase 1)
    azure_openai_endpoint: str | None = None
    azure_openai_key: str | None = None
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_deployment: str | None = None

    @property
    def db_path(self) -> Path:
        p = Path(self.bew_db_path)
        return p if p.is_absolute() else REPO_ROOT / p

    @property
    def data_dir(self) -> Path:
        p = Path(self.bew_data_dir)
        return p if p.is_absolute() else REPO_ROOT / p

    @property
    def migrations_dir(self) -> Path:
        return REPO_ROOT / "migrations"


settings = Settings()
