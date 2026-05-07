# Disco E2E-Test-Suite

**Stand:** 2026-05-07

Sammlung von Test-Szenarien zur **menschen-gesteuerten** Vor-Release-
Validierung. Disco wird von Hand bedient, wie ein Endnutzer ihn bedienen
wuerde — keine programmatischen Asserts gegen die DB, sondern Beobachtung
ueber das UI plus stichprobenhafte SQL-Checks am Ende.

## Was die Suite ist (und was nicht)

**Ist:**
- Drehbuch fuer einen kompletten Pre-Release-Durchlauf
- Eine Sammlung **menschlicher Prompts** (kein Tool-Jargon, keine
  KI-Begriffe — ein Anwender wuerde es so formulieren)
- Pass/Fail-Kriterien pro Szenario (was Disco tun soll, was nicht)
- Failure-Modes (was passiert bei einem korrupten PDF, einem leeren
  Dokument, einer fehlgeschlagenen Engine?)

**Ist nicht:**
- Eine pytest-Suite. Es gibt keine `assert`-Statements.
- Eine CI-Pipeline. Wird manuell vor Releases durchgefuehrt.
- Ein Replacement fuer Unit-Tests (die wohnen unter `src/.../tests/`).

## Vorbereitung

```bash
# 1) Dev-Workspace auswaehlen, Pool generieren (nur einmal noetig)
uv run python scripts/generate_test_fixtures.py

# 2) Manuelle Files (siehe MANIFEST) ggf. aus Prod kopieren
#    Slots 02, 07, 09, 10, 12, 13 — wenn nicht vorhanden, werden die
#    zugehoerigen Szenarien geskipped.

# 3) Frisches Test-Projekt aufsetzen
scripts/setup_e2e_project.sh e2e-smoke-01 --archive-existing

# 4) Dev-Server starten
cd "/Users/BEW/Claude/BEW Doku Projekt"
DISCO_WORKSPACE=~/Disco-dev \
  uv run uvicorn disco.api.main:app --host 127.0.0.1 --port 8766 --reload

# 5) Browser oeffnen: http://127.0.0.1:8766
#    Projekt 'e2e-smoke-01' anwaehlen
```

## Szenario-Liste

| Nr | Szenario | Voraussetzung | Status |
|---|---|---|---|
| 01 | source-onboarding (Registry, Duplikat, Begleit-Excel) | Pool: 01,03,04,05,08,11 + 14a/b | Live-getestet 2026-05-07, Pass mit 2 Befunden |
| 02 | pipeline-fulltest (Routing/Extraktion/Reasoning/Excel-Report/Retry) | nach 01 | Live-getestet 2026-05-07, Pass mit 5 Befunden |
| 03 | context-onboarding (Manifest, Lookup-Excel-Import) | Pool: 06 | TODO |
| 04 | replaces-relations (14a/14b mit identischem Stamm) | nach 02 | TODO |
| 05 | unsupported-formate-handling (DOCX/PPTX bewusst skipped) | Pool: 12,13 | TODO |
| 06 | dwg-engine-stresstest (ezdxf vs libredwg) | Pool: 07 | TODO |

Lebt mit der Suite — neue Szenarien werden hier ergaenzt, wenn neue
Disco-Faehigkeiten dazukommen.

## Format der Szenarien

Jedes Szenario folgt demselben Muster (siehe Template `01-source-onboarding.md`):

1. **Ziel** — was wird in einem Satz validiert.
2. **Voraussetzung** — welcher Pool-Stand wird gebraucht; wenn fehlt,
   sauber skipped.
3. **Drehbuch** — chronologische Reihenfolge der menschlichen Eingaben.
   Jeder User-Prompt steht woertlich da, in `> Zitat`-Form.
4. **Erwartete Beobachtungen** — pro Schritt: was Disco im Chat zeigen
   sollte, welcher Pipeline-Status sich aendert, welche DB-Tabellen
   beruehrt werden.
5. **Pass-Kriterien** — Liste von Checks, die ALLE erfuellt sein muessen.
6. **Failure-Modes** — was schiefgehen kann und wie man's erkennt.

## Konventionen fuer Prompts

Die User-Prompts sollen wie ein Endnutzer geschrieben sein, **nicht** wie
ein Entwickler:

- `"Hallo, neues Projekt"` ✓
- `"Lass mal sources_register auf scope=both laufen"` ✗
- `"Was hast Du da fuer Dateien gefunden?"` ✓
- `"Liste agent_sources WHERE status='active'"` ✗
- `"Schau Dir mal die DCC-Tabelle an, was steht da drin?"` ✓
- `"Importiere context_dcc_codes via import_xlsx_to_table"` ✗

Hintergrund: Disco soll genau die Prompts verstehen, die ein Nutzer
ohne KI-/Tool-Wissen formuliert. Das ist Teil des Tests.

## Test-Archiv

Nach Suite-Abschluss landen die durchgespielten Projekte unter
`~/Disco-dev/.test-archive/<timestamp>/<slug>/` zur Forensik.
Werden nicht automatisch geloescht — bei Bedarf manuell aufraeumen.

## Schwesterdokumente

- `~/Disco-dev/.test-fixtures/MANIFEST.md` — Pool-Slot-Liste mit Status
- `~/Disco-dev/.test-fixtures/README.md` — Pool-Layout + Beschaffung
- `scripts/generate_test_fixtures.py` — synthetische File-Generatoren
- `scripts/setup_e2e_project.sh` — Test-Projekt-Setup
