"""Zentrale Settings — liest .env (falls vorhanden) und liefert typisierte Werte."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Repo-Root: zwei Ebenen über dieser Datei (src/bew/config.py -> src/bew -> src -> repo)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Konfiguration aus .env und Umgebung."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Pfade (mit Defaults, relativ zum Repo-Root)
    bew_data_dir: str = "data"
    bew_db_path: str = "db/bew.db"

    # Azure Document Intelligence (Phase 2)
    azure_doc_intel_endpoint: str | None = None
    azure_doc_intel_key: str | None = None

    # Azure OpenAI (Phase 2)
    azure_openai_endpoint: str | None = None
    azure_openai_key: str | None = None
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_deployment: str | None = None

    # Microsoft Entra ID / MSAL — SharePoint-Connector (Phase 1)
    msal_tenant_id: str | None = None
    msal_client_id: str | None = None

    # Anthropic Claude API (Phase 2 — Chat-Agent)
    anthropic_api_key: str | None = None

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

    @property
    def token_cache_path(self) -> Path:
        return self.data_dir / ".msal_token_cache.json"


settings = Settings()
