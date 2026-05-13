#!/usr/bin/env python3
"""Backfill der `canonical_path`-Spalte in agent_sources nach Migration 011.

Logik:
  1. Liest alle agent_sources-Zeilen
  2. Berechnet canonical_path = PathResolver.to_canonical(rel_path)
     (= NFC + ' : '-Substitution rueckwaerts auf macOS)
  3. Schreibt canonical_path zurueck
  4. Loest Kollisionen auf: bei zwei Zeilen mit gleichem canonical_path
     - identische SHA-256 + ein active + ein deleted: behalte active,
       loesche deleted (= alte NFD-Records aus Re-Scans)
     - alle anderen Faelle: WARNING, kein automatischer Loesch, manuelle
       Triage erforderlich.
  5. Schreibt einen Report (Markdown)

Modi:
  --dry-run   Nichts schreiben, nur Report
  --apply     Schreibt canonical_path + loest Kollisionen auf

USAGE:
  uv run python scripts/backfill_canonical_path.py \\
    --datastore <pfad-zur-datastore.db> \\
    --report <pfad-zur-report.md> \\
    [--dry-run | --apply]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from disco.fs.path_resolver import PathResolver


def open_db(db_path: Path, read_only: bool) -> sqlite3.Connection:
    if not db_path.exists():
        raise SystemExit(f"DB nicht gefunden: {db_path}")
    if read_only:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    else:
        conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def compute_canonical(rows: list[sqlite3.Row], resolver: PathResolver) -> dict[int, str]:
    """id → canonical_path. Kanonisiert filename + folder eigentlich auch?
    Nein — wir kanonisieren nur rel_path, da das der full path ist und
    filename + folder daraus abgeleitet werden koennten. Aber wir lassen
    filename + folder als FS-Repraesentation bestehen — sie sind der
    Hinweis was auf Disk steht."""
    out: dict[int, str] = {}
    for r in rows:
        rel_path = r["rel_path"]
        if rel_path is None:
            continue
        canonical = resolver.to_canonical(rel_path)
        out[r["id"]] = canonical
    return out


def find_collisions(canonical_map: dict[int, str], rows: list[sqlite3.Row]) -> dict[str, list[sqlite3.Row]]:
    """Gruppiert Zeilen nach canonical_path — Gruppen >1 = Kollision."""
    by_id = {r["id"]: r for r in rows}
    by_canonical: dict[str, list[int]] = defaultdict(list)
    for rid, c in canonical_map.items():
        by_canonical[c].append(rid)
    return {c: [by_id[i] for i in ids] for c, ids in by_canonical.items() if len(ids) > 1}


def classify_collision(variants: list[sqlite3.Row]) -> str:
    """Welche Strategie greift?
    - "auto_delete_deleted": same hash + genau ein active + Rest deleted → delete the deleted
    - "manual": alle anderen Faelle, Mensch muss draufschauen
    """
    hashes = {v["sha256"] for v in variants if v["sha256"]}
    statuses = [v["status"] for v in variants]
    actives = [v for v in variants if v["status"] == "active"]

    if len(hashes) == 1 and len(actives) == 1 and len(actives) < len(variants):
        # genau 1 active, Rest deleted, alle gleicher Hash → auto-loesbar
        return "auto_delete_deleted"
    return "manual"


def apply_backfill(
    conn: sqlite3.Connection,
    canonical_map: dict[int, str],
    collisions: dict[str, list[sqlite3.Row]],
) -> dict:
    """Schreibt canonical_path + loest auto-loesbare Kollisionen auf."""
    stats = {
        "canonical_written": 0,
        "auto_deleted": 0,
        "manual_required": 0,
    }

    # 1. Zuerst canonical_path setzen fuer ALLE Zeilen
    for rid, canonical in canonical_map.items():
        conn.execute(
            "UPDATE agent_sources SET canonical_path = ? WHERE id = ?",
            (canonical, rid),
        )
        stats["canonical_written"] += 1

    # 2. Kollisionen aufloesen
    for canonical, variants in collisions.items():
        strategy = classify_collision(variants)
        if strategy == "auto_delete_deleted":
            # Lösche die "deleted"-Records, behalte den "active"
            for v in variants:
                if v["status"] != "active":
                    conn.execute("DELETE FROM agent_sources WHERE id = ?", (v["id"],))
                    stats["auto_deleted"] += 1
        else:
            stats["manual_required"] += 1

    conn.commit()
    return stats


def render_report(
    out: Path,
    project: str,
    rows: list[sqlite3.Row],
    canonical_map: dict[int, str],
    collisions: dict[str, list[sqlite3.Row]],
    apply_stats: dict | None,
) -> None:
    lines: list[str] = []
    p = lines.append
    p(f"# canonical_path Backfill-Report — `{project}`\n")
    p(f"Mode: {'APPLY' if apply_stats else 'DRY-RUN'}\n")
    p(f"- agent_sources Total: {len(rows)}")
    changes = sum(
        1 for r in rows
        if canonical_map.get(r["id"]) is not None
        and canonical_map[r["id"]] != r["rel_path"]
    )
    p(f"- Zeilen mit canonical_path != rel_path (Aenderung): {changes}")
    p(f"- Kollisions-Gruppen: {len(collisions)}")

    if collisions:
        autos = sum(
            1 for v in collisions.values() if classify_collision(v) == "auto_delete_deleted"
        )
        manuals = len(collisions) - autos
        p(f"  - Davon auto-loesbar (active+deleted, gleicher Hash): {autos}")
        p(f"  - Davon **manuelle Triage**: {manuals}")

    if apply_stats:
        p("")
        p("## APPLIED")
        p(f"- canonical_path geschrieben: {apply_stats['canonical_written']}")
        p(f"- Deleted-Records geloescht: {apply_stats['auto_deleted']}")
        p(f"- Manuell zu triagieren: {apply_stats['manual_required']}")

    if collisions:
        p("")
        p("## Kollisions-Beispiele (Top 10)")
        for canonical, variants in list(collisions.items())[:10]:
            strategy = classify_collision(variants)
            p(f"\n### `{canonical}` — {strategy}")
            for v in variants:
                p(
                    f"  - id={v['id']} status={v['status']} "
                    f"sha={v['sha256'][:12] if v['sha256'] else 'NULL'} "
                    f"rel_path=`{v['rel_path']}`"
                )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill canonical_path (Migration 011)")
    ap.add_argument("--datastore", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--project", default="(unknown)")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true")
    grp.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    resolver = PathResolver()
    conn = open_db(args.datastore, read_only=args.dry_run)
    try:
        # Sicherstellen dass canonical_path-Spalte existiert
        cols = [c["name"] for c in conn.execute("PRAGMA table_info(agent_sources)").fetchall()]
        if "canonical_path" not in cols:
            raise SystemExit(
                "agent_sources.canonical_path fehlt — Migration 011 vorher anwenden."
            )

        rows = conn.execute(
            "SELECT id, rel_path, filename, folder, sha256, status FROM agent_sources"
        ).fetchall()
        print(f"agent_sources rows: {len(rows)}")

        canonical_map = compute_canonical(rows, resolver)
        print(f"canonical_path berechnet fuer {len(canonical_map)} Zeilen")

        collisions = find_collisions(canonical_map, rows)
        print(f"Kollisions-Gruppen: {len(collisions)}")

        apply_stats = None
        if args.apply:
            apply_stats = apply_backfill(conn, canonical_map, collisions)
            print(f"APPLIED: {apply_stats}")

        render_report(args.report, args.project, rows, canonical_map, collisions, apply_stats)
        print(f"Report: {args.report}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
