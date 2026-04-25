---
name: report-builder
description: HTML-Reports zum Weitergeben bauen — Single-File-Output, klickbare Quellen, wiederverwendbarer Bauplan im Projekt.
when_to_use: "HTML-Report", "Report bauen", "Auswertung als HTML", "Report zum Weitergeben", "SOLL/IST-Report (HTML)", "IBL-Report", "Management-Report". Fuer formatierte Excel-Exports → stattdessen `excel-reporter`.
---

# Skill: report-builder

**Fuer lesbare HTML-Reports**, die der Nutzer im Browser oeffnet und per Mail
weitergibt. Kein Excel, kein Dashboard, kein Live-System. Ein einziger
`.html`-Snapshot pro Report-Run, mit klickbaren Quellen und einer Sources-
Sektion am Ende.

**Fuer formatierte Tabellen-Exports** (AutoFilter, Status-Farben, Hyperlinks
zwischen Sheets) → stattdessen Skill `excel-reporter`.

## Eiserne Regeln

1. **Single-File-HTML.** CSS, JS, Daten — alles **inline** in einer
   `.html`-Datei. Der Nutzer soll sie per Doppelklick oeffnen oder als
   Mail-Anhang versenden koennen, ohne Server, ohne externe Assets.
2. **Python-Skript baut das HTML, nicht Du im Chat.** Du schreibst ein
   `build_<slug>.py`, `run_python` fuehrt es aus. Nur so bleibt der
   Bauplan reproduzierbar und klein im Chat-Kontext.
3. **Wiederverwendung zuerst.** Vor dem Schreiben eines neuen Skripts
   schaust Du in `exports/reports/`, ob es einen aehnlichen Report schon
   gibt. Wenn ja: Skript kopieren, Queries + Texte anpassen — nicht bei
   Null anfangen. So bleibt der Look ueber Zeit einheitlich.
4. **Traceability ist nicht optional.** Jeder Report endet mit einer
   "Quellen & Methodik"-Sektion. Jede **wesentliche Aussage** (KPI-Zahl,
   Narrative mit konkreten Dokumentennennungen) hat einen klickbaren
   Anker auf ihre Quelle.
5. **Tool-Result = Wahrheit.** "Fertig" meldest Du erst, wenn `run_python`
   mit `exit_code == 0` zurueckkommt und der HTML-Pfad real existiert.

## Pfad-Konvention

```
<projekt>/exports/reports/<slug>/
  build_<slug>.py       ← das Bau-Skript (der "Bauplan")
  report.html           ← letztes Ergebnis (wird ueberschrieben)
  data/                 ← optional: generierte Zwischendaten
```

**Slug-Naming:** `<thema>-<variante>`, keine Datumsstempel im Slug.
Beispiele: `ibl-soll-ist`, `dcc-verteilung`, `dokumenten-lieferstatus`.
Datum + Version stehen **im Report-Inhalt** (Titelzeile), nicht im Pfad.

**Kein Ueberschreiben der alten Version?** Vor dem Lauf `report.html`
nach `v<N>/report.html` kopieren (via `fs_*`). Default ist ueberschreiben —
die Reproduzierbarkeit liegt im Skript, nicht in Snapshots.

## Die drei Phasen

| Phase | Wer treibt | Was passiert |
|---|---|---|
| 1. Auftrag | Du + Nutzer | Ziel, Daten, Kernaussagen, Zielpublikum klaeren |
| 2. Bau | Du (Nutzer review) | Skript schreiben (Vorlage kopieren wenn moeglich), iterieren |
| 3. Abnahme | Du + Nutzer | HTML im Browser sichten, Traceability pruefen |

## Phase 1 — Auftrag klaeren

Bevor Du ein Skript schreibst, **frag gezielt** — nicht offen. Die vier
Fragen, die jeder Report beantworten muss:

1. **Worueber?** Ein Satz: "SOLL/IST-Abgleich der gelieferten Dokumentation
   gegen die IBL". Wenn der Nutzer schwammig antwortet ("Status-Report"):
   konkret nachbohren — welchen Status, welche Daten, fuer wen.
2. **Welche Daten?** Welche Tabellen in `workspace.db` / `ds.*`, welche
   Dateien in `sources/` oder `context/`, welche Filter. Wenn die Daten
   noch nicht importiert sind: **erst importieren**, dann Report.
3. **Welche Kernaussagen?** 3-5 Dinge, die der Report **muss** zeigen.
   Beispiel IBL-SOLL-IST:
   - "Erfuellungsgrad gesamt (X %, Y von Z Positionen geliefert)"
   - "Offene Positionen nach Gewerk"
   - "Zu spaete / ueberfaellige Lieferungen"
   - "Top-Luecken mit Verantwortlichen"
4. **Zielpublikum.** Management (Executive-Summary oben, Zahlen gross,
   wenig Technik) vs. Fach (Tabellen, konkrete Dokumentennummern)? Das
   bestimmt Text-Ton + Detail-Tiefe.

**Frage-Beispiel:**

> "Bevor ich das Skript schreibe, vier Punkte:
> 1. Geht's um den IBL-Abgleich (SOLL aus IBL-Excel gegen IST aus
>    `agent_sources`)?
> 2. Welche IBL-Quelle — Liegt sie schon als Tabelle in `workspace.db`,
>    oder muss ich erst importieren?
> 3. Welche Kernaussagen sollen oben stehen? Mein Vorschlag:
>    Erfuellungsgrad, Offene nach Gewerk, Top-10-Luecken.
> 4. Ziel: zum Weitergeben an AG (formaler Ton) oder projektintern
>    (lockerer, mehr Details)?"

## Phase 2 — Bau

### 2.1 Wiederverwendung pruefen

```text
fs_list({"path": "exports/reports"})
```

Wenn bereits ein Ordner existiert, dessen Slug thematisch passt: lies
dessen `build_*.py` und prueft, ob die Struktur uebernehmbar ist.

```text
fs_read({"path": "exports/reports/<alter-slug>/build_<alter-slug>.py"})
```

Dann schlaegst Du dem Nutzer vor:
> "Es gibt schon `dcc-verteilung` mit aehnlicher Struktur — ich kopier
> das Skript, pass Queries + Texte an, Look bleibt gleich. Ok?"

Wenn **nichts Passendes** da ist: neuer Report, von vorne. Das ist der
erste Fall — Dein Skript wird dann Vorlage fuer spaetere Reports.

### 2.2 Slug festlegen + Ordner anlegen

```text
fs_mkdir({"path": "exports/reports/<slug>"})
```

### 2.3 Skript schreiben

Konventionen fuer `build_<slug>.py`:

- **Liest** aus `workspace.db` (`ds.*` fuer Ebene 1/2, lokal fuer Ebene 3).
  Kein `fs_read` auf PDFs — Inhalt kommt aus `ds.agent_pdf_markdown`.
- **Schreibt** genau eine Datei: `report.html` neben sich selbst.
- **Stdout** ist fuer Status ("Rendered report.html (23 KB, 4 Sektionen,
  12 Quellen-Anker)") — nicht fuer Content.
- **Idempotent** — wiederholter Lauf mit gleichen DB-Daten liefert
  byte-identisches HTML (keine Zeitstempel inline, ausser im Titel).

Minimales Skelett, das Du als **Baseline** nimmst, wenn keine Vorlage da
ist — CSS bewusst schlicht, wird bei Wiederverwendung weitergereicht:

```python
#!/usr/bin/env python3
"""IBL SOLL/IST-Abgleich — HTML-Report.

Liest: agent_ibl_positions (SOLL), ds.agent_sources (IST), Zuordnungs-Logik.
Schreibt: report.html (Single-File, inline CSS/JS).
"""
from __future__ import annotations
import html
import json
import sqlite3
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT.parent.parent.parent / "workspace.db"  # anpassen
OUT = ROOT / "report.html"

def q(sql: str, params: tuple = ()) -> list[dict]:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows

def esc(s) -> str:
    return html.escape("" if s is None else str(s))

# --- Daten laden ---
kpi_total   = q("SELECT COUNT(*) c FROM agent_ibl_positions")[0]["c"]
kpi_erfuellt = q("SELECT COUNT(*) c FROM agent_ibl_positions WHERE status='erfuellt'")[0]["c"]
gaps = q("""
  SELECT p.ibl_id, p.titel, p.gewerk, p.verantwortlich
  FROM agent_ibl_positions p
  WHERE p.status != 'erfuellt'
  ORDER BY p.gewerk, p.ibl_id
""")

# --- Rendering ---
def section_sources() -> str:
    # Pflicht-Sektion: welche Daten, welche Filter, welche Dokumente
    return f"""
    <section id="quellen">
      <h2>Quellen &amp; Methodik</h2>
      <h3>Datenquellen</h3>
      <ul>
        <li><b>IBL</b>: <code>agent_ibl_positions</code> ({kpi_total} Positionen,
            Import aus <code>sources/_meta/IBL_2026.xlsx</code>)</li>
        <li><b>Gelieferte Dokumente</b>: <code>ds.agent_sources</code>
            (Scope: aktive, nicht dupliziert)</li>
      </ul>
      <h3>Zuordnung IBL ↔ Dokument</h3>
      <p>Pattern-Matching ueber <code>ibl_id</code> im Dokumentnamen.
         Bei Mehrfach-Treffern wird die neueste Version gezaehlt.</p>
      <h3>Queries (wesentlich)</h3>
      <details><summary>Erfuellungsgrad</summary>
        <pre>SELECT COUNT(*) FROM agent_ibl_positions WHERE status='erfuellt'</pre>
      </details>
      <details><summary>Offene Positionen</summary>
        <pre>SELECT * FROM agent_ibl_positions WHERE status!='erfuellt' ORDER BY gewerk, ibl_id</pre>
      </details>
    </section>
    """

def gap_rows() -> str:
    out = []
    for g in gaps:
        # Pattern-Match auf Beispiel-Dokument fuer Deep-Link (wenn vorhanden)
        out.append(f"""<tr>
          <td>{esc(g['ibl_id'])}</td>
          <td>{esc(g['titel'])}</td>
          <td>{esc(g['gewerk'])}</td>
          <td>{esc(g['verantwortlich'])}</td>
        </tr>""")
    return "\n".join(out)

erfuellungsgrad = round(100 * kpi_erfuellt / max(kpi_total, 1), 1)

html_out = f"""<!doctype html>
<html lang="de"><head>
<meta charset="utf-8">
<title>IBL SOLL/IST — {date.today().isoformat()}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          max-width: 1080px; margin: 0 auto; padding: 24px 32px;
          color: #222; line-height: 1.55; }}
  h1 {{ font-size: 1.8em; margin: 0 0 4px 0; }}
  h2 {{ font-size: 1.3em; margin-top: 2em; border-bottom: 1px solid #eee;
        padding-bottom: 4px; }}
  h3 {{ font-size: 1.05em; margin-top: 1.3em; color: #333; }}
  .subtitle {{ color: #666; margin-bottom: 1.5em; }}
  .kpis {{ display: flex; gap: 16px; margin: 1em 0 1.5em; flex-wrap: wrap; }}
  .kpi {{ flex: 1; min-width: 180px; padding: 14px 18px; border: 1px solid #e4e4e4;
          border-radius: 6px; background: #fafafa; }}
  .kpi .val {{ font-size: 1.8em; font-weight: 600; }}
  .kpi .lbl {{ font-size: 0.85em; color: #666; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.92em; margin: 8px 0; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left;
            vertical-align: top; }}
  th {{ background: #f5f5f5; }}
  a {{ color: #2563eb; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  details summary {{ cursor: pointer; color: #444; }}
  details pre {{ background: #f7f7f7; padding: 8px; border-radius: 4px;
                 font-size: 0.85em; overflow-x: auto; }}
  footer {{ margin-top: 3em; padding-top: 12px; border-top: 1px solid #eee;
            color: #888; font-size: 0.85em; }}
</style>
</head><body>

<h1>IBL SOLL/IST-Abgleich</h1>
<div class="subtitle">Stand {date.today().isoformat()} &middot;
  <a href="#quellen">Quellen &amp; Methodik</a></div>

<div class="kpis">
  <div class="kpi"><div class="val">{kpi_total}</div>
    <div class="lbl">IBL-Positionen gesamt</div></div>
  <div class="kpi"><div class="val">{kpi_erfuellt}</div>
    <div class="lbl">Erfuellt</div></div>
  <div class="kpi"><div class="val">{erfuellungsgrad} %</div>
    <div class="lbl">Erfuellungsgrad</div></div>
</div>

<section id="offen">
  <h2>Offene Positionen</h2>
  <p>{len(gaps)} Positionen sind aktuell nicht erfuellt
     (<a href="#quellen">Queries siehe Quellen</a>).</p>
  <table>
    <thead><tr><th>IBL-ID</th><th>Titel</th><th>Gewerk</th><th>Verantwortlich</th></tr></thead>
    <tbody>{gap_rows()}</tbody>
  </table>
</section>

{section_sources()}

<footer>
  Gebaut mit <code>build_ibl-soll-ist.py</code> aus
  <code>exports/reports/ibl-soll-ist/</code>.
</footer>

</body></html>"""

OUT.write_text(html_out, encoding="utf-8")
print(f"Rendered {OUT.name} ({OUT.stat().st_size // 1024} KB, "
      f"{kpi_total} Positionen, {len(gaps)} Luecken)")
```

### 2.4 Ausfuehren + iterieren

```text
run_python({"path": "exports/reports/<slug>/build_<slug>.py"})
```

Bei Fehler: stderr lesen, Skript fixen, erneut starten. Bei Erfolg:
HTML-Pfad dem Nutzer nennen und um Sichtprobe bitten.

## Phase 3 — Abnahme

1. HTML im Browser oeffnen lassen:
   > "Oeffne den Report: `open exports/reports/<slug>/report.html`"
2. Drei Dinge gezielt abfragen:
   - Stimmen die KPIs? (Plausibilitaet)
   - Sind die **wesentlichen Aussagen** belegt? Klick in die Sources-
     Sektion — fuehren die Verweise zu echten Quellen?
   - Fehlt was? Braucht's eine Sektion, die nicht drin ist?
3. Nach Korrekturen: Skript anpassen, erneut rendern. HTML wird
   ueberschrieben.

## Traceability — die vier Faustregeln

1. **Jede Zahl in einer KPI-Kachel** → Quellen-Anker (welche Query, wieviele
   Zeilen zugrundeliegen). Wenn 3 KPIs aus derselben Query kommen: ein
   gemeinsamer Anker reicht.
2. **Jede Narrative-Aussage, die konkrete Dokumente nennt** → Deep-Link
   auf das Dokument (relativ zum Projekt-Root). Bei PDF-Seiten:
   `sources/pdf/xyz.pdf#page=12` (funktioniert in Chrome/Safari/Edge).
3. **Detail-Tabellen mit >20 Zeilen** → kein Pflicht-Link pro Zeile, aber
   ein **Aggregat-Verweis** in der Sources-Sektion: "Grundlage: Query X
   mit N Zeilen aus Tabelle Y". Bei 3000 Dokumenten: die Anzahl + der
   Filter ist die Quelle, nicht 3000 einzelne Links.
4. **Executive Summary** → jede Aussage hat mindestens einen
   Drilldown-Anker **in den Report selbst** (z.B. `<a href="#offen">`).

**Nicht** linken:
- Jede Tabellenzeile in einer Detail-Tabelle einzeln. Das ist Laerm.
- Interne Reasoning-Schritte. Der Nutzer will die **Quelle**, nicht den
  Gedankengang.

## Quellen-Sektion (Pflicht-Aufbau)

Jeder Report hat am Ende `<section id="quellen">` mit genau drei
Unterabschnitten:

1. **Datenquellen** — welche Tabellen/Dateien, Zeilenanzahlen,
   Import-Zeitpunkt wenn relevant.
2. **Zuordnung / Methodik** — wie wurden Relationen gebaut
   (Pattern-Matching, Joins, Filter). Ein Absatz reicht.
3. **Queries** — die wesentlichen SQL-Snippets als kollabierbare
   `<details>`-Bloecke (nicht alle Queries, nur die, auf die KPIs oder
   Narrative direkt verweisen).

## Was Du NICHT machst

- **Kein Markdown-Report** als Endprodukt. Der Nutzer will HTML zum
  Anschauen + Weitergeben, kein `.md` das er erst rendern muss.
- **Keine externen Assets** (CDN-CSS, externe JS-Libraries, Images
  ueber HTTP). Einzige Ausnahme: wenn fuer eine Diagramm-Bibliothek
  zwingend erforderlich — dann *bewusst* entscheiden und kommentieren.
  Im Zweifel: SVG inline, keine CDN.
- **Keine generierten Datenzeilen mit 3000+ Eintraegen im HTML.** Das
  blaeht die Datei. Fuer grosse Listen: Top-N plus Aggregat-Verweis,
  oder CSV-Datei daneben legen (`data.csv` im gleichen Ordner) und im
  Report verlinken.
- **Kein "Fertig"** ohne erfolgreichen `run_python`-Exit und existierende
  `report.html`.
- **Keine Datumsstempel im Slug** oder im Dateinamen. Datum steht im
  Titel + in Sources. Der Slug ist der **Plan-Name**, nicht der
  Run-Name.
- **Kein `build_xlsx_from_tables`-Aufruf von hier aus.** Wenn der Nutzer
  am Ende noch Excel will: getrennt, ueber `excel-reporter`.

## Groessenordnungen

Typische Reports:
- **Klein** (1-5 KPIs, 1 Detail-Tabelle <200 Zeilen, 1 Narrative-Absatz):
  50-150 KB HTML. Baut in <5 s.
- **Mittel** (5-10 KPIs, 3-5 Tabellen, mehrere Sektionen, inline SVG-
  Charts): 200-800 KB. Baut in <15 s.
- **Gross** (>500 KB HTML): kritisch pruefen, ob Detail-Tabellen wirklich
  in den Report gehoeren, oder ob ein CSV-Anhang besser waere.
