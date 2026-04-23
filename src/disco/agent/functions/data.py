"""Daten-Tools: freies SQL (read + whitelisted write) fuer den Agent.

Sicherheits-Design:
  - `sqlite_query` ist strikt READ-ONLY. Erlaubt sind SELECT und WITH-CTEs,
    die in einem SELECT muenden. Alles andere (INSERT, UPDATE, DELETE, PRAGMA,
    ATTACH, DROP, ALTER, ...) wird abgelehnt.
  - Nur EIN Statement pro Call. Semikolons im Payload sind nur akzeptiert,
    wenn nach dem letzten Semikolon nichts mehr kommt.
  - Parameter werden als Tupel via sqlite3 uebergeben (keine String-Interpolation).
  - Max. Zeilen-Limit (Default 500) damit der Agent nicht versehentlich
    50k Zeilen in den Kontext zieht.

  - `sqlite_write` akzeptiert INSERT/UPDATE, ABER nur auf whitelisteten
    Tabellen. Die Whitelist ist bewusst klein — Erweiterung geht ueber
    Code-Review.

FTS5: falls in einer spaeteren Migration eine virtuelle FTS5-Tabelle
angelegt wird, funktioniert sie ueber `sqlite_query` transparent (ein
normales SELECT gegen `<fts_table>`).
"""

from __future__ import annotations

import logging
import re
import sqlite3
from typing import Any

from ...db import connect as system_connect
from . import register


def _connect():
    """Verbindung zur aktiven Projekt-DB-Welt.

    Architektur (siehe `docs/architektur-ebenen.md`):
      - ``workspace.db`` (Ebene 3, Reasoning) wird als **main** geoeffnet.
        Der Agent schreibt hier via sqlite_write (work_/agent_/context_-
        Namespace).
      - ``datastore.db`` (Ebene 1+2, Provenance + Content) wird als
        ``ATTACH ... AS ds`` angehaengt — lesbar ueber ``ds.<tabelle>``,
        aber fuer den Chat-Pfad read-only (ATTACH via interner Verbindung,
        nicht via User-SQL).

    Ohne Projekt-Kontext -> system.db (alte Semantik, z.B. CLI-Befehle
    auf der zentralen DB).
    """
    import sqlite3
    from ..context import get_datastore_db_path, get_workspace_db_path

    ws_db = get_workspace_db_path()
    if ws_db is None:
        return system_connect()

    ws_db.parent.mkdir(parents=True, exist_ok=True)
    # URI-Mode auf der main-Connection aktivieren, damit der ATTACH-Call
    # darunter den Query-String `?mode=ro` auswerten kann. Fuer die
    # main-DB (workspace.db) bleibt die Connection voll schreibbar.
    conn = sqlite3.connect(f"file:{ws_db}", uri=True)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row

    ds_db = get_datastore_db_path()
    if ds_db is not None and ds_db.exists():
        # Read-only Attach — SQLite verhindert Schreibversuche physisch.
        # Zusaetzlich lehnt sqlite_write `ds.*`-Ziele schon in der Parser-
        # Schicht ab (siehe _check_write_allowed).
        conn.execute("ATTACH DATABASE ? AS ds", (f"file:{ds_db}?mode=ro",))
    return conn


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

# Bestehende Kern-Tabellen, auf denen sqlite_write fuer INSERT/UPDATE
# erlaubt ist. Fuer DDL gelten die NAMESPACE_-Prefixe weiter unten.
WRITE_WHITELIST: set[str] = {
    "documents",             # status / markdown_path / selected_for_indexing updaten
    "document_sp_fields",    # Agent darf Metadaten nachtragen
}

# Namespace-Praefixe, unter denen der Agent frei schalten und walten darf:
# CREATE TABLE, CREATE INDEX, DROP TABLE, INSERT, UPDATE, DELETE sind frei.
# Alle anderen Tabellen sind geschuetzt.
#
# Drei Arten:
#   work_*     — temporaer (Session-Arbeit, Zwischenstaende)
#   agent_*    — dauerhafte Arbeitsdaten (Reports, Findings, agent_-Memory)
#   context_*  — Lookup-Tabellen aus context/-Dateien (DCC-Katalog,
#                KKS-Hierarchie, Hersteller-Aliasse, Materialklassen)
#                Gedacht fuer "Arbeitsgrundlagen", die bleiben und referenziert werden.
AGENT_NAMESPACE_PREFIXES: tuple[str, ...] = ("work_", "agent_", "context_")

# Verbotene SQL-Tokens fuer sqlite_query (case-insensitive, ganzes Wort)
FORBIDDEN_READ_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "REPLACE", "TRUNCATE", "ATTACH", "DETACH", "PRAGMA", "VACUUM",
    "REINDEX", "ANALYZE",
}

# Fuer sqlite_write erlaubte fuehrende Verben
# INSERT/UPDATE/DELETE -> Daten manipulieren
# CREATE/DROP           -> Schema fuer work_*/agent_* Namespace
ALLOWED_WRITE_VERBS = {"INSERT", "UPDATE", "DELETE", "CREATE", "DROP"}

# Default-Limit fuer Zeilen, damit der Agent nicht alles in den Kontext zieht
DEFAULT_QUERY_LIMIT = 500
MAX_QUERY_LIMIT = 5000


_WORD_RE = re.compile(r"\b([A-Za-z_]+)\b")


# ---------------------------------------------------------------------------
# sqlite_query
# ---------------------------------------------------------------------------


@register(
    name="sqlite_query",
    description=(
        "Fuehrt eine READ-ONLY SQL-Abfrage (SELECT/WITH) gegen die Projekt-DBs "
        "aus und gibt das Ergebnis als JSON-Array von Objekten zurueck. "
        "Die Abfrage laeuft gegen die workspace.db (Ebene 3 — Reasoning) als main-DB; "
        "die datastore.db (Ebene 1+2 — Provenance+Content) ist als ATTACH-DB ds angehaengt "
        "und ueber den Praefix `ds.<tabelle>` lesbar. Beispiel: "
        "`SELECT * FROM ds.agent_sources WHERE extension='pdf'`, "
        "`SELECT * FROM agent_dcc_classification JOIN ds.agent_sources ON ...`. "
        "Nutze Parameter-Bindings (?) statt String-Konkatenation. "
        "Zentrale Tabellen in ds (datastore.db): agent_sources (Registry), "
        "agent_source_metadata, agent_source_relations, agent_source_scans, "
        "agent_pdf_markdown, agent_pdf_inventory, agent_search_*. "
        "In workspace.db schreibt der Agent selbst: "
        "work_* (temporaer), agent_* (dauerhaft), context_* (Lookup). "
        "Verwende PRAGMA NICHT — nur reine SELECT-Statements."
    ),
    parameters={
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "SELECT-Statement, optional mit WITH-CTE. Ein Statement pro Call.",
            },
            "params": {
                "type": "array",
                "description": "Parameter-Werte fuer ?-Platzhalter im SQL.",
                "items": {"type": ["string", "number", "boolean", "null"]},
            },
            "limit": {
                "type": "integer",
                "description": f"Max. Zeilenzahl (Default {DEFAULT_QUERY_LIMIT}, Max {MAX_QUERY_LIMIT}).",
            },
        },
        "required": ["sql"],
    },
    returns="{rows: [...], row_count: int, truncated: bool, columns: [str]}",
)
def _sqlite_query(
    *,
    sql: str,
    params: list[Any] | None = None,
    limit: int = DEFAULT_QUERY_LIMIT,
) -> dict[str, Any]:
    _check_read_only(sql)

    effective_limit = max(1, min(int(limit or DEFAULT_QUERY_LIMIT), MAX_QUERY_LIMIT))

    conn = _connect()
    try:
        cur = conn.execute(sql, tuple(params or ()))
        # Zeilen begrenzen, um Speicher/Kontext zu schuetzen
        rows_raw = cur.fetchmany(effective_limit + 1)
        truncated = len(rows_raw) > effective_limit
        rows_raw = rows_raw[:effective_limit]
        columns = [d[0] for d in (cur.description or [])]
        rows = [dict(zip(columns, r)) for r in rows_raw]
        return {
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "columns": columns,
        }
    except sqlite3.Error as exc:
        raise ValueError(f"SQL-Fehler: {exc}") from exc
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# sqlite_write
# ---------------------------------------------------------------------------


@register(
    name="sqlite_write",
    description=(
        "Fuehrt INSERT/UPDATE/DELETE oder CREATE TABLE/INDEX oder DROP TABLE aus.\n"
        "\n"
        "Zugriffsregeln:\n"
        "  - INSERT/UPDATE auf Kern-Tabellen erlaubt: "
        + ", ".join(sorted(WRITE_WHITELIST)) + ".\n"
        "  - CREATE TABLE / CREATE INDEX / DROP TABLE / INSERT / UPDATE / DELETE "
        "sind frei moeglich fuer Tabellen, deren Name mit 'work_' oder 'agent_' "
        "beginnt (eigener Arbeitsraum fuer Analysen).\n"
        "  - Alle anderen Tabellen sind geschuetzt und werden abgelehnt.\n"
        "\n"
        "Konvention:\n"
        "  - 'work_*' fuer temporaere Analyse-Tabellen (z.B. work_classification).\n"
        "  - 'agent_*' fuer dauerhafte Agent-Arbeitsdaten (z.B. agent_reports).\n"
        "\n"
        "Immer Parameter-Bindings (?) nutzen, keine String-Konkatenation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "Ein einzelnes SQL-Statement.",
            },
            "params": {
                "type": "array",
                "description": "Parameter-Werte fuer ?-Platzhalter.",
                "items": {"type": ["string", "number", "boolean", "null"]},
            },
        },
        "required": ["sql"],
    },
    returns="{affected_rows: int, last_row_id: int|null, verb: str, target_table: str|null}",
)
def _sqlite_write(
    *,
    sql: str,
    params: list[Any] | None = None,
) -> dict[str, Any]:
    verb, target_table = _check_write_allowed(sql)

    conn = _connect()
    try:
        # Schatten-Tabellen-Schutz: wenn eine Tabelle mit gleichem Namen
        # bereits in datastore.db lebt (`ds.sqlite_master`), darf sie nicht
        # in workspace.db nachgebaut oder beschrieben werden — der Chat
        # wuerde sonst eine unsichtbare Parallel-Tabelle fuellen, waehrend
        # Pipelines und Flows aus `ds.` lesen.
        _check_no_shadow_of_datastore(conn, target_table)

        cur = conn.execute(sql, tuple(params or ()))
        conn.commit()
        affected = cur.rowcount if cur.rowcount is not None else 0
        last_id = cur.lastrowid if verb == "INSERT" else None
        return {
            "affected_rows": int(affected),
            "last_row_id": last_id,
            "verb": verb,
            "target_table": target_table,
        }
    except sqlite3.Error as exc:
        raise ValueError(f"SQL-Fehler: {exc}") from exc
    finally:
        conn.close()


def _check_no_shadow_of_datastore(
    conn: sqlite3.Connection,
    target_table: str | None,
) -> None:
    """Verhindert Schatten-Tabellen: wenn `target_table` bereits in
    datastore.db existiert, wird der Schreibversuch in workspace.db
    abgelehnt.

    Motivation: Ein CREATE TABLE agent_pdf_inventory oder ein
    INSERT INTO agent_pdf_inventory aus dem Chat wuerde eine lokale
    workspace.db-Tabelle anlegen, die Pipelines/Flows niemals sehen,
    weil die aus `ds.agent_pdf_inventory` lesen. Fehler klar machen
    und auf die Registry-Tools / Pipelines verweisen.

    Raises:
        ValueError: wenn `target_table` in datastore.db existiert.
    """
    if not target_table:
        return
    try:
        row = conn.execute(
            "SELECT 1 FROM ds.sqlite_master "
            "WHERE type='table' AND lower(name) = lower(?) LIMIT 1",
            (target_table,),
        ).fetchone()
    except sqlite3.OperationalError:
        # Kein ds-ATTACH (keine datastore.db) — Check entfaellt.
        return
    if row is None:
        return
    raise ValueError(
        f"Tabelle '{target_table}' existiert bereits in der datastore.db "
        f"(Ebene 1+2) und ist fuer den Chat read-only. Eine gleichnamige "
        f"Tabelle in workspace.db anzulegen oder zu beschreiben wuerde "
        f"eine unsichtbare Schatten-Tabelle erzeugen — Pipelines und Flows "
        f"lesen aus `ds.{target_table}`, nicht aus workspace.db. "
        f"Schreibzugriffe auf datastore-Tabellen laufen ausschliesslich "
        f"ueber die Registry-Tools (sources_register, sources_attach_metadata, "
        f"sources_detect_duplicates) und die Pipeline-Flows "
        f"(pdf_routing_decision, pdf_to_markdown, build_search_index). "
        f"Fuer eigene Reasoning-Tabellen bitte work_*/agent_*/context_* "
        f"mit einem NEUEN Namen verwenden."
    )


# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------


def _check_read_only(sql: str) -> None:
    """Validiert, dass `sql` ein einzelnes READ-ONLY-Statement ist."""
    stripped = (sql or "").strip()
    if not stripped:
        raise ValueError("Leeres SQL.")
    _check_single_statement(stripped)

    # Erstes Wort muss SELECT oder WITH sein
    first_word = _first_keyword(stripped)
    if first_word not in {"SELECT", "WITH"}:
        if first_word == "PRAGMA":
            raise ValueError(
                "PRAGMA ist in sqlite_query nicht zulaessig. "
                "Fuer Schema-Infos als Table-Valued-Function nutzen, z.B. "
                "SELECT name, type FROM pragma_table_info('meine_tabelle'), "
                "oder via SELECT * FROM sqlite_master WHERE name='meine_tabelle' "
                "die CREATE-DDL abfragen."
            )
        raise ValueError(
            f"sqlite_query akzeptiert nur SELECT/WITH — gefunden: {first_word}. "
            f"Fuer Schreibzugriffe bitte sqlite_write verwenden."
        )

    # Verbotene Keywords im gesamten Statement
    for m in _WORD_RE.finditer(stripped):
        token = m.group(1).upper()
        if token in FORBIDDEN_READ_KEYWORDS:
            raise ValueError(
                f"Verbotenes Keyword in sqlite_query: {token}. "
                f"Nur reine SELECT/WITH-Statements."
            )


def _check_write_allowed(sql: str) -> tuple[str, str | None]:
    """Validiert das SQL und gibt (verb, target_table) zurueck.

    Regeln:
      - INSERT/UPDATE/DELETE erlaubt fuer Kern-Tabellen in WRITE_WHITELIST
        ODER fuer Tabellen mit Namespace-Praefix (work_/agent_).
      - CREATE TABLE / CREATE INDEX / DROP TABLE NUR fuer
        Namespace-Praefix-Tabellen.
      - Kern-Tabellen duerfen NICHT per DDL angefasst werden
        (kein CREATE/DROP auf 'documents' etc.).
    """
    stripped = (sql or "").strip()
    if not stripped:
        raise ValueError("Leeres SQL.")
    _check_single_statement(stripped)

    verb = _first_keyword(stripped)
    if verb not in ALLOWED_WRITE_VERBS:
        raise ValueError(
            f"sqlite_write erlaubt nur {sorted(ALLOWED_WRITE_VERBS)} — gefunden: {verb}."
        )

    # datastore.db ist aus Chat-Sicht read-only — Schreibziele mit
    # `ds.<tabelle>`-Praefix explizit ablehnen. (Zusaetzlich ist die
    # ATTACH-Verbindung physikalisch read-only, aber eine klare Fehler-
    # meldung ist besser als ein SQLite-Fehler.)
    if re.search(r"\bds\.", stripped, re.IGNORECASE):
        raise ValueError(
            "sqlite_write darf nicht auf die datastore.db (Ebene 1+2) schreiben. "
            "Registry/Content liegt dort read-only — Schreibzugriffe gehen nur ueber "
            "Registry-Tools (sources_*) und Pipelines (pdf_*, build_search_index). "
            "Fuer eigene Tabellen bitte work_*/agent_*/context_* in der workspace.db."
        )

    # Zieltabelle ermitteln (verb-spezifisch)
    target = _extract_target_table(stripped, verb)
    if target is None:
        raise ValueError(f"Zieltabelle nicht bestimmbar fuer {verb}.")
    target_lc = target.lower()
    is_namespace = target_lc.startswith(AGENT_NAMESPACE_PREFIXES)

    if verb in ("CREATE", "DROP"):
        # Schema-Aenderungen nur in work_/agent_ Namespace
        if not is_namespace:
            raise ValueError(
                f"{verb} auf '{target}' nicht erlaubt. "
                f"Schema-Aenderungen nur fuer Tabellen mit Praefix "
                f"{list(AGENT_NAMESPACE_PREFIXES)} (z.B. 'work_foo' oder 'agent_bar')."
            )
    else:  # INSERT / UPDATE / DELETE
        in_whitelist = target_lc in {t.lower() for t in WRITE_WHITELIST}
        if not (in_whitelist or is_namespace):
            raise ValueError(
                f"Tabelle '{target}' weder in Whitelist noch im Agent-Namespace. "
                f"Whitelist: {sorted(WRITE_WHITELIST)}, "
                f"Namespace-Praefixe: {list(AGENT_NAMESPACE_PREFIXES)}."
            )

    return verb, target


def _check_single_statement(sql: str) -> None:
    """Erlaubt maximal ein Statement (trailing Semikolon + Whitespace ok)."""
    trimmed = sql.rstrip().rstrip(";").rstrip()
    if ";" in trimmed:
        raise ValueError("Mehrere Statements sind nicht erlaubt.")


def _first_keyword(sql: str) -> str:
    m = _WORD_RE.search(sql)
    return m.group(1).upper() if m else ""


def _extract_target_table(sql: str, verb: str) -> str | None:
    """Zieht den Tabellen-Namen aus verschiedenen SQL-Formen."""
    upper = sql.upper()
    if verb == "INSERT":
        m = re.search(r"\bINSERT\s+(?:OR\s+\w+\s+)?INTO\s+([A-Za-z_][A-Za-z0-9_]*)", upper)
    elif verb == "UPDATE":
        m = re.search(r"\bUPDATE\s+(?:OR\s+\w+\s+)?([A-Za-z_][A-Za-z0-9_]*)", upper)
    elif verb == "DELETE":
        m = re.search(r"\bDELETE\s+FROM\s+([A-Za-z_][A-Za-z0-9_]*)", upper)
    elif verb == "CREATE":
        # CREATE [TEMP|TEMPORARY] [UNIQUE] TABLE|INDEX [IF NOT EXISTS] <name>
        # Bei CREATE INDEX <name> ON <table> nehmen wir die zu aendernde Tabelle
        # (nicht den Index-Namen), denn die Whitelist bezieht sich auf die Basis-Tabelle.
        m_tab = re.search(
            r"\bCREATE\s+(?:TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
            upper,
        )
        if m_tab:
            return m_tab.group(1)
        m_idx = re.search(
            r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?[A-Za-z_][A-Za-z0-9_]*"
            r"\s+ON\s+([A-Za-z_][A-Za-z0-9_]*)",
            upper,
        )
        return m_idx.group(1) if m_idx else None
    elif verb == "DROP":
        m = re.search(
            r"\bDROP\s+(?:TABLE|INDEX)\s+(?:IF\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
            upper,
        )
    else:
        m = None
    return m.group(1) if m else None
