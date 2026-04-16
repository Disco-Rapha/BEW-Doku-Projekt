"""Skill-Loader: Markdown-Files unter skills/ als ladbare "Playbooks".

Konzept (analog zur Anthropic Agent-Skills-Spec):
  - Skills sind Markdown-Files im Repo unter `skills/<name>.md`.
  - Jede Datei beginnt mit einem YAML-aehnlichen Frontmatter (zwischen ---):
        ---
        name: excel-reporter
        description: Multi-Sheet-Excel mit konsistenter Formatierung
        when_to_use: User will eine Excel als Output, Reports, IBL-Exports
        ---
  - Der Body ist Markdown mit konkreten Code-Patterns + Best Practices.

Der Agent kennt zwei Tools:
  - `list_skills()` — listet alle verfuegbaren Skills mit Kurzbeschreibung
  - `load_skill(name)` — liefert den vollstaendigen Skill-Inhalt zurueck

Lazy-Loading: Skills werden nur dann in den Kontext gezogen, wenn der
Agent sie tatsaechlich braucht. Das spart Tokens fuer Turns ohne Excel/SQL.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import register


# Skills liegen im Repo-Root unter skills/
SKILLS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "skills"


_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(?P<fm>.*?)\n---\s*\n(?P<body>.*)$",
    re.DOTALL,
)


def _parse_skill_file(path: Path) -> dict[str, Any]:
    """Liest ein Skill-Markdown-File und parst Frontmatter + Body.

    Frontmatter ist YAML-aehnlich, aber wir nehmen einen kleinen, robusten
    Subset-Parser: jede Zeile 'key: value', keine Verschachtelung, keine Listen.
    """
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    fm: dict[str, str] = {}
    body = text
    if m:
        body = m.group("body").strip()
        for line in m.group("fm").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()

    return {
        "name": fm.get("name") or path.stem,
        "description": fm.get("description", ""),
        "when_to_use": fm.get("when_to_use", ""),
        "body": body,
        "path": str(path),
        "size_bytes": len(text.encode("utf-8")),
    }


def _all_skills() -> list[dict[str, Any]]:
    if not SKILLS_DIR.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(SKILLS_DIR.glob("*.md")):
        try:
            out.append(_parse_skill_file(p))
        except Exception:
            continue
    return out


# ---------------------------------------------------------------------------
# list_skills
# ---------------------------------------------------------------------------


@register(
    name="list_skills",
    description=(
        "Listet alle verfuegbaren Skills (Playbooks) auf, mit Name, Kurzbeschreibung "
        "und Hinweis wann sie zu nutzen sind. Skills sind kuratierte Anleitungen "
        "fuer wiederkehrende Aufgaben (Excel-Bauen, SQL-Reports, Klassifikation, ...). "
        "Wenn Du eine passende Aufgabe hast, ruf `load_skill(name)` um den vollen "
        "Inhalt zu bekommen, und folge dann der dortigen Anleitung."
    ),
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    returns="Liste von {name, description, when_to_use, size_bytes}",
)
def _list_skills() -> list[dict[str, Any]]:
    skills = _all_skills()
    return [
        {
            "name": s["name"],
            "description": s["description"],
            "when_to_use": s["when_to_use"],
            "size_bytes": s["size_bytes"],
        }
        for s in skills
    ]


# ---------------------------------------------------------------------------
# load_skill
# ---------------------------------------------------------------------------


@register(
    name="load_skill",
    description=(
        "Laedt den vollstaendigen Inhalt eines Skills (Playbook-Markdown). "
        "Nutze `list_skills` zuerst, um die Namen zu sehen. "
        "Folge danach exakt den Anweisungen im Skill — die sind getestet und sparen "
        "Iterations-Aufwand. Skills sind nicht ausfuehrbar, sondern Anleitungen."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Skill-Name (siehe list_skills, ohne .md).",
            },
        },
        "required": ["name"],
    },
    returns="{name, description, when_to_use, body, size_bytes}",
)
def _load_skill(*, name: str) -> dict[str, Any]:
    name = (name or "").strip().removesuffix(".md")
    if not name:
        raise ValueError("name ist erforderlich.")
    path = SKILLS_DIR / f"{name}.md"
    if not path.exists():
        available = [s["name"] for s in _all_skills()]
        raise ValueError(
            f"Skill '{name}' nicht gefunden. Verfuegbar: {available}"
        )
    skill = _parse_skill_file(path)
    return {
        "name": skill["name"],
        "description": skill["description"],
        "when_to_use": skill["when_to_use"],
        "body": skill["body"],
        "size_bytes": skill["size_bytes"],
    }
