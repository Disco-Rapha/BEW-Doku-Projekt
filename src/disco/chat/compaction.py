"""Compaction v2 — Handover-Brief + letzte Dialog-Paare erhalten.

Bisher (v1): ein /compact markiert ALLE aktiven Messages als komprimiert,
nullt foundry_response_id und laesst Disco mit leerem Chat + Memory-
Reload weiterlaufen. Der Nachteil: der Faden reisst sichtbar, und Disco
verliert den Kontext zum laufenden Thema.

Jetzt (v2): beim /compact laeuft ein orchestrierter Schritt durch:

  1. Letzte N Dialog-Paare bestimmen (user-Text + folgende assistant-
     Text-Antwort; tool-Turns zaehlen NICHT). Diese bleiben aktiv.
  2. Alles davor wird als komprimiert markiert.
  3. Fuer den komprimierten Teil generiert ein schlanker LLM-Call eine
     kurze Handover-Notiz (aktuelles Thema, Status, offene Punkte) und
     legt sie als neue system-Message direkt vor den erhaltenen Paaren
     ab — damit Disco im naechsten Turn sofort weiss, wo er steht.
  4. foundry_response_id + measured_context_tokens werden zurueckgesetzt
     → naechster Turn laeuft im Stateless-Modus (Phase 2), baut den
     Input neu aus der verkuerzten Message-Liste.

Fehler im LLM-Call werden geschluckt — die Compaction selbst darf nicht
davon abhaengen, dass das Modell einen Handover produziert. Fallback ist
ein template-basierter Brief.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config import settings
from . import repo as chat_repo

logger = logging.getLogger(__name__)


# Wie viele user/assistant-Paare am Ende des Verlaufs erhalten bleiben.
# 3 Paare sind der Kompromiss aus "genug Kontext fuer das laufende Thema"
# und "nicht zu gross, damit die Compaction wirklich spuerbar entlastet".
DEFAULT_KEEP_PAIRS = 3


def _find_cutoff_and_kept(
    messages: list[dict[str, Any]],
    n_pairs: int,
) -> tuple[int | None, list[int]]:
    """Bestimmt Cutoff-ID und die IDs der zu erhaltenden Messages.

    Geht rueckwaerts durch die aktive Message-Liste und sammelt die
    letzten `n_pairs * 2` User/Assistant-Text-Messages. Tool-Turns und
    reine Tool-Only-Assistant-Turns (ohne content) werden uebersprungen
    — wir brauchen nur die Textebene fuer den Handover.

    Returns:
        (cutoff_id, kept_ids). Wenn nichts zu schneiden ist (zu wenig
        Verlauf), liefert die Funktion (None, alle_ids).
    """
    kept_ids: list[int] = []
    # Wir zaehlen user-Messages, weil ein Paar immer durch einen User-
    # Turn eingeleitet wird. Tool-only-Assistant-Turns zu diesem User
    # werden weggelassen — der Nutzer sieht sie ohnehin nicht.
    user_count = 0
    for msg in reversed(messages):
        role = msg["role"]
        if role == "tool":
            continue
        if role == "system":
            # System-Trigger-Summaries zaehlen nicht als Paar, bleiben
            # aber im Kontext, falls sie innerhalb der letzten paar
            # Turns lagen. Wir nehmen sie passiv mit.
            kept_ids.append(int(msg["id"]))
            continue
        if role == "assistant":
            # Assistant ohne content (reiner Tool-Call-Turn) bleibt
            # optional erhalten, wenn schon ein User-Partner auf der
            # Keep-Liste steht; sonst ueberspringen.
            if msg.get("content"):
                kept_ids.append(int(msg["id"]))
            continue
        if role == "user":
            kept_ids.append(int(msg["id"]))
            user_count += 1
            if user_count >= n_pairs:
                break

    if not kept_ids:
        return None, []

    kept_sorted = sorted(kept_ids)
    earliest_kept = kept_sorted[0]
    # Cutoff = alle Messages STRIKT vor dem ersten Keep — sie werden
    # komprimiert. Falls earliest_kept bereits die allererste ist,
    # gibt es nichts zu schneiden.
    first_id = int(messages[0]["id"])
    if earliest_kept <= first_id:
        return None, kept_sorted
    return earliest_kept - 1, kept_sorted


def _format_short_message(msg: dict[str, Any], max_chars: int = 500) -> str:
    """Einzeiler fuer den LLM-Prompt / den Fallback-Brief."""
    role = msg["role"]
    content = (msg.get("content") or "").strip()
    if len(content) > max_chars:
        content = content[:max_chars] + "…"
    tool_info = ""
    calls = msg.get("tool_calls") or []
    if calls:
        names = [c.get("name") or (c.get("function") or {}).get("name") for c in calls]
        names = [n for n in names if n]
        if names:
            tool_info = f" [tool_calls: {', '.join(names[:5])}]"
    return f"[{role}] {content}{tool_info}"


def _build_handover_prompt(
    compacted_messages: list[dict[str, Any]],
    project_slug: str,
) -> str:
    """Baut den Prompt fuer die LLM-Zusammenfassung.

    Die Meldung soll kurz (~200-400 Tokens) bleiben — sie wird Teil des
    naechsten Turn-Inputs, also zaehlt jeder Token.
    """
    lines = [
        "Du bist Disco und fasst gerade einen laengeren Chat-Verlauf ",
        "zusammen, damit Du nach der Kompression weiterarbeiten kannst.",
        "",
        f"Projekt: {project_slug}",
        "",
        "Verlauf (chronologisch, gekuerzt):",
    ]
    for msg in compacted_messages:
        lines.append(_format_short_message(msg, max_chars=400))
    lines.extend([
        "",
        "Erstelle eine kompakte Handover-Notiz (max. 12 Zeilen).",
        "Gliederung:",
        "  - Aktuelles Thema: ein Satz",
        "  - Status: was ist erledigt, was laeuft noch",
        "  - Offene Punkte: 1-3 Bullet-Points",
        "  - Wichtige Fakten aus dem Verlauf: 1-3 Bullets (Projekt-",
        "    spezifische Zahlen, Pfade, Entscheidungen)",
        "",
        "Keine Floskeln. Keine Meta-Kommentare ueber die Kompression.",
        "Nur die Inhalte, die der Disco im naechsten Turn braucht.",
    ])
    return "\n".join(lines)


def _fallback_brief(
    compacted_messages: list[dict[str, Any]],
    project_slug: str,
) -> str:
    """Minimaler Handover-Brief, wenn der LLM-Call fehlschlaegt."""
    n_total = len(compacted_messages)
    n_user = sum(1 for m in compacted_messages if m["role"] == "user")
    n_assistant = sum(1 for m in compacted_messages if m["role"] == "assistant")
    # Letzte 3 user/assistant-Contents rauspicken, damit wenigstens
    # Stichworte fuer das aktuelle Thema im Brief stehen.
    snippets = []
    for msg in reversed(compacted_messages):
        if msg["role"] in ("user", "assistant") and msg.get("content"):
            snippets.append(
                f"  - [{msg['role']}] "
                f"{msg['content'].strip().splitlines()[0][:200]}"
            )
            if len(snippets) >= 3:
                break
    snippets.reverse()
    lines = [
        f"[HANDOVER — Compaction v2, Projekt {project_slug}]",
        f"Komprimiert: {n_total} Messages "
        f"(user={n_user}, assistant={n_assistant}).",
        "Letzte Stichworte aus dem komprimierten Teil:",
        *(snippets or ["  - (keine Text-Messages gefunden)"]),
        "Weiter geht es mit den erhaltenen Dialog-Paaren unten.",
    ]
    return "\n".join(lines)


def _generate_handover_brief(
    compacted_messages: list[dict[str, Any]],
    project_slug: str,
) -> str:
    """Laesst das Foundry-Modell eine Handover-Notiz schreiben.

    Verwendet einen schlanken Responses.create-Call OHNE Tools und OHNE
    previous_response_id — das soll NICHT in die Chat-Chain einfliessen.
    """
    from ..agent.core import get_agent_service

    if not compacted_messages:
        return f"[HANDOVER — Projekt {project_slug}] Nichts zu berichten."

    try:
        svc = get_agent_service()
        svc._ensure_clients()
        client = svc._openai_client
        model = svc._model_deployment()
    except Exception as exc:
        logger.warning("Handover: Foundry-Client nicht verfuegbar (%s)", exc)
        return _fallback_brief(compacted_messages, project_slug)

    prompt = _build_handover_prompt(compacted_messages, project_slug)
    try:
        resp = client.responses.create(
            model=model,
            input=[{"type": "message", "role": "user", "content": prompt}],
            max_output_tokens=600,
            stream=False,
            store=False,
        )
        # Responses-API: resp.output_text aggregiert den Textinhalt. Bei
        # sehr alten SDKs fallen wir auf das manuelle Durchreichen zurueck.
        text = getattr(resp, "output_text", None)
        if not text:
            for item in getattr(resp, "output", []) or []:
                for content in getattr(item, "content", []) or []:
                    t = getattr(content, "text", None)
                    if t:
                        text = (text or "") + t
        if not text:
            logger.warning("Handover: leere LLM-Response, Fallback")
            return _fallback_brief(compacted_messages, project_slug)
        # Kopfzeile ergaenzen, damit Disco den Block im Verlauf sofort
        # als Handover erkennt.
        return f"[HANDOVER — Compaction v2, Projekt {project_slug}]\n{text.strip()}"
    except Exception as exc:
        logger.warning("Handover: LLM-Call fehlgeschlagen (%s), Fallback", exc)
        return _fallback_brief(compacted_messages, project_slug)


# ---------------------------------------------------------------------------
# Memory-Distillation — Schritt VOR der Compaction
# ---------------------------------------------------------------------------
#
# Der Handover-Brief allein konserviert nur den Faden zum aktuellen Thema.
# Was waehrend der Session an dauerhaftem Wissen entstanden ist
# (Konventionen, neue Tabellen, Entscheidungen, Wissens-Bloecke), ginge
# beim Cutoff verloren. Deshalb wird VOR der Compaction ein zweiter,
# eigenstaendiger LLM-Call gefahren, der den komprimierten Block in
# strukturierte Memory-Updates uebersetzt:
#
#   - NOTES-Eintrag (chronologisches Logbuch — was wurde getan, was ist
#     entschieden, was ist offen)
#   - DISCO-Schicht-2-Kapitel (nur wenn neuer dauerhafter Wissens-Block
#     entstanden ist — nicht jedes Mal)
#   - agent_table_docs (nur wenn neue Reasoning-Tabellen angelegt wurden)
#
# Anschliessend wendet der Server die Updates direkt ueber die
# memory_*- und table_doc_*-Funktionen an. Damit ist Memory-Pflege
# Teil der automatischen Compaction, ohne dass der User irgendwas
# triggern muss.

import json as _json


def _build_distillation_prompt(
    compacted_messages: list[dict[str, Any]],
    project_slug: str,
) -> str:
    """Prompt fuer die Memory-Distillation.

    Verlangt JSON-Output. Format:

      {
        "notes_text": "<3-6 Zeilen, was getan/entschieden/offen>" | null,
        "disco_chapters": [
          {"heading": "...", "tags": ["..."], "status": "current",
           "body": "..."}
        ],
        "table_docs": [
          {"table_name": "...", "layer": "workspace|datastore|context",
           "description": "...", "schema_summary": "...",
           "example_query": "...", "source_files": "..."}
        ]
      }

    Wir trauen dem Modell die Entscheidung zu, ob disco_chapters/
    table_docs leer bleiben (Default-Erwartung). NOTES soll fast immer
    befuellt sein — selbst eine kurze Session hat einen Logbuch-
    Eintrag wert.
    """
    lines = [
        "Du bist Disco. Vor einer Chat-Compaction destillierst Du den ",
        "bisherigen Verlauf in dauerhafte Memory-Updates fuer das ",
        f"Projekt '{project_slug}'.",
        "",
        "Verlauf (chronologisch, gekuerzt):",
    ]
    for msg in compacted_messages:
        lines.append(_format_short_message(msg, max_chars=600))
    lines.extend([
        "",
        "Liefere AUSSCHLIESSLICH ein JSON-Objekt zurueck, sonst nichts.",
        "Schema:",
        "{",
        '  "notes_text": "<3-6 Zeilen oder null>",',
        '  "disco_chapters": [',
        '    {"heading": "...", "tags": ["..."], "status": "current",',
        '     "body": "<Markdown-Inhalt>"}',
        "  ],",
        '  "table_docs": [',
        '    {"table_name": "...", "layer": "workspace|datastore|context",',
        '     "description": "...", "schema_summary": "...",',
        '     "example_query": "...", "source_files": "..."}',
        "  ]",
        "}",
        "",
        "Regeln:",
        "- notes_text: knapper chronologischer Eintrag (was getan, ",
        "  was entschieden, was offen). Fast immer befuellt.",
        "- disco_chapters: NUR wenn ein dauerhafter Wissens-Block ",
        "  entstanden ist (neuer Lookup-Pfad, neue Konvention, ",
        "  fachliche Erkenntnis, die auch in zwei Wochen relevant ",
        "  bleibt). Sonst leeres Array.",
        "- table_docs: NUR wenn in der Session neue Reasoning-",
        "  Tabellen angelegt wurden, deren Doku noch fehlt. Sonst ",
        "  leeres Array.",
        "- Keine Floskeln, kein Meta-Text, kein Markdown-Code-Fence ",
        "  um das JSON.",
    ])
    return "\n".join(lines)


def _generate_memory_distillation(
    compacted_messages: list[dict[str, Any]],
    project_slug: str,
) -> dict[str, Any] | None:
    """Schickt den komprimierten Block zur LLM und erwartet JSON.

    Returns None bei Fehler — Compaction laeuft trotzdem weiter.
    """
    from ..agent.core import get_agent_service

    if not compacted_messages:
        return None

    try:
        svc = get_agent_service()
        svc._ensure_clients()
        client = svc._openai_client
        model = svc._model_deployment()
    except Exception as exc:
        logger.warning("Memory-Distillation: Foundry-Client fehlt (%s)", exc)
        return None

    prompt = _build_distillation_prompt(compacted_messages, project_slug)
    try:
        resp = client.responses.create(
            model=model,
            input=[{"type": "message", "role": "user", "content": prompt}],
            max_output_tokens=2000,
            stream=False,
            store=False,
        )
        text = getattr(resp, "output_text", None)
        if not text:
            for item in getattr(resp, "output", []) or []:
                for content in getattr(item, "content", []) or []:
                    t = getattr(content, "text", None)
                    if t:
                        text = (text or "") + t
        if not text:
            logger.warning("Memory-Distillation: leere LLM-Response")
            return None
    except Exception as exc:
        logger.warning("Memory-Distillation LLM-Call fehlgeschlagen (%s)", exc)
        return None

    # JSON parsen — manchmal kommt Markdown-Fence trotz Aufforderung.
    text = text.strip()
    if text.startswith("```"):
        # ```json\n...\n``` oder ```\n...\n```
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        parsed = _json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("Top-Level ist kein Objekt")
    except Exception as exc:
        logger.warning(
            "Memory-Distillation: JSON-Parse fehlgeschlagen (%s); raw: %s",
            exc, text[:200],
        )
        return None

    return parsed


def _apply_memory_distillation(
    distillation: dict[str, Any],
    project_slug: str,
) -> dict[str, Any]:
    """Wendet die LLM-Updates auf NOTES.md / DISCO.md / agent_table_docs an.

    Best-effort: jeder Teil wird einzeln versucht. Fehler in einem
    Block werden geloggt, brechen aber nicht den Rest ab.
    """
    from ..agent.context import use_project
    from ..agent.functions.memory import _memory_append
    from ..agent.functions.table_docs import _table_doc_set

    report: dict[str, Any] = {
        "notes_appended": False,
        "disco_chapters_added": 0,
        "table_docs_set": 0,
        "errors": [],
    }

    with use_project(project_slug):
        # NOTES-Eintrag
        notes_text = (distillation.get("notes_text") or "").strip()
        if notes_text:
            try:
                _memory_append(file="NOTES.md", content=notes_text)
                report["notes_appended"] = True
            except Exception as exc:
                logger.warning("Memory-Distillation NOTES-Append: %s", exc)
                report["errors"].append(f"notes: {exc}")

        # DISCO Schicht-2-Kapitel
        for chapter in distillation.get("disco_chapters") or []:
            if not isinstance(chapter, dict):
                continue
            heading = (chapter.get("heading") or "").strip()
            body = (chapter.get("body") or "").strip()
            if not heading or not body:
                continue
            try:
                _memory_append(
                    file="DISCO.md",
                    content=body,
                    heading=heading,
                    tags=chapter.get("tags") or None,
                    status=chapter.get("status") or "current",
                )
                report["disco_chapters_added"] += 1
            except Exception as exc:
                logger.warning(
                    "Memory-Distillation DISCO-Chapter '%s': %s", heading, exc,
                )
                report["errors"].append(f"disco/{heading}: {exc}")

        # agent_table_docs
        for td in distillation.get("table_docs") or []:
            if not isinstance(td, dict):
                continue
            tname = (td.get("table_name") or "").strip()
            layer = (td.get("layer") or "").strip()
            description = (td.get("description") or "").strip()
            if not tname or not layer or not description:
                continue
            try:
                _table_doc_set(
                    table_name=tname,
                    layer=layer,
                    description=description,
                    schema_summary=td.get("schema_summary") or None,
                    example_query=td.get("example_query") or None,
                    source_files=td.get("source_files") or None,
                )
                report["table_docs_set"] += 1
            except Exception as exc:
                logger.warning(
                    "Memory-Distillation table_doc_set '%s': %s", tname, exc,
                )
                report["errors"].append(f"table/{tname}: {exc}")

    return report


def run_compaction_with_handover(
    project_slug: str,
    keep_pairs: int = DEFAULT_KEEP_PAIRS,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Fuehrt die Compaction-v2-Sequenz aus.

    Schritte:
      1. Aktive Messages laden.
      2. Cutoff + Keep-Liste bestimmen (letzte keep_pairs user-Nachrichten
         und deren Assistant-Text-Antworten).
      3. Komprimierten Block an _generate_handover_brief uebergeben.
      4. Cutoff anwenden (mark_compacted), Handover-Brief als neue
         system-Message persistieren.
      5. foundry_response_id + measured_context_tokens zuruecksetzen,
         token_estimate neu rechnen.

    Gibt ein Report-Dict zurueck — fuer API-Antworten + Logging.
    """
    db = db_path or settings.db_path
    active = chat_repo.list_active_messages(project_slug, db_path=db)
    if len(active) <= keep_pairs * 2:
        # Zu wenig Verlauf, nichts zu komprimieren.
        return {
            "ok": True,
            "skipped": True,
            "reason": (
                f"Zu wenig aktiver Verlauf ({len(active)} Messages) — "
                f"mindestens {keep_pairs * 2 + 1} noetig."
            ),
            "marked_compacted": 0,
            "kept_ids": [int(m["id"]) for m in active],
        }

    cutoff, kept_ids = _find_cutoff_and_kept(active, keep_pairs)
    if cutoff is None:
        return {
            "ok": True,
            "skipped": True,
            "reason": "Kein Cutoff bestimmbar (Verlauf zu kurz).",
            "marked_compacted": 0,
            "kept_ids": kept_ids,
        }

    compacted_msgs = [m for m in active if int(m["id"]) <= cutoff]
    logger.info(
        "Compaction v2 (%s): %d zu komprimieren, %d bleiben",
        project_slug, len(compacted_msgs), len(active) - len(compacted_msgs),
    )

    # Schritt 1 (NEU 2026-05-09): Memory-Distillation. Bevor der
    # Cutoff den Verlauf einklappt, fragen wir das Modell nach
    # strukturierten Memory-Updates und wenden sie direkt auf
    # NOTES.md / DISCO.md / agent_table_docs an. Best-effort —
    # Fehler im LLM-Call oder JSON-Parse brechen die Compaction
    # NICHT ab.
    distillation_report: dict[str, Any] = {
        "notes_appended": False,
        "disco_chapters_added": 0,
        "table_docs_set": 0,
        "errors": [],
    }
    try:
        distillation = _generate_memory_distillation(compacted_msgs, project_slug)
        if distillation is not None:
            distillation_report = _apply_memory_distillation(distillation, project_slug)
            logger.info(
                "Memory-Distillation (%s): notes=%s chapters=%d tables=%d errors=%d",
                project_slug,
                distillation_report["notes_appended"],
                distillation_report["disco_chapters_added"],
                distillation_report["table_docs_set"],
                len(distillation_report["errors"]),
            )
    except Exception as exc:
        logger.warning(
            "Memory-Distillation komplett fehlgeschlagen (%s): %s — "
            "Compaction laeuft ohne Memory-Update weiter.",
            project_slug, exc,
        )
        distillation_report["errors"].append(f"top: {exc}")

    # Schritt 2: Handover-Brief ueber den komprimierten Block generieren.
    # Der Brief ist der Ersatz fuer den kompletten alten Verlauf — er
    # wird im naechsten Turn von build_responses_api_input als system →
    # developer Message wieder aufgegriffen.
    brief = _generate_handover_brief(compacted_msgs, project_slug)

    # Transaktional: erst komprimieren, dann Brief als neue system-Message
    # appenden. Die neue Message kommt nach dem Cutoff, also im aktiven
    # Bereich. token_estimate fortschreiben uebernehmen append_message +
    # recompute_token_estimate.
    marked = chat_repo.mark_compacted(project_slug, cutoff, db_path=db)
    chat_repo.append_message(
        project_slug=project_slug,
        role="system",
        content=brief,
        db_path=db,
    )

    # Chain-Reset: naechster Turn laeuft Stateless (Phase 2).
    chat_repo.set_response_id(project_slug, None, db_path=db)
    chat_repo.clear_measured_context(project_slug, db_path=db)
    new_estimate = chat_repo.recompute_token_estimate(project_slug, db_path=db)

    # Memory-Reform Phase 3: NOTES-Auto-Archiv. Einträge älter als
    # 30 Tage wandern bei jeder Compaction nach .disco/notes-archive/.
    # Idempotent + best-effort — Compaction selbst darf nicht crashen,
    # wenn das Archivieren schiefgeht.
    archive_report: dict[str, Any] = {"archived": 0}
    try:
        archive_report = archive_old_notes_entries(project_slug)
    except Exception as exc:
        logger.warning(
            "NOTES-Archivierung beim Compaction fehlgeschlagen (%s): %s",
            project_slug, exc,
        )
        archive_report = {"archived": 0, "error": str(exc)}

    return {
        "ok": True,
        "skipped": False,
        "marked_compacted": marked,
        "cutoff_message_id": int(cutoff),
        "kept_ids": kept_ids,
        "handover_brief_chars": len(brief),
        "new_token_estimate": new_estimate,
        "notes_archive": archive_report,
        "memory_distillation": distillation_report,
    }


# ---------------------------------------------------------------------------
# Memory-Reform Phase 3 — NOTES-Auto-Archiv
# ---------------------------------------------------------------------------

# Schwelle: Einträge älter als N Tage wandern in .disco/notes-archive/.
NOTES_ARCHIVE_THRESHOLD_DAYS = 30


def archive_old_notes_entries(
    project_slug: str,
    threshold_days: int = NOTES_ARCHIVE_THRESHOLD_DAYS,
    *,
    workspace_root: "Path | None" = None,
) -> dict[str, Any]:
    """Verschiebt alte NOTES-H2-Einträge in `.disco/notes-archive/<jahr-monat>.md`.

    NOTES.md wird durch H2-Header `## YYYY-MM-DD HH:MM:SS` strukturiert
    (siehe `memory_append`). Einträge älter als `threshold_days` werden
    pro Jahr-Monat zusammengefasst nach
    `.disco/notes-archive/<jahr-monat>.md` verschoben. Aktuelle NOTES.md
    behält die jüngeren Einträge.

    Idempotent + atomar (tmp+rename pro Datei). Best-effort: bei
    File-Fehler wird ein Report mit `error` zurückgegeben statt zu
    crashen.

    Returns:
        Report-Dict mit `archived` (Anzahl verschobene Einträge) und
        `kept` (Anzahl bleibende Einträge in NOTES.md).
    """
    from pathlib import Path
    from datetime import date, datetime, timedelta
    import re

    # Projekt-Root finden
    root = workspace_root
    if root is None:
        root = Path(settings.workspace_root) / "projects" / project_slug
    notes_path = root / "NOTES.md"
    if not notes_path.exists():
        return {"archived": 0, "kept": 0, "reason": "NOTES.md fehlt"}

    raw = notes_path.read_text(encoding="utf-8")
    # H2-Timestamp-Header finden: "## YYYY-MM-DD HH:MM:SS"
    pattern = re.compile(
        r"^## (\d{4}-\d{2}-\d{2})(?:[ T]\d{2}:\d{2}:\d{2})?\s*$",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(raw))
    if not matches:
        return {"archived": 0, "kept": 0, "reason": "keine Timestamp-H2-Einträge"}

    cutoff = date.today() - timedelta(days=threshold_days)

    # Header (alles vor dem ersten H2-Timestamp) bleibt erhalten
    header = raw[: matches[0].start()].rstrip()

    # Einträge: jeder von H2-Start bis zum nächsten H2-Start
    entries: list[tuple[date, str]] = []
    for i, m in enumerate(matches):
        try:
            entry_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        block = raw[m.start():end].rstrip() + "\n"
        entries.append((entry_date, block))

    to_archive = [(d, b) for d, b in entries if d < cutoff]
    to_keep = [(d, b) for d, b in entries if d >= cutoff]

    if not to_archive:
        return {"archived": 0, "kept": len(to_keep)}

    # Pro Jahr-Monat eine Archiv-Datei
    archive_dir = root / ".disco" / "notes-archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    by_month: dict[str, list[str]] = {}
    for d, block in to_archive:
        ym = d.strftime("%Y-%m")
        by_month.setdefault(ym, []).append(block)

    archived_files: list[str] = []
    for ym, blocks in sorted(by_month.items()):
        archive_path = archive_dir / f"{ym}.md"
        # Idempotent: append, wenn die Datei schon existiert (mit Trenner)
        if archive_path.exists():
            existing = archive_path.read_text(encoding="utf-8").rstrip()
            new_content = existing + "\n\n" + "\n".join(blocks)
        else:
            new_content = (
                f"# NOTES-Archiv {ym}\n\n"
                f"Einträge aus NOTES.md, archiviert per Auto-Archiv "
                f"(Schwelle: {threshold_days} Tage).\n\n"
                + "\n".join(blocks)
            )
        # Atomar schreiben
        tmp = archive_path.with_suffix(archive_path.suffix + ".tmp")
        tmp.write_text(new_content.rstrip() + "\n", encoding="utf-8")
        tmp.replace(archive_path)
        archived_files.append(archive_path.name)

    # Neues NOTES.md = Header + zu_behaltende Einträge
    new_notes = header.rstrip() + "\n\n" + "".join(b for _, b in to_keep)
    if not new_notes.endswith("\n"):
        new_notes += "\n"
    tmp = notes_path.with_suffix(notes_path.suffix + ".tmp")
    tmp.write_text(new_notes, encoding="utf-8")
    tmp.replace(notes_path)

    return {
        "archived": len(to_archive),
        "kept": len(to_keep),
        "archive_files": archived_files,
    }
