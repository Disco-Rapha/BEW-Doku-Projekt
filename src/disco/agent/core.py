"""AgentService — der Haupt-Agent auf Basis der Azure OpenAI Responses API.

Architektur (Migration 006+):

    User-Message                                Foundry (Sweden Central)
       |                                                 |
       v                                                 v
    AgentService.run_turn(project_slug, text)
       |
       |  1. AIProjectClient / OpenAI-Client
       |     -> authentifiziert gegen Foundry-Projekt-Endpoint
       |
       |  2. responses.create(stream=True,
       |        model=<deployment>,
       |        input=<user_text_oder_tool_outputs>,
       |        instructions=<system_prompt>,
       |        tools=[code_interpreter, *custom_functions],
       |        previous_response_id=<aus project_chat_state oder None>)
       |
       |  3. Event-Loop:
       |        - text.delta         -> yield text-Chunk
       |        - function_call.done -> via `dispatch(...)` ausfuehren
       |        - code_interpreter.* -> yield status
       |        - response.completed -> foundry_response_id merken, pruefen
       |                                ob Tool-Calls anstehen
       |
       |  4. Wenn Tool-Calls anstehen: neue Runde mit
       |     input=[{type: "function_call_output", call_id, output}, ...]
       |
       v
    yields typed events an die UI-Schicht

Persistenz (1-Chat-pro-Projekt, Migration 006):
  - `project_chat_state` haelt pro Projekt-Slug den letzten
    `foundry_response_id` (wird bei jeder fertigen Response aktualisiert)
    + eine Token-Schaetzung fuer die Kompressions-Warnung.
  - `chat_messages` spiegelt alle User-/Assistant-/Tool-Nachrichten
    lokal (mit `project_slug` als Foreign Key, nicht mehr `thread_id`).
    Bei Kompression werden Messages mit `is_compacted=1` markiert, nicht
    geloescht (Audit-Trail bleibt in der DB).

Wichtige Abgrenzung:
  - Der AgentService kennt keine WebSockets, kein FastAPI. Er ist reine
    Bibliothek. Die WebSocket-Schicht (`src/bew/api/main.py`) konsumiert
    die Events und streamt sie als JSON an den Browser.
  - Synchron implementiert; FastAPI kann sync-Generatoren via Worker-Thread
    + asyncio.Queue konsumieren.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import REPO_ROOT, settings
from ..chat import repo as chat_repo
from . import functions as fn_registry


logger = logging.getLogger(__name__)


SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.md"


# ---------------------------------------------------------------------------
# Event-Typen fuer den AgentService-Stream
# ---------------------------------------------------------------------------


@dataclass
class AgentEvent:
    """Basis fuer alles, was AgentService.run_turn() yieldet.

    Subklassen haben konkrete Felder. `type` ist ein stabiler String, den
    die UI-Schicht fuer den Renderer matcht.
    """

    type: str

    def to_dict(self) -> dict[str, Any]:
        # flache Serialisierung, passt fuer JSON-ueber-WebSocket
        out: dict[str, Any] = {"type": self.type}
        for k, v in self.__dict__.items():
            if k == "type":
                continue
            out[k] = v
        return out


@dataclass
class TextDeltaEvent(AgentEvent):
    text: str = ""
    type: str = "text_delta"


@dataclass
class ToolCallStartEvent(AgentEvent):
    call_id: str = ""
    name: str = ""
    type: str = "tool_call_start"


@dataclass
class ToolCallArgsEvent(AgentEvent):
    """Die vollstaendigen Argumente, nachdem das Modell sie zu Ende geschrieben hat."""

    call_id: str = ""
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    type: str = "tool_call_args"


@dataclass
class ToolResultEvent(AgentEvent):
    call_id: str = ""
    name: str = ""
    result: str = ""                # JSON-String, wie an Foundry zurueckgegeben
    type: str = "tool_result"


@dataclass
class CodeInterpreterEvent(AgentEvent):
    """Status-Events aus dem Foundry-Code-Interpreter (Built-in-Tool)."""

    phase: str = ""                 # "in_progress" | "interpreting" | "completed"
    code: str | None = None
    type: str = "code_interpreter"


@dataclass
class FileSearchEvent(AgentEvent):
    phase: str = ""                 # "in_progress" | "searching" | "completed"
    type: str = "file_search"


@dataclass
class ErrorEvent(AgentEvent):
    message: str = ""
    type: str = "error"


@dataclass
class DoneEvent(AgentEvent):
    response_id: str | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None
    total_token_estimate: int | None = None  # aktueller Chat-Fill nach diesem Turn
    type: str = "done"


# ---------------------------------------------------------------------------
# AgentService
# ---------------------------------------------------------------------------


class AgentService:
    """Fuehrt einen Chat-Turn gegen Foundry aus und streamt Events.

    Nutzung:
        svc = AgentService()
        for event in svc.run_turn(project_slug="anlage-musterstadt", user_text="Hi"):
            ... # event: AgentEvent
    """

    # Maximale Anzahl an Tool-Call-Runden pro Turn (Sicherheitsnetz gegen
    # Endlos-Loops bei fehlerhaftem Tool-Gebrauch durch das Modell).
    # 48 deckt Batch-Workflows ab (z.B. 16 Context-PDFs mit je 3-4
    # Tool-Calls = ~60 Calls). Bei echten Endlos-Loops greift das
    # Abort-Handling (offene Calls mit 'aborted' beantworten).
    MAX_TOOL_ROUNDS = 48

    def __init__(self) -> None:
        self._openai_client = None

    # -------------------- Client-Init (lazy) --------------------

    def _ensure_clients(self) -> None:
        """Baut einen OpenAI-kompatiblen Client gegen Foundry/Azure-OpenAI.

        Drei Auth-Varianten, in dieser Prioritaet (erste passende gewinnt):
          1. Foundry-Projekt-Endpoint + Foundry-API-Key (empfohlen) —
             ein Endpoint, ein Key, alle Modelle und Agents des Projekts.
          2. Azure-OpenAI-Resource-Endpoint + Azure-OpenAI-Key (klassisch) —
             direkte Ressource, falls jemand schon diese Credentials hat.
          3. Foundry-Endpoint + DefaultAzureCredential (`az login`) —
             fuer Managed-Identity/Prod ohne Keys.
        """
        if self._openai_client is not None:
            return

        try:
            from openai import AzureOpenAI, OpenAI
        except ImportError as exc:
            raise RuntimeError("openai-Paket fehlt. `uv sync` laufen lassen.") from exc

        # Weg 1: Foundry Project (Endpoint + Project-API-Key)
        # Der neue /openai/v1 Pfad ist versionslos — api-version als Query-Param
        # wird abgelehnt ("api-version query parameter is not allowed when using
        # /v1 path"). Der OpenAI-SDK-Client spricht /v1 nativ.
        #
        # Timeout: 30 Minuten. Disco macht manchmal lange Turns (16 DI-
        # Extraktionen + SQL + fs_write = 10-20 Min pro Turn). Der Default
        # von 600s (10 Min) reicht dafuer nicht.
        import httpx as _httpx
        _client_timeout = _httpx.Timeout(1800.0, connect=30.0)

        if settings.foundry_endpoint and settings.foundry_api_key:
            base_url = settings.foundry_endpoint.rstrip("/") + "/openai/v1"
            self._openai_client = OpenAI(
                base_url=base_url,
                api_key=settings.foundry_api_key,
                timeout=_client_timeout,
            )
            logger.info(
                "Foundry-Client (Project-API-Key, /openai/v1): endpoint=%s deployment=%s",
                settings.foundry_endpoint,
                self._model_deployment(),
            )
            return

        # Weg 2: Azure OpenAI Resource (klassisch)
        if settings.azure_openai_endpoint and settings.azure_openai_key:
            self._openai_client = AzureOpenAI(
                azure_endpoint=settings.azure_openai_endpoint,
                api_key=settings.azure_openai_key,
                api_version=settings.azure_openai_api_version,
                timeout=_client_timeout,
            )
            logger.info(
                "Azure-OpenAI-Client (Resource-Key): endpoint=%s api_version=%s deployment=%s",
                settings.azure_openai_endpoint,
                settings.azure_openai_api_version,
                self._model_deployment(),
            )
            return

        # Weg 3: Foundry via DefaultAzureCredential (az login)
        if settings.foundry_endpoint:
            try:
                from azure.ai.projects import AIProjectClient
                from azure.identity import DefaultAzureCredential
            except ImportError as exc:
                raise RuntimeError(
                    "azure-ai-projects/azure-identity fehlt. `uv sync`."
                ) from exc

            credential = DefaultAzureCredential()
            project_client = AIProjectClient(
                endpoint=settings.foundry_endpoint,
                credential=credential,
            )
            self._openai_client = project_client.get_openai_client()
            logger.info(
                "Foundry-Client (DefaultAzureCredential): endpoint=%s deployment=%s",
                settings.foundry_endpoint,
                self._model_deployment(),
            )
            return

        raise RuntimeError(
            "Kein Auth-Weg konfiguriert. In .env eintragen:\n"
            "  Variante A (empfohlen): FOUNDRY_ENDPOINT + FOUNDRY_API_KEY\n"
            "  Variante B (klassisch): AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_KEY + AZURE_OPENAI_DEPLOYMENT\n"
            "  Variante C (Azure AD): FOUNDRY_ENDPOINT + vorher `az login`"
        )

    def _model_deployment(self) -> str:
        """Bevorzugt AZURE_OPENAI_DEPLOYMENT, faellt zurueck auf FOUNDRY_MODEL_DEPLOYMENT."""
        return (
            settings.azure_openai_deployment
            or settings.foundry_model_deployment
        )

    # -------------------- Tool-Liste (Fallback-Weg) --------------------

    def _build_tools(self, file_search_vector_store_ids: list[str] | None = None) -> list[dict]:
        """Baut die Tool-Liste fuer den Fallback-Weg (ohne Portal-Agent).

        Wird nur genutzt, wenn KEIN Portal-Agent konfiguriert ist. Beim
        Portal-Agent-Weg liegen Tools zentral im Portal.
        """
        tools: list[dict] = fn_registry.get_tool_schemas()
        tools.append({"type": "code_interpreter", "container": {"type": "auto"}})
        if file_search_vector_store_ids:
            tools.append(
                {
                    "type": "file_search",
                    "vector_store_ids": list(file_search_vector_store_ids),
                }
            )
        return tools

    def _system_prompt(self) -> str:
        """Fallback-System-Prompt fuer den Direkt-Modell-Weg."""
        try:
            return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        except OSError:
            logger.warning("system_prompt.md nicht lesbar — nutze Fallback")
            return "Du bist Disco — Reasoning-Assistent fuer technische Dokumentation. Antworte auf Deutsch."

    # -------------------- Agent-Referenz (Portal-Agent-Weg) --------------------

    def _agent_reference(self) -> dict | None:
        """Wenn FOUNDRY_AGENT_ID in .env gesetzt ist, geben wir eine
        agent_reference fuer den `extra_body`-Param zurueck.

        Formate, die wir akzeptieren:
          - "disco-prod-agent"      -> name=disco-prod-agent, latest Version
          - "disco-prod-agent:2"    -> name=disco-prod-agent, version=2
        """
        raw = (settings.foundry_agent_id or "").strip()
        if not raw:
            return None
        name, _, version = raw.partition(":")
        ref: dict[str, Any] = {"type": "agent_reference", "name": name}
        if version:
            ref["version"] = version
        return ref

    # -------------------- Haupt-Methode --------------------

    def run_turn(
        self,
        project_slug: str,
        user_text: str,
        file_search_vector_store_ids: list[str] | None = None,
        _system_trigger: dict[str, Any] | None = None,
    ) -> Iterator[AgentEvent]:
        """Fuehrt einen kompletten Turn aus (User-Nachricht -> Assistant-Antwort).

        Ein Chat ist an ein Projekt gebunden (`project_slug`). Der
        letzte `foundry_response_id` wird in `project_chat_state`
        gehalten und als `previous_response_id` im naechsten Turn
        wiederverwendet — so entsteht die Conversation-Kette bei
        Foundry.

        Spiegelt User- und Assistant-Nachrichten in `chat_messages`.
        Yield'et typisierte Events fuer die UI.

        `_system_trigger` ist Teil der internen API fuer
        `run_system_turn()` — typische Caller setzen es NICHT. Wenn
        es gesetzt ist, erwartet run_turn ein Dict mit Keys:

            {"kind": "status_change"|"scheduled_check"|"done"|"failed",
             "summary": "kurz fuer UI",
             "is_system": True}

        In diesem Fall wird die Message mit role='system' persistiert
        (statt 'user'), der Developer-Context-Block erhaelt einen
        SYSTEM-TRIGGER-Hinweis, und der ContextVar
        `is_system_triggered()` steht fuer die Dauer des Turns auf
        True (wird von `flow_run` zum Ablehnen genutzt).
        """
        if not project_slug or not project_slug.strip():
            yield ErrorEvent(
                message="Kein aktives Projekt. Jeder Chat braucht einen project_slug."
            )
            return
        project_slug = project_slug.strip()

        try:
            self._ensure_clients()
        except Exception as exc:
            yield ErrorEvent(message=str(exc))
            return

        # State holen (legt bei Bedarf an) + Eingangs-Message persistieren.
        # Bei System-Trigger speichern wir eine role='system'-Message mit
        # der kurzen Zusammenfassung (summary), nicht den vollen
        # Trigger-Kontext. Die volle Trigger-Info geht als user_text
        # direkt in den Foundry-Call, damit das Modell sie sieht.
        state = chat_repo.get_or_create_state(project_slug)
        if _system_trigger:
            chat_repo.append_message(
                project_slug,
                role="system",
                content=_system_trigger.get("summary") or "[System-Trigger]",
            )
        else:
            chat_repo.append_message(project_slug, role="user", content=user_text)

        logger.info(
            "run_turn project=%s prev_response_id=%s token_estimate=%d%s (Sandbox aktiv)",
            project_slug,
            state.get("foundry_response_id") or "-",
            state.get("token_estimate") or 0,
            " [SYSTEM-TRIGGER]" if _system_trigger else "",
        )

        # Projekt-Kontext aktivieren — gilt fuer alle Tool-Aufrufe in
        # diesem Turn (fs_*, sqlite_*, memory_*). Reset im finally am Ende.
        from .context import _current_project, _is_system_triggered
        _ctx_token = _current_project.set(project_slug)
        _sys_token = _is_system_triggered.set(bool(_system_trigger))

        previous_response_id: str | None = state.get("foundry_response_id")

        # Projekt-Kontext als developer-Message prependen.
        # Damit weiss Disco in jedem Turn ohne Nachfrage, in welchem Projekt er
        # arbeitet — und er bekommt beruecksichtigt, dass list_projects /
        # get_project_details / search_documents / list_documents in dieser
        # Session NUR das aktive Projekt zeigen.
        current_input: str | list[dict]
        from ..projects import get_project_by_slug
        _p_info = get_project_by_slug(project_slug)
        # Optionaler Zusatz-Block fuer System-Trigger. Disco muss explizit
        # verstehen, dass er NICHT vom User angesprochen wurde, sondern
        # vom System wegen eines Flow-Ereignisses. Die Nachricht erklaert
        # Arbeitsweise + die asymmetrische Auto-Aktions-Regel (cancel/pause
        # ok, neu starten verboten).
        trigger_block = ""
        if _system_trigger:
            kind = _system_trigger.get("kind", "unknown")
            trigger_block = (
                "\n\n[SYSTEM-TRIGGER — kein Nutzer-Input]\n"
                f"kind: {kind}\n"
                "Du wurdest vom System aufgeweckt, weil ein Flow-Ereignis "
                "eingetreten ist. Dein Auftrag:\n"
                "  1. Trigger-Kontext unten lesen.\n"
                "  2. Kurz pruefen (NOTES, Skills, flow_status), ob die "
                "Ergebnisse den Erwartungen entsprechen.\n"
                "  3. Knapp im Chat mitteilen, was Du gesehen hast — der "
                "Nutzer liest das asynchron.\n\n"
                "REGELN fuer den System-Turn:\n"
                "  - flow_pause und flow_cancel DARFST Du autonom aufrufen, "
                "wenn Du einen systematischen Fehler siehst (Cost-Protection).\n"
                "  - flow_run (neuer Run) ist GESPERRT — Kosten erfordern "
                "menschliche Freigabe. Schreib stattdessen eine Empfehlung "
                "in den Chat.\n"
                "  - Halte Dich kurz. Ein System-Turn ist ein Statusbericht, "
                "kein vollstaendiger Deep-Dive.\n"
            )

        if _p_info is not None:
            # Env-Label fuer die Disco-Instanz (prod|dev). Wird vom
            # DISCO_ENV-Flag in der .env gesetzt — so weiss Disco ob er
            # in der Produktiv-Umgebung oder der Dev-Sandbox laeuft.
            _env_label = (settings.disco_env or "prod").strip().lower()
            _env_display = "PROD" if _env_label == "prod" else "DEV"
            _agent_display = settings.foundry_agent_id or "—"
            _ctx_text = (
                f"[DISCO-UMGEBUNG: {_env_display}]\n"
                f"agent_id: {_agent_display}\n"
                f"env: {_env_label}\n\n"
                "[AKTIVES PROJEKT — aus Sandbox-Kontext]\n"
                f"slug: {_p_info.get('slug')}\n"
                f"id: {_p_info['id']}\n"
                f"name: {_p_info['name']}\n"
                f"description: {_p_info.get('description') or '—'}\n\n"
                "Du arbeitest bereits IN diesem Projekt. fs_*- und "
                "sqlite_*-Tools sind auf dessen Verzeichnis bzw. "
                "data.db gescoped. memory_*-Tools schreiben auf die "
                "drei Memory-Dateien im Projekt-Root (README.md, "
                "NOTES.md, DISCO.md). "
                "Frage den Nutzer NICHT 'in welchem Projekt arbeiten wir' "
                "— das ist oben bereits gesetzt. Rufe list_projects "
                "NICHT als Start-Check auf (es liefert in der Sandbox "
                "ohnehin nur dieses eine Projekt). "
                "Andere Projekte existieren fuer Dich in dieser Sitzung "
                "nicht."
                + trigger_block
            )
            current_input = [
                {"type": "message", "role": "developer", "content": _ctx_text},
                {"type": "message", "role": "user", "content": user_text},
            ]
        else:
            # Projekt nur im Workspace, nicht in system.db — trotzdem arbeiten
            if _system_trigger:
                # Ohne Projekt-Info-Block muessen wir den Trigger-Block
                # separat als developer-Message schicken, damit Disco die
                # System-Trigger-Regeln kennt.
                current_input = [
                    {
                        "type": "message",
                        "role": "developer",
                        "content": trigger_block.strip(),
                    },
                    {"type": "message", "role": "user", "content": user_text},
                ]
            else:
                current_input = user_text

        # Zwei Wege:
        #   (A) Portal-Agent per ID: Modell + Prompt + Tools kommen aus dem
        #       Foundry-Projekt. Nur input, ggf. previous_response_id noetig.
        #   (B) Direkt-Modell (Fallback): Modell + Prompt + Tools muessen bei
        #       jedem Call mitgeschickt werden.
        agent_ref = self._agent_reference()
        use_portal_agent = agent_ref is not None

        if not use_portal_agent:
            tools = self._build_tools(file_search_vector_store_ids)
            instructions = self._system_prompt()
            model = self._model_deployment()
        else:
            logger.info("run_turn: Portal-Agent-Weg via agent_reference=%s", agent_ref)

        assistant_text_buf: list[str] = []
        last_response_id: str | None = None
        last_usage: dict[str, Any] | None = None
        recorded_tool_calls: list[dict[str, Any]] = []
        recorded_tool_results: list[dict[str, Any]] = []

        for round_idx in range(self.MAX_TOOL_ROUNDS):
            # Jede Runde ein Responses.create-Call.
            # Zwei Formen, abhaengig von use_portal_agent:
            call_kwargs: dict[str, Any] = dict(
                input=current_input,
                stream=True,
                store=True,
                # gpt-5 Hard-Cap: 128 000 Output-Tokens je Response (Foundry).
                # Wir nutzen den Vollwert — jede Drosselung darunter waere
                # kuenstlich. Bei normalen Antworten produziert das Modell
                # eh nur die paar 100 Tokens, die es braucht.
                max_output_tokens=128_000,
            )
            if use_portal_agent:
                # Portal-Agent-Weg: Modell/Prompt/Tools kommen aus dem Portal.
                # Die agent_reference wird ueber extra_body geschickt, weil
                # es eine Azure-Erweiterung der OpenAI-Responses-API ist.
                # WICHTIG: `reasoning` / `text` duerfen hier NICHT mitkommen —
                # Foundry antwortet sonst mit HTTP 400 "Not allowed when agent
                # is specified". Diese Settings gehoeren in die Portal-Agent-
                # Definition selbst (siehe scripts/foundry_setup.py).
                call_kwargs["extra_body"] = {"agent_reference": agent_ref}
            else:
                # Direkt-Modell-Weg (ohne Portal-Agent) — hier duerfen wir
                # reasoning/verbosity pro Request steuern.
                call_kwargs["model"] = model
                call_kwargs["instructions"] = instructions
                call_kwargs["tools"] = tools
                # GPT-5.1 Inference-Settings (siehe config.py). Offizielle
                # Responses-API-Form.
                call_kwargs["reasoning"] = {"effort": settings.foundry_reasoning_effort}
                call_kwargs["text"] = {"verbosity": settings.foundry_verbosity}

            # previous_response_id nur uebergeben, wenn gesetzt — sonst meldet
            # die API "type: Value is 'null' but should be 'string'"
            if previous_response_id:
                call_kwargs["previous_response_id"] = previous_response_id
            try:
                stream = self._openai_client.responses.create(**call_kwargs)
            except Exception as exc:
                logger.exception("responses.create fehlgeschlagen")
                yield ErrorEvent(message=f"Foundry-Call fehlgeschlagen: {exc}")
                return

            # Pro Runde sammeln.
            # Key = Output-Item-ID (fc_xxx), Value.call_id = Function-Call-ID
            # (call_xxx). Beide IDs sind unterschiedlich! fc_xxx matched die
            # spaeteren arguments.delta/done Events, call_xxx gehoert ins
            # function_call_output-Input beim naechsten responses.create.
            pending_tool_calls: dict[str, dict[str, Any]] = {}

            try:
                for event in stream:
                    etype = getattr(event, "type", "")

                    # --- Text-Streaming ---
                    if etype == "response.output_text.delta":
                        delta = getattr(event, "delta", "") or ""
                        assistant_text_buf.append(delta)
                        yield TextDeltaEvent(text=delta)

                    # --- Function-Calls (unsere Custom Functions) ---
                    elif etype == "response.output_item.added":
                        item = getattr(event, "item", None)
                        if item is not None and getattr(item, "type", "") == "function_call":
                            item_id = getattr(item, "id", "") or ""
                            call_id = getattr(item, "call_id", "") or item_id
                            name = getattr(item, "name", "") or ""
                            pending_tool_calls[item_id] = {
                                "call_id": call_id,
                                "name": name,
                                "args_buf": [],
                            }
                            yield ToolCallStartEvent(call_id=call_id, name=name)

                    elif etype == "response.function_call_arguments.delta":
                        item_id = getattr(event, "item_id", "") or ""
                        delta = getattr(event, "delta", "") or ""
                        entry = pending_tool_calls.get(item_id)
                        if entry is not None:
                            entry["args_buf"].append(delta)

                    elif etype == "response.function_call_arguments.done":
                        item_id = getattr(event, "item_id", "") or ""
                        args_json = getattr(event, "arguments", "") or ""
                        entry = pending_tool_calls.get(item_id)
                        if entry is not None:
                            name = entry["name"]
                            call_id = entry["call_id"]
                        else:
                            # Fallback: falls output_item.added nie kam
                            name = getattr(event, "name", "") or ""
                            call_id = item_id
                            pending_tool_calls[item_id] = {
                                "call_id": call_id,
                                "name": name,
                                "args_buf": [],
                            }
                            entry = pending_tool_calls[item_id]
                        try:
                            parsed_args = json.loads(args_json) if args_json else {}
                        except json.JSONDecodeError:
                            parsed_args = {"_raw": args_json}
                        entry["arguments"] = parsed_args
                        yield ToolCallArgsEvent(
                            call_id=call_id, name=name, arguments=parsed_args
                        )

                    # --- Code Interpreter (Built-in) ---
                    elif etype == "response.code_interpreter_call.in_progress":
                        yield CodeInterpreterEvent(phase="in_progress")
                    elif etype == "response.code_interpreter_call_code.delta":
                        # Wir streamen Code-Fragmente nicht einzeln — nur bei done
                        pass
                    elif etype == "response.code_interpreter_call_code.done":
                        code = getattr(event, "code", None)
                        yield CodeInterpreterEvent(phase="code", code=code)
                    elif etype == "response.code_interpreter_call.interpreting":
                        yield CodeInterpreterEvent(phase="interpreting")
                    elif etype == "response.code_interpreter_call.completed":
                        yield CodeInterpreterEvent(phase="completed")

                    # --- File Search (Built-in) ---
                    elif etype == "response.file_search_call.in_progress":
                        yield FileSearchEvent(phase="in_progress")
                    elif etype == "response.file_search_call.searching":
                        yield FileSearchEvent(phase="searching")
                    elif etype == "response.file_search_call.completed":
                        yield FileSearchEvent(phase="completed")

                    # --- Fertig mit dieser Runde ---
                    elif etype == "response.completed":
                        resp = getattr(event, "response", None)
                        if resp is not None:
                            last_response_id = getattr(resp, "id", None) or last_response_id
                            usage = getattr(resp, "usage", None)
                            if usage is not None:
                                last_usage = {
                                    "input": getattr(usage, "input_tokens", None),
                                    "output": getattr(usage, "output_tokens", None),
                                }

                    # --- Fehler / Abbruch ---
                    elif etype == "response.failed":
                        # Foundry liefert bei 429 / Rate-Limit / Server-Fehlern
                        # oft nur ein Teil-Feld. Wir ziehen alles raus, was da
                        # ist, loggen den Rohzustand fuer Post-Mortem und
                        # bauen dem User eine reichere Meldung zusammen.
                        err = getattr(event, "response", None)
                        err_obj = getattr(err, "error", None)
                        msg = getattr(err_obj, "message", None)
                        code = getattr(err_obj, "code", None)
                        type_ = getattr(err_obj, "type", None)
                        status = getattr(err, "status", None)
                        logger.error(
                            "Foundry response.failed — code=%r type=%r status=%r msg=%r event=%r",
                            code, type_, status, msg, event,
                        )
                        parts = [str(p) for p in (code, type_, msg) if p]
                        ui_msg = " — ".join(parts) if parts else "keine Details von Foundry"
                        yield ErrorEvent(message=f"Foundry meldet Fehler: {ui_msg}")
                        return
                    elif etype == "error":
                        msg = getattr(event, "message", "") or ""
                        code = getattr(event, "code", None) or getattr(event, "type", None)
                        logger.error(
                            "Stream-Error-Event — code=%r msg=%r event=%r",
                            code, msg, event,
                        )
                        parts = [str(p) for p in (code, msg) if p]
                        ui_msg = " — ".join(parts) if parts else repr(event)
                        yield ErrorEvent(message=f"Stream-Fehler: {ui_msg}")
                        return

                    # andere Events (refusal, reasoning, mcp, image_gen, ...)
                    # ignorieren wir still — bei Bedarf spaeter ergaenzen.

            except Exception as exc:
                # openai.APIError traegt body/code/status mit. Ohne explizites
                # Ausziehen geht die eigentliche Ursache (z. B. 429 Rate-Limit)
                # im Log verloren und die UI sieht nur "Too Many Requests".
                detail_parts: list[str] = []
                status_code: int | None = None
                code: str | None = None
                body: Any = None
                try:
                    from openai import APIError, APIStatusError  # lazy
                    if isinstance(exc, APIError):
                        code = getattr(exc, "code", None)
                        body = getattr(exc, "body", None)
                        if isinstance(exc, APIStatusError):
                            status_code = getattr(exc, "status_code", None)
                except Exception:
                    pass

                # Azure-429 erkennen auch dann, wenn status_code fehlt
                # (SSE-Stream-Error liefert oft nur message "Too Many Requests")
                msg_text = str(exc) or ""
                is_rate_limit = (
                    status_code == 429
                    or "429" in msg_text
                    or "too many requests" in msg_text.lower()
                    or (isinstance(code, str) and "rate" in code.lower())
                )

                if status_code is not None:
                    detail_parts.append(f"status={status_code}")
                if code:
                    detail_parts.append(f"code={code}")
                if body is not None:
                    detail_parts.append(f"body={body!r}")
                detail = " [" + " ".join(detail_parts) + "]" if detail_parts else ""

                logger.exception("Fehler im Event-Stream%s", detail)

                if is_rate_limit:
                    ui_msg = (
                        f"Azure OpenAI Rate-Limit (429): {msg_text or 'Too Many Requests'}. "
                        "Moeglicherweise laeuft parallel ein Flow auf demselben Deployment — "
                        "kurz warten und erneut versuchen."
                    )
                else:
                    ui_msg = f"Stream-Fehler: {msg_text}{detail}"
                yield ErrorEvent(message=ui_msg)
                return

            # Nach der Runde: previous_response_id fuer die naechste Runde merken
            if last_response_id:
                previous_response_id = last_response_id

            # Wenn keine Tool-Calls offen sind, ist der Turn beendet
            tool_calls_to_dispatch = [
                (iid, d) for iid, d in pending_tool_calls.items() if "arguments" in d
            ]
            if not tool_calls_to_dispatch:
                break

            # Tool-Calls ausfuehren und als next-round-input vorbereiten.
            # Beim function_call_output-Input wird die call_id verwendet
            # (nicht die item_id).
            next_input: list[dict] = []
            for item_id, d in tool_calls_to_dispatch:
                call_id = d["call_id"]
                name = d["name"]
                args = d["arguments"]
                result_json = fn_registry.dispatch(name, args)

                recorded_tool_calls.append(
                    {"call_id": call_id, "name": name, "arguments": args}
                )
                recorded_tool_results.append(
                    {"call_id": call_id, "name": name, "result": result_json}
                )

                yield ToolResultEvent(call_id=call_id, name=name, result=result_json)

                next_input.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": result_json,
                    }
                )

            current_input = next_input
            # Schleife faehrt fort mit neuem responses.create-Call
        else:
            # for-else: Schleife ist ohne break durchgelaufen -> Max-Rounds.
            # WICHTIG: Wir muessen die letzten offenen Tool-Calls noch
            # "abschliessen" (mit synthetischem Output an Foundry zuruecksenden),
            # sonst bleibt die Conversation mit unbeantwortetem function_call
            # haengen und der NAECHSTE Turn scheitert mit
            # "No tool output found for function call ...".
            pending_unanswered = [
                (iid, d) for iid, d in pending_tool_calls.items()
                if "arguments" in d
            ]
            if pending_unanswered and previous_response_id:
                abort_outputs = [
                    {
                        "type": "function_call_output",
                        "call_id": d["call_id"],
                        "output": json.dumps({
                            "error": "aborted",
                            "reason": f"Max. {self.MAX_TOOL_ROUNDS} Tool-Call-Runden erreicht. "
                                      "Agent hat zu viele Tool-Calls produziert, Turn wurde abgebrochen.",
                        }),
                    }
                    for _, d in pending_unanswered
                ]
                try:
                    # Blocking, aber kein Streaming noetig — nur "close the loop"
                    close_resp = self._openai_client.responses.create(
                        input=abort_outputs,
                        previous_response_id=previous_response_id,
                        store=True,
                        max_output_tokens=200,
                        **({"extra_body": {"agent_reference": agent_ref}}
                           if use_portal_agent else {
                               "model": model,
                               "instructions": instructions,
                               "tools": tools,
                           }),
                    )
                    last_response_id = getattr(close_resp, "id", last_response_id)
                except Exception as exc:
                    logger.warning("Abort-Close fehlgeschlagen: %s", exc)
            yield ErrorEvent(
                message=f"Max. {self.MAX_TOOL_ROUNDS} Tool-Call-Runden erreicht. "
                        "Turn wurde sauber beendet — Du kannst direkt einen neuen Prompt senden."
            )

        # Assistant-Antwort persistieren
        full_text = "".join(assistant_text_buf)
        chat_repo.append_message(
            project_slug=project_slug,
            role="assistant",
            content=full_text if full_text else None,
            tool_calls=recorded_tool_calls or None,
            foundry_message_id=last_response_id,
            tokens_input=(last_usage or {}).get("input") if last_usage else None,
            tokens_output=(last_usage or {}).get("output") if last_usage else None,
        )
        if recorded_tool_results:
            chat_repo.append_message(
                project_slug=project_slug,
                role="tool",
                tool_results=recorded_tool_results,
            )

        # Foundry-Response-ID im project_chat_state speichern (fuer naechsten Turn)
        if last_response_id:
            chat_repo.set_response_id(project_slug, last_response_id)

        # Aktuellen Token-Fill fuer die UI holen (70/90-Warnung)
        current_state = chat_repo.get_state(project_slug)
        current_token_estimate = (
            int(current_state["token_estimate"]) if current_state else None
        )

        yield DoneEvent(
            response_id=last_response_id,
            tokens_input=(last_usage or {}).get("input") if last_usage else None,
            tokens_output=(last_usage or {}).get("output") if last_usage else None,
            total_token_estimate=current_token_estimate,
        )

        # Projekt-Kontext + System-Trigger-Flag zuruecksetzen
        # (verhindert Leak in andere Turns)
        try:
            _current_project.reset(_ctx_token)
        except Exception:
            pass
        try:
            _is_system_triggered.reset(_sys_token)
        except Exception:
            pass

    # -------------------- System-Trigger --------------------

    def run_system_turn(
        self,
        project_slug: str,
        trigger_kind: str,
        trigger_summary: str,
        trigger_context: str,
    ) -> Iterator[AgentEvent]:
        """Fuehrt einen vom System ausgeloesten Turn aus.

        Wird von `flow_notifications.process_pending_notifications()`
        gerufen, wenn ein Worker eine Notification in die DB gelegt hat
        (erstes Item fertig, Heartbeat, Run beendet, ...).

        Unterschiede zu run_turn:
          - Input-Message wird als role='system' persistiert (die UI kann
            sie als Trigger-Bubble rendern, nicht als User-Nachricht).
          - Developer-Context erklaert die System-Trigger-Regeln (asym-
            metrische Auto-Aktion).
          - Der ContextVar `is_system_triggered()` steht auf True, damit
            `flow_run` autonome Neustarts verweigern kann.

        Parameter
        ---------
        trigger_kind : str
            status_change | scheduled_check | done | failed.
            (Legacy-Kinds first_item/second_item/half/heartbeat werden
            vom Watcher inzwischen stumm silenced — kommen hier in der
            Regel nicht mehr an.)
        trigger_summary : str
            Kurz (eine Zeile), wird im Chat als role='system'-Message
            persistiert. Beispiel: "Zwischenstand Run #5 (3/100) — laeuft 6 min".
        trigger_context : str
            Voller Trigger-Text mit Run-Stand, letzten Items, Logs,
            Flow-README-Excerpt, urspruenglicher Erwartung. Wird als
            user_text an Foundry geschickt (aber nicht persistiert).
        """
        yield from self.run_turn(
            project_slug=project_slug,
            user_text=trigger_context,
            _system_trigger={
                "kind": trigger_kind,
                "summary": trigger_summary,
                "is_system": True,
            },
        )


# Modul-weites Singleton — leichter Wiederverwendungsfall aus FastAPI
_default_service: AgentService | None = None


def get_agent_service() -> AgentService:
    """Gibt das Prozess-weite AgentService-Singleton zurueck (lazy)."""
    global _default_service
    if _default_service is None:
        _default_service = AgentService()
    return _default_service


# Silencer-Re-Export: Nutzer koennten ihn brauchen
__all__ = [
    "AgentService",
    "AgentEvent",
    "TextDeltaEvent",
    "ToolCallStartEvent",
    "ToolCallArgsEvent",
    "ToolResultEvent",
    "CodeInterpreterEvent",
    "FileSearchEvent",
    "ErrorEvent",
    "DoneEvent",
    "get_agent_service",
    "REPO_ROOT",
]
