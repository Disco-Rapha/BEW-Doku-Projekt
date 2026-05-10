# ★ Object-Graph als zweite Disco-DB

**Status:** Konzept, prio HOCH-strategisch.
**Entstanden:** 2026-04-23 (Memory-Notiz), vertieft 2026-05-10.
**Notion-BL-Item:** verlinkt aus dem Disco-Backlog (Component: Object-Graph).


**Kerngedanke:** Disco soll künftig nicht nur Dokumente kennen, die
Objekte beschreiben, sondern **Objekte (Anlagen-Komponenten:
Pumpen, Ventile, Motoren, Sensoren, Bauwerks-Elemente etc.) und ihre
technischen Zusammenhänge** als eigene Reasoning-Schicht verfügbar
haben. Dann wird Cross-Source-Reasoning erst richtig stark — Disco
kann z. B. „wenn diese Pumpe ausfällt, was hängt downstream dran?"
oder „welche Datenblätter belegen welchen KKS, mit welcher
Konfidenz?" deterministisch beantworten.

**Stand der Vorbereitung:**

- Erstes Konzept aus Memory-Notiz 2026-04-23
  (`project_objekt_inhalt_modell.md`): dünnes Meta-Schema +
  symmetrische Dialekt-Schicht für KKS/RDS-PP UND DCC/VGB.
  Status damals: *„Super Ansatz, wir werden es tun."*
- Vertiefte Vorbereitungs-MD geschrieben **2026-05-10** mit
  10 Entscheidungs-Punkten als Diskussions-Tagesordnung,
  Schema-Vorschlägen, drei durchgespielten Reasoning-Use-Cases,
  und konkreter Migrations-Reihenfolge der bestehenden
  `agent_kks_*`-/`agent_component_register`-/
  `agent_building_element_register`-Tabellen.
- **Datei (außerhalb des Repos, weil Kunden-Beispiele drin):**
  `~/Claude/discussion-prep-object-graph.md`.

**Was die MD klärt (für die Diskussion vorbereitet):**

| Punkt | Optionen + Empfehlung |
|---|---|
| Objekt-Scope | physisch / +logisch / +bautechnisch / +Räume — Empfehlung: physisch + logisch + bautechnisch |
| Hierarchie-Quelle | KKS allein / KKS+sekundär / symmetrische Dialekt-Schicht — Empfehlung: KKS-primär, Schema mehrachsen-fähig |
| Relation-Typen | MVP-Set: parent_of, belongs_to_system, documented_by, feeds, controls, supersedes, mounted_in |
| Property-Modell | Hybrid: Standard-Felder als Spalten + JSON für domänen-spezifisch + eigene `agent_object_property_evidence` mit Provenienz |
| Edge-Schema | Generische Edge-Tabelle mit `relation_type`-Spalte |
| Befüllung | KKS-Master → Excel-Listen → Datenblatt-PDFs → Pläne → Fachunternehmer-Erklärungen → manuelle Pflege |
| Storage | **Plan A: SQLite-Property-Graph in `datastore.db`** (kein neues Tool, Mandantentrennung intakt). Plan B: LadybugDB als zweite DB pro Projekt — bei > 50k Objekten oder Multi-Hop-Schmerz |
| Tool-Layer | MVP 8 Tools: `object_show`, `object_neighbors`, `object_path`, `objects_in_system`, `objects_by_type`, `documents_for_object`, `object_lineage`, `object_query` |
| Use-Cases | Soll/Ist-Vollständigkeit · Impact-Analyse · Identdaten-Konsolidierung über alle Quellen |
| Industrie-Standards | Pragmatik mit bewusster Standard-Kompatibilität (KKS+RDS-PP+VGB als Hauptachsen, ISO-15926/CFIHOS/DEXPI/IFC als spätere Mapping-Hülle) |

**Vorgeschlagener Diskussions-Ablauf:**
2,5–3 h ruhige Session, in 6 Blöcken (Walkthrough, Scope+Hierarchie+Edges+
Properties, Edge-Schema+Befüllung+Storage, Tools+Use-Cases+Standards,
Migrations-Reihenfolge, Roadmap+Aufwand).

**Wann starten:** strategisch nach BEW-Demo Dienstag 2026-05-12 und
nach der Korrekturlieferung von Sascha/Peter/Roman (die Korrekturen
sind die fachliche Wahrheit, auf der wir den Object-Graph initial
befüllen).

**Pointer:**
- Vorbereitungs-MD: `~/Claude/discussion-prep-object-graph.md`
- Memory-Vorgänger-Konzept:
  `~/.claude/projects/-Users-BEW-Claude-BEW-Doku-Projekt/memory/project_objekt_inhalt_modell.md`
- Anschluss an: Embedding-DCC-Klassifikator-Idee (siehe Section
  *Document Intelligence*) — beide brauchen die Korrekturlieferung als
  fachliche Wahrheit, beide profitieren voneinander (Object-Graph als
  Filter-Schicht für Embedding-Klassifikator).
