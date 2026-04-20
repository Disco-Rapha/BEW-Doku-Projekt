---
name: planning
description: Plan vor Action — bei Aufgaben mit mehr als 3 Schritten zuerst einen strukturierten Plan anlegen, dann ausführen.
when_to_use: "lass uns planen", "große Aufgabe", ">3 Schritte", oder wenn Du von Dir aus merkst, dass die Aufgabe mehrstufig ist.
---

# Skill: planning

Dieser Skill ist Dein Kompass bei **mehrstufigen Aufgaben**. Statt
loszulegen und Dich nach 3 Tool-Calls zu verzetteln, schreibst Du
zuerst einen strukturierten Plan, arbeitest ihn ab, und dokumentierst
Fortschritt.

**Vorbild:** Wie ein Entwickler ein TODO schreibt, bevor er anfängt,
und wie Claude Code einen Plan-Mode hat.

## Wann einen Plan anlegen

- Aufgabe besteht aus **mehr als 3 Schritten**
- Aufgabe läuft **über mehrere Turns** (Du bist nicht in einem Call fertig)
- Aufgabe hat **Abhängigkeiten** (Schritt B braucht Ergebnis aus A)
- **Bulk-Arbeit** (viele Dateien, viele Dokumente)
- Der Benutzer sagt: *"lass uns planen"*, *"das wird größer"*,
  *"wir machen das in mehreren Schritten"*

**Nicht** für Einzelaktionen wie „lies README" oder „zeig mir die
Tabelle". Dafür brauchst Du keinen Plan.

## Der Workflow

### 1. Plan-Liste prüfen (am Session-Start, immer)

```text
plan_list({})
```

Gibt es einen **offenen** oder **in-progress** Plan? Dann lies ihn zuerst:

```text
plan_read({"filename": "<aus plan_list>"})
```

Wenn er noch relevant ist, arbeite dort weiter statt einen neuen anzulegen.

### 2. Neuen Plan anlegen

```text
plan_write({
  "title": "<kurzer Titel, eine Zeile>",
  "goal": "<1-3 Sätze: was soll am Ende stehen?>",
  "steps": [
    "Schritt 1 — konkret, überprüfbar",
    "Schritt 2 — ...",
    "Schritt 3 — ...",
    "Schritt 4 — ..."
  ],
  "status": "in-progress"
})
```

**Titel-Beispiele** (gut):
- „Dokumenten-Klassifikation Elektro"
- „SOLL/IST-Abgleich Bauwerk gegen VGB A.3"
- „Context-Onboarding für 16 neue Normen"

**Titel-Beispiele** (schlecht):
- „Arbeit" (zu vage)
- „Klassifikation von 493 Dokumenten nach Gewerk und Dokumenttyp
  basierend auf VGB S 831 mit Excel-Export" (Titel, nicht Roman)

**Schritte formulieren:**
- Jeder Schritt **ein Satz**, klar und überprüfbar
- **Verb am Anfang**: „Registriere …", „Prüfe …", „Exportiere …"
- Kein Gedanken-Prosa, keine Begründungen (die kommen in `goal`
  oder als Notiz)

### 3. Arbeiten — und Fortschritt dokumentieren

Nach jedem wichtigen Zwischenstand:

```text
plan_append_note({
  "filename": "<aus plan_write>",
  "note": "<kurze Notiz mit konkreter Zahl/Ergebnis>"
})
```

**Gute Notizen:**
- „Schritt 1 erledigt: 47 Dateien registriert, 2 Duplikate gefunden."
- „Schritt 3 blockiert — Datei `specs.xlsx` fehlt in `sources/`."
- „Zwischenstand: 200/493 Dokumente klassifiziert, 18 mit niedriger
  Konfidenz (< 0.7)."

**Schlechte Notizen** (nicht tun):
- „habe gearbeitet"
- „Fortschritt gemacht"
- „Läuft"

### 4. Schritte als erledigt markieren

Wenn ein Schritt **komplett** fertig ist: `plan_write` nochmal mit dem
gleichen `filename`, aber dem Schritt als `[x]` markiert. Das Tool
bewahrt die Notizen automatisch.

```text
plan_write({
  "filename": "2026-04-17_ibl-klassifikation.md",
  "title": "...",
  "goal": "...",
  "steps": [
    "[x] Schritt 1 erledigt",
    "[x] Schritt 2 erledigt",
    "Schritt 3 — offen",
    "Schritt 4 — offen"
  ],
  "status": "in-progress"
})
```

### 5. Plan abschliessen

Wenn alle Schritte erledigt sind:

```text
plan_write({
  "filename": "...",
  "title": "...",
  "goal": "...",
  "steps": [...alle mit [x]...],
  "status": "done"
})
```

Plus eine letzte Notiz mit dem Endergebnis. Der Plan bleibt als
Audit-Trail liegen.

## Status-Werte im Überblick

| Status | Wann |
|---|---|
| `open` | Plan steht, wurde aber noch nicht angefangen |
| `in-progress` | Arbeit läuft |
| `blocked` | Fortschritt blockiert (fehlende Info, fehlende Datei) |
| `done` | Alle Schritte erledigt, Ergebnis steht |
| `abandoned` | Plan wurde verworfen (Ansatz falsch, Anforderung geändert) |

## Was in den Plan gehört — und was nicht

**Gehört in den Plan:**
- Ziel (Goal)
- Schritte (Checklist)
- Status-Notizen mit Zahlen/Ergebnissen
- Blocker und offene Fragen

**Gehört NICHT in den Plan** (sondern in NOTES.md oder `memory.md`):
- Langfristige Erkenntnisse über das Projekt („der Kunde bevorzugt X")
- Faustregeln, die über die aktuelle Aufgabe hinaus gelten
- Referenz-Daten (Hersteller-Listen etc.)

Faustregel: **Plan = heutige Arbeit. NOTES = Projektverlauf. memory = dauerhaft.**

## Beispiel-Plan

```markdown
# Plan: Dokumenten-Klassifikation Elektro

**Status:** in-progress
**Erstellt:** 2026-04-17 10:15:00
**Letztes Update:** 2026-04-17 14:20:00

## Ziel

Alle 493 Elektro-PDFs in sources/ nach Gewerk und DCC klassifizieren.
Ergebnis: Tabelle agent_classification + Excel-Export in exports/.

## Schritte

- [x] Sources registrieren und Duplikate prüfen
- [x] Klassifikations-Prompt auf 20 Stichproben testen
- [ ] Alle 493 Dokumente durchlaufen (Pipeline)
- [ ] Niedrig-Konfidenz-Fälle manuell reviewen
- [ ] Excel-Export mit Sheets pro Gewerk

## Notizen

**2026-04-17 10:15:00** — Plan angelegt.
**2026-04-17 11:40:00** — Schritt 1 erledigt: 493 Dateien registriert,
12 Duplikate erkannt (alle als duplicate-of markiert).
**2026-04-17 14:20:00** — Schritt 2 erledigt: Stichprobe 20/20 korrekt,
Prompt funktioniert. Starte jetzt mit Bulk.
```
