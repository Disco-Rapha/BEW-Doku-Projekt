"""Microsoft Graph API Client für SharePoint-Zugriff.

Synchrones httpx wird verwendet (kein async) — kompatibel mit Streamlit
und einfacherem Threading-Modell. Alle API-Calls gehen gegen
https://graph.microsoft.com/v1.0.

Referenz: https://learn.microsoft.com/en-us/graph/api/resources/driveitem
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import httpx

from .auth import MSALTokenManager, FILES_SCOPES

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
# Maximale Seitengröße für Listen-Endpunkte
PAGE_SIZE = 200


class GraphError(Exception):
    """Wird bei HTTP-Fehlern (4xx/5xx) vom Graph-API geworfen."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"Graph API Fehler {status_code}: {message}")


class GraphClient:
    """Thin wrapper um httpx für Microsoft Graph API Calls.

    Args:
        token_manager: MSALTokenManager für Token-Beschaffung.
        timeout: HTTP-Timeout in Sekunden (Default 60s für Downloads).
    """

    def __init__(self, token_manager: MSALTokenManager, timeout: float = 60.0) -> None:
        self._token_mgr = token_manager
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Sites & Drives
    # ------------------------------------------------------------------

    def resolve_site_id(self, site_url: str) -> str:
        """Löst eine SharePoint-Site-URL zu einer Graph-Site-ID auf.

        Args:
            site_url: Vollständige URL, z.B. https://tenant.sharepoint.com/sites/MySite
        Returns:
            Site-ID als String (Format: hostname,site-id,web-id)
        """
        # Graph erwartet: /sites/{hostname}:{relative_path}
        # z.B. /sites/tenant.sharepoint.com:/sites/MySite
        from urllib.parse import urlparse
        parsed = urlparse(site_url)
        hostname = parsed.netloc
        site_path = parsed.path.rstrip("/")
        endpoint = f"/sites/{hostname}:{site_path}"
        data = self._get(endpoint)
        return data["id"]

    def get_drives(self, site_id: str) -> list[dict]:
        """Gibt alle Drives (Bibliotheken) einer Site zurück.

        Returns:
            Liste von Drive-dicts mit id, name, driveType.
        """
        data = self._get(f"/sites/{site_id}/drives")
        return data.get("value", [])

    def find_drive_by_name(self, site_id: str, library_name: str) -> dict | None:
        """Sucht eine Bibliothek anhand des Namens. Gibt None zurück wenn nicht gefunden."""
        drives = self.get_drives(site_id)
        for drive in drives:
            if drive.get("name", "").lower() == library_name.lower():
                return drive
        return None

    # ------------------------------------------------------------------
    # Ordner & Dateien
    # ------------------------------------------------------------------

    def get_root_children(self, drive_id: str) -> list[dict]:
        """Gibt DriveItems im Root-Verzeichnis einer Bibliothek zurück."""
        data = self._get(f"/drives/{drive_id}/root/children?$top={PAGE_SIZE}")
        return data.get("value", [])

    def get_item_children(self, drive_id: str, item_id: str) -> list[dict]:
        """Gibt direkte Kinder eines Ordners zurück."""
        data = self._get(
            f"/drives/{drive_id}/items/{item_id}/children?$top={PAGE_SIZE}"
        )
        return data.get("value", [])

    def list_all_items(self, drive_id: str) -> Iterator[dict]:
        """Iteriert über alle DriveItems (Ordner und Dateien) einer Bibliothek.

        Verwendet BFS (Breadth-First-Search) mit Pagination.
        Jedes Item wird einmalig geliefert.

        Yields:
            DriveItem-dicts mit id, name, file/folder-Eigenschaft, parentReference, etc.
        """
        queue: list[str | None] = [None]  # None = Root
        while queue:
            parent_id = queue.pop(0)
            if parent_id is None:
                url = f"/drives/{drive_id}/root/children?$top={PAGE_SIZE}"
            else:
                url = f"/drives/{drive_id}/items/{parent_id}/children?$top={PAGE_SIZE}"

            while url:
                data = self._get_absolute(url) if url.startswith("https://") else self._get(url)
                items = data.get("value", [])
                for item in items:
                    yield item
                    if "folder" in item:
                        queue.append(item["id"])
                # Pagination: @odata.nextLink
                url = data.get("@odata.nextLink")

    def list_all_folders(self, drive_id: str) -> Iterator[dict]:
        """Iteriert nur über Ordner (keine Dateien)."""
        for item in self.list_all_items(drive_id):
            if "folder" in item:
                yield item

    def list_all_files(self, drive_id: str) -> Iterator[dict]:
        """Iteriert nur über Dateien (keine Ordner)."""
        for item in self.list_all_items(drive_id):
            if "file" in item:
                yield item

    def get_item(self, drive_id: str, item_id: str) -> dict:
        """Gibt ein einzelnes DriveItem zurück."""
        return self._get(f"/drives/{drive_id}/items/{item_id}")

    # ------------------------------------------------------------------
    # Snapshot + Delta (Metadaten inkl. SP-Spalten, kein Download)
    # ------------------------------------------------------------------

    # Felder die wir für jeden Item abrufen
    _SNAPSHOT_SELECT = (
        "id,name,size,file,folder,webUrl,"
        "lastModifiedDateTime,createdDateTime,"
        "parentReference,createdBy,lastModifiedBy,deleted"
    )

    def snapshot_items(self, drive_id: str) -> tuple[Iterator[dict], str]:
        """Vollständiger Metadaten-Scan einer Bibliothek via Delta-Endpunkt.

        Der Delta-Endpunkt liefert beim ersten Aufruf ALLE Items + einen
        deltaLink für spätere inkrementelle Abfragen.

        SP-Bibliotheksspalten werden via $expand=listItem($expand=fields)
        mitgeliefert.

        Returns:
            (items_iterator, delta_link)
            items_iterator: alle DriveItems (Ordner + Dateien)
            delta_link: für nachfolgende delta_items()-Aufrufe speichern
        """
        url = (
            f"{GRAPH_BASE}/drives/{drive_id}/root/delta"
            f"?$select={self._SNAPSHOT_SELECT}"
            f"&$expand=listItem($expand=fields)"
            f"&$top={PAGE_SIZE}"
        )
        items, delta_link = self._collect_delta_pages(url)
        return iter(items), delta_link

    def delta_items(self, delta_link: str) -> tuple[Iterator[dict], str]:
        """Inkrementelle Änderungen seit dem letzten Snapshot/Delta-Aufruf.

        Verwendet den gespeicherten deltaLink aus dem vorherigen Lauf.
        Liefert nur neue, geänderte und gelöschte Items.

        Gelöschte Items erkennbar an: item.get("deleted") is not None

        Returns:
            (items_iterator, new_delta_link)
        """
        items, new_delta_link = self._collect_delta_pages(delta_link)
        return iter(items), new_delta_link

    def _collect_delta_pages(self, start_url: str) -> tuple[list[dict], str]:
        """Paginiert durch alle Delta-Seiten und sammelt Items + finalen deltaLink."""
        items: list[dict] = []
        delta_link: str = ""
        url: str | None = start_url

        while url:
            data = self._get_absolute(url) if url.startswith("https://") else self._get(url)
            items.extend(data.get("value", []))

            if "@odata.deltaLink" in data:
                delta_link = data["@odata.deltaLink"]
                url = None
            else:
                url = data.get("@odata.nextLink")

        return items, delta_link

    # ------------------------------------------------------------------
    # Downloads
    # ------------------------------------------------------------------

    def download_file(self, drive_id: str, item_id: str, dest_path: Path) -> None:
        """Lädt eine Datei herunter und speichert sie unter dest_path.

        Verwendet Streaming um Speicher zu schonen.
        Erstellt übergeordnete Verzeichnisse automatisch.

        Raises:
            GraphError: Bei HTTP-Fehler.
        """
        token = self._token_mgr.get_token(FILES_SCOPES)
        url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content"
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        with httpx.stream(
            "GET",
            url,
            headers={"Authorization": f"Bearer {token}"},
            follow_redirects=True,
            timeout=self._timeout,
        ) as resp:
            if resp.status_code >= 400:
                raise GraphError(resp.status_code, resp.text)
            with dest_path.open("wb") as f:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    f.write(chunk)

    # ------------------------------------------------------------------
    # Interna
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        token = self._token_mgr.get_token(FILES_SCOPES)
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

    def _get(self, path: str) -> dict:
        """GET-Request gegen GRAPH_BASE + path."""
        url = f"{GRAPH_BASE}{path}"
        return self._get_absolute(url)

    def _get_absolute(self, url: str) -> dict:
        """GET-Request gegen eine vollständige URL (z.B. nextLink)."""
        resp = httpx.get(url, headers=self._headers(), timeout=self._timeout)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                detail = resp.text
            raise GraphError(resp.status_code, detail)
        return resp.json()
