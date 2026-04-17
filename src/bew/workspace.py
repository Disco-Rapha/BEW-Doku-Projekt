"""Disco-Workspace: Projekt-Lifecycle (Init, List, Show, Delete).

Ein Projekt im Disco-Workspace ist ein Verzeichnis unter
`<workspace>/projects/<slug>/` mit einer festen Struktur:

    <slug>/
    ├── README.md          ← Du editierst: Worum geht's?
    ├── NOTES.md           ← Disco fuehrt fort: chronologisches Logbuch
    ├── sources/           ← Arbeitsdokumente (zu bearbeitendes Material)
    ├── context/           ← Arbeitsgrundlagen (Normen, Kataloge, Richtlinien)
    │   └── _manifest.md   ← Agent-gepflegte Uebersicht aller Kontext-Dateien
    ├── work/              ← Discos Arbeitsraum
    ├── exports/           ← Endprodukte (nicht ueberschreiben)
    ├── data.db            ← Projekt-DB (work_*/agent_*/context_*-Tabellen)
    └── .disco/            ← Discos Hirn fuer dieses Projekt
        ├── memory.md      ← Faustregeln, dauerhafte Erkenntnisse
        ├── plans/         ← aktive Aufgaben-Plaene
        ├── sessions/      ← Session-Zusammenfassungen
        └── local-skills/  ← optional projekt-spezifische Skills

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

    'Vattenfall Reuter' -> 'vattenfall-reuter'
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
    "context",
    "work",
    "exports",
    ".disco",
    ".disco/plans",
    ".disco/sessions",
    ".disco/local-skills",
)


def _readme_template(name: str, slug: str) -> str:
    return f"""# {name}

**Slug:** `{slug}`
**Angelegt:** {datetime.now().strftime("%Y-%m-%d")}

## Worum geht es?

*(Hier traegst Du den Projekt-Kontext ein: Auftrag, Auftraggeber,
Standard, Frist, Ansprechpartner. Disco liest das beim Session-Start
mit, damit er den Hintergrund versteht.)*

## Quellen

Originaldaten liegen unter `sources/`. Beispiele:
- *(noch keine — fuelle sources/, sobald Du Quelldaten hast)*

## Aktueller Stand

*(kurze Standortbestimmung — was wurde zuletzt erreicht?)*

## Konventionen fuer Disco

- Arbeits-Tabellen: `work_*` (temporaer) und `agent_*` (dauerhaft)
- Endprodukte landen in `exports/` mit Datum und Versions-Suffix
- Disco fuehrt `NOTES.md` chronologisch fort, ohne nachzufragen
"""


def _notes_template(name: str) -> str:
    return f"""# Projekt-Notizen: {name}

Chronologisches Logbuch — Disco fuehrt es nach jeder relevanten
Session fort. Aelteste Eintraege oben.

---

## {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

### Initialisierung

Projekt im Disco-Workspace angelegt. Verzeichnisstruktur erstellt,
leere Projekt-DB initialisiert.
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
- Projekt-/Firmenrichtlinien (BEW-Standard-Dokumentensatz)
- Referenzwerte (Materialklassen-Tabellen, Grenzwerte)

**Was gehoert NICHT hierher?**
- IST-Dokumente (die gehoeren nach `sources/`)
- Zwischenstaende (nach `work/`)
- Endprodukte (nach `exports/`)

---

## Inhalte

*(leer — Disco fuellt beim naechsten "neue Kontextdateien sichten")*
"""


def _memory_template(name: str) -> str:
    return f"""# Disco-Memory: {name}

**Hier sammelt Disco dauerhafte Erkenntnisse zu diesem Projekt.**

Nicht chronologisch (das ist `NOTES.md`), sondern als Faustregeln,
Konventionen, gelernte Vorlieben des Benutzers, Schluessel-Erkenntnisse
zu den Daten. Disco liest die Datei zu Beginn jeder neuen Session.

## Konventionen

- *(Trag hier ein, sobald Du etwas Festes weisst.)*

## Datenstruktur

- *(z.B. "KKS-System Y0XYZ steht fuer ...")*

## Verworfen / nicht relevant

- *(damit Disco nicht erneut darauf reinfaellt)*
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
        overwrite_files: True = README/NOTES/memory.md ueberschreiben.

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
    files = {
        "README.md": _readme_template(name, slug),
        "NOTES.md": _notes_template(name),
        ".disco/memory.md": _memory_template(name),
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

    # Eintraege in DB ohne Verzeichnis
    for slug, db_entry in by_slug.items():
        if slug not in seen_slugs:
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
