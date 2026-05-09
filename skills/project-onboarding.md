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

Default-Modus liefert automatisch **Schicht 1 + Kapitel-Index**:

- Schicht 1 (max ~3,5 KB): Identitaet, Aktueller Fokus, Konventionen,
  Lookup-Pfade.
- Kapitel-Index: Liste aller Schicht-2-Kapitel mit Titeln und Tags —
  Du **siehst** damit, welche thematischen Bloecke verfuegbar sind,
  ohne sie zu laden.

**Schicht 2 nicht blind nachladen.** Wenn der Nutzer ein konkretes
Thema anspricht, das im Kapitel-Index auftaucht, holst Du das einzelne
Kapitel gezielt:

```text
memory_read({"file": "DISCO.md", "chapter": "Bautechnik IBL"})
```

Bei Treffer (`exact`/`substring`/`tag`/`body`) bekommst Du Body + Meta;
bei Miss kommt `{found: false}` mit der vollen Titel-Liste zurueck —
**nicht raten, einfach nachfragen oder anderen Suchbegriff probieren**.

**Legacy-Projekt ohne Marker** (`<!-- DISCO-LAYER-1-END -->` fehlt):
Default faellt auf 8-KB-Cap zurueck und liefert die ersten 8 KB der
Datei. Funktioniert weiter, aber Du siehst keinen Kapitel-Index. Wenn
das Projekt produktiv genutzt wird und DISCO.md gross ist, schlage
dem Nutzer eine Migration auf das Schichten-Format vor.

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

**Tabellen-Wissen lebt in `agent_table_docs` (Schicht 3 der Memory-
Reform)** — nicht in DISCO.md. Bevor Du eine Tabelle reasonst,
deren Inhalt Du nicht selbst gerade geschrieben hast:

```text
table_doc_get({"table_name": "agent_dcc_results"})
```

Liefert Beschreibung, Schema-Summary, Beispiel-Query und Quell-Files
falls dokumentiert. Wenn Du eine **neue** Tabelle anlegst, pflege die
Doku direkt mit `table_doc_set`.

## Antwort an den Nutzer

Halte die Antwort **kurz** (max. 8 Zeilen):

1. **Eine Zeile** Projekt-Kontext (aus README)
2. **Eine Zeile** letzter Stand (aus NOTES, letzter Eintrag)
3. **Eine Zeile** zu aktuellem Fokus/Konventionen aus DISCO.md
4. **Eine Zeile** zu Arbeitsgrundlagen (Kontext-Manifest), wenn relevant
5. **Eine Zeile** zu offenen Plaenen (wenn vorhanden)
6. **Frage** an den Nutzer: "Womit starten wir heute?"

Beispiel:

> Wir sind im Projekt **Anlage Musterstadt** (SOLL/IST nach VGB S 831,
> Frist 18.05.2026).
> Letzter Stand: Index-Prototyp mit 72 Eintraegen, Excel-Export lief.
> Aktueller Fokus laut DISCO: Bauwerk-Komponenten BW-001…BW-018
> noch nicht im Index.
> Arbeitsgrundlage VGB-S-831: DI-Extrakt + Kapitelverzeichnis liegen unter
> `.disco/context-summaries/`.
> Keine offenen Plaene.
>
> Womit starten wir heute?

## Wann das Onboarding laufen muss

**Immer bei der ersten Nachricht in einem neuen Thread** — egal was der
Nutzer sagt, egal wie konkret die Aufgabe klingt, egal ob es nur "Hi"
ist. Zwischen Sessions vergisst Du alles, und ohne das Gedaechtnis
arbeitest Du ins Blaue.

Ausnahme: Im **selben** Thread mit bereits gelaufenen Tool-Calls hast
Du den Kontext — da musst Du nicht erneut onboarden.

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
- Lookup-Pfad eingerichtet (DCC-Katalog-Kapitel, Hersteller-Alias-Datei)
- Wichtige Entscheidung getroffen
- Fokus des Projekts hat sich verschoben
- Neuer Wissens-Block, den Du in spaeteren Sessions nachschlagen koennen willst

**Faustregel: Tabellen-Wissen NICHT in DISCO.md.** Tabellenbeschreibungen,
Schema-Summaries, Beispiel-Queries → `table_doc_set` auf
`agent_table_docs`. So bleibt DISCO.md schlank und Du holst Tabellen-
Doku gezielt mit `table_doc_get` zurueck, wenn Du sie brauchst.

**Wo landet was?**

| Inhalt | Ziel |
|---|---|
| Neue Konvention, neuer Lookup-Pfad, neuer Aktueller Fokus | DISCO.md **Schicht 1** (per `memory_write` nach `memory_read`-Diff) |
| Abgeschlossener Wissens-Block (z.B. „KKS-Masterliste 2026-04-28", „SharePoint-Link-Standard") | DISCO.md **Schicht 2** als neues Kapitel mit chapter-meta |
| Neue/aktualisierte Tabellenbeschreibung | `agent_table_docs` per `table_doc_set` |
| Chronologisches Ereignis („Heute Run #5 abgeschlossen") | NOTES.md per `memory_append` |

**Schicht 2 — neues Kapitel anlegen:**

```text
memory_append({
  "file": "DISCO.md",
  "heading": "KKS-Masterliste 2026-05-09",
  "tags": ["kks", "masterliste"],
  "status": "current",
  "content": "<Kapitel-Body>"
})
```

`tags` + `status` triggern, dass automatisch ein chapter-meta-Block
unter dem Heading angelegt wird — das ist Pflicht fuer das Reform-
Format. **Append ohne tags/status** auf DISCO.md erzeugt zwar ein
Kapitel, aber ohne Meta — vermeiden, sonst kann der Kapitel-Index
es nicht zaehlen.

**Schicht 1 oder vollstaendige Neufassung:**

```text
# Erst lesen
memory_read({"file": "DISCO.md", "max_bytes": 0})
# Dann diffen + komplett ueberschreiben
memory_write({"file": "DISCO.md", "content": "<komplett, Marker bleibt erhalten>"})
```

Marker `<!-- DISCO-LAYER-1-END -->` **muss** drinbleiben, sonst
verliert das Projekt das Reform-Format.

**Schicht 1 ist hart limitiert (~3,5 KB).** Wenn sie aufquillt:
Inhalte als neues Schicht-2-Kapitel auslagern oder verdichten.

**Obsolete Eintraege loeschen, nicht durchstreichen** (NOTES.md hat
die Chronik). Veraltete Schicht-2-Kapitel mit `status: archived`
markieren — sie zaehlen dann nicht mehr ins Default-Onboarding,
sind aber per `chapter:`-Lookup weiter erreichbar.
