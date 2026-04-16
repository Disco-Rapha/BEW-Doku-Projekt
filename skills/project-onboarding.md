---
name: project-onboarding
description: Disco betritt ein Projekt zum ersten Mal in einer Session — liest README/NOTES/memory ein, fasst zusammen wo wir stehen, fragt was heute zu tun ist.
when_to_use: Am Anfang jeder neuen Chat-Session in einem Projekt. Wenn Du nicht weißt, was im Projekt schon getan wurde, oder wenn der Benutzer „erinnerst Du dich noch?" fragt.
---

# Skill: project-onboarding

Wenn Du in eine neue Chat-Session in einem Projekt kommst, weißt Du
zunächst nichts. Diese Routine bringt Dich auf Stand. Sie ist **kurz**
und **strukturiert**, damit der Benutzer nicht warten muss.

## Verbindlicher Workflow

Sobald Du erkennst, dass eine Session frisch ist (kein vorheriger Chat-
Verlauf in diesem Thread, oder der Benutzer fragt explizit nach Stand):

### 1. Projekt-Wurzel auflisten

```text
fs_list({"path": ""})
```

Damit weißt Du, welche Standard-Verzeichnisse befüllt sind und welche
Dateien im Projekt-Root liegen.

### 2. README.md lesen (User-Beschreibung)

```text
fs_read({"path": "README.md"})
```

Das ist der Kontext-Text, den der Benutzer selbst gepflegt hat:
Worum geht das Projekt überhaupt, welche Frist, welcher Auftraggeber.

### 3. NOTES.md lesen (chronologisches Logbuch)

```text
fs_read({"path": "NOTES.md", "max_bytes": 30000})
```

Das ist Dein eigenes Logbuch aus früheren Sessions: was wurde getan,
was kam raus, was war noch offen. Lies die letzten 1–2 Einträge.

### 4. .disco/memory.md lesen (Faustregeln)

```text
fs_read({"path": ".disco/memory.md"})
```

Dauerhafte Erkenntnisse: Konventionen, Vorlieben des Benutzers,
Schlüssel-Erkenntnisse zu den Daten. Immer komplett lesen.

### 5. Aktive Pläne prüfen (optional)

```text
fs_list({"path": ".disco/plans"})
```

Falls da Dateien liegen: kurz reinschauen, ob ein offener Plan auf
Fortsetzung wartet.

### 6. Projekt-DB-Status (optional, wenn relevant)

Wenn das Projekt schon Datenarbeit gesehen hat, ein kurzer SQL-Check:

```text
sqlite_query({"sql": "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'work_%' OR name LIKE 'agent_%' ORDER BY name"})
```

Damit siehst Du auf einen Blick, welche Arbeits-Tabellen bereits
existieren.

## Antwort an den Benutzer

Halte die Antwort **kurz** (max. 8 Zeilen):

1. **Eine Zeile** zum Projekt-Kontext (aus README)
2. **Eine Zeile** zum letzten Stand (aus NOTES letzter Eintrag)
3. **Eine Zeile** zu Konventionen oder Faustregeln, die heute relevant sind
4. **Eine Zeile** zu offenen Plänen (wenn vorhanden)
5. **Frage** an den Benutzer: "Womit starten wir heute?"

Beispiel:

> Wir sind im Projekt **Vattenfall Reuter** (Lagerhalle Reuter,
> SOLL/IST nach VGB S 831, Frist 18.05.2026).
> Letzter Stand: IBL-Prototyp mit 72 Einträgen erstellt, Excel-Export
> nach `exports/` lief.
> Faustregel: Du nutzt für Hersteller-Zuordnung den BEW-Standard-
> Dokumentensatz, nicht VGB-T-Marker.
> Offen: Bauwerk-Komponenten BW-001 bis BW-018 sind noch nicht in
> die IBL übernommen.
>
> Womit starten wir heute?

## Wann das Onboarding NICHT laufen muss

- Wenn der Benutzer sofort eine konkrete Aufgabe stellt, ohne nach Stand
  zu fragen — dann arbeite los, das Onboarding schiebst Du in den Hintergrund.
- Wenn Du im selben Thread schon Tool-Calls gemacht hast — dann hast Du
  den Kontext.

## Wann das Onboarding ZWINGEND laufen muss

- Wenn der Benutzer fragt: "Wo waren wir?" / "Was haben wir hier letztes Mal gemacht?"
- Wenn Dein letzter Eintrag in NOTES.md älter als 7 Tage ist — dann
  könntest Du den Kontext "vergessen" haben.

## NOTES.md fortführen am Session-Ende

Wenn der Benutzer sagt "danke, das war's" oder die Session endet, **bevor**
Du Dich verabschiedest:

```text
project_notes_append({
  "project_id": <id>,
  "section_title": "<datum> – <kurzes Thema>",
  "content": "<3–6 Zeilen: was wurde gemacht, was ist das Ergebnis, was ist offen>"
})
```

Wenn der Benutzer das nicht explizit will, frag einmal kurz:
"Soll ich den Stand noch in NOTES festhalten?"
