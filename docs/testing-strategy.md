# Test-Strategie — Disco

**Stand:** 2026-05-09. Beschreibt, wie Disco getestet wird — was
automatisch, was manuell, was mit echtem Modell.

---

## Drei Test-Schichten

| Schicht | Zweck | Aufwand pro Run | Modell-Calls |
|---|---|---|---|
| **Unit-Tests** | Tool-Implementierungen, Parser, Helper | Sekunden | nein |
| **E2E-Szenarien** | Disco-Verhalten in echten Workflows | 5–15 Min | ja (echtes GPT) |
| **UAT-Sessions** | manuelle Akzeptanz im Browser | Tage | ja |

Aktueller Schwerpunkt: **E2E-Szenarien**. Unit-Tests sind dünn (Backlog),
das Modell-Verhalten lässt sich am sinnvollsten gegen echte Tool-Calls
prüfen — alles Mocking landet sonst in Halluzinations-Imitation.

---

## E2E-Szenarien

### Layout

```
tests/e2e/
├── scenarios/
│   ├── 01-source-onboarding.md
│   ├── 02-pipeline-fulltest.md
│   └── 03-memory-reform.md
└── (Setup-Skripte unter scripts/setup_e2e_project.sh)
```

Jedes Szenario ist ein **Markdown-Drehbuch**: Voraussetzung, Schritt-
für-Schritt-Prompts, erwartetes Disco-Verhalten, Pass/Fail-Kriterien.
Die Tests laufen aktuell **manuell im Browser** über den
Claude-Preview-MCP oder direkt im Chat — kein Test-Runner.

### Setup-Pattern

Jedes Szenario erwartet ein frisches Test-Projekt. Aufsetzen über:

```bash
scripts/setup_e2e_project.sh <slug> [--archive-existing]
```

Das Skript legt das Projekt im Dev-Workspace an, kopiert vordefinierte
Test-Daten (Pool-Slots) und initialisiert `data.db`. Vor dem Test:
Dev-Server (Port 8766) laufen lassen, Browser auf das Projekt
umstellen, Chat leeren.

### Disco-Mind-Test (Pattern für Verhaltens-Validierung)

Eingeführt für die Memory-Reform (`03-memory-reform.md`). Pattern für
jeden Test-Punkt:

| Feld | Beispiel |
|---|---|
| Test-ID | `T2` |
| Frage | "Was ist eigentlich der Stand bei Bautechnik IBL?" |
| Erwartung | Substring-Match → Kapitel `Bautechnik IBL Roh-Stand` gezielt nachladen |
| Beobachtung | Disco hit per Substring, 462 B Body |
| Pass/Fail | ✅ |

Die Tests prüfen nicht nur „liefert eine Antwort", sondern
**welche Tool-Calls** Disco macht und in welcher Reihenfolge. Das ist
wichtig, weil das Modell oft mehrere Wege zur richtigen Antwort hat,
aber nur einer davon Token-/Latenz-effizient ist.

**Trace-Quellen für die Validation:**

- `.disco/memory-access.log` (TSV, jeder `memory_read`-Call mit Modus +
  Hit-Type + Bytes + Reference-Count)
- `.disco/sessions/*.json` (jede Chat-Turn-Trace mit Tool-Calls)
- WebSocket-Frames im Browser-DevTools (Echtzeit, nützlich beim
  Debugging)

### Disco-Mind-Test T1–T7 (Memory-Reform)

Vollständig dokumentiert in `tests/e2e/scenarios/03-memory-reform.md`.
Übersicht:

| ID | Was geprüft | Erwartung |
|---|---|---|
| T1 | Default-Onboarding | Schicht 1 + Index, kein Vollscan |
| T2 | Substring-Hit | gezieltes Kapitel, ~500 B |
| T3 | Miss | klares ❌, KEINE Halluzination |
| T4 | Tag/Body-Match | Kapitel auflösen, refcount++ |
| T5 | Token-Sockel-Messung | Default < 4 KB |
| T6 | `table_doc_get` | volle Schema-Doku zurück |
| T7 | Backward-Compat (kein Marker) | Legacy-Pfad funktioniert |

---

## UAT-Sessions (User Acceptance)

Unter `tests/uat/` liegen **manuelle Akzeptanz-Notizen** vom Nutzer
(Raphael) — Beobachtungen aus echter Arbeit mit Prod-Projekten,
Bug-Sichtungen, Feature-Wünsche. Keine strukturierten Drehbücher,
sondern Spurenlesen.

**Konvention:** wenn der Nutzer ein UAT-Findung meldet, das nicht
sofort gefixt wird, landet eine Kurzfassung in `docs/BACKLOG.md`
mit Section-Header `User-Feedback YYYY-MM-DD`.

---

## Was an Unit-Tests fehlt (Backlog)

Aktuell sind Unit-Tests dünn. Lohnenswert wären:

- **Memory-Tools:** `_split_at_layer_marker`, `_parse_chapter_meta`,
  `_iter_chapters`, `_find_chapter` (alle exportiert in `memory.py`,
  pure Funktionen). 1 Tag Aufwand.
- **Compaction-NOTES-Archiv:** `archive_old_notes_entries` mit
  hand-gebauten NOTES-Strings — 30-Tage-Schwelle, Idempotenz, Edge-
  Cases (kein Datum, kollidierende Header).
- **Pfad-Helper:** `_safe_path_in_root` (in `api/main.py`) gegen
  Path-Traversal-Versuche.
- **Sources-Match:** `sources_attach_metadata` Pfad-Matching mit
  Unicode-Edge-Cases (NFC/NFD, Umlaute, kombinierende Zeichen).

Test-Framework-Vorschlag: `pytest`, kein Mocking-Framework — die
oben genannten Funktionen sind alle synchron, deterministisch, ohne
DB.

---

## Was an Test-Automatisierung fehlt (Backlog)

Heute laufen die E2E-Szenarien manuell. Mittelfristig sinnvoll:

- **Drehbuch-Runner:** Skript, das ein Szenario-Markdown parst, die
  Prompts in Reihe an einen frischen Chat sendet, jede Tool-Call-
  Sequenz mit dem `expected_tool_calls`-Block im Markdown vergleicht.
  Memory-Trace + Token-Verbrauch wird automatisch mitgemessen.
- **CI-Integration:** vor jedem Prod-Deploy alle Szenarien grün
  gegen einen frischen Foundry-Agent. Hürde: echte LLM-Calls →
  Kosten + Latenz. Kompromiss: nightly statt pre-commit.

---

## Pointer

- **Szenarien:** `tests/e2e/scenarios/`
- **Setup-Skript:** `scripts/setup_e2e_project.sh`
- **UAT-Notizen:** `tests/uat/`
- **Memory-Trace-Spec:** `src/disco/agent/functions/memory.py`
  (Funktion `_log_memory_access`)
