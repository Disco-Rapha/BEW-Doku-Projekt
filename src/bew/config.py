"""Zentrale Settings — liest .env (falls vorhanden) und liefert typisierte Werte.

Disco trennt strikt zwischen:
  - REPO_ROOT       — Code, Skills, Migrations (in Git)
  - WORKSPACE_ROOT  — Daten, DB, Projekte (NIEMALS in Git, default ~/Disco/)

Diese Trennung ist DSGVO-relevant: Kundendaten landen nie im Code-Repo,
auch wenn `git add -A` versehentlich falsch tippt.
"""

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

    # ------------------------------------------------------------------
    # Workspace (NEU — saubere Trennung Code <-> Daten)
    # ------------------------------------------------------------------
    # Default: ~/Disco/ — ausserhalb von iCloud, ausserhalb des Git-Repos.
    # Ueberschreibbar via .env: DISCO_WORKSPACE=/pfad/zu/workspace
    disco_workspace: str = "~/Disco"

    # Optional: explizit gesetzte Pfade ueberschreiben die abgeleiteten.
    # In der Regel leer lassen.
    disco_system_db_path: str | None = None    # default: <workspace>/system.db
    disco_projects_dir: str | None = None      # default: <workspace>/projects
    disco_logs_dir: str | None = None          # default: <workspace>/logs

    # Aktuelles Projekt (Slug). Wird vom Chat-Thread gesetzt; Tools nutzen ihn
    # spaeter (Phase 2b/c) fuer Sandboxing. Aktuell nur informational.
    disco_current_project: str | None = None

    # ------------------------------------------------------------------
    # Azure / Foundry / OpenAI / MSAL — wie gehabt
    # ------------------------------------------------------------------
    azure_doc_intel_endpoint: str | None = None
    azure_doc_intel_key: str | None = None

    azure_openai_endpoint: str | None = None
    azure_openai_key: str | None = None
    azure_openai_api_version: str = "preview"
    azure_openai_deployment: str | None = None

    msal_tenant_id: str | None = None
    msal_client_id: str | None = None

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    foundry_endpoint: str | None = None
    foundry_api_key: str | None = None
    foundry_model_deployment: str = "gpt-5"
    foundry_agent_id: str | None = None

    # ------------------------------------------------------------------
    # Pfad-Properties — alles geht durchs Workspace
    # ------------------------------------------------------------------

    @property
    def workspace_root(self) -> Path:
        """Aufgeloester, absoluter Workspace-Pfad. Wird notfalls angelegt."""
        p = Path(self.disco_workspace).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def db_path(self) -> Path:
        """System-DB (Threads, Projekte-Liste, Sources). Default: <workspace>/system.db"""
        if self.disco_system_db_path:
            p = Path(self.disco_system_db_path).expanduser()
            return p if p.is_absolute() else self.workspace_root / p
        return self.workspace_root / "system.db"

    @property
    def projects_dir(self) -> Path:
        """Wurzel aller Projekt-Verzeichnisse. Default: <workspace>/projects"""
        if self.disco_projects_dir:
            p = Path(self.disco_projects_dir).expanduser()
            base = p if p.is_absolute() else self.workspace_root / p
        else:
            base = self.workspace_root / "projects"
        base.mkdir(parents=True, exist_ok=True)
        return base

    @property
    def logs_dir(self) -> Path:
        """Service-Logs. Default: <workspace>/logs"""
        if self.disco_logs_dir:
            p = Path(self.disco_logs_dir).expanduser()
            base = p if p.is_absolute() else self.workspace_root / p
        else:
            base = self.workspace_root / "logs"
        base.mkdir(parents=True, exist_ok=True)
        return base

    # ----- Kompatibilitaet mit altem Code (data_dir) ------------------
    # Alter Code redet noch von "data_dir" als globalem Schreibraum.
    # Solange wir die Sandbox-Migration (Phase 2b/c) noch nicht durch haben,
    # zeigt data_dir auf das aktive Projekt-Verzeichnis ODER (wenn keins
    # gesetzt) auf den Workspace selbst — dann darf der Agent ueber
    # alle Projekte hinweg arbeiten (wie gehabt).
    @property
    def data_dir(self) -> Path:
        """Schreibraum fuer fs_*-Tools.

        - Wenn DISCO_CURRENT_PROJECT gesetzt: Pfad des Projekts.
        - Sonst: Workspace-Root (alle Projekte sichtbar).
        """
        if self.disco_current_project:
            p = self.projects_dir / self.disco_current_project
            p.mkdir(parents=True, exist_ok=True)
            return p
        return self.workspace_root

    @property
    def migrations_dir(self) -> Path:
        """Migrationen leben im Code-Repo, nicht im Workspace."""
        return REPO_ROOT / "migrations"

    @property
    def skills_dir(self) -> Path:
        """Skills leben im Code-Repo (zentral, versionierbar)."""
        return REPO_ROOT / "skills"

    @property
    def token_cache_path(self) -> Path:
        """MSAL-Token-Cache liegt im Workspace (nicht im Code-Repo)."""
        return self.workspace_root / ".msal_token_cache.json"


settings = Settings()
