# Report-Builder — Skript-Skelett für `build_<slug>.py`

**Stand 2026-05-08.** Vollständiges Beispiel-Skelett, das der Skill
[`report-builder`](../skills/report-builder.md) referenziert. Bei einem
neuen HTML-Report (kein bestehender Report im Projekt zur Wiederver-
wendung): dieses Skelett kopieren und an Slug + Daten anpassen.

> Holen mit `fs_read("docs/report-builder-template.md", section="Skript-Skelett")`.

## Datei-Konventionen

- **Liest** aus `workspace.db` (`ds.*` für Provenance/Content,
  lokal für Reasoning). Kein `fs_read` auf PDFs — Inhalt kommt aus
  `ds.agent_doc_markdown`.
- **Schreibt** genau eine Datei: `report.html` neben sich selbst.
- **Stdout** ist für Status (*„Rendered report.html (23 KB,
  4 Sektionen, 12 Quellen-Anker)"*) — nicht für Content.
- **Idempotent** — wiederholter Lauf mit gleichen DB-Daten liefert
  byte-identisches HTML (keine Zeitstempel inline, außer im Titel).

## Skript-Skelett

```python
#!/usr/bin/env python3
"""IBL SOLL/IST-Abgleich — HTML-Report.

Liest: agent_ibl_positions (SOLL), ds.agent_sources (IST), Zuordnungs-Logik.
Schreibt: report.html (Single-File, inline CSS/JS).
"""
from __future__ import annotations
import html
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
kpi_total    = q("SELECT COUNT(*) c FROM agent_ibl_positions")[0]["c"]
kpi_erfuellt = q("SELECT COUNT(*) c FROM agent_ibl_positions WHERE status='erfuellt'")[0]["c"]
gaps = q("""
  SELECT p.ibl_id, p.titel, p.gewerk, p.verantwortlich
  FROM agent_ibl_positions p
  WHERE p.status != 'erfuellt'
  ORDER BY p.gewerk, p.ibl_id
""")

# --- Rendering ---
def section_sources() -> str:
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
      <p>Pattern-Matching über <code>ibl_id</code> im Dokumentnamen.
         Bei Mehrfach-Treffern wird die neueste Version gezählt.</p>
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
      f"{kpi_total} Positionen, {len(gaps)} Lücken)")
```

## CSS-Baseline-Erläuterung

Die Style-Block-Basis ist bewusst schlicht und mit
projekttypischen Werten: serifenlose System-Schrift, max-width
1080px, KPI-Kacheln in Flexbox, dezente Border-Farben. Wenn ein
Projekt einen einheitlichen Look hat, übernimmst Du den CSS-Block
1:1 von einem bestehenden Report im selben Projekt — Konsistenz
über Reports hinweg ist wichtiger als individuelle CSS-Akrobatik.
