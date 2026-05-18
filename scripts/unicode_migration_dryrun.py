#!/usr/bin/env python3
"""Trockenlauf-Analyse fuer die Unicode/Pfad-Migration.

ZWECK: vor der echten Migration (Option B aus der Diskussion 2026-05-13)
quantifizieren wie viele Risiko-Faelle in den realen Daten existieren.
Strikt READ-ONLY — schreibt NICHTS in DBs, schreibt NICHTS in Prod-FS.
Erzeugt nur einen Markdown-Report.

USAGE:
    uv run python scripts/unicode_migration_dryrun.py \\
        --datastore <pfad-zur-datastore.db> \\
        --workspace <pfad-zur-workspace.db> \\
        --sources-root <pfad-zum-sources-Verzeichnis-fuer-FS-Tests> \\
        --report <ausgabe.md>

BEISPIEL (rea-denox via Staging):
    uv run python scripts/unicode_migration_dryrun.py \\
        --datastore ~/Disco-dev/staging/bew-rsd-rea-denox/datastore.db \\
        --workspace ~/Disco-dev/staging/bew-rsd-rea-denox/workspace.db \\
        --sources-root ~/Disco/projects/bew-rsd-rea-denox/sources \\
        --report ~/Disco-dev/staging/bew-rsd-rea-denox/unicode_dryrun_report.md

ABDECKUNG (gegen die Risiken aus der Architektur-Diskussion):
  R1  Trailing-Dot-Rekonstruktion: wie viele Excel-Folder haben Trailing-
      Dot, wie viele FS-Folder waeren betroffen, wie viel Coverage erreicht
      ein NFC + Trailing-Dot-Mapping?
  R2  UNIQUE-Kollisionen: wieviele agent_sources kollidieren beim NFC-
      Normalisieren?
  R3  Roundtrip: fuer eine Stichprobe — canonicalize(fs_path) → resolve_to_fs
      → Path.exists(). Wenn nicht, ist der Resolver kaputt fuer diese Stelle.

PLUS deskriptive Bestandsaufnahme:
  - NFC/NFD-Verteilung
  - Sonderzeichen-Inventar (Top-N)
  - Pfad-Trenner-Statistik (: vs /)
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Iterable

# ----------------------------------------------------------------
# Read-only SQLite-Verbindung — Belt + Suspenders mit URI mode=ro
# ----------------------------------------------------------------


def ro_connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise SystemExit(f"DB nicht gefunden: {db_path}")
    uri = f"file:{db_path}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ----------------------------------------------------------------
# Kanonisierungs-Funktion (Spielwiese-Variante fuer den Trockenlauf)
# ----------------------------------------------------------------
# Die echte Resolver-Funktion kommt spaeter als eigener Modul. Hier
# nur fuer die Analyse: NFC + Slash-Replacement + Lower-Casing weglassen
# (weil Casing erhalten bleiben soll).
#
# Hinweis: Trailing-Dot-Rekonstruktion ist KEINE reine Funktion vom
# FS-Pfad — sie braucht den Excel-Snapshot als Quelle. Wir testen
# also nur das Match-Verhalten.


def to_canonical(fs_path: str) -> str:
    """FS-Path (NFD, ': ' als Trenner) → canonical NFC-Form."""
    nfc = unicodedata.normalize("NFC", fs_path)
    # Mac-OneDrive ersetzt '/' in SP-Subpath durch ' : ' (Space-Doppelpunkt-
    # Space). Wir reversen das.
    nfc = nfc.replace(" : ", "/")
    return nfc


def is_nfd(s: str) -> bool:
    """Heuristik: enthaelt der String Combining-Marks (NFD-Bytes)?"""
    return any(unicodedata.combining(c) > 0 for c in s)


def first_nondefault_char(s: str) -> str | None:
    """Liefert das erste 'spannende' Zeichen (Non-ASCII oder Combining)."""
    for c in s:
        if ord(c) > 127 or unicodedata.combining(c) > 0:
            return c
    return None


# ----------------------------------------------------------------
# Risk-Checks
# ----------------------------------------------------------------


def check_nfc_nfd_distribution(rows: list[sqlite3.Row], col: str) -> dict:
    """Wie viele Strings sind in NFD?"""
    nfd_count = 0
    nfc_count = 0
    pure_ascii = 0
    sample_nfd: list[str] = []
    for row in rows:
        s = row[col]
        if not s:
            continue
        if all(ord(c) < 128 for c in s):
            pure_ascii += 1
        elif is_nfd(s):
            nfd_count += 1
            if len(sample_nfd) < 5:
                sample_nfd.append(s)
        else:
            nfc_count += 1
    return {
        "total": len(rows),
        "pure_ascii": pure_ascii,
        "nfc": nfc_count,
        "nfd": nfd_count,
        "sample_nfd": sample_nfd,
    }


def check_special_chars(rows: list[sqlite3.Row], col: str) -> Counter:
    """Inventar aller Non-ASCII / Combining-Marks (Top-N)."""
    chars: Counter = Counter()
    for row in rows:
        s = row[col]
        if not s:
            continue
        for c in s:
            if ord(c) > 127 or unicodedata.combining(c) > 0:
                chars[c] += 1
    return chars


def check_path_separator(rows: list[sqlite3.Row], col: str) -> dict:
    """Pfad-Trenner-Statistik: wie viele Pfade haben ' : '? Wie viele '/' im Filename?"""
    has_colon_sep = 0
    has_slash = 0
    sample_colon: list[str] = []
    sample_slash: list[str] = []
    for row in rows:
        s = row[col]
        if not s:
            continue
        if " : " in s:
            has_colon_sep += 1
            if len(sample_colon) < 5:
                sample_colon.append(s)
        if "/" in s:
            has_slash += 1
            if len(sample_slash) < 5:
                sample_slash.append(s)
    return {
        "with_colon_sep": has_colon_sep,
        "with_slash": has_slash,
        "sample_colon": sample_colon,
        "sample_slash": sample_slash,
    }


def check_collisions(rows: list[sqlite3.Row], col: str) -> dict:
    """R2: wuerden NFC-normalisierte Werte miteinander kollidieren?"""
    bucket: dict[str, list[str]] = {}
    for row in rows:
        s = row[col]
        if not s:
            continue
        canonical = to_canonical(s)
        bucket.setdefault(canonical, []).append(s)
    collisions = {k: v for k, v in bucket.items() if len(v) > 1}
    return {
        "total_rows": len(rows),
        "distinct_canonicals": len(bucket),
        "collision_groups": len(collisions),
        "sample_collisions": dict(list(collisions.items())[:5]),
    }


def check_trailing_dot_folders(workspace_db: Path) -> dict:
    """R1: wie viele SP-Folder haben Trailing-Dot? Wie viele wuerden FS-Folder ohne Dot
    eindeutig matchen? Alle agent_sp_*-Tabellen mit path-Spalte werden gescannt."""
    conn = ro_connect(workspace_db)
    try:
        sp_folders: set[str] = set()
        tbls = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE 'agent_sp_%' AND name NOT LIKE '%_norm'"
        ).fetchall()
        for r in tbls:
            tname = r["name"]
            try:
                cols = [c["name"] for c in conn.execute(f"PRAGMA table_info({tname})").fetchall()]
                if "path" not in cols:
                    continue
                rows = conn.execute(
                    f"SELECT DISTINCT path FROM {tname} WHERE path IS NOT NULL"
                ).fetchall()
                for r2 in rows:
                    sp_folders.add(r2["path"])
            except sqlite3.OperationalError:
                continue
        with_trailing_dot = [p for p in sp_folders if p and any(seg.endswith(".") for seg in p.split("/"))]
        return {
            "sp_folders_total": len(sp_folders),
            "sp_folders_with_trailing_dot": len(with_trailing_dot),
            "sample_with_dot": with_trailing_dot[:5],
        }
    finally:
        conn.close()


def check_roundtrip_fs_existence(rows: list[sqlite3.Row], sources_root: Path, max_samples: int = 200) -> dict:
    """R3: nimm Stichprobe an rel_path-Werten, baue absoluten FS-Pfad,
    rufe .exists() auf. Wenn nicht: notiere als 'lost'."""
    ok = 0
    missing: list[str] = []
    for row in rows[:max_samples]:
        rel = row["rel_path"]
        if not rel:
            continue
        abs_path = sources_root / rel
        if abs_path.exists():
            ok += 1
        else:
            missing.append(rel)
    return {
        "tested": min(max_samples, len(rows)),
        "ok": ok,
        "missing": len(missing),
        "sample_missing": missing[:5],
    }


def check_norm_table_match(workspace_db: Path) -> dict:
    """Bestaetigt das bestehende _norm-Match-Verhalten (Baseline).
    Behandelt fehlende Tabellen sauber."""
    conn = ro_connect(workspace_db)
    try:
        # Welche _norm-Tabellen existieren?
        existing = {
            r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_norm'"
            ).fetchall()
        }
        if "agent_sources_norm" not in existing:
            return {"info": "agent_sources_norm fehlt — _norm-Krücke in diesem Projekt nicht aktiv"}
        fs_total = conn.execute("SELECT COUNT(*) FROM agent_sources_norm").fetchone()[0]
        sp_norm_tables = [t for t in existing if t.startswith("agent_sp_") and t != "agent_sources_norm"]
        if not sp_norm_tables:
            return {
                "info": "Keine agent_sp_*_norm-Tabellen — kein SP-Cross-Check in diesem Projekt",
                "fs_norm_total": fs_total,
            }
        sp_norm_total = 0
        matched_total = 0
        per_table = {}
        for tname in sp_norm_tables:
            cols = [c["name"] for c in conn.execute(f"PRAGMA table_info({tname})").fetchall()]
            if "name_norm" not in cols:
                continue
            total = conn.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
            matched = conn.execute(
                f"SELECT COUNT(*) FROM {tname} ppn WHERE EXISTS "
                f"(SELECT 1 FROM agent_sources_norm n WHERE n.filename_norm = ppn.name_norm)"
            ).fetchone()[0]
            per_table[tname] = (total, matched)
            sp_norm_total += total
            matched_total += matched
        return {
            "fs_norm_total": fs_total,
            "sp_norm_total": sp_norm_total,
            "matched": matched_total,
            "per_table": per_table,
        }
    finally:
        conn.close()


# ----------------------------------------------------------------
# Report-Generierung
# ----------------------------------------------------------------


def fmt_pct(part: int, total: int) -> str:
    if not total:
        return "n/a"
    return f"{100.0 * part / total:.1f}%"


def write_report(
    out: Path,
    project: str,
    nfd_filename: dict,
    nfd_relpath: dict,
    nfd_sp_path: dict,
    chars_filename: Counter,
    chars_relpath: Counter,
    pathsep_relpath: dict,
    pathsep_sppath: dict,
    collisions_filename: dict,
    collisions_relpath: dict,
    trailing_dot: dict,
    roundtrip: dict,
    norm_match: dict,
) -> None:
    lines: list[str] = []
    p = lines.append
    p(f"# Unicode/Pfad-Migration — Trockenlauf-Report\n")
    p(f"**Projekt:** `{project}`")
    p(f"**Erzeugt:** automatisch, READ-ONLY, ohne DB-Schreibvorgang.\n")
    p("---\n")

    p("## 1. NFC/NFD-Verteilung\n")
    for label, d in (
        ("agent_sources.filename", nfd_filename),
        ("agent_sources.rel_path", nfd_relpath),
        ("agent_sp_projektdoku.path", nfd_sp_path),
    ):
        p(f"### `{label}`")
        p(f"- Total: {d['total']}")
        p(f"- Pure ASCII: {d['pure_ascii']} ({fmt_pct(d['pure_ascii'], d['total'])})")
        p(f"- NFC: {d['nfc']} ({fmt_pct(d['nfc'], d['total'])})")
        p(f"- **NFD: {d['nfd']} ({fmt_pct(d['nfd'], d['total'])})**")
        if d["sample_nfd"]:
            p("- Beispiele NFD:")
            for s in d["sample_nfd"]:
                p(f"  - `{s}`")
        p("")

    p("## 2. Sonderzeichen-Inventar (Top 20)\n")
    p("### filename")
    for c, n in chars_filename.most_common(20):
        try:
            name = unicodedata.name(c, "(unnamed)")
        except Exception:
            name = "(no name)"
        p(f"- U+{ord(c):04X} `{c}` ({name}) — {n}x")
    p("")
    p("### rel_path")
    for c, n in chars_relpath.most_common(20):
        try:
            name = unicodedata.name(c, "(unnamed)")
        except Exception:
            name = "(no name)"
        p(f"- U+{ord(c):04X} `{c}` ({name}) — {n}x")
    p("")

    p("## 3. Pfad-Trenner-Statistik\n")
    p("### rel_path (Filesystem)")
    p(f"- mit ' : ' (OneDrive-Substitution): {pathsep_relpath['with_colon_sep']}")
    p(f"- mit '/' (regulaerer Trenner): {pathsep_relpath['with_slash']}")
    for s in pathsep_relpath["sample_colon"]:
        p(f"  - `{s}`")
    p("")
    p("### sp_projektdoku.path (SharePoint)")
    p(f"- mit ' : ': {pathsep_sppath['with_colon_sep']}")
    p(f"- mit '/': {pathsep_sppath['with_slash']}")
    p("")

    p("## 4. R2 — NFC-Kollisions-Check\n")
    p("### Auf filename")
    p(f"- Total Rows: {collisions_filename['total_rows']}")
    p(f"- Distinct nach NFC-Normalisierung: {collisions_filename['distinct_canonicals']}")
    p(f"- **Kollisions-Gruppen: {collisions_filename['collision_groups']}**")
    for canon, variants in collisions_filename["sample_collisions"].items():
        p(f"  - canonical: `{canon}`")
        for v in variants:
            p(f"    - variant: `{v}`")
    p("")
    p("### Auf rel_path")
    p(f"- Total Rows: {collisions_relpath['total_rows']}")
    p(f"- Distinct nach NFC-Normalisierung: {collisions_relpath['distinct_canonicals']}")
    p(f"- **Kollisions-Gruppen: {collisions_relpath['collision_groups']}**")
    for canon, variants in collisions_relpath["sample_collisions"].items():
        p(f"  - canonical: `{canon}`")
        for v in variants:
            p(f"    - variant: `{v}`")
    p("")

    p("## 5. R1 — Trailing-Dot-Coverage\n")
    p(f"- SP-Folder-Pfade (distinct): {trailing_dot['sp_folders_total']}")
    p(f"- davon mit Trailing-Dot in mindestens einer Segment: {trailing_dot['sp_folders_with_trailing_dot']}")
    if trailing_dot["sample_with_dot"]:
        for s in trailing_dot["sample_with_dot"]:
            p(f"  - `{s}`")
    p("")

    p("## 6. R3 — Roundtrip / FS-Existence (Stichprobe)\n")
    p(f"- Getestet: {roundtrip['tested']} rel_path-Werte")
    p(f"- File existiert auf Disk: {roundtrip['ok']} ({fmt_pct(roundtrip['ok'], roundtrip['tested'])})")
    p(f"- Datei **nicht** gefunden: {roundtrip['missing']}")
    if roundtrip["sample_missing"]:
        p("- Beispiele fehlend:")
        for s in roundtrip["sample_missing"]:
            p(f"  - `{s}`")
    p("")

    p("## 7. Baseline: bestehende _norm-Match-Rate\n")
    if "error" in norm_match:
        p(f"- Fehler: {norm_match['error']}")
    elif "info" in norm_match:
        p(f"- {norm_match['info']}")
        if "fs_norm_total" in norm_match:
            p(f"- agent_sources_norm Total: {norm_match['fs_norm_total']}")
    else:
        p(f"- agent_sources_norm Total: {norm_match.get('fs_norm_total')}")
        p(f"- agent_sp_*_norm Total: {norm_match.get('sp_norm_total')}")
        p(f"- Matched via _norm: {norm_match.get('matched')} "
          f"({fmt_pct(norm_match.get('matched', 0), norm_match.get('sp_norm_total', 0))})")
        if norm_match.get("per_table"):
            p("- per Tabelle:")
            for tname, (total, matched) in norm_match["per_table"].items():
                p(f"  - `{tname}`: {matched}/{total} ({fmt_pct(matched, total)})")
    p("")

    p("## Zusammenfassung & Empfehlung\n")
    p("- Wenn NFD-Anteil in filename oder rel_path > 0: Migration noetig (erwartet)")
    p("- Wenn Kollisions-Gruppen > 0: Vor Migration **manuelle Triage** dieser Faelle")
    p("- Wenn Roundtrip-OK-Rate < 95%: Resolver oder Pfad-Mapping hat ein Loch — VOR Migration fixen")
    p("- Wenn SP-Trailing-Dot-Folder hoch: SP-Link-Generierung braucht Excel-basierte Rekonstruktion")
    p("")
    p("**Read-only-Hinweis**: dieses Skript hat ausschliesslich SELECT-Queries gegen "
      "die Staging-DBs ausgefuehrt und Filesystem-Existence-Checks gegen Prod-FS gemacht. "
      "Keine Schreibvorgaenge.")

    out.write_text("\n".join(lines), encoding="utf-8")


# ----------------------------------------------------------------
# Main
# ----------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Unicode-Migrations-Trockenlauf (read-only)")
    parser.add_argument("--datastore", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--sources-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--project", default="(unknown)")
    args = parser.parse_args()

    print(f"Trockenlauf gegen:")
    print(f"  datastore.db : {args.datastore}")
    print(f"  workspace.db : {args.workspace}")
    print(f"  sources-root : {args.sources_root}")
    print(f"  report       : {args.report}")
    print()

    # --- Datastore lesen ---
    ds = ro_connect(args.datastore)
    try:
        sources = ds.execute("SELECT filename, rel_path, folder FROM agent_sources").fetchall()
    finally:
        ds.close()

    # --- Workspace lesen: alle agent_sp_*-Tabellen mit `path`-Spalte sammeln ---
    ws = ro_connect(args.workspace)
    sp_paths: list = []
    sp_tables_found: list[str] = []
    try:
        # Welche agent_sp_*-Tabellen existieren ueberhaupt (projekt-individuell)?
        tbls = ws.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE 'agent_sp_%' AND name NOT LIKE '%_norm'"
        ).fetchall()
        for r in tbls:
            tname = r["name"]
            try:
                # Pruefen ob die Tabelle eine `path`-Spalte hat
                cols = [c["name"] for c in ws.execute(f"PRAGMA table_info({tname})").fetchall()]
                if "path" not in cols:
                    continue
                paths = ws.execute(f"SELECT path FROM {tname} WHERE path IS NOT NULL").fetchall()
                sp_paths.extend(paths)
                sp_tables_found.append(tname)
            except sqlite3.OperationalError:
                continue
    finally:
        ws.close()
    print(f"SP-Tabellen gefunden: {sp_tables_found or '(keine)'}")

    print(f"agent_sources rows : {len(sources)}")
    print(f"agent_sp_projektdoku.path rows: {len(sp_paths)}")
    print()

    print("=> Risk-Checks ...")
    nfd_filename = check_nfc_nfd_distribution(sources, "filename")
    nfd_relpath = check_nfc_nfd_distribution(sources, "rel_path")
    nfd_sp_path = check_nfc_nfd_distribution(sp_paths, "path")
    chars_filename = check_special_chars(sources, "filename")
    chars_relpath = check_special_chars(sources, "rel_path")
    pathsep_relpath = check_path_separator(sources, "rel_path")
    pathsep_sppath = check_path_separator(sp_paths, "path")
    collisions_filename = check_collisions(sources, "filename")
    collisions_relpath = check_collisions(sources, "rel_path")
    trailing_dot = check_trailing_dot_folders(args.workspace)
    roundtrip = check_roundtrip_fs_existence(sources, args.sources_root)
    norm_match = check_norm_table_match(args.workspace)

    print("=> Report schreiben ...")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_report(
        args.report,
        args.project,
        nfd_filename, nfd_relpath, nfd_sp_path,
        chars_filename, chars_relpath,
        pathsep_relpath, pathsep_sppath,
        collisions_filename, collisions_relpath,
        trailing_dot, roundtrip, norm_match,
    )
    print(f"OK. Report: {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
