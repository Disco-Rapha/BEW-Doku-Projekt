"""Flow-Tools fuer Disco — den Bau und die Ueberwachung von Flows vom Chat aus.

Diese Tools binden das `bew.flows`-Framework an den Agent an. Disco kann
damit:

  - bestehende Flows eines Projekts **auflisten** und **lesen**
    (`flow_list`, `flow_show`)
  - einen neuen Flow **anlegen** mit Skelett-Dateien (`flow_create`)
    — danach passt Disco README und runner.py per fs_write an
  - einen Flow **starten** (`flow_run`) — Worker laeuft im Hintergrund
  - den **Status** eines Runs abfragen (`flow_status`, `flow_runs`)
  - Items eines Runs durchsehen (`flow_items`)
  - Logs lesen (`flow_logs`)
  - einen laufenden Flow **pausieren** oder **abbrechen**
    (`flow_pause`, `flow_cancel`)

Alle Tools wirken auf das **aktive Projekt** (aus dem
`bew.agent.context`-Sandbox). Ohne Projekt-Kontext: klare Fehlermeldung.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ...flows import service as flow_service
from ..context import get_project_root
from . import register


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Skelett-Templates fuer neu angelegte Flows
# ---------------------------------------------------------------------------

_README_SKELETON = """# Flow: {name}

## Zweck

*(Disco + Nutzer fuellen aus: Was soll der Flow tun? Ein paar Saetze.)*

## Input

- Tabelle: *(z.B. agent_sources)*
- Filter: *(z.B. WHERE status='active')*
- Dateien: *(z.B. .disco/context-extracts/<hash>.md)*

## Verarbeitung pro Item

1. *(Schritt 1)*
2. *(Schritt 2)*

## Output (JSON pro Item)

```json
{{"...": "..."}}
```

## Externe Dienste

*(Keine / Azure OpenAI / Azure Doc Intel — mit geschaetzten Kosten)*

## Parameter

- `limit` *(int, optional)* — max. Anzahl Items
- `budget_eur` *(float, optional)* — Hart-Limit fuer Kosten

## Fehlerbehandlung

*(Pro Item: Retry-Strategie. Global: Auto-Pause-Schwellen.)*

## Kostenschaetzung

*(Pro Item: X EUR. Gesamt bei N Items: Y EUR. Hart-Limit: Z EUR.)*

## Status und Kontrolle

- Fortschritt: `disco flow status <run_id> --project <slug>`
- Items: `disco flow items <run_id> --project <slug>`
- Logs: `disco flow logs <run_id> --project <slug>`
- Pause/Cancel: `disco flow pause/cancel <run_id> --project <slug>`

## Wie erkennst Du, dass es funktioniert hat

*(Akzeptanzkriterien — z.B. SQL-Aggregation, Stichproben-Pruefung.)*

## Entscheidungen

*(Disco pflegt hier chronologisch die wichtigen Abstimmungen mit
dem Nutzer: "am <Datum>: <Entscheidung>".)*

## Historie

- *(Datum)* — v1: Initial.
"""


_RUNNER_SKELETON = '''"""Flow: {name}.

Siehe README.md.
"""

from __future__ import annotations

from bew.flows.sdk import FlowRun, run_context


def process_item(item: dict) -> dict:
    """Pro-Item-Logik. Gibt JSON-serialisierbares dict zurueck."""
    # TODO: Disco + Nutzer implementieren die eigentliche Verarbeitung
    return {{"rel_path": item.get("rel_path"), "status": "todo"}}


def main() -> None:
    with run_context(FlowRun.from_env()) as run:
        run.log(f"Flow {{run.flow_name}} gestartet (run_id={{run.run_id}})")

        # TODO: Input-Query an die Projekt-Struktur anpassen
        items = run.db.query(
            """
            SELECT id, rel_path, sha256
              FROM agent_sources
             WHERE status = 'active'
            """
        )
        run.set_total(len(items))
        run.log(f"Input-Query: {{len(items)}} Items")

        for item in items:
            def work(it=item):
                return process_item(it)

            run.process(
                input_ref=f"source:{{item['id']}}",
                fn=work,
                max_retries=3,
            )


if __name__ == "__main__":
    main()
'''


# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------


def _active_project_root() -> Path:
    """Gibt den aktiven Projekt-Root zurueck; wirft ValueError wenn ohne Kontext."""
    root = get_project_root()
    if root is None:
        raise ValueError(
            "Flow-Tools brauchen ein aktives Projekt. "
            "Wenn Du im CLI bist: 'disco agent chat --project <slug>' starten. "
            "Wenn Du in einem Thread bist: der Thread muss an ein Projekt "
            "gebunden sein."
        )
    return root


def _run_to_dict(run: flow_service.RunInfo) -> dict[str, Any]:
    return {
        "id": run.id,
        "flow_name": run.flow_name,
        "title": run.title,
        "status": run.status,
        "worker_pid": run.worker_pid,
        "config": run.config,
        "total_items": run.total_items,
        "done_items": run.done_items,
        "failed_items": run.failed_items,
        "skipped_items": run.skipped_items,
        "total_cost_eur": run.total_cost_eur,
        "total_tokens_in": run.total_tokens_in,
        "total_tokens_out": run.total_tokens_out,
        "pause_requested": run.pause_requested,
        "cancel_requested": run.cancel_requested,
        "error": run.error,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


def _flow_to_dict(info: flow_service.FlowInfo, project_root: Path) -> dict[str, Any]:
    return {
        "name": info.name,
        "path": str(info.path.relative_to(project_root)),
        "has_runner": info.has_runner,
        "has_readme": info.has_readme,
        "readme_excerpt": info.readme_excerpt,
        "last_modified": info.last_modified,
        "run_count": info.run_count,
    }


# ---------------------------------------------------------------------------
# flow_list
# ---------------------------------------------------------------------------


@register(
    name="flow_list",
    description=(
        "Listet alle Flows im aktiven Projekt (Ordner unter flows/). "
        "Gute erste Anlaufstelle, bevor Du einen Flow baust oder startest: "
        "'welche Flows gibt es schon?'. Zeigt pro Flow: Name, Readme-Auszug, "
        "ob runner.py und README existieren, wann zuletzt geaendert, "
        "Anzahl bisheriger Runs."
    ),
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    returns="{flows: [{name, path, has_runner, has_readme, readme_excerpt, last_modified, run_count}], total}",
)
def _flow_list() -> dict[str, Any]:
    project_root = _active_project_root()
    flows = flow_service.list_flows(project_root)
    return {
        "flows": [_flow_to_dict(f, project_root) for f in flows],
        "total": len(flows),
    }


# ---------------------------------------------------------------------------
# flow_show
# ---------------------------------------------------------------------------


@register(
    name="flow_show",
    description=(
        "Zeigt Details zu einem Flow: voller README-Text, Ordner-Inhalt, "
        "die letzten 10 Runs. Nutze das BEVOR Du einen Flow startest — "
        "die README ist gleichzeitig Spec UND Arbeitsprotokoll: da steht, "
        "was der Flow tut, wie Fehler behandelt werden, Kosten, Akzeptanz-"
        "kriterien, vergangene Entscheidungen mit dem Nutzer."
    ),
    parameters={
        "type": "object",
        "properties": {
            "flow_name": {
                "type": "string",
                "description": "Name des Flows (Ordnername unter flows/).",
            },
        },
        "required": ["flow_name"],
    },
    returns=(
        "{name, path, has_runner, has_readme, readme_content, runner_lines, "
        "files: [str], recent_runs: [run_summary]}"
    ),
)
def _flow_show(*, flow_name: str) -> dict[str, Any]:
    project_root = _active_project_root()
    info = flow_service.get_flow(project_root, flow_name)

    readme_path = info.path / "README.md"
    runner_path = info.path / "runner.py"

    readme_content = ""
    if readme_path.is_file():
        try:
            readme_content = readme_path.read_text(encoding="utf-8")
        except OSError as exc:
            readme_content = f"(Lesefehler: {exc})"

    runner_lines = 0
    if runner_path.is_file():
        try:
            runner_lines = sum(
                1 for _ in runner_path.open("r", encoding="utf-8", errors="replace")
            )
        except OSError:
            pass

    files = sorted(
        p.name for p in info.path.iterdir() if p.is_file()
    )
    subdirs = sorted(
        p.name for p in info.path.iterdir() if p.is_dir()
    )

    recent = flow_service.list_runs(project_root, flow_name=flow_name, limit=10)
    return {
        "name": info.name,
        "path": str(info.path.relative_to(project_root)),
        "has_runner": info.has_runner,
        "has_readme": info.has_readme,
        "readme_content": readme_content,
        "runner_lines": runner_lines,
        "files": files,
        "subdirs": subdirs,
        "recent_runs": [
            {
                "id": r.id,
                "status": r.status,
                "items": f"{r.done_items}/{r.total_items}",
                "failed": r.failed_items,
                "cost_eur": r.total_cost_eur,
                "created_at": r.created_at,
                "finished_at": r.finished_at,
            }
            for r in recent
        ],
    }


# ---------------------------------------------------------------------------
# flow_create
# ---------------------------------------------------------------------------


@register(
    name="flow_create",
    description=(
        "Legt einen neuen Flow-Ordner an (<projekt>/flows/<flow_name>/) "
        "mit Skelett-README und Skelett-runner.py. Idempotent: wenn der "
        "Ordner bereits existiert, werden nur fehlende Dateien angelegt. "
        "Danach solltest Du README.md und runner.py per fs_read ansehen, "
        "mit dem Nutzer das Ziel klaeren und die Skelette per fs_write "
        "an das Projekt anpassen."
    ),
    parameters={
        "type": "object",
        "properties": {
            "flow_name": {
                "type": "string",
                "description": (
                    "Slug-artiger Name, a-z/0-9/_-, z.B. 'dcc-klassifikation'. "
                    "Wird zum Ordnernamen."
                ),
            },
        },
        "required": ["flow_name"],
    },
    returns="{name, path, readme_path, runner_path, created}",
)
def _flow_create(*, flow_name: str) -> dict[str, Any]:
    project_root = _active_project_root()
    # Validierung wird in service-Funktionen gemacht; hier nur Ordner anlegen.
    flows_dir = project_root / "flows"
    flows_dir.mkdir(parents=True, exist_ok=True)
    target_dir = flows_dir / flow_name
    was_new = not target_dir.exists()
    target_dir.mkdir(parents=True, exist_ok=True)

    readme_path = target_dir / "README.md"
    runner_path = target_dir / "runner.py"

    wrote_readme = False
    if not readme_path.exists():
        readme_path.write_text(
            _README_SKELETON.format(name=flow_name),
            encoding="utf-8",
        )
        wrote_readme = True

    wrote_runner = False
    if not runner_path.exists():
        runner_path.write_text(
            _RUNNER_SKELETON.format(name=flow_name),
            encoding="utf-8",
        )
        wrote_runner = True

    # Validieren, dass der Service den Flow jetzt findet
    try:
        info = flow_service.get_flow(project_root, flow_name)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Flow konnte nicht angelegt werden: {exc}") from exc

    return {
        "name": info.name,
        "path": str(info.path.relative_to(project_root)),
        "readme_path": str(readme_path.relative_to(project_root)),
        "runner_path": str(runner_path.relative_to(project_root)),
        "created": was_new,
        "readme_written": wrote_readme,
        "runner_written": wrote_runner,
        "hint": (
            "Jetzt README und runner.py anpassen: "
            f"fs_read pfad='{info.path.relative_to(project_root)}/README.md', "
            "dann mit dem Nutzer ueber Zweck/Input/Output/Kosten abstimmen, "
            "dann per fs_write die finalen Versionen schreiben. "
            "Zum Starten: flow_run(flow_name='{name}')."
        ).replace("{name}", flow_name),
    }


# ---------------------------------------------------------------------------
# flow_run — create + start in einem Aufruf
# ---------------------------------------------------------------------------


@register(
    name="flow_run",
    description=(
        "Startet einen neuen Run eines Flows. Legt in der DB einen Eintrag "
        "in agent_flow_runs an und startet den Worker als detachten "
        "Subprocess. Der Aufruf kehrt SOFORT zurueck (nicht-blockierend) — "
        "Status danach mit flow_status abfragen. "
        "\n\n"
        "Typischer Workflow:\n"
        "  1) Test-Run mit begrenzter Menge: config={\"limit\": 5}\n"
        "  2) Ergebnisse pruefen per flow_items\n"
        "  3) Wenn ok: Full-Run ohne limit, aber mit budget_eur-Limit\n"
        "  4) flow_status periodisch abfragen; flow_pause bei Anomalien."
    ),
    parameters={
        "type": "object",
        "properties": {
            "flow_name": {
                "type": "string",
                "description": "Name des Flows (muss unter flows/ existieren).",
            },
            "title": {
                "type": "string",
                "description": (
                    "Optionaler kurzer Titel fuer diesen Run "
                    "(z.B. 'DCC-Klassifikation Test-Run 5 Items')."
                ),
            },
            "config": {
                "type": "object",
                "description": (
                    "Parameter fuer den Runner. Typisch: "
                    "{\"limit\": 5} fuer Stichprobe, "
                    "{\"budget_eur\": 15} fuer Kosten-Hart-Limit. "
                    "Der Flow-Runner bestimmt welche Keys er interpretiert — "
                    "steht in der README des Flows unter 'Parameter'."
                ),
            },
        },
        "required": ["flow_name"],
    },
    returns="{run_id, flow_name, status, worker_pid, config, hint}",
)
def _flow_run(
    *,
    flow_name: str,
    title: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Asymmetric Auto-Action: wenn dieser Turn vom System getriggert wurde
    # (flow_notifications, nicht User), darf Disco NICHT autonom neue Runs
    # starten. Cancel/Pause ist ok (Cost-Protection), aber Starts kosten
    # Geld und muessen vom Menschen freigegeben werden.
    from ..context import is_system_triggered

    if is_system_triggered():
        raise ValueError(
            "flow_run blockiert: Du wurdest vom System getriggert und darfst "
            "keine neuen Runs starten (Cost-Protection). Wenn Du findest, "
            "dass ein neuer Run noetig ist, schreib das als Empfehlung — der "
            "User startet ihn manuell."
        )

    project_root = _active_project_root()
    try:
        run = flow_service.create_run(
            project_root, flow_name, title=title, config=config
        )
        run = flow_service.start_run(project_root, run.id)
    except (KeyError, FileNotFoundError, ValueError, RuntimeError) as exc:
        raise ValueError(str(exc)) from exc

    return {
        "run_id": run.id,
        "flow_name": run.flow_name,
        "status": run.status,
        "worker_pid": run.worker_pid,
        "config": run.config,
        "hint": (
            f"Run {run.id} laeuft im Hintergrund. "
            f"Status: flow_status(run_id={run.id}). "
            f"Items ansehen: flow_items(run_id={run.id}). "
            f"Logs: flow_logs(run_id={run.id}, tail=50)."
        ),
    }


# ---------------------------------------------------------------------------
# flow_runs
# ---------------------------------------------------------------------------


@register(
    name="flow_runs",
    description=(
        "Listet bisherige Runs im aktiven Projekt (neueste zuerst). "
        "Gute erste Frage am Session-Start: 'laeuft noch ein Run?'. "
        "Filter optional nach flow_name oder status."
    ),
    parameters={
        "type": "object",
        "properties": {
            "flow_name": {
                "type": "string",
                "description": "Nur Runs dieses Flows zeigen.",
            },
            "status": {
                "type": "string",
                "description": "Nur Runs mit diesem Status (pending/running/paused/done/failed/cancelled).",
            },
            "limit": {
                "type": "integer",
                "description": "Max. Anzahl (Default 20, Max 200).",
            },
        },
        "required": [],
    },
    returns="{runs: [run_summary], total}",
)
def _flow_runs(
    *,
    flow_name: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    project_root = _active_project_root()
    effective_limit = max(1, min(int(limit or 20), 200))
    runs = flow_service.list_runs(
        project_root,
        flow_name=flow_name,
        status=status,
        limit=effective_limit,
    )
    return {
        "runs": [_run_to_dict(r) for r in runs],
        "total": len(runs),
    }


# ---------------------------------------------------------------------------
# flow_status
# ---------------------------------------------------------------------------


@register(
    name="flow_status",
    description=(
        "Details zu einem konkreten Run: Status, Fortschritt, Kosten, "
        "Control-Signale, evtl. Fehler. Bei laufenden Runs periodisch "
        "abfragen, um Fortschritt zu melden."
    ),
    parameters={
        "type": "object",
        "properties": {
            "run_id": {"type": "integer", "description": "ID aus agent_flow_runs."},
        },
        "required": ["run_id"],
    },
    returns="run_summary (alle Felder von agent_flow_runs)",
)
def _flow_status(*, run_id: int) -> dict[str, Any]:
    project_root = _active_project_root()
    run = flow_service.get_run(project_root, run_id)
    return _run_to_dict(run)


# ---------------------------------------------------------------------------
# flow_items
# ---------------------------------------------------------------------------


@register(
    name="flow_items",
    description=(
        "Zeigt einzelne Items eines Runs (input_ref, status, attempts, "
        "output_json, Fehler). Nutze das, um Test-Run-Ergebnisse zu "
        "pruefen oder bei einem Full-Run die fehlgeschlagenen Items zu "
        "inspizieren (status='failed')."
    ),
    parameters={
        "type": "object",
        "properties": {
            "run_id": {"type": "integer"},
            "status": {
                "type": "string",
                "description": "Nur Items mit diesem Status (pending/running/done/failed/skipped).",
            },
            "limit": {"type": "integer", "description": "Max. Anzahl (Default 50, Max 500)."},
        },
        "required": ["run_id"],
    },
    returns="{items: [{id, input_ref, status, attempts, output, error, cost_eur, ...}], total}",
)
def _flow_items(
    *,
    run_id: int,
    status: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    project_root = _active_project_root()
    effective_limit = max(1, min(int(limit or 50), 500))
    items = flow_service.list_run_items(
        project_root, run_id, status=status, limit=effective_limit
    )
    return {
        "items": items,
        "total": len(items),
    }


# ---------------------------------------------------------------------------
# flow_pause
# ---------------------------------------------------------------------------


@register(
    name="flow_pause",
    description=(
        "Signalisiert dem Worker, dass er beim naechsten Item pausieren "
        "soll. Kehrt sofort zurueck — der Worker reagiert innerhalb von "
        "~2 Sekunden. Ein pausierter Run kann spaeter mit flow_run "
        "(auf demselben flow_name) NICHT fortgesetzt werden — dafuer "
        "muesste der Service intern start_run auf dem paused-Run rufen. "
        "Derzeit: pause ist fuer 'stopp und pruef', resume folgt per "
        "explizitem CLI-Kommando."
    ),
    parameters={
        "type": "object",
        "properties": {
            "run_id": {"type": "integer"},
        },
        "required": ["run_id"],
    },
    returns="{run_id, status, pause_requested}",
)
def _flow_pause(*, run_id: int) -> dict[str, Any]:
    project_root = _active_project_root()
    run = flow_service.request_pause(project_root, run_id)
    return {
        "run_id": run.id,
        "status": run.status,
        "pause_requested": run.pause_requested,
    }


# ---------------------------------------------------------------------------
# flow_cancel
# ---------------------------------------------------------------------------


@register(
    name="flow_cancel",
    description=(
        "Signalisiert dem Worker, dass er abbrechen soll. Mit force=true "
        "wird der Subprocess zusaetzlich SIGTERM bekommen. Ohne force "
        "reagiert der Worker beim naechsten Item, innerhalb von ~2 Sekunden."
    ),
    parameters={
        "type": "object",
        "properties": {
            "run_id": {"type": "integer"},
            "force": {
                "type": "boolean",
                "description": "Wenn true: zusaetzlich SIGTERM an den Worker.",
            },
        },
        "required": ["run_id"],
    },
    returns="{run_id, status, cancel_requested}",
)
def _flow_cancel(*, run_id: int, force: bool = False) -> dict[str, Any]:
    project_root = _active_project_root()
    if force:
        flow_service.kill_run(project_root, run_id)
    else:
        flow_service.request_cancel(project_root, run_id)
    run = flow_service.get_run(project_root, run_id)
    return {
        "run_id": run.id,
        "status": run.status,
        "cancel_requested": run.cancel_requested,
    }


# ---------------------------------------------------------------------------
# flow_logs
# ---------------------------------------------------------------------------


@register(
    name="flow_logs",
    description=(
        "Zeigt die letzten Zeilen der Run-Logs (log.txt + stderr.log). "
        "Nuetzlich, um zu verstehen, was der Worker gerade macht oder "
        "warum ein Run failed ist."
    ),
    parameters={
        "type": "object",
        "properties": {
            "run_id": {"type": "integer"},
            "tail": {
                "type": "integer",
                "description": "Letzte N Zeilen (Default 50, Max 500).",
            },
        },
        "required": ["run_id"],
    },
    returns="{run_id, log_text, stderr_text, has_stdout}",
)
def _flow_logs(*, run_id: int, tail: int = 50) -> dict[str, Any]:
    project_root = _active_project_root()
    effective_tail = max(1, min(int(tail or 50), 500))
    log_dir = project_root / ".disco" / "flows" / "runs" / str(run_id)

    def _read_tail(path: Path) -> str:
        if not path.is_file():
            return ""
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            return f"(Lesefehler: {exc})"
        return "\n".join(lines[-effective_tail:])

    log_text = _read_tail(log_dir / "log.txt")
    stderr_text = _read_tail(log_dir / "stderr.log")
    stdout_path = log_dir / "stdout.log"
    return {
        "run_id": run_id,
        "log_text": log_text,
        "stderr_text": stderr_text,
        "has_stdout": stdout_path.is_file() and stdout_path.stat().st_size > 0,
        "log_dir": str(log_dir.relative_to(project_root)) if log_dir.exists() else None,
    }
