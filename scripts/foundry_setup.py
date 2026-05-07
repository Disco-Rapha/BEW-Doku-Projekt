"""Foundry-Agent-Registrierung im Projekt (REST + Project-API-Key).

Aufruf:
    uv run python scripts/foundry_setup.py
    # oder
    uv run bew agent setup

Voraussetzungen:
    - FOUNDRY_ENDPOINT in .env (Projekt-Endpoint aus dem Portal)
    - FOUNDRY_API_KEY in .env (Project-API-Key aus dem Portal)

Was das Script tut:
    1. Baut die Tool-Liste aus der Custom-Function-Registry + Code Interpreter.
    2. Liest den System-Prompt aus src/disco/agent/system_prompt.md.
    3. Schickt einen POST an /agents/<agent_name>/versions — legt den Agent
       an (neue Version, wenn er bereits existiert).
    4. Patch der .env: FOUNDRY_AGENT_ID = <agent_name>:<version>.

Agent-Name wird aus FOUNDRY_AGENT_ID in der .env gelesen (der Teil vor
":<version>"). Fallback: "disco-agent". So kann Dev z. B. mit
FOUNDRY_AGENT_ID=disco-dev-agent einen eigenen Agent im Dev-Projekt
registrieren, ohne das Script zu editieren.

Der Agent erscheint danach im Foundry-Portal unter "Agents" und kann dort
getestet, versioniert und per Playground bedient werden. Unser Runtime
(AgentService) nutzt ihn aktuell nicht direkt, sondern die Responses API
stateless — der Portal-Agent dient als Referenz / zentrale Konfiguration.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


# Paket importierbar machen, ohne dass man das Script installiert
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


AGENT_NAME_DEFAULT = "disco-agent"
API_VERSION = "v1"


def _resolve_agent_name(agent_id_raw: str | None) -> str:
    """Liefert den Agent-Namen ohne ':<version>'-Suffix.

    FOUNDRY_AGENT_ID kann ein reiner Name (`disco-dev-agent`) oder ein
    gepinnter Verweis (`disco-dev-agent:29`) sein. Fuer den Setup-POST
    brauchen wir nur den Namen.
    """
    raw = (agent_id_raw or "").strip()
    if not raw:
        return AGENT_NAME_DEFAULT
    return raw.split(":", 1)[0]


def setup_agent(
    *,
    model_deployment: str | None = None,
    reasoning_effort: str | None = None,
    verbosity: str | None = None,
    verbose: bool = True,
) -> dict:
    """Pusht eine neue Foundry-Agent-Version mit Override-Optionen.

    Args:
      model_deployment: ueberschreibt settings.foundry_model_deployment
      reasoning_effort: 'minimal'|'low'|'medium'|'high' — ueberschreibt
        settings.foundry_reasoning_effort
      verbosity: 'low'|'medium'|'high' — ueberschreibt
        settings.foundry_verbosity
      verbose: print Setup-Log auf stdout (CLI), bei API-Aufrufen False

    Side-Effects:
      - .env wird mit den Override-Werten gepatched (Persistenz ueber Restart)
      - settings-Singleton wird in-process aktualisiert (sonst sieht der
        laufende Server die alten Werte)
      - neue Foundry-Agent-Version wird POSTet

    Returns:
      dict mit keys: id, version, created_at, model, reasoning_effort,
                     verbosity, agent_name
    Raises:
      RuntimeError bei Auth-/HTTP-Fehlern.
    """
    from disco.agent import get_tool_schemas
    from disco.config import settings

    import httpx

    # --- Preflight ---
    if not settings.foundry_endpoint:
        raise RuntimeError("FOUNDRY_ENDPOINT ist nicht gesetzt (.env).")
    if not settings.foundry_api_key:
        raise RuntimeError(
            "FOUNDRY_API_KEY ist nicht gesetzt (.env). "
            "Portal -> Projekt -> Endpunkte -> Project API Key kopieren."
        )

    # Effektive Werte (Override > Settings)
    eff_model = model_deployment or settings.foundry_model_deployment
    eff_reasoning = reasoning_effort or settings.foundry_reasoning_effort
    eff_verbosity = verbosity or settings.foundry_verbosity

    agent_name = _resolve_agent_name(settings.foundry_agent_id)

    if verbose:
        print(f"Foundry-Endpoint: {settings.foundry_endpoint}")
        print(f"Modell-Deployment: {eff_model}")
        print(f"Agent-Name: {agent_name}")

    system_prompt_path = REPO_ROOT / "src" / "disco" / "agent" / "system_prompt.md"
    instructions = system_prompt_path.read_text(encoding="utf-8")
    if verbose:
        print(f"System-Prompt: {len(instructions)} Zeichen")

    tools = get_tool_schemas()
    tools.append({"type": "code_interpreter", "container": {"type": "auto"}})
    if verbose:
        print(f"Tools: {len(tools)} ({len(tools) - 1} Custom Functions + Code Interpreter)")

    body = {
        "definition": {
            "kind": "prompt",
            "model": eff_model,
            "instructions": instructions,
            "tools": tools,
            "reasoning": {"effort": eff_reasoning},
            "text": {"verbosity": eff_verbosity},
        },
        "description": (
            "Disco — Haupt-Agent fuer technische Dokumentation, "
            "SQL-Analyse, Excel-Export, PDF-Extraktion."
        ),
        "metadata": {"project": "disco", "phase": "2a"},
    }

    if verbose:
        print(f"Reasoning-Effort: {eff_reasoning}  Verbosity: {eff_verbosity}")

    base = settings.foundry_endpoint.rstrip("/")
    url = f"{base}/agents/{agent_name}/versions"
    if verbose:
        print(f"\nPOST {url}?api-version={API_VERSION}")
    try:
        r = httpx.post(
            url,
            params={"api-version": API_VERSION},
            headers={
                "api-key": settings.foundry_api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=body,
            timeout=60.0,
        )
    except httpx.HTTPError as exc:
        raise RuntimeError(f"HTTP-Verbindung fehlgeschlagen: {exc}") from exc

    if r.status_code not in (200, 201):
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")

    resp = r.json()
    version = resp.get("version", "?")
    agent_id = resp.get("id") or f"{agent_name}:{version}"
    created_at = resp.get("created_at")

    if verbose:
        print(f"\nOK Agent registriert:")
        print(f"  id           : {agent_id}")
        print(f"  version      : {version}")
        print(f"  created_at   : {created_at}")

    # --- .env patchen (Persistenz fuer Server-Restart) ---
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        if model_deployment is not None:
            _patch_env(env_path, "FOUNDRY_MODEL_DEPLOYMENT", eff_model)
        if reasoning_effort is not None:
            _patch_env(env_path, "FOUNDRY_REASONING_EFFORT", eff_reasoning)
        if verbosity is not None:
            _patch_env(env_path, "FOUNDRY_VERBOSITY", eff_verbosity)

        existing = _read_env_value(env_path, "FOUNDRY_AGENT_ID")
        if existing != agent_name:
            _patch_env(env_path, "FOUNDRY_AGENT_ID", agent_id)
            if verbose:
                print(f"OK .env aktualisiert: FOUNDRY_AGENT_ID={agent_id}")

    # --- Settings-Singleton in-process aktualisieren (sonst sieht der
    # laufende Server die alten Werte beim naechsten setup) ---
    if model_deployment is not None:
        settings.foundry_model_deployment = eff_model
    if reasoning_effort is not None:
        settings.foundry_reasoning_effort = eff_reasoning
    if verbosity is not None:
        settings.foundry_verbosity = eff_verbosity

    return {
        "id": agent_id,
        "version": version,
        "created_at": created_at,
        "model": eff_model,
        "reasoning_effort": eff_reasoning,
        "verbosity": eff_verbosity,
        "agent_name": agent_name,
    }


def main() -> int:
    """CLI-Entry-Point: setup_agent() ohne Override (alle Werte aus .env)."""
    try:
        result = setup_agent(verbose=True)
    except RuntimeError as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 1

    agent_name = result["agent_name"]
    print(
        f"\nFertig. Der Agent ist jetzt im Foundry-Portal sichtbar:\n"
        f"  https://ai.azure.com -> Dein Projekt -> Agents -> {agent_name}\n"
        f"Dort kannst Du ihn im Playground testen und bei Bedarf "
        f"System-Prompt / Tools editieren."
    )
    return 0


def _read_env_value(env_path: Path, key: str) -> str | None:
    """Liest einen einzelnen Wert aus der .env (oder None, wenn nicht gesetzt)."""
    pattern = re.compile(rf"^{re.escape(key)}=(.*)$", re.MULTILINE)
    m = pattern.search(env_path.read_text(encoding="utf-8"))
    return m.group(1).strip() if m else None


def _patch_env(env_path: Path, key: str, value: str) -> None:
    """Patcht eine einzelne Variable in .env ohne Kommentare zu verlieren."""
    content = env_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    replacement = f"{key}={value}"
    if pattern.search(content):
        content = pattern.sub(replacement, content)
    else:
        if not content.endswith("\n"):
            content += "\n"
        content += replacement + "\n"
    env_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
