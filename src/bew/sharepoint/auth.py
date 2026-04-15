"""MSAL-basierter Token-Manager für Microsoft 365 / SharePoint.

Verwendet den OAuth2 Device Authorization Grant (Device Flow):
- Der Benutzer öffnet eine URL im Browser und gibt einen Code ein.
- Nach erfolgreichem Login wird ein Access- und Refresh-Token lokal gecacht.
- Folge-Aufrufe lösen das Token still (silent acquire) aus dem Cache auf.

Der Token-Cache liegt als JSON-Datei unter data/.msal_token_cache.json
(gitignored, enthält OAuth2-Refresh-Token).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import msal

from ..config import settings

logger = logging.getLogger(__name__)

# Scopes für SharePoint-Lesezugriff via Microsoft Graph
FILES_SCOPES = ["https://graph.microsoft.com/Files.Read.All"]


class MSALAuthError(Exception):
    """Wird geworfen wenn Authentifizierung dauerhaft fehlschlägt."""


class MSALTokenManager:
    """Verwaltet OAuth2 Device-Flow-Login und Token-Cache für Microsoft 365.

    Args:
        tenant_id: Azure Entra ID Tenant-ID (GUID).
        client_id: App-Registrierungs-Client-ID (GUID).
        cache_path: Pfad zur Token-Cache-Datei. Default: data/.msal_token_cache.json
    """

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        cache_path: Optional[Path] = None,
    ) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._cache_path = cache_path or settings.token_cache_path
        self._cache = msal.SerializableTokenCache()
        self._app: Optional[msal.PublicClientApplication] = None

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def get_token(
        self,
        scopes: list[str] | None = None,
        force_interactive: bool = False,
    ) -> str | None:
        """Gibt ein gültiges Access-Token zurück.

        Ablauf:
        1. Cache-Datei laden.
        2. Silent acquire versuchen (Refresh-Token im Cache).
        3. Wenn nicht möglich oder force_interactive=True: Device Flow starten.
        4. Cache persistieren.

        Returns:
            Access-Token als str, oder None bei Abbruch durch Benutzer.
        Raises:
            MSALAuthError: Bei dauerhaftem Fehler (z.B. ungültige Client-ID).
        """
        if scopes is None:
            scopes = FILES_SCOPES

        self._load_cache()
        app = self._build_app()

        # 1. Silent acquire (aus Cache)
        if not force_interactive:
            accounts = app.get_accounts()
            if accounts:
                result = app.acquire_token_silent(scopes, account=accounts[0])
                if result and "access_token" in result:
                    self._save_cache()
                    return result["access_token"]

        # 2. Device Flow
        flow = app.initiate_device_flow(scopes=scopes)
        if "user_code" not in flow:
            raise MSALAuthError(
                f"Device-Flow konnte nicht gestartet werden: {flow.get('error_description', flow)}"
            )

        # Anweisung ausgeben — wird sowohl in CLI als auch in Streamlit angezeigt
        print(flow["message"])  # noqa: T201 — bewusst print für interaktiven Flow

        result = app.acquire_token_by_device_flow(flow)

        if "access_token" in result:
            self._save_cache()
            return result["access_token"]
        elif result.get("error") == "authorization_declined":
            return None
        else:
            raise MSALAuthError(
                f"Login fehlgeschlagen: {result.get('error_description', result.get('error'))}"
            )

    def is_authenticated(self) -> bool:
        """True wenn mindestens ein Konto mit gültigem Token im Cache liegt."""
        self._load_cache()
        app = self._build_app()
        accounts = app.get_accounts()
        if not accounts:
            return False
        # Silent acquire prüfen — gibt None zurück wenn Token abgelaufen und kein Refresh möglich
        result = app.acquire_token_silent(FILES_SCOPES, account=accounts[0])
        return result is not None and "access_token" in result

    def clear_cache(self) -> None:
        """Löscht den Token-Cache (Cache-Datei und In-Memory-Cache)."""
        if self._cache_path.exists():
            self._cache_path.unlink()
        self._cache = msal.SerializableTokenCache()
        self._app = None

    def get_username(self) -> str | None:
        """Gibt den Benutzernamen des angemeldeten Kontos zurück, oder None."""
        self._load_cache()
        app = self._build_app()
        accounts = app.get_accounts()
        if accounts:
            return accounts[0].get("username")
        return None

    # ------------------------------------------------------------------
    # Interna
    # ------------------------------------------------------------------

    def _load_cache(self) -> None:
        """Liest Cache aus Datei, falls vorhanden."""
        if self._cache_path.exists():
            try:
                self._cache.deserialize(self._cache_path.read_text(encoding="utf-8"))
            except Exception:
                logger.warning("Token-Cache konnte nicht gelesen werden — wird ignoriert.")

    def _save_cache(self) -> None:
        """Schreibt Cache zurück wenn er sich geändert hat."""
        if self._cache.has_state_changed:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(
                self._cache.serialize(), encoding="utf-8"
            )
            # Berechtigungen einschränken (nur Eigentümer lesen/schreiben)
            try:
                self._cache_path.chmod(0o600)
            except OSError:
                pass  # Windows unterstützt chmod nicht vollständig

    def _build_app(self) -> msal.PublicClientApplication:
        """Erstellt MSAL PublicClientApplication (einmal, dann gecacht)."""
        if self._app is None:
            authority = f"https://login.microsoftonline.com/{self._tenant_id}"
            self._app = msal.PublicClientApplication(
                client_id=self._client_id,
                authority=authority,
                token_cache=self._cache,
            )
        return self._app
