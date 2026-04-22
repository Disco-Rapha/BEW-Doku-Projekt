---
name: context-onboarding
description: Kontext-Dateien inhaltlich analysieren (DI fuer PDFs), Zusammenfassung + Projektziel-Bezug schreiben, Manifest pflegen.
when_to_use: "neue Kontextdateien", "Norm abgelegt", "Richtlinie dazu", oder wenn context/ unkuratierte Dateien enthaelt.
---

# Skill: context-onboarding

Context-Dateien sind **Arbeitsgrundlagen** — Normen, Kataloge,
Richtlinien, Referenztabellen. Disco muss sie **inhaltlich verstehen**
um sie bei der Arbeit gezielt nachschlagen zu koennen.

## Voraussetzung: Projektziel muss bekannt sein

Bevor Du context/ analysierst, pruefe ob README.md ein Projektziel
enthaelt. Wenn nicht:

> "Bevor ich die Kontextdateien analysiere, brauche ich Dein
> Projektziel — damit ich beurteilen kann, was davon relevant ist.
> Was ist das Ziel dieses Projekts?"

Erst wenn das Ziel klar ist (in README.md festgehalten), geht's weiter.

## Verbindlicher Workflow

### 1. Ist-Stand erfassen

```text
fs_read({"path": "README.md"})
fs_list({"path": "context", "recursive": false})
fs_read({"path": "context/_manifest.md"})
```

Damit weisst Du:
- Das Projektziel (aus README)
- Welche Dateien in context/ liegen
- Welche davon schon im Manifest stehen (= bereits analysiert)

### 2. Diff bilden

Neue Dateien = in context/ aber NICHT im Manifest.
`_manifest.md` selbst ignorieren. Nur echte Inhaltsdateien zaehlen.

### 3. Pro neue Datei: inhaltlich analysieren

**WICHTIG: Fuer Context-Dateien gilt ein hoher Qualitaetsanspruch.
Jede Datei muss INHALTLICH verstanden werden — nicht nur katalogisiert.
Ueberspringe KEINEN der folgenden Schritte.**

#### PDF-Dateien — IMMER ueber die Markdown-Pipeline

Fuer Context-PDFs gilt derselbe Weg wie fuer alle PDFs in Disco:
einmalige Konvertierung nach Markdown, dann ausschliesslich aus
`agent_pdf_markdown` lesen. Niemals pypdf / DI / Docling direkt.

**Schritt 1 — Routing + Extraktion (einmalig):**
```text
flow_run({"flow": "pdf_routing_decision"})
flow_run({"flow": "pdf_to_markdown"})
```
Das fuellt `agent_pdf_markdown` fuer alle Inventory-Eintraege —
Context-PDFs inklusive, sobald sie unter `context/` liegen und vom
Inventory-Flow erfasst sind.

Kosten: Context-PDFs laufen typisch auf `docling-standard` (0 EUR)
oder `azure-di` (~0.01 EUR/Seite) — Keine Rueckfrage beim Nutzer
noetig, das ist Standard-Workflow.

**Schritt 2 — Markdown lesen:**
```text
pdf_markdown_read({"rel_path": "context/<datei>.pdf"})
```

Zwei Faelle:

**Kleines Dokument (< 50 KB Markdown):** komplett lesen, default-
`max_chars` reicht. Der Call liefert `{markdown, char_count,
truncated: false}`.

**Grosses Dokument (> 50 KB Markdown):** Volltext passt NICHT in
den Kontext. Kombinierte Strategie — **beide Schritte PFLICHT:**

**Schritt A — Erste ~30 KB lesen (fuer die Summary):**
```text
pdf_markdown_read({"rel_path": "context/<datei>.pdf", "max_chars": 30000})
```
Die ersten Seiten enthalten bei Normen/Richtlinien typisch:
Titelseite, Inhaltsverzeichnis, Einleitung, Begriffe, Scope. Das
reicht fuer eine fundierte Summary.

**Schritt B — Struktur-Extraktion (als Nachschlage-Referenz):**
Erst Markdown in eine Datei spiegeln, dann Struktur ziehen:
```text
pdf_markdown_read({"rel_path": "context/<datei>.pdf", "max_chars": 500000})
fs_write({"path": ".disco/context-extracts/<datei>.md", "text": "<markdown>"})
extract_markdown_structure({"path": ".disco/context-extracts/<datei>.md"})
```
Das Skelett (~5-15 KB) enthaelt alle Ueberschriften, Seitenzahlen,
Tabellen-Headern und Kontext-Saetze und wird am Ende der Summary-
Datei als **Kapitelverzeichnis** angehaengt.

Die Summary entsteht also aus:
1. Inhalt der ersten ~30 KB (Schritt A) → Zusammenfassung + Typ
2. Struktur-Skelett (Schritt B) → Kapitelverzeichnis + Seitenzahlen

**NIEMALS versuchen den Volltext komplett zu laden** — das sprengt
das Token-Limit und der Turn crasht. `pdf_markdown_read` nutzt
standardmaessig eine 50-KB-Kappung und setzt `truncated=true`, um
das zu verhindern.

#### Excel/CSV — Struktur + IMMER DB-Import bei Lookup-Tabellen

```text
xlsx_inspect({"path": "context/<datei>.xlsx"})
```

Wenn es eine Lookup-Tabelle ist (klare Spalten, strukturierte Daten):
- **Direkt importieren** (nicht nur vorschlagen), Zieltabelle
  `context_<sprechender_name>`.
- Pro Sheet einzeln importieren wenn die Sheets verschiedene
  Themen abdecken.
- Nach dem Import: `sqlite_query` mit `LIMIT 5` um dem Nutzer
  eine Stichprobe zu zeigen.

#### Markdown/TXT (< 50 KB)

```text
fs_read({"path": "context/<datei>.md"})
```

Komplett lesen, direkt zusammenfassen.

### 4. Zusammenfassung + Projektziel-Bezug schreiben — PFLICHT

**Dieser Schritt darf NICHT uebersprungen werden.** Pro Datei MUSS
eine Summary-Datei unter `.disco/context-summaries/` entstehen.
Ohne Summary hat die DI-Extraktion keinen Zweck.

```text
fs_write({"path": ".disco/context-summaries/<datei>.md", "content": "..."})
```

Die Summary basiert auf dem DI-Extrakt (nicht auf Vermutungen).
Disco schreibt sie **nach dem Lesen des Extrakts**, nicht vorher.

**Pflicht-Sektionen** (alle muessen vorhanden sein):

```markdown
# <Dateiname>

## Typ und Umfang
<norm / richtlinie / lookup-tabelle / referenzwerte / handbuch>
<Seitenzahl / Zeilenzahl / Sheet-Anzahl>

## Inhalt (Zusammenfassung)
<3-6 Saetze: Was steht KONKRET in der Datei? Keine Vermutungen —
nur was aus dem DI-Extrakt oder den Daten hervorgeht.>

## Schluessel-Kapitel / -Abschnitte
<KONKRETE Liste mit Seitenzahlen / Sheet-Namen aus dem Extrakt.
Nicht raten — nur auflisten was tatsaechlich gefunden wurde.>
Beispiel:
- S. 12-18: Begriffe und Definitionen
- S. 23-45: Dokumentenarten (DCC-Katalog)
- S. 67-120: Anhang A.2 (Systemzuordnung)
- Sheet "ET-LT-IT-KT": 49 Zeilen, DCC-Zuordnung pro System

## Projektziel-Bezug
<KONKRET: Wie hilft diese Datei beim Erreichen des Projektziels
aus README.md? Welche Kapitel/Tabellen werden fuer welchen
Meilenstein gebraucht? Gibt es Luecken?>

## Nachschlagen
<Konkrete Hinweise fuer Disco selbst in spaeteren Sessions:
"Bei Fragen zu DCC-Codes → Kapitel X, Seite Y."
"Fuer Bauteil-Zuordnung → Sheet Z, Spalte W."
"Um Seite 121-130 zu lesen: fs_read(path='.disco/context-extracts/datei.md', offset=<byte>, max_bytes=8000)">

## Kapitelverzeichnis (aus Struktur-Extraktion)
<Hier das Ergebnis von extract_markdown_structure einfuegen — das
komplette Skelett mit allen Ueberschriften und Seitenzahlen. Disco
nutzt das in spaeteren Sessions um gezielt per fs_read mit offset
in ein bestimmtes Kapitel zu springen.>
```

**Qualitaetspruefung:** Wenn eine Summary weniger als 10 Zeilen hat,
keine konkreten Seitenzahlen/Sheet-Namen enthaelt, oder kein
Kapitelverzeichnis am Ende hat (bei grossen Dateien), ist sie zu
duenn. Dann nochmal den Extrakt lesen und konkretisieren.

### 5. Manifest-Eintrag (kurz)

Pro Datei einen **kompakten** Eintrag in `context/_manifest.md`
anfuegen (append):

```markdown
---

### <dateiname>

- **Typ:** <klassifikation>
- **Umfang:** <Seiten / Zeilen / Sheets>
- **Zusammenfassung:** <1-2 Saetze>
- **Projektziel-Bezug:** <1 Satz>
- **Detail-Summary:** .disco/context-summaries/<datei>.md
- **DI-Extrakt:** .disco/context-extracts/<datei>.md (bei PDFs)
- **In DB:** <context_<name> (N Zeilen)> (bei Lookup-Tabellen)
- **Stand:** <YYYY-MM-DD>
```

### 6. Rueckmeldung an den Benutzer

Pro Datei **2-3 Zeilen** im Chat:

> **vgb-s-831.pdf** (287 S., ~2.87 EUR DI-Kosten)
> Dokumentationsstandard VGB S 831 (2015). Kern: DCC-Matrizen in
> A.3 (welche Dokumente pro Bauteiltyp), Systemzuordnung in A.2.
> → Direkt relevant fuer Dein Projekt-Ziel.

Am Ende:
> "Kontext ist analysiert. Bei der Arbeit werde ich gezielt in die
> Summaries schauen, wenn ich z.B. DCC-Codes nachschlagen muss.
> Bereit fuer Schritt 3 — Quellen laden?"

### 7. Offene Fragen an den Nutzer

Wenn Dir beim Analysieren etwas unklar ist:
- "In der Norm fehlt ein Kapitel zu Rohrleitungstechnik — brauchst
  Du das fuer dieses Projekt, oder nur Elektro/Bau?"
- "Die DCC-Liste hat 395 Codes, aber Dein Projektziel erwaehnt
  nur Elektro. Soll ich auf E*-Codes filtern?"

**Frag gezielt, nicht pauschal.** "Ist das so OK?" ist zu vage.

## Drei Artefakte pro Context-PDF

```
context/<datei>.pdf                      ← Original (unveraendert)
.disco/context-extracts/<datei>.md       ← DI-Markdown (Volltext)
.disco/context-summaries/<datei>.md      ← Agent-Zusammenfassung
context/_manifest.md                     ← Kurzeintrag
```

## Bei Session-Start: Summaries lesen, nicht Extracts

Beim project-onboarding liest Disco:
1. `context/_manifest.md` (kurz, immer)
2. `.disco/context-summaries/*.md` (mittel, bei Bedarf)

Die `.disco/context-extracts/*.md` sind **Rohdaten** (gross, potenziell
100+ Seiten Markdown). Die liest Disco nur bei gezieltem Nachschlagen,
nicht beim Onboarding.

## Was Du NICHT tun sollst

- **Kein ganzes DI-Extrakt in den Chat-Kontext laden** (zu gross,
  Token-Limit). Nur die Summary oder gezielte Ausschnitte per
  `fs_read` mit `max_bytes`.
- **Keine DI-Extraktion fuer Sources** (zu teuer bei 1000+ PDFs).
  DI ist fuer Context-PDFs (wenige, wichtig, einmalig).
- **Kein "Fertig" ohne tatsaechliche Analyse.** Der Manifest-Eintrag
  muss eine echte Zusammenfassung enthalten, nicht nur Dateiname+Groesse.
