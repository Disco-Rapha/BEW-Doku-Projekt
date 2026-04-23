"""CRUD fuer project_chat_state und chat_messages (Migration 006).

Datenmodell:
  - project_chat_state: genau eine Zeile pro Projekt-Slug.
    Haelt den letzten Foundry-Response-Handle (fuer previous_response_id)
    und den geschaetzten Context-Fill (fuer Kompressions-Warnung).
  - chat_messages: hat project_slug, nicht thread_id. Messages werden
    bei Kompression nicht geloescht, sondern mit is_compacted=1 markiert.

Konventionen:
  - datetime('now') via SQLite, keine Python-Zeitstempel
  - JSON-Felder als String gespeichert, beim Lesen geparst
  - Optionaler db_path fuer Tests
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Literal

from ..config import settings
from ..db import connect


Role = Literal["user", "assistant", "tool", "system"]


# ----------------------------------------------------------------
# project_chat_state — eine Zeile pro Projekt
# ----------------------------------------------------------------


def get_or_create_state(
    project_slug: str,
    model_used: str | None = None,
    db_path=None,
) -> dict[str, Any]:
    """Holt den Chat-State eines Projekts, legt ihn an falls nicht vorhanden.

    Idempotent: bei bestehendem State wird nichts geaendert (auch nicht
    model_used — das bleibt wie beim ersten Anlegen).
    """
    model = model_used or settings.foundry_model_deployment
    conn = connect(db_path or settings.db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO project_chat_state "
            "  (project_slug, model_used) VALUES (?, ?)",
            (project_slug, model),
        )
        conn.commit()
        return _get_state(project_slug, conn=conn)
    finally:
        conn.close()


def get_state(project_slug: str, db_path=None) -> dict[str, Any] | None:
    """Gibt den Chat-State zurueck, None wenn das Projekt noch keinen hat."""
    conn = connect(db_path or settings.db_path)
    try:
        row = conn.execute(
            "SELECT project_slug, foundry_response_id, model_used, "
            "       token_estimate, last_compaction_at, created_at, updated_at "
            "FROM project_chat_state WHERE project_slug = ?",
            (project_slug,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _get_state(project_slug: str, conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        "SELECT project_slug, foundry_response_id, model_used, "
        "       token_estimate, last_compaction_at, created_at, updated_at "
        "FROM project_chat_state WHERE project_slug = ?",
        (project_slug,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Chat-State fuer Projekt {project_slug!r} nicht gefunden.")
    return dict(row)


def set_response_id(
    project_slug: str,
    foundry_response_id: str | None,
    db_path=None,
) -> None:
    """Speichert den letzten Foundry-Response-Handle.

    None setzt ihn zurueck (z.B. nach Kompression — neuer Thread-Anfang).
    """
    conn = connect(db_path or settings.db_path)
    try:
        conn.execute(
            "UPDATE project_chat_state "
            "SET foundry_response_id = ?, updated_at = datetime('now') "
            "WHERE project_slug = ?",
            (foundry_response_id, project_slug),
        )
        conn.commit()
    finally:
        conn.close()


def update_token_estimate(
    project_slug: str,
    token_estimate: int,
    db_path=None,
) -> None:
    """Aktualisiert die Token-Schaetzung (fuer 70/90-Warnungen)."""
    conn = connect(db_path or settings.db_path)
    try:
        conn.execute(
            "UPDATE project_chat_state "
            "SET token_estimate = ?, updated_at = datetime('now') "
            "WHERE project_slug = ?",
            (int(token_estimate), project_slug),
        )
        conn.commit()
    finally:
        conn.close()


def recompute_token_estimate(project_slug: str, db_path=None) -> int:
    """Rechnet token_estimate neu aus den aktiven Messages.

    Wird typisch direkt nach Kompression gerufen — dann sollte der Wert
    nahe Null sein (nur noch System-Prompts + Triad).
    """
    conn = connect(db_path or settings.db_path)
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(token_count), 0) AS s "
            "FROM chat_messages "
            "WHERE project_slug = ? AND is_compacted = 0",
            (project_slug,),
        ).fetchone()
        total = int(row["s"]) if row else 0
        conn.execute(
            "UPDATE project_chat_state "
            "SET token_estimate = ?, updated_at = datetime('now') "
            "WHERE project_slug = ?",
            (total, project_slug),
        )
        conn.commit()
        return total
    finally:
        conn.close()


def mark_compacted(
    project_slug: str,
    cutoff_message_id: int,
    db_path=None,
) -> int:
    """Setzt is_compacted=1 auf alle aktiven Messages bis cutoff_message_id.

    Returns:
        Anzahl der markierten Messages.
    """
    conn = connect(db_path or settings.db_path)
    try:
        cur = conn.execute(
            "UPDATE chat_messages "
            "SET is_compacted = 1 "
            "WHERE project_slug = ? "
            "  AND is_compacted = 0 "
            "  AND id <= ?",
            (project_slug, int(cutoff_message_id)),
        )
        conn.execute(
            "UPDATE project_chat_state "
            "SET last_compaction_at = datetime('now'), "
            "    updated_at = datetime('now') "
            "WHERE project_slug = ?",
            (project_slug,),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def delete_state(project_slug: str, db_path=None) -> None:
    """Loescht den Chat-State + alle Messages eines Projekts.

    Wird bei `disco project delete` genutzt (existiert noch nicht — kommt
    spaeter), hier als konsistente API-Funktion bereits vorhanden.
    """
    conn = connect(db_path or settings.db_path)
    try:
        conn.execute(
            "DELETE FROM chat_messages WHERE project_slug = ?",
            (project_slug,),
        )
        conn.execute(
            "DELETE FROM project_chat_state WHERE project_slug = ?",
            (project_slug,),
        )
        conn.commit()
    finally:
        conn.close()


# ----------------------------------------------------------------
# chat_messages
# ----------------------------------------------------------------


def _estimate_tokens(content: str | None, tool_calls_json: str | None, tool_results_json: str | None) -> int:
    """Grobe Token-Schaetzung: 1 Token ~= 4 Zeichen.

    Ausreichend genau fuer Kompressions-Warnung (70/90 %). Wenn wir spaeter
    Praezision brauchen, tauschen wir auf tiktoken.
    """
    total_chars = 0
    if content:
        total_chars += len(content)
    if tool_calls_json:
        total_chars += len(tool_calls_json)
    if tool_results_json:
        total_chars += len(tool_results_json)
    # Ceil-Division
    return (total_chars + 3) // 4


# ----------------------------------------------------------------
# agent_tool_calls — strukturierte Spiegelung der JSON-Rohdaten
# ----------------------------------------------------------------
# Die Rohdaten landen weiterhin in chat_messages.tool_calls_json /
# tool_results_json (wir aendern das nicht). Zusaetzlich spiegeln wir
# jeden Call in agent_tool_calls, damit Dashboard-Queries ohne
# JSON-Parsing auskommen. Bei Fehlern beim Spiegeln loggen wir und
# schlucken die Exception — die Chat-Persistenz darf NIE davon abhaengen.


_ARG_SUMMARY_MAX = 160
_RESULT_SUMMARY_MAX = 500


def _summarize_arguments(args_value: Any) -> str:
    """Kompakte One-Liner-Repraesentation der Tool-Argumente fuer Dashboards.

    args_value kann ein JSON-String (wie Foundry ihn liefert) oder ein Dict sein.
    """
    if args_value is None:
        return ""
    if isinstance(args_value, str):
        try:
            parsed = json.loads(args_value)
        except json.JSONDecodeError:
            return args_value[:_ARG_SUMMARY_MAX]
    else:
        parsed = args_value
    if isinstance(parsed, dict):
        parts = []
        for k, v in parsed.items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                s = str(v)
                if len(s) > 60:
                    s = s[:57] + "..."
                parts.append(f"{k}={s}")
            else:
                parts.append(f"{k}=<...>")
        summary = ", ".join(parts)
    else:
        summary = json.dumps(parsed, ensure_ascii=False)
    return summary[:_ARG_SUMMARY_MAX]


def _parse_tool_result(result_value: Any) -> tuple[str | None, bool, str | None]:
    """Interpretiert das Tool-Result. Liefert (summary, is_error, error_msg).

    Convention in disco.agent.functions.__init__.dispatch: Fehler werden immer
    als JSON-String '{"error": "..."}' serialisiert.
    """
    if result_value is None:
        return None, False, None
    # result kann schon dict sein (bei Tool-Messages im recorded_tool_results-Pfad
    # liefert der Agent-Loop ein dict, nicht den Raw-String).
    if isinstance(result_value, str):
        raw = result_value
        try:
            parsed = json.loads(result_value)
        except json.JSONDecodeError:
            parsed = None
    else:
        parsed = result_value
        raw = json.dumps(result_value, ensure_ascii=False)
    summary = raw[:_RESULT_SUMMARY_MAX]
    is_error = False
    error_msg: str | None = None
    if isinstance(parsed, dict) and "error" in parsed and len(parsed) == 1:
        is_error = True
        error_msg = str(parsed["error"])[:_RESULT_SUMMARY_MAX]
    return summary, is_error, error_msg


def _record_tool_call_requests(
    conn: sqlite3.Connection,
    message_id: int,
    project_slug: str,
    tool_calls: list[dict[str, Any]],
) -> None:
    """Legt fuer jeden Tool-Call im assistant-Turn eine agent_tool_calls-Zeile an."""
    for call in tool_calls:
        try:
            call_id = call.get("call_id") or call.get("id")
            name = call.get("name") or (call.get("function") or {}).get("name")
            args = call.get("arguments")
            if args is None and "function" in call:
                args = (call["function"] or {}).get("arguments")
            if not name:
                continue
            arguments_json = (
                args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)
                if args is not None else None
            )
            arguments_summary = _summarize_arguments(args)
            conn.execute(
                "INSERT OR IGNORE INTO agent_tool_calls "
                "  (message_id, project_slug, tool_call_id, tool_name, "
                "   arguments_json, arguments_summary) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    message_id,
                    project_slug,
                    call_id,
                    name,
                    arguments_json,
                    arguments_summary,
                ),
            )
        except Exception:  # pragma: no cover — Telemetrie darf nichts kaputtmachen
            import logging
            logging.getLogger(__name__).exception(
                "Konnte Tool-Call-Request nicht spiegeln (message_id=%s)", message_id
            )


def _record_tool_call_results(
    conn: sqlite3.Connection,
    result_message_id: int,
    project_slug: str,
    tool_results: Any,
) -> None:
    """Verknuepft Tool-Results mit den zuvor angelegten agent_tool_calls-Zeilen.

    Ergaenzt result_summary, result_is_error, result_error_msg, duration_ms.
    Matching laeuft ueber (project_slug, tool_call_id).
    """
    # Ergebnisse koennen entweder eine Liste (recorded_tool_results) oder ein
    # einzelnes dict sein (legacy). Normalisieren.
    if isinstance(tool_results, list):
        results_iter = tool_results
    elif isinstance(tool_results, dict):
        results_iter = [tool_results]
    else:
        return

    for res in results_iter:
        try:
            call_id = res.get("call_id") or res.get("tool_call_id")
            if not call_id:
                continue
            raw_result = res.get("result")
            if raw_result is None:
                raw_result = res.get("content")
            summary, is_error, err_msg = _parse_tool_result(raw_result)
            # duration_ms kommt idealerweise aus dem Dispatch (Python-Seite,
            # Millisekunden-Auflösung). Fehlt sie (alte Daten oder Legacy-
            # Pfad), fallen wir zurueck auf die SQL-Differenz der created_at
            # Stempel — die ist aber Sekunden-Auflösung, also oft 0.
            duration_ms = res.get("duration_ms")
            if duration_ms is not None:
                conn.execute(
                    "UPDATE agent_tool_calls "
                    "SET result_message_id = ?, "
                    "    result_summary = ?, "
                    "    result_is_error = ?, "
                    "    result_error_msg = ?, "
                    "    duration_ms = ? "
                    "WHERE project_slug = ? AND tool_call_id = ? "
                    "  AND result_message_id IS NULL",
                    (
                        result_message_id,
                        summary,
                        1 if is_error else 0,
                        err_msg,
                        int(duration_ms),
                        project_slug,
                        call_id,
                    ),
                )
            else:
                conn.execute(
                    "UPDATE agent_tool_calls "
                    "SET result_message_id = ?, "
                    "    result_summary = ?, "
                    "    result_is_error = ?, "
                    "    result_error_msg = ?, "
                    "    duration_ms = ( "
                    "       SELECT CAST((julianday(cm_res.created_at) - julianday(cm_req.created_at)) "
                    "                   * 86400 * 1000 AS INTEGER) "
                    "       FROM chat_messages cm_req, chat_messages cm_res "
                    "       WHERE cm_req.id = agent_tool_calls.message_id "
                    "         AND cm_res.id = ? "
                    "    ) "
                    "WHERE project_slug = ? AND tool_call_id = ? "
                    "  AND result_message_id IS NULL",
                    (
                        result_message_id,
                        summary,
                        1 if is_error else 0,
                        err_msg,
                        result_message_id,
                        project_slug,
                        call_id,
                    ),
                )
        except Exception:  # pragma: no cover
            import logging
            logging.getLogger(__name__).exception(
                "Konnte Tool-Call-Result nicht verknuepfen (call_id=%s)",
                res.get("call_id") if isinstance(res, dict) else None,
            )


def append_message(
    project_slug: str,
    role: Role,
    content: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    tool_results: dict[str, Any] | list[dict[str, Any]] | None = None,
    foundry_message_id: str | None = None,
    tokens_input: int | None = None,
    tokens_output: int | None = None,
    db_path=None,
) -> dict[str, Any]:
    """Haengt eine Message an den Projekt-Chat an.

    Legt den project_chat_state-Eintrag bei Bedarf an (Idempotenz fuer
    den ersten User-Turn eines Projekts).

    Returns:
        Das geschriebene Message-Dict inkl. id, token_count, created_at.
    """
    if role not in ("user", "assistant", "tool", "system"):
        raise ValueError(f"Ungueltige Rolle: {role!r}")

    tool_calls_json = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None
    tool_results_json = (
        json.dumps(tool_results, ensure_ascii=False) if tool_results is not None else None
    )
    token_count = _estimate_tokens(content, tool_calls_json, tool_results_json)

    conn = connect(db_path or settings.db_path)
    try:
        # State sicherstellen (idempotent)
        conn.execute(
            "INSERT OR IGNORE INTO project_chat_state (project_slug, model_used) "
            "VALUES (?, ?)",
            (project_slug, settings.foundry_model_deployment),
        )

        cur = conn.execute(
            "INSERT INTO chat_messages "
            "  (project_slug, role, content, tool_calls_json, tool_results_json, "
            "   foundry_message_id, tokens_input, tokens_output, token_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                project_slug,
                role,
                content,
                tool_calls_json,
                tool_results_json,
                foundry_message_id,
                tokens_input,
                tokens_output,
                token_count,
            ),
        )

        # Tool-Calls in agent_tool_calls spiegeln (best-effort; loggt und
        # schluckt Exceptions, damit die Chat-Persistenz unbeeinflusst bleibt).
        msg_id = cur.lastrowid
        if role == "assistant" and tool_calls:
            _record_tool_call_requests(conn, msg_id, project_slug, tool_calls)
        elif role == "tool" and tool_results is not None:
            _record_tool_call_results(conn, msg_id, project_slug, tool_results)

        # token_estimate fortschreiben (nur ueber aktive, d.h. nicht komprimierte,
        # Messages — was fuer eine frische Message per Definition zutrifft)
        conn.execute(
            "UPDATE project_chat_state "
            "SET token_estimate = token_estimate + ?, "
            "    updated_at = datetime('now') "
            "WHERE project_slug = ?",
            (token_count, project_slug),
        )
        conn.commit()
        return _get_message(cur.lastrowid, conn=conn)
    finally:
        conn.close()


def list_active_messages(
    project_slug: str,
    db_path=None,
) -> list[dict[str, Any]]:
    """Gibt alle NICHT komprimierten Messages eines Projekts chronologisch zurueck.

    Das ist die Basis, die der Agent in seinen Context laedt.
    """
    conn = connect(db_path or settings.db_path)
    try:
        rows = conn.execute(
            "SELECT id, project_slug, role, content, tool_calls_json, "
            "       tool_results_json, foundry_message_id, "
            "       tokens_input, tokens_output, token_count, "
            "       is_compacted, created_at "
            "FROM chat_messages "
            "WHERE project_slug = ? AND is_compacted = 0 "
            "ORDER BY id ASC",
            (project_slug,),
        ).fetchall()
        return [_hydrate_message(dict(r)) for r in rows]
    finally:
        conn.close()


def list_all_messages(
    project_slug: str,
    include_compacted: bool = True,
    db_path=None,
) -> list[dict[str, Any]]:
    """Gibt alle Messages (inkl. komprimierter, falls Flag gesetzt).

    Fuer die UI-Anzeige mit Kompressions-Divider.
    """
    conn = connect(db_path or settings.db_path)
    try:
        sql = (
            "SELECT id, project_slug, role, content, tool_calls_json, "
            "       tool_results_json, foundry_message_id, "
            "       tokens_input, tokens_output, token_count, "
            "       is_compacted, created_at "
            "FROM chat_messages WHERE project_slug = ? "
        )
        if not include_compacted:
            sql += "AND is_compacted = 0 "
        sql += "ORDER BY id ASC"
        rows = conn.execute(sql, (project_slug,)).fetchall()
        return [_hydrate_message(dict(r)) for r in rows]
    finally:
        conn.close()


def last_active_message_id(project_slug: str, db_path=None) -> int | None:
    """Gibt die hoechste Message-ID der aktiven Messages zurueck.

    Wird als Cutoff fuer mark_compacted genutzt: vor der Kompression
    wird dieser Wert gelesen, danach werden alle Messages bis zu diesem
    Wert als komprimiert markiert.
    """
    conn = connect(db_path or settings.db_path)
    try:
        row = conn.execute(
            "SELECT MAX(id) AS max_id FROM chat_messages "
            "WHERE project_slug = ? AND is_compacted = 0",
            (project_slug,),
        ).fetchone()
        return int(row["max_id"]) if row and row["max_id"] is not None else None
    finally:
        conn.close()


def _get_message(message_id: int, conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id, project_slug, role, content, tool_calls_json, "
        "       tool_results_json, foundry_message_id, "
        "       tokens_input, tokens_output, token_count, "
        "       is_compacted, created_at "
        "FROM chat_messages WHERE id = ?",
        (message_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Message ID {message_id} nicht gefunden.")
    return _hydrate_message(dict(row))


def _hydrate_message(msg: dict[str, Any]) -> dict[str, Any]:
    """Parst die JSON-Strings zurueck zu Python-Strukturen."""
    tc = msg.pop("tool_calls_json", None)
    tr = msg.pop("tool_results_json", None)
    msg["tool_calls"] = json.loads(tc) if tc else None
    msg["tool_results"] = json.loads(tr) if tr else None
    return msg


def backfill_agent_tool_calls(db_path=None) -> dict[str, int]:
    """Befuellt agent_tool_calls aus bestehenden chat_messages rueckwirkend.

    Idempotent — dank dem UNIQUE-Index auf (message_id, tool_call_id) werden
    bereits gespiegelte Calls uebersprungen. Results koennen mehrfach laufen,
    weil das UPDATE auf 'result_message_id IS NULL' filtert.

    Returns:
        {"requests_inserted": N, "results_matched": M}
    """
    conn = connect(db_path or settings.db_path)
    requests_inserted = 0
    results_matched = 0
    try:
        # 1. Assistant-Turns mit tool_calls_json aufloesen
        rows = conn.execute(
            "SELECT id, project_slug, tool_calls_json FROM chat_messages "
            "WHERE role = 'assistant' AND tool_calls_json IS NOT NULL "
            "ORDER BY id ASC"
        ).fetchall()
        for r in rows:
            try:
                calls = json.loads(r["tool_calls_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            if not calls:
                continue
            before = conn.execute(
                "SELECT COUNT(*) AS c FROM agent_tool_calls WHERE message_id = ?",
                (r["id"],),
            ).fetchone()["c"]
            _record_tool_call_requests(conn, r["id"], r["project_slug"], calls)
            after = conn.execute(
                "SELECT COUNT(*) AS c FROM agent_tool_calls WHERE message_id = ?",
                (r["id"],),
            ).fetchone()["c"]
            requests_inserted += (after - before)
        conn.commit()

        # 2. Tool-Turns mit tool_results_json den Requests zuordnen
        rows = conn.execute(
            "SELECT id, project_slug, tool_results_json FROM chat_messages "
            "WHERE role = 'tool' AND tool_results_json IS NOT NULL "
            "ORDER BY id ASC"
        ).fetchall()
        for r in rows:
            try:
                results = json.loads(r["tool_results_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            if not results:
                continue
            before = conn.execute(
                "SELECT COUNT(*) AS c FROM agent_tool_calls "
                "WHERE result_message_id = ?",
                (r["id"],),
            ).fetchone()["c"]
            _record_tool_call_results(conn, r["id"], r["project_slug"], results)
            after = conn.execute(
                "SELECT COUNT(*) AS c FROM agent_tool_calls "
                "WHERE result_message_id = ?",
                (r["id"],),
            ).fetchone()["c"]
            results_matched += (after - before)
        conn.commit()

        return {
            "requests_inserted": requests_inserted,
            "results_matched": results_matched,
        }
    finally:
        conn.close()


# ----------------------------------------------------------------
# chat_message_feedback — User-Signale fuer spaetere Evals
# ----------------------------------------------------------------


def add_message_feedback(
    message_id: int,
    rating: str,
    comment: str | None = None,
    db_path=None,
) -> dict[str, Any]:
    """Legt ein Feedback-Event zu einer Assistant-Message an.

    Mehrere Events pro Message erlaubt; der neueste gilt.
    """
    if rating not in ("good", "bad"):
        raise ValueError(f"rating muss 'good' oder 'bad' sein, nicht {rating!r}")
    conn = connect(db_path or settings.db_path)
    try:
        # project_slug aus der Message holen
        row = conn.execute(
            "SELECT project_slug FROM chat_messages WHERE id = ?",
            (int(message_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"Message {message_id} nicht gefunden")
        cur = conn.execute(
            "INSERT INTO chat_message_feedback "
            "  (message_id, project_slug, rating, comment) "
            "VALUES (?, ?, ?, ?)",
            (int(message_id), row["project_slug"], rating, comment),
        )
        conn.commit()
        fb = conn.execute(
            "SELECT id, message_id, project_slug, rating, comment, created_at "
            "FROM chat_message_feedback WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
        return dict(fb)
    finally:
        conn.close()


def latest_feedback_for_messages(
    message_ids: list[int],
    db_path=None,
) -> dict[int, dict[str, Any]]:
    """Holt das neueste Feedback pro Message (message_id -> feedback-dict).

    Wird von der UI genutzt, um den Knopf-Zustand zu rendern.
    """
    if not message_ids:
        return {}
    conn = connect(db_path or settings.db_path)
    try:
        placeholders = ",".join("?" for _ in message_ids)
        rows = conn.execute(
            f"SELECT id, message_id, project_slug, rating, comment, created_at "
            f"FROM chat_message_feedback "
            f"WHERE message_id IN ({placeholders}) "
            f"ORDER BY message_id, created_at DESC",
            [int(m) for m in message_ids],
        ).fetchall()
        seen: dict[int, dict[str, Any]] = {}
        for r in rows:
            mid = int(r["message_id"])
            if mid in seen:
                continue
            seen[mid] = dict(r)
        return seen
    finally:
        conn.close()
