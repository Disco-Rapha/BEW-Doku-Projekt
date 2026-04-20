"""Disco-Workspace: Projekt-Lifecycle (Init, List, Show, Delete).

Ein Projekt im Disco-Workspace ist ein Verzeichnis unter
`<workspace>/projects/<slug>/` mit einer festen Struktur:

    <slug>/
    ├── README.md          ← Der Nutzer pflegt: Projekt-Briefing (Ziel,
    │                        Auftraggeber, Frist, Ansprechpartner)
    ├── NOTES.md           ← Disco fuehrt chronologisch fort (append-only)
    ├── DISCO.md           ← Discos destilliertes Arbeitsgedaechtnis
    │                        (Konventionen, Tabellen, Lookups, Entscheidungen)
    ├── sources/           ← Arbeitsdokumente (zu bearbeitendes Material)
    ├── context/           ← Arbeitsgrundlagen (Normen, Kataloge, Richtlinien)
    │   └── _manifest.md   ← Agent-gepflegte Uebersicht aller Kontext-Dateien
    ├── work/              ← Discos Arbeitsraum (Skripte, Zwischenstaende)
    ├── exports/           ← Endprodukte (nicht ueberschreiben)
    ├── data.db            ← Projekt-DB (work_*/agent_*/context_*-Tabellen)
    └── .disco/            ← Internes (Plaene, Sessions, Extrakte, Summaries)
        ├── plans/
        ├── sessions/
        ├── context-extracts/
        ├── context-summaries/
        └── local-skills/

Parallel wird ein Eintrag in der zentralen `projects`-Tabelle der
system.db angelegt, damit das Projekt im UI/CLI auftaucht.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import settings
from .db import connect


# ---------------------------------------------------------------------------
# Slug-Konvention (analog zu functions/notes.py, aber strikter)
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
_SLUGIFY_NONALNUM = re.compile(r"[^a-z0-9]+")
_SLUGIFY_DASHES = re.compile(r"-{2,}")


def slugify(name: str) -> str:
    """Wandelt einen Namen in einen sauberen Slug.

    'Anlage Musterstadt'   -> 'anlage-musterstadt'
    'KKW: Block 09 (Süd)' -> 'kkw-block-09-sued'
    """
    s = (name or "").strip().lower()
    s = (s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
         .replace("ß", "ss"))
    s = _SLUGIFY_NONALNUM.sub("-", s)
    s = _SLUGIFY_DASHES.sub("-", s)
    s = s.strip("-")
    return s or "unnamed"


def validate_slug(slug: str) -> str:
    """Validiert einen Slug strikt. Wirft ValueError bei Verstoss."""
    if not _SLUG_RE.match(slug or ""):
        raise ValueError(
            f"Ungueltiger Slug {slug!r}. Erlaubt: a-z, 0-9, '-', '_', "
            f"max 63 Zeichen, muss mit Buchstabe/Zahl beginnen."
        )
    return slug


# ---------------------------------------------------------------------------
# Standard-Verzeichnisse + Templates
# ---------------------------------------------------------------------------

PROJECT_SUBDIRS: tuple[str, ...] = (
    "sources",
    "sources/_meta",
    "context",
    "work",
    "work/scripts",
    "exports",
    ".disco",
    ".disco/plans",
    ".disco/sessions",
    ".disco/local-skills",
    ".disco/context-extracts",
    ".disco/context-summaries",
)


def _readme_template(name: str, slug: str) -> str:
    """README.md — primaer vom Nutzer gepflegtes Projekt-Briefing.

    Disco liest es beim Session-Start, darf es bei Rueckfrage auch
    updaten (memory_write), aber die Inhalte "gehoeren" dem Nutzer.
    Wenn das Template leer ist, fragt Disco beim Onboarding nach.
    """
    return f"""# {name}

**Slug:** `{slug}`
**Angelegt:** {datetime.now().strftime("%Y-%m-%d")}

## Projektziel

*(Was soll am Ende dieses Projekts herauskommen? 1-3 Saetze.
Beispiel: "Aus drei Datenquellen Dokumente klassifizieren und in
eine neue Ordnerstruktur nach VGB S 831 ueberfuehren.")*

## Kontext

*(Auftraggeber, Standard, Frist, Ansprechpartner. Was muss Disco
wissen, damit er den Hintergrund richtig einordnet?)*

## Quellen

*(Welche Daten sind zu verarbeiten? Woher kommen sie? Umfang?)*

## Erwartete Ergebnisse

*(Welche konkreten Artefakte soll Disco liefern? Excel-Reports,
klassifizierte Ordner, SOLL/IST-Vergleich?)*
"""


def _notes_template(name: str) -> str:
    """NOTES.md — chronologisches Logbuch, append-only.

    Disco pflegt die Datei ueber memory_append; der erste Eintrag
    setzt den Rahmen.
    """
    return f"""# Projekt-Notizen: {name}

Chronologisches Logbuch. Disco fuehrt es per `memory_append(file="NOTES.md")`
nach jeder wesentlichen Session-Etappe fort. Aelteste Eintraege oben,
neue am Ende.

---

## {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

### Initialisierung

Projekt im Disco-Workspace angelegt. Verzeichnisstruktur + leere
Projekt-DB initialisiert.
"""


def _disco_md_template(name: str) -> str:
    """DISCO.md — Discos destilliertes Arbeitsgedaechtnis.

    Vorbild: Claude Codes CLAUDE.md. Das ist Discos "zweite Quelle
    der Wahrheit" pro Projekt — alles was er nach einer Kompression
    (oder in einer neuen Session) braucht, damit er sofort wieder
    arbeitsfaehig ist.
    """
    return f"""# DISCO.md — {name}

Discos destilliertes Arbeitsgedaechtnis fuer dieses Projekt. Wird von
Disco selbst gepflegt (memory_write / memory_append). Lies am Session-
Start immer zuerst README.md, NOTES.md (letzte Eintraege) und dann
diese Datei.

Kurze, nachschlagbare Notizen — kein Fliesstext. Mehrere H2-Abschnitte
fuer die Themenbereiche unten. Obsolete Eintraege loeschen, nicht
durchstreichen (NOTES.md hat die Chronik).

## Aktueller Fokus

*(Was steht gerade an? 1-3 Saetze. Wird bei Fokus-Wechsel ueberschrieben.)*

## Konventionen

*(Dateinamen, Ordnerstrukturen, Namenskonventionen fuer Tabellen,
Eigenarten des Projekts. Beispiel: "Gewerk-Namen immer klein-
geschrieben: elektro/mechanik/bauwerk".)*

## Projekt-Tabellen

*(Welche work_*/agent_*/context_*-Tabellen existieren, was steht drin?
Eine Zeile pro Tabelle reicht. Beispiel:
`agent_sources` — Registry aller sources/-Dateien, 493 Eintraege.)*

## Lookup-Pfade

*(Wo liegt welches Nachschlagewerk? Beispiel:
- DCC-Katalog: `.disco/context-extracts/vgb-s-831.md`, Kapitel A.3 ab S. 121
- Hersteller-Liste: `context_hersteller_aliasse`-Tabelle)*

## Glossar

*(Projekt-/Fachspezifische Abkuerzungen und Begriffe.
Beispiel: "DCC = Document Class Code nach VGB S 831.")*

## Entscheidungen

*(Groessere Entscheidungen mit Datum und kurzer Begruendung. Neu
unten anhaengen. Alte Entscheidungen bleiben lesbar, aber wenn
eine neue eine alte ueberstimmt: kurz dazuschreiben "ersetzt
Entscheidung vom YYYY-MM-DD".)*
"""


def _context_manifest_template(name: str) -> str:
    return f"""# Kontext-Manifest: {name}

**Was ist das?** Hier listet Disco alle Kontext-Dateien in `context/` auf
— mit Kurzbeschreibung, Typ und Hinweis, wann sie relevant sind.

**Wie wird es gepflegt?** Automatisch durch Disco. Nach jedem Hinzufuegen
neuer Kontext-Dateien sagst Du Disco "es gibt neue Kontextdateien",
er sichtet, aktualisiert dieses Manifest und bietet ggf. an, Lookup-
Tabellen in die DB zu importieren (`context_*`-Praefix).

**Was gehoert in `context/`?**
- Dokumentationsstandards (VGB S 831, DIN-Normen)
- Lookup-Tabellen (DCC-Katalog, KKS-Hierarchie, Hersteller-Aliasse)
- Projekt-/Firmenrichtlinien (Firmen-Standard-Dokumentensatz)
- Referenzwerte (Materialklassen-Tabellen, Grenzwerte)

**Was gehoert NICHT hierher?**
- IST-Dokumente (die gehoeren nach `sources/`)
- Zwischenstaende (nach `work/`)
- Endprodukte (nach `exports/`)

---

## Inhalte

*(leer — Disco fuellt beim naechsten "neue Kontextdateien sichten")*
"""


# ---------------------------------------------------------------------------
# Projekt-DB-Initialisierung
# ---------------------------------------------------------------------------

PROJECT_DB_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations" / "project"


def _init_project_db(db_path: Path) -> None:
    """Legt eine Projekt-DB an und wendet alle Template-Migrationen an.

    Konvention:
      - work_*   — temporaere Session-Tabellen
      - agent_*  — dauerhafte Agent-Arbeitsdaten (inkl. Sources-Registry)
      - context_* — Lookup-Tabellen aus context/
      - _disco_* — interne Meta-Tabellen (Schema-Version, Scan-Historie)

    Template-Migrationen liegen unter `migrations/project/NNN_*.sql`,
    werden idempotent per CREATE IF NOT EXISTS angelegt.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        # Meta-Tabelle fuer Schema-Tracking
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS _disco_meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            INSERT OR IGNORE INTO _disco_meta (key, value)
                VALUES ('schema_version', '1');
            INSERT OR IGNORE INTO _disco_meta (key, value)
                VALUES ('created_at', datetime('now'));
            CREATE TABLE IF NOT EXISTS _disco_project_migrations (
                filename   TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        conn.commit()

        # Template-Migrationen anwenden (idempotent)
        if PROJECT_DB_MIGRATIONS_DIR.exists():
            applied = {
                r[0] for r in conn.execute(
                    "SELECT filename FROM _disco_project_migrations"
                ).fetchall()
            }
            for mig in sorted(PROJECT_DB_MIGRATIONS_DIR.glob("*.sql")):
                if mig.name in applied:
                    continue
                sql = mig.read_text(encoding="utf-8")
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO _disco_project_migrations (filename) VALUES (?)",
                    (mig.name,),
                )
                conn.commit()
    finally:
        conn.close()


def seed_sample_sources(project_path: Path) -> dict[str, Any]:
    """Legt Sample-Dateien unter sources/ + _meta/ an, fuer Tests.

    Bewusst klein und selbsterklaerend:
      - 5 kurze Dummy-PDFs mit eingebettetem Text (pypdf)
      - 3 Dummy-Markdown-Dateien
      - _meta/sources-meta.xlsx mit einer Zeile pro Dummy-PDF
    """
    from openpyxl import Workbook
    from pypdf import PdfWriter

    sources = project_path / "sources"
    meta = sources / "_meta"
    elektro = sources / "Elektro"
    bauwerk = sources / "Bauwerk"
    allgem = sources / "Allgemein"
    for p in (meta, elektro, bauwerk, allgem):
        p.mkdir(parents=True, exist_ok=True)

    created: list[str] = []

    # Einfache 1-Seiten-PDFs (leer, fuer Scan-Test reicht das — sha256 variiert ueber den Namen)
    dummies = [
        (elektro / "Schaltplan_A1.pdf", "Schaltplan A1 — Elektro"),
        (elektro / "Produktdatenblatt_SMA_STP50.pdf", "Produktdatenblatt SMA STP50"),
        (elektro / "Konformitaet_SMA.pdf", "Konformitaetserklaerung SMA"),
        (bauwerk / "Statik_Tragwerk.pdf", "Statik Tragwerk"),
        (bauwerk / "Brandschutz_Konzept.pdf", "Brandschutz-Konzept"),
        (allgem / "Uebergabeprotokoll_V1.pdf", "Uebergabeprotokoll V1"),
        (allgem / "Dokumenten_Index.pdf", "Dokumenten-Index"),
    ]
    for pdf_path, title in dummies:
        if pdf_path.exists():
            continue
        # Minimal-PDF mit 1 leeren Seite — pypdf kann's.
        # Fuer echten Textinhalt brauchte es reportlab; fuer Scan-Test reicht dies.
        w = PdfWriter()
        w.add_blank_page(width=595, height=842)
        w.add_metadata({"/Title": title})
        with pdf_path.open("wb") as fh:
            w.write(fh)
        created.append(str(pdf_path.relative_to(project_path)))

    # Markdown-Dummies
    md_files = [
        (elektro / "Wartungsanleitung.md", "# Wartungsanleitung\n\nJaehrliche Pruefung.\n"),
        (bauwerk / "Bauzeichnung_Readme.md", "# Bauzeichnung Readme\n\nSiehe Statik.\n"),
        (allgem / "Inhaltsverzeichnis.md", "# Inhaltsverzeichnis\n\n- Elektro\n- Bauwerk\n"),
    ]
    for mp, content in md_files:
        if mp.exists():
            continue
        mp.write_text(content, encoding="utf-8")
        created.append(str(mp.relative_to(project_path)))

    # Begleit-Excel in _meta/
    meta_xlsx = meta / "sources-meta.xlsx"
    if not meta_xlsx.exists():
        wb = Workbook()
        ws = wb.active
        ws.title = "Metadaten"
        ws.append(["rel_path", "gewerk", "dcc", "hersteller", "bemerkung"])
        ws.append(["Elektro/Schaltplan_A1.pdf", "Elektro", "FA010", "", "Uebersichtsschaltplan"])
        ws.append(["Elektro/Produktdatenblatt_SMA_STP50.pdf", "Elektro", "DA010", "SMA", "Wechselrichter"])
        ws.append(["Elektro/Konformitaet_SMA.pdf", "Elektro", "QC010", "SMA", ""])
        ws.append(["Bauwerk/Statik_Tragwerk.pdf", "Bauwerk", "TB040", "Goldbeck", "Tragwerksplanung"])
        ws.append(["Bauwerk/Brandschutz_Konzept.pdf", "Bauwerk", "QA010", "", "Brandschutz"])
        ws.append(["Allgemein/Uebergabeprotokoll_V1.pdf", "Allgemein", "BB020", "", ""])
        wb.save(meta_xlsx)
        created.append(str(meta_xlsx.relative_to(project_path)))

    return {
        "count": len(created),
        "files": created,
    }


def bootstrap_all_project_migrations() -> dict[str, list[str]]:
    """Wendet Template-Migrationen auf ALLE bestehenden Projekt-DBs an.

    Wird beim Server-Startup aufgerufen — sorgt dafuer, dass Bestands-
    Projekte beim Deployment einer neuen Migration automatisch
    aktualisiert werden, ohne dass der Nutzer pro Projekt etwas tun muss.

    Returns:
        Mapping slug → Liste der neu angewendeten Migrations-Dateinamen.
        Projekte ohne data.db (orphans) werden uebersprungen.
    """
    result: dict[str, list[str]] = {}
    if not settings.projects_dir.exists():
        return result
    for project_path in sorted(settings.projects_dir.iterdir()):
        if not project_path.is_dir():
            continue
        db_path = project_path / "data.db"
        if not db_path.exists():
            continue
        try:
            applied = apply_project_db_migrations(db_path)
        except Exception:  # noqa: BLE001
            # Einzelner Migrations-Fehler darf den Server-Start nicht
            # blockieren — Logging via Aufrufer.
            applied = []
        if applied:
            result[project_path.name] = applied
    return result


def apply_project_db_migrations(db_path: Path) -> list[str]:
    """Wendet Template-Migrationen auf eine bestehende Projekt-DB an.

    Nuetzlich fuer Bestands-Projekte nach Update der Template-Scripts.
    Gibt die Liste der neu angewendeten Dateinamen zurueck.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Projekt-DB nicht gefunden: {db_path}")
    newly_applied: list[str] = []
    conn = sqlite3.connect(str(db_path))
    try:
        # Falls die Meta-Tabelle noch nicht existiert (alte Projekte)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS _disco_project_migrations (
                filename   TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        conn.commit()
        applied = {
            r[0] for r in conn.execute(
                "SELECT filename FROM _disco_project_migrations"
            ).fetchall()
        }
        if PROJECT_DB_MIGRATIONS_DIR.exists():
            for mig in sorted(PROJECT_DB_MIGRATIONS_DIR.glob("*.sql")):
                if mig.name in applied:
                    continue
                conn.executescript(mig.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO _disco_project_migrations (filename) VALUES (?)",
                    (mig.name,),
                )
                conn.commit()
                newly_applied.append(mig.name)
    finally:
        conn.close()
    return newly_applied


# ---------------------------------------------------------------------------
# init_project — die Hauptaktion
# ---------------------------------------------------------------------------

def init_project(
    slug: str,
    name: str | None = None,
    description: str | None = None,
    overwrite_files: bool = False,
) -> dict[str, Any]:
    """Legt ein Disco-Projekt an (Verzeichnis + DB + system.db-Eintrag).

    Idempotent: wenn das Projekt bereits existiert, werden fehlende
    Verzeichnisse/Templates ergaenzt, aber nichts ueberschrieben (es
    sei denn overwrite_files=True).

    Args:
        slug: Slug fuer Verzeichnisname & Identifikation.
        name: Anzeigename. Default: slug, mit erstem Buchstaben gross.
        description: Optionaler Kurztext.
        overwrite_files: True = README/NOTES/DISCO.md ueberschreiben.

    Returns:
        Dict mit slug, name, path, db_path, project_id (system.db),
        created (bool — true wenn neu).
    """
    slug = validate_slug(slug)
    if not name:
        name = slug.replace("-", " ").replace("_", " ").title()

    project_path = settings.projects_dir / slug
    is_new = not project_path.exists()

    # 1) Verzeichnisstruktur
    project_path.mkdir(parents=True, exist_ok=True)
    for sub in PROJECT_SUBDIRS:
        (project_path / sub).mkdir(parents=True, exist_ok=True)

    # 2) Templates (nur wenn fehlt oder overwrite)
    # 3-Datei-Memory-Modell: README (User), NOTES (Disco-Logbuch),
    # DISCO (Discos destilliertes Arbeitsgedaechtnis, CLAUDE.md-inspiriert).
    files = {
        "README.md": _readme_template(name, slug),
        "NOTES.md": _notes_template(name),
        "DISCO.md": _disco_md_template(name),
        "context/_manifest.md": _context_manifest_template(name),
    }
    for rel_path, content in files.items():
        target = project_path / rel_path
        if not target.exists() or overwrite_files:
            target.write_text(content, encoding="utf-8")

    # 3) Projekt-DB + Template-Migrationen (idempotent)
    db_path = project_path / "data.db"
    _init_project_db(db_path)
    apply_project_db_migrations(db_path)

    # 4) Eintrag in system.db (projects-Tabelle) — slug ist Schluessel
    sysconn = connect()
    try:
        row = sysconn.execute(
            "SELECT id FROM projects WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            cur = sysconn.execute(
                "INSERT INTO projects (slug, name, description) VALUES (?, ?, ?)",
                (slug, name, description or f"Projekt {slug}"),
            )
            sysconn.commit()
            project_id = cur.lastrowid
        else:
            project_id = row[0]
            # Name/Description aktualisieren falls neu uebergeben
            if description:
                sysconn.execute(
                    "UPDATE projects SET name = ?, description = ?, "
                    "updated_at = datetime('now') WHERE id = ?",
                    (name, description, project_id),
                )
                sysconn.commit()
    finally:
        sysconn.close()

    return {
        "slug": slug,
        "name": name,
        "path": str(project_path),
        "db_path": str(db_path),
        "project_id": project_id,
        "created": is_new,
    }


# ---------------------------------------------------------------------------
# list_projects — alle Projekte im Workspace
# ---------------------------------------------------------------------------


def list_workspace_projects() -> list[dict[str, Any]]:
    """Listet alle Projekte: Verzeichnisse unter <workspace>/projects/.

    Verschmilzt mit den Eintraegen aus system.db.projects (per Slug).
    Verzeichnisse ohne DB-Eintrag werden trotzdem angezeigt (orphans).
    """
    proj_root = settings.projects_dir
    dirs = sorted([p for p in proj_root.iterdir() if p.is_dir()])

    # system.db Eintraege abrufen — slug ist jetzt eigene Spalte
    sysconn = connect()
    try:
        db_rows = sysconn.execute(
            "SELECT id, slug, name, description, status, created_at FROM projects"
        ).fetchall()
    finally:
        sysconn.close()
    by_slug = {(r["slug"] or slugify(r["name"])): dict(r) for r in db_rows}

    out: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    for d in dirs:
        slug = d.name
        seen_slugs.add(slug)
        db_entry = by_slug.get(slug)
        meta = _read_project_meta(d)
        out.append({
            "slug": slug,
            "name": db_entry["name"] if db_entry else slug.title(),
            "path": str(d),
            "db_id": db_entry["id"] if db_entry else None,
            "status": db_entry["status"] if db_entry else "orphan-fs-only",
            "description": db_entry["description"] if db_entry else None,
            "has_data_db": (d / "data.db").exists(),
            "files_in_sources": meta["files_in_sources"],
            "files_in_context": meta["files_in_context"],
            "files_in_exports": meta["files_in_exports"],
            "files_in_work": meta["files_in_work"],
            "created_at": db_entry["created_at"] if db_entry else None,
        })

    # Eintraege in DB ohne Verzeichnis — archivierte ueberspringen
    # (Verzeichnis liegt unter <workspace>/archive/, nicht im projects/-Dir)
    for slug, db_entry in by_slug.items():
        if slug in seen_slugs:
            continue
        if db_entry.get("status") == "archived":
            continue
        out.append({
            "slug": slug,
            "name": db_entry["name"],
            "path": None,
            "db_id": db_entry["id"],
            "status": "orphan-db-only",
            "description": db_entry["description"],
            "has_data_db": False,
            "files_in_sources": 0,
            "files_in_context": 0,
            "files_in_exports": 0,
            "files_in_work": 0,
            "created_at": db_entry["created_at"],
        })

    out.sort(key=lambda x: (x["status"] != "active", x["name"].lower()))
    return out


def _read_project_meta(project_path: Path) -> dict[str, int]:
    """Zaehlt Dateien in den Standard-Unterordnern (schnell)."""
    def _count(sub: str) -> int:
        p = project_path / sub
        if not p.exists():
            return 0
        return sum(1 for _ in p.rglob("*") if _.is_file())
    return {
        "files_in_sources": _count("sources"),
        "files_in_context": _count("context"),
        "files_in_exports": _count("exports"),
        "files_in_work": _count("work"),
    }


# ---------------------------------------------------------------------------
# show_project — Details
# ---------------------------------------------------------------------------


def show_project(slug: str) -> dict[str, Any]:
    """Liefert detailierte Infos zu einem Projekt."""
    slug = validate_slug(slug)
    project_path = settings.projects_dir / slug
    if not project_path.exists():
        raise KeyError(f"Projekt '{slug}' nicht gefunden unter {project_path}")

    # Basis-Infos — slug ist jetzt eigene Spalte, primaerer Lookup
    sysconn = connect()
    try:
        row = sysconn.execute(
            """SELECT id, name, description, status, created_at, updated_at
               FROM projects WHERE slug = ?
            """,
            (slug,),
        ).fetchone()
    finally:
        sysconn.close()

    meta = _read_project_meta(project_path)
    db_path = project_path / "data.db"
    db_size = db_path.stat().st_size if db_path.exists() else 0
    db_tables: list[str] = []
    if db_path.exists():
        c = sqlite3.connect(str(db_path))
        try:
            db_tables = [
                r[0]
                for r in c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_disco_%' "
                    "ORDER BY name"
                ).fetchall()
            ]
        finally:
            c.close()

    return {
        "slug": slug,
        "name": row["name"] if row else slug.title(),
        "path": str(project_path),
        "db_id": row["id"] if row else None,
        "status": row["status"] if row else "orphan-fs-only",
        "description": row["description"] if row else None,
        "created_at": row["created_at"] if row else None,
        "updated_at": row["updated_at"] if row else None,
        "db_path": str(db_path),
        "db_size": db_size,
        "db_tables": db_tables,
        **meta,
    }


# ---------------------------------------------------------------------------
# archive_project — Projekt verschieben + in DB markieren
# ---------------------------------------------------------------------------


def archive_project(slug: str) -> dict[str, Any]:
    """Archiviert ein Projekt: verschiebt den Ordner + markiert DB-Status.

    Wirkung:
      - Verzeichnis wird verschoben nach `<workspace>/archive/<slug>-<timestamp>/`
      - `projects`-Eintrag in system.db bekommt status='archived'
      - Projekt taucht in `list_workspace_projects()` nicht mehr auf
        (das dortige `iterdir()` liest nur `<workspace>/projects/`, und der
        projects-DB-Eintrag wird als "archived" gefiltert).

    Reversibel: Manuelles Zurueckverschieben des Ordners + Status-Reset
    stellt das Projekt wieder her.

    Args:
        slug: Slug des zu archivierenden Projekts.

    Returns:
        Dict mit slug, archive_path (neuer Pfad), project_id.

    Raises:
        ValueError: Ungueltiger Slug.
        FileNotFoundError: Projekt-Verzeichnis existiert nicht.
    """
    slug = validate_slug(slug)
    project_path = settings.projects_dir / slug
    if not project_path.exists() or not project_path.is_dir():
        raise FileNotFoundError(
            f"Projekt-Verzeichnis nicht gefunden: {project_path}"
        )

    archive_root = settings.projects_dir.parent / "archive"
    archive_root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    archive_path = archive_root / f"{slug}-{timestamp}"
    # Falls doch exakter Namens-Clash (unrealistisch, Sekunden-Genauigkeit):
    suffix = 1
    while archive_path.exists():
        archive_path = archive_root / f"{slug}-{timestamp}-{suffix}"
        suffix += 1

    # 1) Verzeichnis verschieben
    project_path.rename(archive_path)

    # 2) System-DB-Eintrag markieren
    sysconn = connect()
    project_id: int | None = None
    try:
        row = sysconn.execute(
            "SELECT id FROM projects WHERE slug = ?", (slug,)
        ).fetchone()
        if row is not None:
            project_id = row[0]
            sysconn.execute(
                "UPDATE projects SET status = 'archived', "
                "updated_at = datetime('now') WHERE id = ?",
                (project_id,),
            )
            sysconn.commit()
    finally:
        sysconn.close()

    return {
        "slug": slug,
        "archive_path": str(archive_path),
        "project_id": project_id,
    }
