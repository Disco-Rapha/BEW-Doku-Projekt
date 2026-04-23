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

    # Handover-Brief ueber den komprimierten Block generieren. Der Brief
    # ist der Ersatz fuer den kompletten alten Verlauf — er wird im
    # naechsten Turn von build_responses_api_input als system → developer
    # Message wieder aufgegriffen.
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

    return {
        "ok": True,
        "skipped": False,
        "marked_compacted": marked,
        "cutoff_message_id": int(cutoff),
        "kept_ids": kept_ids,
        "handover_brief_chars": len(brief),
        "new_token_estimate": new_estimate,
    }
