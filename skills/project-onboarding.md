---
name: project-onboarding
description: Session-Start-Routine — README + NOTES + DISCO.md + context/_manifest lesen, Stand zusammenfassen, naechsten Schritt vorschlagen.
when_to_use: "wo waren wir?", "was haben wir letztes Mal gemacht?", "erinnerst Du dich?" oder frische Session ohne bisherigen Chat-Verlauf.
---

# Skill: project-onboarding

Wenn Du in eine neue Chat-Session in einem Projekt kommst, weisst Du
zunaechst nichts. Diese Routine bringt Dich auf Stand — **kurz** und
**strukturiert**, damit der Nutzer nicht warten muss.

## Verbindlicher Workflow

Sobald Du erkennst, dass die Session frisch ist (kein vorheriger Chat-
Verlauf in diesem Thread, oder der Nutzer fragt explizit nach Stand):

### 1. Projekt-Wurzel auflisten

```text
fs_list({"path": ""})
```

Damit siehst Du, welche Standard-Verzeichnisse befuellt sind und welche
Dateien im Projekt-Root liegen. Erwartet: README.md, NOTES.md, DISCO.md,
sources/, context/, work/, exports/, data.db.

### 2. README.md lesen — Projektziel pruefen

```text
memory_read({"file": "README.md"})
```

Das ist der Kontext-Text, den der Nutzer selbst gepflegt hat.
**WICHTIG: Pruefe ob ein konkretes Projektziel drinsteht.**

Wenn README.md nur das leere Template enthaelt (kein Projektziel, nur
Platzhalter wie "*(Was soll am Ende dieses Projekts herauskommen?...)*")
→ **frag den Nutzer aktiv:**

> "Ich sehe, dass das Projektziel noch nicht festgehalten ist.
> Bevor wir richtig arbeiten koennen, brauche ich Dein Briefing:
>
> 1. **Was ist das Ziel** dieses Projekts?
>    (z.B. 'Dokumente nach VGB S 831 klassifizieren')
> 2. **Welche Ergebnisse** soll ich am Ende liefern?
>    (z.B. 'Excel mit Klassifikation + neue Ordnerstruktur')
> 3. **Welche Quellen** wirst Du laden?
>    (z.B. '1600 PDFs aus SharePoint + KKS-Liste als Excel')
> 4. **Kontext/Frist** — gibt es einen Auftraggeber, eine Deadline?
>
> Ich trage das strukturiert ins README ein."

Nach der Antwort: **ein** `memory_write({"file": "README.md", ...})` mit
den vier Abschnitten (Projektziel / Kontext / Quellen / Erwartete Ergebnisse).
Dann erst mit dem Onboarding fortfahren.

### 3. NOTES.md lesen (Ende — letzter Stand)

```text
memory_read({"file": "NOTES.md"})
```

Das ist Dein chronologisches Logbuch aus frueheren Sessions. Lies die
letzten 1–2 Eintraege (der Anfang ist meist Boilerplate). Ziel: **Was
wurde zuletzt getan, was war offen?**

### 4. DISCO.md lesen (Dein destilliertes Arbeitsgedaechtnis)

```text
memory_read({"file": "DISCO.md"})
```

Das ist Deine "zweite Wahrheit" nach dem README. Dort stehen
Konventionen, Projekt-Tabellen, Lookup-Pfade, Glossar, Entscheidungen —
alles was Du brauchst, um sofort wieder arbeitsfaehig zu sein.
**Komplett lesen** — DISCO.md ist absichtlich kurz und nachschlagbar.

### 5. context/_manifest.md lesen (Arbeitsgrundlagen)

```text
fs_read({"path": "context/_manifest.md"})
```

Das Manifest zaehlt auf, welche Normen/Kataloge/Richtlinien im Projekt
liegen — Du musst nicht jeden Volltext kennen, aber **welche Datei bei
welcher Frage hilft**. Wenn das Manifest nicht existiert oder leer ist
und `fs_list({"path": "context"})` zeigt unpflegte Dateien: sag dem
Nutzer, dass wir `context-onboarding` durchlaufen sollten.

### 6. Aktive Plaene pruefen

```text
plan_list({})
```

Wenn ein Plan mit Status `in-progress` oder `blocked` dabei ist:
**zuerst reinschauen** bevor Du etwas Neues anfaengst:

```text
plan_read({"filename": "<aus plan_list>"})
```

### 7. Projekt-DB-Status (optional, wenn relevant)

Bei Datenarbeit kurzer Check:

```text
sqlite_query({"sql": "SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE 'work_%' OR name LIKE 'agent_%' OR name LIKE 'context_%') ORDER BY name"})
```

Damit siehst Du, welche Arbeits-/Kontext-Tabellen existieren.

## Antwort an den Nutzer

Halte die Antwort **kurz** (max. 8 Zeilen):

1. **Eine Zeile** Projekt-Kontext (aus README)
2. **Eine Zeile** letzter Stand (aus NOTES, letzter Eintrag)
3. **Eine Zeile** zu aktuellem Fokus/Konventionen aus DISCO.md
4. **Eine Zeile** zu Arbeitsgrundlagen (Kontext-Manifest), wenn relevant
5. **Eine Zeile** zu offenen Plaenen (wenn vorhanden)
6. **Frage** an den Nutzer: "Womit starten wir heute?"

Beispiel:

> Wir sind im Projekt **Vattenfall Reuter** (Lagerhalle Reuter,
> SOLL/IST nach VGB S 831, Frist 18.05.2026).
> Letzter Stand: IBL-Prototyp mit 72 Eintraegen, Excel-Export lief.
> Aktueller Fokus laut DISCO: Bauwerk-Komponenten BW-001…BW-018
> noch nicht in der IBL.
> Arbeitsgrundlage VGB-S-831: DI-Extrakt + Kapitelverzeichnis liegen unter
> `.disco/context-summaries/`.
> Keine offenen Plaene.
>
> Womit starten wir heute?

## Wann das Onboarding NICHT laufen muss

- Nutzer stellt sofort eine konkrete Aufgabe, ohne nach Stand zu fragen
  → arbeite los, Onboarding minimal (`fs_list` + `memory_read("DISCO.md")`).
- Im selben Thread schon Tool-Calls gemacht → Kontext hast Du.

## Wann das Onboarding ZWINGEND laufen muss

- Nutzer fragt "Wo waren wir?" / "Was haben wir letztes Mal gemacht?"
- Dein letzter Eintrag in NOTES.md ist aelter als 7 Tage — dann
  koennte Deine grobe Erinnerung veraltet sein.

## NOTES.md fortfuehren am Session-Ende

Wenn der Nutzer sagt "danke, das war's" oder die Session endet,
**bevor** Du Dich verabschiedest:

```text
memory_append({
  "file": "NOTES.md",
  "heading": "<kurzes Thema>",
  "content": "<3–6 Zeilen: was wurde gemacht, was ist das Ergebnis, was ist offen>"
})
```

Wenn der Nutzer das nicht explizit will, kurz fragen:
"Soll ich den Stand noch in NOTES festhalten?"

## DISCO.md pflegen — wann und wie

**Wann:**
- Neue Konvention entstanden ("wir nennen die Gewerke immer kleingeschrieben")
- Neue Tabelle angelegt, die ueberdauern soll (nicht work_*)
- Lookup-Pfad eingerichtet (DCC-Katalog-Kapitel, Hersteller-Alias-Tabelle)
- Wichtige Entscheidung getroffen
- Fokus des Projekts hat sich verschoben

**Wie:**
- Fuer gezielte Updates eines Abschnitts: `memory_append({"file":
  "DISCO.md", "heading": "Projekt-Tabellen", "content": "`agent_sources` — Registry ..."})` — das haengt einen neuen H2-Abschnitt an.
- Fuer vollstaendige Neufassung: vorher `memory_read`, dann
  `memory_write({"file": "DISCO.md", "content": "<komplett>"})`.
- Obsolete Eintraege **loeschen**, nicht durchstreichen (NOTES.md hat die Chronik).
