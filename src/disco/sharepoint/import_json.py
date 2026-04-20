"""Importiert SharePoint REST-API JSON-Exporte in die lokale DB.

Kein Graph-API-Zugang nötig — der Nutzer exportiert die Bibliotheksdaten direkt
im Browser per DevTools-Script und importiert die resultierende JSON-Datei hier.

JSON-Formate die akzeptiert werden:
    - Direkte Liste (Browser-Script-Output):         [{"Id": 1, ...}, ...]
    - odata=nometadata:                              {"value": [...]}
    - odata=verbose:                                 {"d": {"results": [...]}}

Idempotenz:
    UNIQUE INDEX (source_id, source_item_id) → mehrfache Imports sind safe.
    Bestehende Dokumente werden aktualisiert, neue angelegt.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..sources import get_source, parse_config, update_last_synced, update_source_status

logger = logging.getLogger(__name__)

# Felder die NICHT in document_sp_fields gespeichert werden (SP-System-intern)
_SKIP_REST_FIELDS = frozenset({
    # OData-Metadaten
    "odata.type", "odata.id", "odata.etag", "odata.editLink",
    # Datei-/Ordner-Identifikatoren
    "FileSystemObjectType", "FSObjType",
    "Id", "ID", "GUID", "UniqueId",
    # Pfad und Name
    "FileLeafRef", "FileRef", "File_x0020_Type",
    "ParentVersionString", "ParentLeafName",
    # Zeitstempel und Autoren (werden direkt auf Spalten gemappt)
    "Modified", "Created",
    "Author", "Editor", "AuthorId", "EditorId",
    "AppAuthor", "AppEditor", "AppAuthorId", "AppEditorId",
    # Datei-/Ordner-Objekte
    "File", "Folder",
    "FileSizeDisplay",
    # Content-Type
    "ContentTypeId", "ContentType", "ComplianceAssetId",
    # SP-Interna
    "owshiddenversion", "WorkflowVersion",
    "_UIVersionString", "OData__UIVersionString", "OData__x005f_UIVersionString",
    "_ModerationStatus", "_ModerationComments",
    "_HasCopyDestinations", "_CopySource",
    "Attachments", "SMTotalSize", "SMLastModifiedDate",
    "SMTotalFileStreamSize", "SMTotalFileCount",
    "CheckoutUser", "CheckedOutUserId", "CheckedOutTitle",
    "IsCheckedoutToLocal", "VirusStatus",
    "ItemChildCount", "FolderChildCount",
    "Edit", "LinkFilenameNoMenu", "LinkFilename", "LinkFilename2",
    "SelectTitle", "SelectFilename", "DocIcon",
    "HTML_x0020_File_x0020_Type",
    "ProgId", "ScopeId", "MetaInfo", "Restricted",
    "InstanceID", "Order", "WorkflowInstanceID", "SyncClientId",
    "_CheckinComment", "Thumbnail",
    "ServerRedirectedEmbedUri", "ServerRedirectedEmbedUrl",
})

# Einfache Dateiendung → MIME-Typ Tabelle
_EXT_MIME: dict[str, str] = {
    "pdf":  "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc":  "application/msword",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls":  "application/vnd.ms-excel",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt":  "application/vnd.ms-powerpoint",
    "txt":  "text/plain",
    "csv":  "text/csv",
    "zip":  "application/zip",
    "png":  "image/png",
    "jpg":  "image/jpeg",
    "jpeg": "image/jpeg",
    "msg":  "application/vnd.ms-outlook",
}


# ---------------------------------------------------------------------------
# Ergebnis-Datenklasse
# ---------------------------------------------------------------------------

@dataclass
class ImportResult:
    source_id: int
    folders_upserted: int = 0
    files_new: int = 0
    files_updated: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Importer
# ---------------------------------------------------------------------------

class SharePointJSONImporter:
    """Importiert einen SP REST-API JSON-Export in die lokale DB.

    Args:
        conn:      Offene SQLite-Verbindung (wird nicht geschlossen).
        source_id: Ziel-Quelle in der DB.
    """

    def __init__(self, conn: sqlite3.Connection, source_id: int) -> None:
        self._conn = conn
        self._source_id = source_id

        source = get_source(source_id)
        self._project_id: int = source["project_id"]
        cfg = parse_config(source)
        self._site_url: str = cfg.get("site_url", "").rstrip("/")
        self._library_name: str = cfg.get("library_name", "Dokumente")

        # Wird nach dem Laden der Items ggf. verfeinert
        self._library_prefix: str = self._compute_library_prefix()
        self._site_base: str = self._compute_site_base()

    # ------------------------------------------------------------------
    # Öffentlicher Einstieg
    # ------------------------------------------------------------------

    def run(self, json_path: Path) -> ImportResult:
        """Liest JSON-Datei und importiert alle Items in die DB."""
        result = ImportResult(source_id=self._source_id)
        update_source_status(self._source_id, "active")

        items = self._load_items(json_path)
        logger.info("Importiere %d Items aus '%s'", len(items), json_path.name)

        # Library-Prefix anhand echter Daten verfeinern
        self._refine_library_prefix(items)

        folders = [i for i in items if self._is_folder(i)]
        files   = [i for i in items if not self._is_folder(i) and i.get("FileLeafRef")]

        folder_map = self._load_folder_map()
        for item in folders:
            try:
                db_id = self._upsert_folder(item, folder_map)
                folder_map[self._item_sp_id(item)] = db_id
                result.folders_upserted += 1
            except Exception as exc:
                msg = f"Ordner '{item.get('FileLeafRef')}': {exc}"
                logger.warning(msg)
                result.errors.append(msg)

        for item in files:
            try:
                self._upsert_file(item, result)
            except Exception as exc:
                msg = f"Datei '{item.get('FileLeafRef')}': {exc}"
                logger.warning(msg)
                result.errors.append(msg)

        update_last_synced(self._source_id)
        return result

    # ------------------------------------------------------------------
    # JSON laden und normalisieren
    # ------------------------------------------------------------------

    def _load_items(self, json_path: Path) -> list[dict]:
        raw = json.loads(json_path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            # odata=verbose: {"d": {"results": [...]}}
            if "d" in raw and isinstance(raw["d"], dict) and "results" in raw["d"]:
                return raw["d"]["results"]
            # odata=nometadata: {"value": [...]}
            if "value" in raw and isinstance(raw["value"], list):
                return raw["value"]
        raise ValueError(
            f"Unbekanntes JSON-Format. Erwartete Liste oder dict mit 'value'/'d.results'. "
            f"Gefundene Keys: {list(raw.keys())[:5] if isinstance(raw, dict) else type(raw)}"
        )

    # ------------------------------------------------------------------
    # Pfad- und URL-Berechnungen
    # ------------------------------------------------------------------

    def _compute_library_prefix(self) -> str:
        """Berechnet den server-relativen Bibliotheks-Pfad aus der Konfiguration."""
        if not self._site_url:
            return ""
        parsed = urlparse(self._site_url)
        return parsed.path.rstrip("/") + "/" + self._library_name + "/"

    def _compute_site_base(self) -> str:
        """Gibt https://hostname zurück."""
        if not self._site_url:
            return ""
        parsed = urlparse(self._site_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _refine_library_prefix(self, items: list[dict]) -> None:
        """Verfeinert den Library-Prefix anhand echter FileRef-Werte.

        Nötig falls der Bibliotheksname vom Pfad abweicht (z.B. 'Documents' vs 'Dokumente').
        """
        refs = [
            i["FileRef"] for i in items
            if i.get("FileRef") and not self._is_folder(i)
        ]
        if not refs:
            return

        # Tiefe des Site-Pfades ermitteln (z.B. /sites/MySite → depth 2)
        parsed = urlparse(self._site_url)
        site_depth = len([p for p in parsed.path.strip("/").split("/") if p])
        lib_depth = site_depth + 1  # + 1 für den Bibliotheks-Ordner

        parts_list = [r.lstrip("/").split("/") for r in refs]
        # Gemeinsamer Prefix bis zur Bibliotheks-Ebene
        candidate = parts_list[0][:lib_depth]
        if all(p[:lib_depth] == candidate for p in parts_list):
            self._library_prefix = "/" + "/".join(candidate) + "/"
            logger.debug("Library-Prefix verfeinert: %s", self._library_prefix)

    def _source_path(self, file_ref: str) -> str:
        """Relativer Pfad innerhalb der Bibliothek (ohne Library-Prefix)."""
        if self._library_prefix and file_ref.startswith(self._library_prefix):
            return file_ref[len(self._library_prefix):]
        # Fallback: führendes / entfernen
        return file_ref.lstrip("/")

    def _sp_web_url(self, file_ref: str) -> str | None:
        if not self._site_base or not file_ref:
            return None
        return self._site_base + file_ref

    # ------------------------------------------------------------------
    # Feld-Hilfsmethoden
    # ------------------------------------------------------------------

    @staticmethod
    def _is_folder(item: dict) -> bool:
        return item.get("FileSystemObjectType", item.get("FSObjType", 0)) == 1

    @staticmethod
    def _item_sp_id(item: dict) -> str:
        """Stabile eindeutige ID (GUID bevorzugt, Fallback auf list-item-ID)."""
        guid = item.get("GUID") or item.get("UniqueId")
        if guid:
            return guid
        item_id = item.get("Id") or item.get("ID")
        return f"sp_list_{item_id}" if item_id else "sp_unknown"

    @staticmethod
    def _user_title(user_field: Any) -> str | None:
        """Extrahiert den Anzeigenamen aus Author/Editor-Feldern."""
        if isinstance(user_field, dict):
            return user_field.get("Title") or user_field.get("Name")
        if isinstance(user_field, str) and ";#" in user_field:
            # SP-Lookup-Format: "1;#John Doe"
            return user_field.split(";#", 1)[1]
        return None

    @staticmethod
    def _parse_size(item: dict) -> int:
        """Liest die Dateigröße in Bytes (File.Length ist String in SP REST API)."""
        file_obj = item.get("File") or {}
        length = file_obj.get("Length")
        if length is not None:
            try:
                return int(str(length))
            except (ValueError, TypeError):
                pass
        # FileSizeDisplay wie "12,3 KB" als Fallback
        display = re.sub(r"[^\d.]", "", str(item.get("FileSizeDisplay", "")))
        if display:
            try:
                return int(float(display))
            except ValueError:
                pass
        return 0

    @staticmethod
    def _custom_fields(item: dict) -> dict[str, str]:
        """Alle Custom-Felder als String-Dict (ohne SP-Systemfelder)."""
        result: dict[str, str] = {}
        for key, value in item.items():
            if key in _SKIP_REST_FIELDS:
                continue
            if value is None:
                continue
            # Verschachtelte Objekte (expandierte Lookups) überspringen
            if isinstance(value, (dict, list)):
                continue
            result[key] = str(value)
        return result

    # ------------------------------------------------------------------
    # DB-Operationen
    # ------------------------------------------------------------------

    def _load_folder_map(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT sp_item_id, id FROM source_folders WHERE source_id = ?",
            (self._source_id,),
        ).fetchall()
        return {r["sp_item_id"]: r["id"] for r in rows}

    def _upsert_folder(self, item: dict, folder_map: dict[str, int]) -> int:
        sp_id      = self._item_sp_id(item)
        name       = item.get("FileLeafRef", "")
        file_ref   = item.get("FileRef", "")
        sp_path    = self._source_path(file_ref)
        sp_web_url = self._sp_web_url(file_ref)

        self._conn.execute(
            """
            INSERT INTO source_folders
                (source_id, parent_id, sp_item_id, name, sp_path, sp_web_url, updated_at)
            VALUES (?, NULL, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(source_id, sp_item_id) DO UPDATE SET
                name       = excluded.name,
                sp_path    = excluded.sp_path,
                sp_web_url = excluded.sp_web_url,
                updated_at = excluded.updated_at
            """,
            (self._source_id, sp_id, name, sp_path, sp_web_url),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT id FROM source_folders WHERE source_id = ? AND sp_item_id = ?",
            (self._source_id, sp_id),
        ).fetchone()
        return row["id"]

    def _upsert_file(self, item: dict, result: ImportResult) -> None:
        sp_id      = self._item_sp_id(item)
        name       = item.get("FileLeafRef", "")
        file_ref   = item.get("FileRef", "")
        size       = self._parse_size(item)
        sp_path    = self._source_path(file_ref)
        sp_web_url = self._sp_web_url(file_ref)

        modified_at  = item.get("Modified")
        created_at   = item.get("Created")
        modified_by  = self._user_title(item.get("Editor"))
        created_by   = self._user_title(item.get("Author"))
        list_item_id = str(item.get("Id") or item.get("ID") or "")
        content_type = str(item.get("ContentType") or "")[:200]
        file_ext     = str(item.get("File_x0020_Type") or "").lower().lstrip(".")
        mime_type    = _EXT_MIME.get(file_ext, "application/octet-stream")
        custom       = self._custom_fields(item)

        existing = self._conn.execute(
            "SELECT id FROM documents WHERE source_id = ? AND source_item_id = ?",
            (self._source_id, sp_id),
        ).fetchone()

        if existing:
            doc_id = existing["id"]
            self._conn.execute(
                """
                UPDATE documents SET
                    original_name   = ?,
                    size_bytes      = ?,
                    mime_type       = ?,
                    sp_modified_at  = ?,
                    sp_created_at   = ?,
                    sp_modified_by  = ?,
                    sp_created_by   = ?,
                    sp_web_url      = ?,
                    sp_content_type = ?,
                    sp_list_item_id = ?,
                    source_path     = ?,
                    updated_at      = datetime('now')
                WHERE id = ?
                """,
                (
                    name, size, mime_type,
                    modified_at, created_at, modified_by, created_by,
                    sp_web_url, content_type, list_item_id,
                    sp_path, doc_id,
                ),
            )
            result.files_updated += 1
        else:
            cur = self._conn.execute(
                """
                INSERT INTO documents (
                    original_name, relative_path, size_bytes, mime_type, status,
                    sp_modified_at, sp_created_at, sp_modified_by, sp_created_by,
                    sp_web_url, sp_content_type, sp_list_item_id,
                    project_id, source_id, source_item_id, source_path
                ) VALUES (
                    ?, '', ?, ?, 'discovered',
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?
                )
                """,
                (
                    name, size, mime_type,
                    modified_at, created_at, modified_by, created_by,
                    sp_web_url, content_type, list_item_id,
                    self._project_id, self._source_id, sp_id, sp_path,
                ),
            )
            doc_id = cur.lastrowid
            result.files_new += 1

        self._conn.commit()
        self._upsert_sp_fields(doc_id, custom)

    def _upsert_sp_fields(self, doc_id: int, fields: dict[str, str]) -> None:
        for key, value in fields.items():
            self._conn.execute(
                """
                INSERT INTO document_sp_fields (document_id, field_name, field_value, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(document_id, field_name) DO UPDATE SET
                    field_value = excluded.field_value,
                    updated_at  = excluded.updated_at
                """,
                (doc_id, key, value),
            )
        if fields:
            self._conn.commit()


def _ext_to_mime(ext: str) -> str:
    return _EXT_MIME.get(ext.lower().lstrip("."), "application/octet-stream")
