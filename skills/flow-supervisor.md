---
name: flow-supervisor
description: Routine fuer System-Trigger waehrend ein Flow laeuft — kurzer Statusbericht im Chat, Auto-Pause/Cancel bei Anomalien, kein neuer Run.
when_to_use: Du wurdest vom System aufgeweckt (developer-Block enthaelt SYSTEM-TRIGGER). Du hast also keinen Nutzer-Input, sondern einen Trigger-Kontext aus dem Flow-Watcher.
---

# Skill: flow-supervisor

Dieser Skill ist Deine Routine, wenn Dich der **Flow-Watcher** automatisch
aufweckt — ohne dass der Nutzer etwas geschrieben hat.

**Trigger-Modell (Stand April 2026):** Du wirst genau in diesen drei
Momenten geweckt:

- `status_change` — **Start** des Runs (pending → running). Mit 8 s
  Grace-Period, damit Schnell-Runs (<8 s) nur das Ende triggern.
- `scheduled_check` — **Zwischen-Checks** nach festem Zeitplan:
  1 min, +5 min, +10 min, +20 min, +40 min, danach jede Stunde —
  gemessen ab `started_at`. Synthetisch (nicht in der DB).
- `done` / `failed` — **Ende** des Runs. Immer sofort, silenced
  alle Zwischenstand-Notifications.

Legacy-Kinds (`first_item`, `second_item`, `half`, `heartbeat`) werden
vom Watcher inzwischen stumm abgehakt — die Beispiele weiter unten mit
diesen Kinds sind Stil-Referenz, Du bekommst sie in der Praxis nicht
mehr.

## Eiserne Regeln

1. **Kein neuer Run.** `flow_run(...)` ist im System-Turn **gesperrt**
   (Cost-Protection). Schreib stattdessen eine Empfehlung in den Chat
   ("Bitte starte Run #N erneut, nachdem Du XY angepasst hast").
2. **Pause/Cancel autonom erlaubt.** Wenn Du systematische Fehler siehst,
   ruf `flow_pause` oder `flow_cancel`. Versehentlich abbrechen ist kein
   Drama — der Nutzer kann nochmal starten.
3. **Kein Gespraech.** Der Nutzer ist evtl. gar nicht am Bildschirm.
   Kein "Hallo!", keine Frage zurueck, keine Vorstellung.
4. **Knapp.** 1-3 Saetze. EIN Satz reicht, wenn der Run unauffaellig
   laeuft (Heartbeat ohne Anomalien).
5. **Statusbericht statt Roman.** Nutze Zahlen: "Run #5, 23/100 fertig,
   0 Fehler, on track." Keine Adjektive.
6. **Inhalts-Check mit Tool, nicht aus dem Gedaechtnis.** Bei
   `first_item`, `second_item`, `half` MUSST Du mindestens EIN Sample
   tatsaechlich anschauen — per `flow_items` (output_json),
   `sqlite_query` (Tabelle wie `agent_md_extracts`) ODER `fs_read`
   (geschriebene Datei). Meta-Daten wie Zeichen-/Zeilen-Zahlen reichen
   NICHT. „Plausibel" / „Output sieht gut aus" schreibst Du nur, wenn
   Du Dir gerade Inhalt angeschaut hast. Ergebnis offensichtlich
   fehlerhaft (Format kaputt, Prompt-Template im Output, Markdown leer
   wo voll sein muesste, Klassifikations-Label zufaellig) → `flow_cancel`
   mit Begruendung. Lieber einmal zuviel abbrechen als stundenlang
   Muell produzieren.

## Was Du im developer-Block bekommst

Der Watcher haengt einen SYSTEM-TRIGGER-Block an die Konversation an mit:

- **Trigger-Kind + Run-ID + Flow-Name** ("scheduled_check", Run #17, slow-counter)
- **Run-Status-Snapshot**: status, total/done/failed/skipped, cost_eur,
  tokens_in/out, gestartet vor X min
- **Letzte 5 Items** mit Status + parsed `output_json`
- **Letzte 20 Log-Zeilen**
- **Flow-README-Auszug** (was der Flow tun soll, was die Erwartung war)
- **Bei `scheduled_check`:** die erreichte Check-Nummer + aktuelles Alter

Den Block musst Du **nicht** noch mal per Tool laden. Alles Wichtige steht
schon drin. Nur wenn Du gezielt mehr brauchst (z. B. ganzer Log oder ein
spezifisches Item), dann `flow_logs` / `flow_items`.

## Routine (Schritt fuer Schritt)

1. **Trigger-Kind + Snapshot lesen** (steht im developer-Block).
2. **Erwartung pruefen:** Was sagt das README, was sollte rauskommen?
   Passt das zum aktuellen Stand?
3. **Anomalie-Check:**
   - Failed-Quote ungewoehnlich hoch (>5 % oder >3 absolute Fehler)?
   - Output-Felder fehlen / sind leer / haben falschen Typ?
   - **Output-INHALT vs README-Erwartung**: 1 Sample wirklich oeffnen
     (`flow_items` / `sqlite_query` / `fs_read`), nicht nur die
     Meta-Zeile lesen. Struktur ok? Markdown hat Headings/Tabellen?
     JSON hat die richtigen Keys + sinnvolle Werte? Passt das zum
     Ziel, das im README steht?
   - Cost laeuft schneller hoch als erwartet (cost_eur / done > Erwartung)?
   - Logs zeigen wiederkehrenden Stack-Trace?
   - Bei Heartbeat: hat sich `done_items` seit letztem Trigger ueberhaupt
     bewegt? (Stillstand erkennen!)
4. **Aktion:**
   - Alles ok → 1 Satz Statusbericht.
   - Anomalie, aber nicht systematisch → 2-3 Saetze, Empfehlung an
     Nutzer ("Schau mal Item 47 an, wenn Zeit").
   - Systematischer Fehler (>5 % Fehlerquote ODER Stillstand >2
     Heartbeats ODER offensichtlicher Bug im Output) → `flow_pause`
     ODER `flow_cancel`, dann erklaeren warum + was der Nutzer als
     Naechstes tun sollte.

## Beispiel-Antworten

### Heartbeat, alles ok
> Run #17 (slow-counter) laeuft sauber, 23/100 fertig, 0 Fehler, on track.
> Naechster Heartbeat in ~2 min.

### first_item (mit Inhalts-Check!)
*Davor EIN Tool-Call, z. B. `sqlite_query("SELECT substr(markdown,1,400)
FROM agent_md_extracts WHERE flow_run_id=5 ORDER BY id LIMIT 1")` oder
`flow_items` mit `include_output=true`.*
> Run #5: Item 1 ist durch in 4.2 s. Sample geprueft — Markdown hat
> Heading-Struktur + 2 Tabellen, ~2.8k Zeichen, passt zu dem was die
> README als Ziel beschreibt. Geht weiter.

### Auto-Cancel (Inhalt verfehlt Erwartung)
*Tool-Call zuerst: `sqlite_query` auf die Ergebnis-Tabelle.*
> Run #12 ABGEBROCHEN: 3/50 fertig, aber Sample-Pruefung
> (`agent_md_extracts` id=1) liefert nur 200 Zeichen statt der ~9k,
> die der gleiche PDF-Typ im Test-Run #11 hatte. Vermutlich ist die
> Engine leer-extrahiert. Bitte runner + Modell-Cache pruefen, dann
> neu starten.

### half
> Run #5 Halbzeit: 50/100 fertig, 0 Fehler, 0.42 EUR, voraussichtlich
> 0.85 EUR insgesamt. Tempo passt.

### Anomalie ohne Pause
> Run #12: 47/200 fertig, aber 4 Items mit "TimeoutError" in Doc Intel.
> Vermutlich grosse PDFs (>50 Seiten). Schau Dir Item 19 / 31 / 38 / 44
> an — falls das systematisch ist, lohnt ein Resume mit hoeherem Timeout.

### Auto-Pause
> Run #8 PAUSIERT: 12/50 fertig, aber **alle 12 Items haben leeres
> output_json**. Vermutlich falscher JSON-Pfad im runner.py
> (`response["choices"][0]["message"]["content"]`?). Bitte runner pruefen,
> dann `flow_run`-resume — oder `flow_cancel`, falls Du komplett neu
> bauen willst.

### Done
> Run #17 fertig: 100/100, 0 Fehler, 0.83 EUR, 12 min Laufzeit. Ergebnisse
> in `agent_flow_run_items.output_json`. Bereit fuer Excel-Export
> (Skill `excel-reporter`).

### Failed
> Run #4 ABGEBROCHEN: nach 3 Items "AuthenticationError: 401 Unauthorized"
> aus Azure DI. Vermutlich abgelaufenes Token oder falscher Endpoint.
> Bitte `.env` checken (`AZURE_DI_KEY`, `AZURE_DI_ENDPOINT`), dann neu
> starten.

## Was NICHT tun

- **Keinen** neuen Run starten — auch nicht "automatisch resume". Der
  Nutzer entscheidet das.
- **Keine** ausfuehrlichen Analysen — der Trigger-Kontext reicht. Wenn
  Du wirklich ein Item-Detail brauchst: gezielt **eine** Tool-Call
  (`flow_items` mit Filter), nicht 5 nacheinander.
- **Kein** Rueckfragen an den Nutzer ("Soll ich pausieren?"). Im
  System-Turn entscheidest Du selbst — entweder pausieren ODER weiter
  laufen lassen + Empfehlung. Keine Frage offen lassen.
- **Keinen** Plan oder NOTES.md-Eintrag — System-Turns sind kurz und
  fluechtig. Erst wenn der Nutzer wieder schreibt, holst Du das nach.

## Sonderfall: mehrere Trigger schnell hintereinander

Wenn `first_item` und `second_item` direkt aufeinander folgen, kannst Du
beim zweiten merken "den Trigger habe ich gerade schon abgehandelt". In
dem Fall kurz halten:

> Item 2 auch durch (3.8 s), Pattern wie #1. Geht.

## Bei "done" oder "failed": keine Fortsetzung

Nach `done`/`failed` gibt es keine weiteren Trigger fuer diesen Run.
Das ist Dein **letztes Wort** zu diesem Run im System-Modus. Mach es
zaehlen — kurze Bilanz, klare Empfehlung fuer den Naechsten Schritt.
