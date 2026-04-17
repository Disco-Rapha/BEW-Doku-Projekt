"""AgentService — der Haupt-Agent auf Basis der Azure OpenAI Responses API.

Architektur (Phase 2a):

    User-Message                                Foundry (Sweden Central)
       |                                                 |
       v                                                 v
    AgentService.run_turn(thread_id, text)
       |
       |  1. AIProjectClient (azure-ai-projects)
       |     -> get_openai_client() liefert authentifizierten OpenAI-Client
       |
       |  2. responses.create(stream=True,
       |        model=<deployment>,
       |        input=<user_text_oder_tool_outputs>,
       |        instructions=<system_prompt>,
       |        tools=[code_interpreter, file_search, *custom_functions],
       |        previous_response_id=<letzte_id_oder_None>)
       |
       |  3. Event-Loop:
       |        - text.delta         -> yield text-Chunk
       |        - function_call.done -> via `dispatch(...)` ausfuehren
       |        - code_interpreter.* -> yield status
       |        - response.completed -> previous_response_id merken, pruefen
       |                                ob Tool-Calls anstehen
       |
       |  4. Wenn Tool-Calls anstehen: neue Runde mit
       |     input=[{type: "function_call_output", call_id, output}, ...]
       |
       v
    yields typed events an die UI-Schicht

Persistenz:
  - BEW-thread_id -> Foundry-Conversation wird via
    `chat_threads.foundry_thread_id` gespeichert (erste Response erzeugt die
    Conversation-ID).
  - Jede User-/Assistant-/Tool-Nachricht wird zusaetzlich lokal in
    `chat_messages` gespiegelt.

Wichtige Abgrenzung:
  - Der AgentService kennt keine WebSockets, kein FastAPI. Er ist reine
    Bibliothek. Die WebSocket-Schicht (`src/bew/api/main.py`) konsumiert
    die Events und streamt sie als JSON an den Browser.
  - Synchron implementiert; FastAPI kann sync-Generatoren via
    `anyio.to_thread.run_sync` konsumieren.
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
    type: str = "done"


# ---------------------------------------------------------------------------
# AgentService
# ---------------------------------------------------------------------------


class AgentService:
    """Fuehrt einen Chat-Turn gegen Foundry aus und streamt Events.

    Nutzung:
        svc = AgentService()
        for event in svc.run_turn(thread_id=17, user_text="Hi"):
            ... # event: AgentEvent
    """

    # Maximale Anzahl an Tool-Call-Runden pro Turn (Sicherheitsnetz gegen
    # Endlos-Loops bei fehlerhaftem Tool-Gebrauch durch das Modell).
    # 24 deckt realistische Workflows (sources-onboarding mit register +
    # metadata + duplicates + mehreren SQL-Verifikationen) ab.
    MAX_TOOL_ROUNDS = 24

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
        if settings.foundry_endpoint and settings.foundry_api_key:
            base_url = settings.foundry_endpoint.rstrip("/") + "/openai/v1"
            self._openai_client = OpenAI(
                base_url=base_url,
                api_key=settings.foundry_api_key,
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
            return "Du bist der BEW-Dokumenten-Assistent. Antworte auf Deutsch."

    # -------------------- Agent-Referenz (Portal-Agent-Weg) --------------------

    def _agent_reference(self) -> dict | None:
        """Wenn FOUNDRY_AGENT_ID in .env gesetzt ist, geben wir eine
        agent_reference fuer den `extra_body`-Param zurueck.

        Formate, die wir akzeptieren:
          - "bew-doku-agent"      -> name=bew-doku-agent, latest Version
          - "bew-doku-agent:2"    -> name=bew-doku-agent, version=2
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
        thread_id: int,
        user_text: str,
        file_search_vector_store_ids: list[str] | None = None,
    ) -> Iterator[AgentEvent]:
        """Fuehrt einen kompletten Turn aus (User-Nachricht -> Assistant-Antwort).

        Spiegelt User- und Assistant-Nachrichten in `chat_messages`.
        Yield'et typisierte Events fuer die UI.
        """
        try:
            self._ensure_clients()
        except Exception as exc:
            yield ErrorEvent(message=str(exc))
            return

        # User-Message persistieren
        thread = chat_repo.get_thread(thread_id)
        chat_repo.append_message(thread_id, role="user", content=user_text)

        # Projekt-Kontext bestimmen: wenn der Thread einer project_id
        # zugeordnet ist, holen wir den slug und aktivieren den
        # Sandbox-Modus fuer alle Tool-Aufrufe in diesem Turn.
        project_slug: str | None = None
        if thread.get("project_id"):
            from ..db import connect as system_connect
            sysconn = system_connect()
            try:
                row = sysconn.execute(
                    "SELECT slug FROM projects WHERE id = ?",
                    (thread["project_id"],),
                ).fetchone()
                if row and row["slug"]:
                    project_slug = row["slug"]
            finally:
                sysconn.close()
            if project_slug:
                logger.info(
                    "run_turn thread=%s project_slug=%s (Sandbox aktiv)",
                    thread_id, project_slug,
                )

        # Projekt-Kontext aktivieren — gilt fuer alle Tool-Aufrufe in
        # diesem Turn (fs_*, sqlite_*). Reset im finally am Ende von
        # run_turn (siehe unten).
        from .context import _current_project
        _ctx_token = _current_project.set(project_slug)

        previous_response_id: str | None = thread.get("foundry_thread_id")
        # Bei uns wird foundry_thread_id als previous_response_id der letzten
        # Assistant-Antwort verwendet. Name "foundry_thread_id" bleibt aus
        # Schema-Gruenden (Migration 004), auch wenn es technisch eine
        # response_id aus der Responses API ist.

        current_input: str | list[dict] = user_text

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
                call_kwargs["extra_body"] = {"agent_reference": agent_ref}
            else:
                # Direkt-Modell-Weg (ohne Portal-Agent)
                call_kwargs["model"] = model
                call_kwargs["instructions"] = instructions
                call_kwargs["tools"] = tools

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
                        err = getattr(event, "response", None)
                        msg = getattr(getattr(err, "error", None), "message", "unbekannt")
                        yield ErrorEvent(message=f"Foundry meldet Fehler: {msg}")
                        return
                    elif etype == "error":
                        msg = getattr(event, "message", "") or str(event)
                        yield ErrorEvent(message=f"Stream-Fehler: {msg}")
                        return

                    # andere Events (refusal, reasoning, mcp, image_gen, ...)
                    # ignorieren wir still — bei Bedarf spaeter ergaenzen.

            except Exception as exc:
                logger.exception("Fehler im Event-Stream")
                yield ErrorEvent(message=f"Stream-Fehler: {exc}")
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

        # Assistant-Antwort zusammen persistieren
        full_text = "".join(assistant_text_buf)
        chat_repo.append_message(
            thread_id=thread_id,
            role="assistant",
            content=full_text if full_text else None,
            tool_calls=recorded_tool_calls or None,
            foundry_message_id=last_response_id,
            tokens_input=(last_usage or {}).get("input") if last_usage else None,
            tokens_output=(last_usage or {}).get("output") if last_usage else None,
        )
        if recorded_tool_results:
            chat_repo.append_message(
                thread_id=thread_id,
                role="tool",
                tool_results=recorded_tool_results,
            )

        # Foundry-Response-ID im Thread speichern (fuer naechsten Turn)
        if last_response_id:
            chat_repo.set_foundry_thread_id(thread_id, last_response_id)

        yield DoneEvent(
            response_id=last_response_id,
            tokens_input=(last_usage or {}).get("input") if last_usage else None,
            tokens_output=(last_usage or {}).get("output") if last_usage else None,
        )

        # Projekt-Kontext zuruecksetzen (verhindert Leak in andere Turns)
        try:
            _current_project.reset(_ctx_token)
        except Exception:
            pass


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
