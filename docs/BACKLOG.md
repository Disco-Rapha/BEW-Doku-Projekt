# Disco Backlog

**Der lebende Backlog liegt in Notion:** [Disco Backlog (Notion)](https://www.notion.so/e04a894ca0ca4727851cc0885fedb75f)

Migriert am 2026-05-11. Diese Datei dient nur noch als Pointer-File
fuer das Repo.

## Wo was lebt

| Was | Wo |
|---|---|
| **Backlog-Items** mit Status / Priority / Type / Component | Notion-DB *Disco Backlog* (Command Center) |
| **Lange Konzept-Material zu Star-Items** (Schemas, Phasen, Tabellen) | `docs/concepts/*.md` im Repo |
| **Architektur-Entscheidungen** | `docs/architecture-decisions.md` |
| **Schichten-Architektur + Datenmodell** | `docs/architektur-ebenen.md` |
| **Produktvision + State + Roadmap** | `docs/PRODUCT.md` |
| **Konventionen / Tools / Pipeline** | `CLAUDE.md` |
| **Operations / Deploy / Rollback** | `docs/operations-runbook.md` |
| **Test-Strategie** | `docs/testing-strategy.md` |
| **DISCO.md-Migration** | `docs/disco-md-migration-playbook.md` |
| **Netzwerk-Egress-Policy** | `docs/network-egress-policy.md` |
| **DWG-Setup** | `docs/dwg-setup.md` |
| **SDK-Referenz** | `docs/sdk-reference.md` |
| **Historische Konzept-Docs / Audits** | `docs/archive/` |

## Konzept-Files unter `docs/concepts/`

Die vier Star-Items mit umfangreichem Konzept-Material:

- [`object-graph.md`](concepts/object-graph.md) — Anlagen-Komponenten
  als zweite Reasoning-Schicht
- [`kritis-compliance.md`](concepts/kritis-compliance.md) —
  Disco-Box + BEW-Azure-Tenant fuer KRITIS-Einsatz
- [`data-lineage.md`](concepts/data-lineage.md) — Data-Lineage +
  Daten-Architektur Ebene 3
- [`extraction-pipeline-overhaul.md`](concepts/extraction-pipeline-overhaul.md)
  — konsolidiertes Konzept fuer die Extraction-Pipeline-Refaktorierung

Die jeweiligen Notion-BL-Items verlinken auf diese Files. Echte
Tracking-Arbeit (Status, Priority, Assignment) passiert in Notion.

## Pflege-Workflow ab 2026-05-11

- **Neues BL-Item:** direkt in Notion anlegen (Status `Backlog`, Type,
  Priority, Component setzen)
- **Konzept-Material:** bei umfangreichen Star-Items als `docs/concepts/<topic>.md`
  ablegen + im Notion-Item verlinken
- **Commit-Refs:** im Notion-Item-Feld *Commit Refs* nachpflegen, wenn
  ein Fix gemerged wird
- **Done:** Status in Notion auf `Done` setzen — die View
  *Done (last 30d)* zeigt es automatisch

## Migration-History

| Datum | Was | Quelle |
|---|---|---|
| 2026-05-11 | 41 aktive Items nach Notion migriert | dieser Commit |
| 2026-05-09 | Done-Items aus dem Repo entfernt (BACKLOG-Cleanup) | Commit `0b7469a` |
| 2026-05-09 | Konzept-Docs und Audits nach `docs/archive/` verschoben | Commit `369d440` |

Falls Du auf historische Markdown-Stände zurückgreifen willst:
`git log -- docs/BACKLOG.md`.
