# Disco — Produktvision: vom Dokumentenmanagement zum Projektbüro-Agent

**Stand 2026-05-07** — Brainstorm vor der Vorstellung bei einem
Projektleiter. Nicht-aktiv-bearbeitete Roadmap, dient als Anker für
spätere Diskussionen.

---

## Kern-These

Disco ist heute ein starkes **Dokumentenmanagement-Tool** für
technische Großprojekte. Die zugrundeliegende Architektur (Pipeline,
Skills, Search, Multi-Format-Routing, Excel-Reports) ist aber
**bewusst generalistisch** angelegt. Damit hat Disco das Potenzial,
sich zu einem **vollwertigen Projektbüro-Agent** zu entwickeln —
ein KI-Tool, das die ganze Bandbreite an Projektbüro-Aufgaben
systematisch unterstützt.

## Persönlicher Hintergrund (User)

Lange Erfahrung im Projektbüro großer Projekte. Beobachtung dort:
**Datenqualität + Daten-Verfügbarkeit + Projekt-Steuerung** sind
die drei kritischen Erfolgsfaktoren. Wer die Daten parat hat,
steuert das Projekt richtig. Wer sie sucht oder rekonstruiert,
verliert.

Disco zielt genau auf diese Lücke: er macht die Daten verfügbar,
kontextualisiert sie, und unterstützt aktiv beim Steuern.

## Themenfelder, in denen Disco unterstützen soll

Heute live, weiter ausbauen:

1. **Dokumentenmanagement** — Quellen registrieren, kanonisieren,
   extrahieren, indizieren, suchen, Reports bauen. Funktioniert
   bereits gut.

Geplant / als Vision:

2. **Legal / Contract Management** — Verträge mit Generalunternehmern
   strukturiert verwalten, Klauseln nachschlagen, Fristen tracken.

3. **Claim Management** — Nachforderungen und Mängelansprüche mit
   Beleg-Trail. Verknüpfung zwischen Vertragsklausel, Korrespondenz,
   Kostenfolge.

4. **Contract Communication** — bei FIDIC-Verträgen mit GUs läuft
   Kommunikation hochstrukturiert nach klausel-bezogenen Notification-
   Pflichten ab. Disco kann hier als Klausel-bewusster Schreib- und
   Recherche-Assistent fungieren.

5. **Qualitätsmanagement** — z.B. mechanische Endkontrollen bei BEW.
   Pflicht-Berichte, Checklisten, Konsistenz-Prüfung gegen Normen
   (VGB S 831 etc.).

6. **Terminplanung** — Schedule-Management, Verzugs-Analyse,
   Critical-Path-Verständnis.

7. **Weitere Projektbüro-Themen** — Risiko-Management, Reporting-
   an-Auftraggeber, Variation-Orders, Subcontractor-Koordination.

## Disco-Vision in einem Satz

> Disco ist das KI-gestützte Projektbüro für technische Großprojekte:
> es hält die Daten parat, verbindet die Themen, treibt die Prozesse,
> und hebt damit die Qualität der Projekt-Steuerung deutlich.

---

## Anmerkungen — wie das technisch passt

### Was Disco heute bereits hat, das zur Vision passt

- **Pipeline-Architektur ist projektagnostisch.** Dieselben sechs
  Schritte (Registrierung → Anreicherung → Kanonik → Routing →
  Extraction → Suchindex) funktionieren für DM-Pakete, Vertragsakten,
  QM-Berichte, Schedule-Exports. Das war von Anfang an richtig
  dimensioniert.
- **Skills sind themen-spezifisch erweiterbar** ohne den Kern
  anzufassen. Heute haben wir `excel-reporter`, `excel-formatter`,
  `pipeline-diagnostics`, `flow-supervisor` etc. Künftig könnten
  `legal-fidic-onboarding`, `claim-trail-builder`, `qm-endkontrolle`
  dazukommen.
- **SQL-Tabellen + Lookup-Excels** passen perfekt für Vertragsklausel-
  Kataloge, Norm-Matrizen, QM-Vorgabe-Listen.
- **Multi-Format-Routing** (PDF/Excel/DWG/Bild) ist bereits da. Bei
  Phase 2b kommen DOCX/PPTX hinzu (relevant für Verträge, Reports,
  Präsentationen).
- **Cost-Tracking** ist in Place — bei Skalierung auf mehrere
  Themen-Domänen pro Projekt kritisch, dass Kosten transparent
  bleiben.

### Was für die Vision noch fehlt

- **Frist-Tracking / Date-Reasoning** — bei FIDIC-Notifications und
  Claim-Fristen ist „28 days from becoming aware" Pflicht. Disco
  müsste Datums-Aware werden, Fristen aus Klauseln ableiten und
  proaktiv erinnern.
- **Cross-Document-Linkage explizit modellieren** — heute haben wir
  `agent_source_relations` für Duplikate/Replaces. Für Claim-Trail
  bräuchten wir reichere Relations: „antwortet auf", „bezieht sich auf
  Klausel", „belegt Cause für".
- **Workflow-Engine für Genehmigungs-Prozesse** — wer hat was wann
  unterschrieben, was steht aus.
- **Email-/Kommunikations-Integration** — Outlook/MS365-Anbindung für
  Korrespondenz-Tracking. Heute alles File-basiert.
- **Domain-Skills pro Themenfeld** — Legal/QM/Terminplanung jeweils
  ein eigenes Skill-Set mit Trigger-Phrasen, Workflow-Templates,
  Pflicht-Checks.

### Risiko / Empfehlung für die Reifung

- **Generalistisch bleiben hat Wert**: Disco wird in jedem Projekt
  nützlich. Aber jede neue Domäne erhöht System-Prompt-/Skill-/Tool-
  Komplexität. Saubere Skill-Trennung ist Pflicht.
- **Eine Domäne nach der anderen reifen lassen** — nicht alle 5
  parallel. Vorschlag-Reihenfolge: Legal/Contract zuerst (klare
  Strukturen, FIDIC-Standard hilft), dann QM, dann Termin. Claim-
  Management baut auf Legal auf.
- **Pipeline + Search + Excel-Reports bleiben generisch** — sind das
  Fundament. Domäne-spezifische Logik kommt rein über Skills +
  themen-spezifische Tools, nicht durch Eingriff in den Kern.
- **Kunden-Datenschutz wird kritischer** mit Legal-Inhalten. DSGVO,
  Anwaltsgeheimnis, Mandantentrennung — heute über Workspace-
  Isolation gelöst, müsste für Vertragsdaten ggf. nochmal verschärft
  werden (z.B. Foundry-Region-Pinning auf EU + Audit-Logs).

### Wo das im aktuellen Plan landet

Diese Vision ist **strategisch**, nicht akut. Sie gehört nicht in
den BACKLOG (der ist taktisch), sondern als eigenständiges
Vision-Dokument hier in `docs/`. Der ★-Konsolidat
„EXTRACTION-PIPELINE OVERHAUL" reift gerade die generische
Pipeline weiter — danach ist die Architektur stabil genug, um
themen-spezifische Domains anzudocken.

Konkret später: nach Stable-Release v1.0 wäre der natürliche
Punkt, mit der ersten Domain-Erweiterung (Vorschlag: Legal/FIDIC)
zu starten.

---

*Dokument lebt — bei nächsten Vision-Gesprächen erweitern,
nicht als abgeschlossen behandeln.*
