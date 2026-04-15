"""SharePoint Metadata Snapshot + Delta Sync.

Kein Dateidownload — nur Metadaten aus dem Graph API.

Zwei Betriebsmodi:
  run_snapshot()  Erster vollständiger Lauf: alle Items + SP-Spalten erfassen,
                  deltaLink speichern.
  run_delta()     Folgeläufe: nur Änderungen seit letztem Lauf verarbeiten.

Dokument-Lebenszyklus (status):
  discovered      Gefunden in SP, noch nicht heruntergeladen
  needs_reindex   Inhalt hat sich geändert (sp_quick_xor_hash anders)
  deleted         In SP gelöscht
  downloading / downloaded / indexing / indexed  → spätere Phasen

Idempotenz:
  Ordner:    UNIQUE INDEX (source_id, sp_item_id) → INSERT OR REPLACE
  Dokumente: UNIQUE INDEX (source_id, source_item_id) → Vergleich vor Upsert
  SP-Felder: UNIQUE INDEX (document_id, field_name)   → INSERT OR REPLACE
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from ..sources import update_drive_id, update_last_synced, update_source_status
from .graph import GraphClient, GraphError

logger = logging.getLogger(__name__)

# SP-Felder die wir NICHT in document_sp_fields speichern (interne SP-Systemfelder)
_SKIP_SP_FIELDS = frozenset({
    "id", "FileRef", "FileLeafRef", "FSObjType", "UniqueId",
    "ProgId", "ScopeId", "_UIVersionString", "Modified", "Created",
    "Author", "Editor", "_HasCopyDestinations", "_CopySource",
    "owshiddenversion", "WorkflowVersion", "_UIVersion", "Attachments",
    "SMTotalSize", "SMLastModifiedDate", "SMTotalFileStreamSize",
    "SMTotalFileCount", "ParentVersionString", "ParentLeafName",
    "DocConcurrencyToken", "CheckoutUser", "VirusStatus",
    "CheckedOutTitle", "IsCheckedoutToLocal", "ContentTypeId",
    "HTML_x0020_File_x0020_Type", "_ModerationStatus",
    "_ModerationComments", "LinkFilenameNoMenu", "LinkFilename",
    "LinkFilename2", "SelectTitle", "SelectFilename", "Edit",
    "ItemChildCount", "FolderChildCount", "AppAuthor", "AppEditor",
})


# ---------------------------------------------------------------------------
# Ergebnis-Datenklassen
# ---------------------------------------------------------------------------

@dataclass
class SnapshotResult:
    source_id: int
    folders_upserted: int = 0
    files_new: int = 0
    files_updated_meta: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class DeltaResult:
    source_id: int
    files_new: int = 0
    files_updated_content: int = 0   # sp_quick_xor_hash geändert → needs_reindex
    files_updated_meta: int = 0      # nur Metadaten/SP-Felder geändert
    files_deleted: int = 0
    folders_upserted: int = 0
    errors: list[str] = field(default_factory=list)


class SyncError(Exception):
    """Fataler Fehler (z.B. Bibliothek nicht gefunden, Auth-Fehler)."""


# ---------------------------------------------------------------------------
# Haupt-Klasse
# ---------------------------------------------------------------------------

class SharePointSyncer:
    """Metadata-Only Snapshot + Delta Sync für eine SharePoint-Bibliothek.

    Args:
        conn:   Offene SQLite-Verbindung (wird nicht geschlossen).
        graph:  Initialisierter GraphClient.
        source: Row aus sources-Tabelle als dict (inkl. config_json).
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        graph: GraphClient,
        source: dict[str, Any],
    ) -> None:
        self._conn = conn
        self._graph = graph
        self._source = source
        self._source_id: int = source["id"]
        self._project_id: int = source["project_id"]
        self._config: dict[str, Any] = json.loads(source.get("config_json") or "{}")

    # ------------------------------------------------------------------
    # Öffentliche Einstiege
    # ------------------------------------------------------------------

    def run_snapshot(self) -> SnapshotResult:
        """Vollständiger Metadaten-Scan. Lädt KEINE Dateien herunter.

        Beim ersten Aufruf: alle Items erfassen + deltaLink speichern.
        Bei Folgeaufruf ohne Delta: erneuter Vollscan (überschreibt alles).

        Returns:
            SnapshotResult mit Statistiken.
        Raises:
            SyncError: Bibliothek nicht gefunden, Auth-Fehler.
        """
        result = SnapshotResult(source_id=self._source_id)
        update_source_status(self._source_id, "active")

        try:
            drive_id = self._resolve_drive()
            items_iter, delta_link = self._graph.snapshot_items(drive_id)
            self._process_items(list(items_iter), result_snapshot=result)
            self._save_delta_link(delta_link)
            update_last_synced(self._source_id)
        except SyncError:
            update_source_status(self._source_id, "error")
            raise
        except Exception as exc:
            update_source_status(self._source_id, "error")
            raise SyncError(f"Snapshot fehlgeschlagen: {exc}") from exc

        return result

    def run_delta(self) -> DeltaResult:
        """Inkrementeller Sync — nur Änderungen seit letztem Snapshot/Delta.

        Requires: sp_delta_link in sources muss gesetzt sein (nach run_snapshot).

        Returns:
            DeltaResult mit Statistiken.
        Raises:
            SyncError: Kein deltaLink vorhanden, Auth-Fehler.
        """
        result = DeltaResult(source_id=self._source_id)

        delta_link = self._load_delta_link()
        if not delta_link:
            raise SyncError(
                "Kein Delta-Link vorhanden. Bitte zuerst 'Snapshot' ausführen."
            )

        update_source_status(self._source_id, "active")
        try:
            items_iter, new_delta_link = self._graph.delta_items(delta_link)
            self._process_items(list(items_iter), result_delta=result)
            self._save_delta_link(new_delta_link)
            update_last_synced(self._source_id)
        except SyncError:
            update_source_status(self._source_id, "error")
            raise
        except Exception as exc:
            update_source_status(self._source_id, "error")
            raise SyncError(f"Delta-Sync fehlgeschlagen: {exc}") from exc

        return result

    # ------------------------------------------------------------------
    # Item-Verarbeitung (gemeinsam für Snapshot + Delta)
    # ------------------------------------------------------------------

    def _process_items(
        self,
        items: list[dict],
        result_snapshot: SnapshotResult | None = None,
        result_delta: DeltaResult | None = None,
    ) -> None:
        """Verarbeitet eine Liste von DriveItems (Ordner + Dateien + gelöschte)."""
        # Erst Ordner (für parent_id-Mapping), dann Dateien
        folders = [i for i in items if "folder" in i and not i.get("deleted")]
        files   = [i for i in items if "file"   in i and not i.get("deleted")]
        deleted = [i for i in items if i.get("deleted")]

        # Ordner-Mapping aufbauen
        folder_map = self._load_folder_map()

        for item in folders:
            try:
                db_id = self._upsert_folder(item, folder_map)
                folder_map[item["id"]] = db_id
                if result_snapshot:
                    result_snapshot.folders_upserted += 1
                elif result_delta:
                    result_delta.folders_upserted += 1
            except Exception as exc:
                msg = f"Ordner {item.get('name')}: {exc}"
                logger.warning(msg)
                if result_snapshot:
                    result_snapshot.errors.append(msg)
                elif result_delta:
                    result_delta.errors.append(msg)

        for item in files:
            try:
                self._upsert_file(item, folder_map, result_snapshot, result_delta)
            except Exception as exc:
                msg = f"{item.get('name', item.get('id'))}: {exc}"
                logger.warning("Datei-Fehler: %s", msg)
                if result_snapshot:
                    result_snapshot.errors.append(msg)
                    result_snapshot.files_failed += 1
                elif result_delta:
                    result_delta.errors.append(msg)

        for item in deleted:
            try:
                self._mark_deleted(item)
                if result_delta:
                    result_delta.files_deleted += 1
            except Exception as exc:
                logger.warning("Lösch-Fehler %s: %s", item.get("id"), exc)

    # ------------------------------------------------------------------
    # Ordner
    # ------------------------------------------------------------------

    def _load_folder_map(self) -> dict[str, int]:
        """Lädt alle bekannten sp_item_id → db_id Mappings dieser Quelle."""
        rows = self._conn.execute(
            "SELECT sp_item_id, id FROM source_folders WHERE source_id = ?",
            (self._source_id,),
        ).fetchall()
        return {r["sp_item_id"]: r["id"] for r in rows}

    def _upsert_folder(self, item: dict, folder_map: dict[str, int]) -> int:
        """Legt einen Ordner an oder aktualisiert ihn. Gibt DB-id zurück."""
        sp_item_id  = item["id"]
        name        = item.get("name", "")
        parent_ref  = item.get("parentReference", {})
        parent_sp_id = parent_ref.get("id")
        parent_path  = parent_ref.get("path", "")
        sp_web_url   = item.get("webUrl")

        # Vollpfad berechnen
        sp_path = parent_path + "/" + name if parent_path else name

        # Root-Ordner: kein parent_id
        if parent_path.endswith(":/root:") or parent_path.endswith("/root"):
            parent_db_id = None
        else:
            parent_db_id = folder_map.get(parent_sp_id) if parent_sp_id else None

        self._conn.execute(
            """
            INSERT INTO source_folders
                (source_id, parent_id, sp_item_id, name, sp_path, sp_web_url, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(source_id, sp_item_id) DO UPDATE SET
                parent_id  = excluded.parent_id,
                name       = excluded.name,
                sp_path    = excluded.sp_path,
                sp_web_url = excluded.sp_web_url,
                updated_at = excluded.updated_at
            """,
            (self._source_id, parent_db_id, sp_item_id, name, sp_path, sp_web_url),
        )
        self._conn.commit()

        row = self._conn.execute(
            "SELECT id FROM source_folders WHERE source_id = ? AND sp_item_id = ?",
            (self._source_id, sp_item_id),
        ).fetchone()
        return row["id"]

    # ------------------------------------------------------------------
    # Dateien
    # ------------------------------------------------------------------

    def _upsert_file(
        self,
        item: dict,
        folder_map: dict[str, int],
        result_snapshot: SnapshotResult | None,
        result_delta: DeltaResult | None,
    ) -> None:
        """Legt ein Dokument an oder aktualisiert Metadaten + SP-Felder."""
        sp_item_id    = item["id"]
        name          = item.get("name", "")
        size_bytes    = item.get("size", 0)
        sp_web_url    = item.get("webUrl")
        mime_type     = item.get("file", {}).get("mimeType") or "application/octet-stream"
        new_hash      = item.get("file", {}).get("hashes", {}).get("quickXorHash")

        parent_ref    = item.get("parentReference", {})
        sp_path       = parent_ref.get("path", "") + "/" + name
        sp_modified_at = item.get("lastModifiedDateTime")
        sp_created_at  = item.get("createdDateTime")
        sp_modified_by = _user_name(item.get("lastModifiedBy"))
        sp_created_by  = _user_name(item.get("createdBy"))

        list_item      = item.get("listItem") or {}
        sp_list_item_id = list_item.get("id")
        sp_content_type = (list_item.get("contentType") or {}).get("name")
        sp_fields       = list_item.get("fields") or {}

        # Vorhandenes Dokument suchen
        existing = self._conn.execute(
            "SELECT id, sp_quick_xor_hash FROM documents "
            "WHERE source_id = ? AND source_item_id = ?",
            (self._source_id, sp_item_id),
        ).fetchone()

        if existing:
            doc_id       = existing["id"]
            old_hash     = existing["sp_quick_xor_hash"]
            content_changed = new_hash and old_hash and new_hash != old_hash

            new_status = "needs_reindex" if content_changed else None  # None = unverändert lassen

            self._conn.execute(
                """
                UPDATE documents SET
                    original_name     = ?,
                    size_bytes        = ?,
                    mime_type         = ?,
                    sp_modified_at    = ?,
                    sp_created_at     = ?,
                    sp_modified_by    = ?,
                    sp_created_by     = ?,
                    sp_web_url        = ?,
                    sp_quick_xor_hash = ?,
                    sp_content_type   = ?,
                    sp_list_item_id   = ?,
                    source_path       = ?,
                    status            = COALESCE(?, status),
                    updated_at        = datetime('now')
                WHERE id = ?
                """,
                (
                    name, size_bytes, mime_type,
                    sp_modified_at, sp_created_at, sp_modified_by, sp_created_by,
                    sp_web_url, new_hash, sp_content_type, sp_list_item_id,
                    sp_path, new_status,
                    doc_id,
                ),
            )
            self._conn.commit()
            self._upsert_sp_fields(doc_id, sp_fields)

            if result_snapshot:
                result_snapshot.files_updated_meta += 1
            elif result_delta:
                if content_changed:
                    result_delta.files_updated_content += 1
                else:
                    result_delta.files_updated_meta += 1
        else:
            # Neues Dokument
            cur = self._conn.execute(
                """
                INSERT INTO documents (
                    original_name, relative_path, size_bytes, mime_type, status,
                    sp_modified_at, sp_created_at, sp_modified_by, sp_created_by,
                    sp_web_url, sp_quick_xor_hash, sp_content_type, sp_list_item_id,
                    project_id, source_id, source_item_id, source_path
                ) VALUES (
                    ?, '', ?, ?, 'discovered',
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?
                )
                """,
                (
                    name, size_bytes, mime_type,
                    sp_modified_at, sp_created_at, sp_modified_by, sp_created_by,
                    sp_web_url, new_hash, sp_content_type, sp_list_item_id,
                    self._project_id, self._source_id, sp_item_id, sp_path,
                ),
            )
            self._conn.commit()
            doc_id = cur.lastrowid
            self._upsert_sp_fields(doc_id, sp_fields)
            self._log_event(doc_id, "sp_snapshot_new", "ok")

            if result_snapshot:
                result_snapshot.files_new += 1
            elif result_delta:
                result_delta.files_new += 1

    def _upsert_sp_fields(self, doc_id: int, fields: dict[str, Any]) -> None:
        """Schreibt SP-Bibliotheksspalten in document_sp_fields."""
        for key, value in fields.items():
            if key in _SKIP_SP_FIELDS:
                continue
            if value is None:
                continue
            # Wert als Text normalisieren
            if isinstance(value, (dict, list)):
                text_value = json.dumps(value, ensure_ascii=False)
            else:
                text_value = str(value)

            self._conn.execute(
                """
                INSERT INTO document_sp_fields (document_id, field_name, field_value, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(document_id, field_name) DO UPDATE SET
                    field_value = excluded.field_value,
                    updated_at  = excluded.updated_at
                """,
                (doc_id, key, text_value),
            )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Gelöschte Items
    # ------------------------------------------------------------------

    def _mark_deleted(self, item: dict) -> None:
        """Setzt Status 'deleted' für ein in SP gelöschtes Dokument."""
        sp_item_id = item.get("id")
        if not sp_item_id:
            return
        self._conn.execute(
            "UPDATE documents SET status = 'deleted', updated_at = datetime('now') "
            "WHERE source_id = ? AND source_item_id = ?",
            (self._source_id, sp_item_id),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Drive auflösen
    # ------------------------------------------------------------------

    def _resolve_drive(self) -> str:
        """Gibt die drive_id zurück, löst sie auf wenn nötig."""
        if self._config.get("drive_id"):
            return self._config["drive_id"]

        site_url     = self._config.get("site_url", "")
        library_name = self._config.get("library_name", "")

        if not site_url:
            raise SyncError("Keine site_url in der Quellen-Konfiguration.")

        logger.info("Löse Site-ID auf: %s", site_url)
        site_id = self._graph.resolve_site_id(site_url)

        logger.info("Suche Bibliothek '%s' ...", library_name)
        drive = self._graph.find_drive_by_name(site_id, library_name)
        if drive is None:
            raise SyncError(
                f"Bibliothek '{library_name}' nicht in Site {site_url} gefunden."
            )

        drive_id = drive["id"]
        update_drive_id(self._source_id, drive_id)
        self._config["drive_id"] = drive_id
        logger.info("Drive-ID: %s", drive_id)
        return drive_id

    # ------------------------------------------------------------------
    # Delta-Link
    # ------------------------------------------------------------------

    def _load_delta_link(self) -> str | None:
        row = self._conn.execute(
            "SELECT sp_delta_link FROM sources WHERE id = ?",
            (self._source_id,),
        ).fetchone()
        return row["sp_delta_link"] if row else None

    def _save_delta_link(self, delta_link: str) -> None:
        self._conn.execute(
            "UPDATE sources SET sp_delta_link = ?, updated_at = datetime('now') WHERE id = ?",
            (delta_link, self._source_id),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_event(
        self,
        document_id: int,
        step: str,
        status: str,
        error_message: str | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO processing_events (document_id, step, status, error_message) "
            "VALUES (?, ?, ?, ?)",
            (document_id, step, status, error_message),
        )
        self._conn.commit()


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _user_name(user_obj: dict | None) -> str | None:
    """Extrahiert den Anzeigenamen aus einem createdBy/lastModifiedBy-Objekt."""
    if not user_obj:
        return None
    return (
        user_obj.get("user", {}).get("displayName")
        or user_obj.get("application", {}).get("displayName")
    )
