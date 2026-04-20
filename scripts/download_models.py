#!/usr/bin/env python
"""Laedt die Docling-MLX-Modelle in den HuggingFace-Cache.

Hintergrund
-----------
`huggingface_hub.snapshot_download()` haengt auf macOS reproduzierbar bei
LFS-Dateien > 100 MB (TCP-Connect-Probleme zum HF-CDN, tritt auf auch wenn
`curl` zur selben URL sofort funktioniert). Dieses Skript umgeht das Problem
durch direkten Download mit `curl --continue-at -` (Range-Resume) und baut
danach die HF-Cache-Struktur (`blobs/` + `snapshots/<sha>/*` Symlinks +
`refs/main`) selbst auf — genau so wie huggingface_hub es erwarten wuerde.

Eigenschaften
-------------
- Idempotent: vollstaendig vorhandene Dateien werden uebersprungen.
- Resume-faehig: abgebrochene Downloads werden bei Wiederaufnahme fortgesetzt.
- Keine Python-Abhaengigkeiten ausser stdlib (urllib, subprocess).
- Funktioniert offline, sobald der Cache einmal befuellt wurde — Docling,
  mlx_vlm und transformers.AutoTokenizer finden die Modelle dann ohne
  weitere HTTP-Calls.

Aufruf
------
    uv run python scripts/download_models.py

Gibt bei Erfolg Exit-Code 0 zurueck, bei Fehler != 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Modell-Spezifikationen
# ---------------------------------------------------------------------------
# Wenn Docling auf neuere Modell-Versionen aktualisiert wird, hier den SHA
# oder "main" anpassen. Ein Lauf mit "main" loest automatisch den aktuellen
# Commit-SHA auf und legt sauber `refs/main` an.


class ModelSpec(NamedTuple):
    repo_id: str       # z.B. "ibm-granite/granite-docling-258M-mlx"
    revision: str      # "main" oder ein Commit-SHA (40 hex chars)
    purpose: str       # Kurzbeschreibung fuer die Konsolen-Ausgabe


MODELS: list[ModelSpec] = [
    ModelSpec(
        repo_id="ibm-granite/granite-docling-258M-mlx",
        revision="main",
        purpose="Granite-Docling VLM (Default-Engine fuer markdown_extract)",
    ),
    ModelSpec(
        repo_id="docling-project/SmolDocling-256M-preview-mlx-bf16",
        revision="main",
        purpose="SmolDocling VLM (Alternative, ~2x schneller als Granite)",
    ),
]


# ---------------------------------------------------------------------------
# HTTP-Helpers (stdlib only)
# ---------------------------------------------------------------------------

HF_API = "https://huggingface.co/api"
HF_RESOLVE = "https://huggingface.co"


def _http_json(url: str, *, timeout: int = 30) -> object:
    """GET -> JSON. Nutzt curl, weil Python-urllib auf macOS gelegentlich
    beim Connect zu huggingface.co haengt (TCP- oder TLS-Problem, exakt
    reproduzierbar). Curl hat dieses Problem nicht."""
    result = subprocess.run(
        [
            "curl",
            "-sSL",                    # silent, aber Fehler zeigen
            "--fail",                  # 4xx/5xx als Exit-Code != 0
            "--max-time", str(timeout),
            "-A", "disco-download-models/1.0",
            url,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def resolve_revision(repo_id: str, revision: str) -> str:
    """Aufloesung: Branch/Tag-Name -> Commit-SHA. SHA unveraendert durchreichen."""
    if len(revision) == 40 and all(c in "0123456789abcdef" for c in revision.lower()):
        return revision.lower()
    data = _http_json(f"{HF_API}/models/{repo_id}/revision/{revision}")
    sha = data["sha"] if isinstance(data, dict) else None  # type: ignore[index]
    if not isinstance(sha, str) or len(sha) != 40:
        raise RuntimeError(f"Konnte {revision} nicht aufloesen: {data!r}")
    return sha


def fetch_tree(repo_id: str, sha: str) -> list[dict]:
    """Liste aller Dateien im Repo mit size + LFS-Infos.

    Die Liste ist rekursiv flach (keine verschachtelten Directories).
    Jeder Eintrag enthaelt mindestens:
      type: "file" | "directory"
      path: relativer Pfad im Repo
      oid:  Git-Blob-SHA (40 hex) — Etag fuer non-LFS-Dateien
      size: Groesse in Bytes
    Bei LFS zusaetzlich:
      lfs.oid:  SHA-256 (64 hex) — Etag fuer LFS-Dateien (= Blob-Filename im Cache)
      lfs.size: Groesse in Bytes (sollte == size sein)
    """
    url = f"{HF_API}/models/{repo_id}/tree/{sha}?recursive=true"
    data = _http_json(url)
    if not isinstance(data, list):
        raise RuntimeError(f"Unerwartete Tree-Antwort: {data!r}")
    return [e for e in data if isinstance(e, dict) and e.get("type") == "file"]


def blob_etag(entry: dict) -> str:
    """Welcher Etag wird im HF-Cache als Blob-Filename verwendet?

    LFS-Files: SHA-256 aus lfs.oid (64 hex).
    Normale Files: Git-Blob-SHA aus oid (40 hex).
    """
    lfs = entry.get("lfs")
    if isinstance(lfs, dict) and isinstance(lfs.get("oid"), str):
        return lfs["oid"]
    return entry["oid"]


# ---------------------------------------------------------------------------
# Cache-Layout
# ---------------------------------------------------------------------------


def hf_cache_root() -> Path:
    """HF-Cache-Root finden. Respektiert HF_HUB_CACHE / HF_HOME."""
    env_cache = os.environ.get("HF_HUB_CACHE")
    if env_cache:
        return Path(env_cache).expanduser()
    env_home = os.environ.get("HF_HOME")
    if env_home:
        return Path(env_home).expanduser() / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def repo_cache_dir(root: Path, repo_id: str) -> Path:
    """Verzeichnis-Konvention: models--<org>--<name>."""
    return root / f"models--{repo_id.replace('/', '--')}"


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def curl_download(url: str, target: Path, *, show_progress: bool) -> None:
    """curl -L --fail --continue-at - -o <target> <url>.

    Kein Python-Wrapper um Request/Response — wir wollen exakt das Verhalten
    von curl mit HTTP-Range-Resume, weil Python hier hin und wieder haengt.

    show_progress=True bei groesseren Dateien (> ein paar MB) aktiviert
    curls einzeiligen Fortschrittsbalken auf stderr, sonst still.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "curl",
        "-L",                          # follow redirects (HF -> CDN)
        "--fail",                      # fail on 4xx/5xx
        "--continue-at", "-",          # resume from current file size
        "--show-error",
        "--progress-bar" if show_progress else "--silent",
        "-o", str(target),
        url,
    ]
    subprocess.run(cmd, check=True)


def _fmt_size(n: int | None) -> str:
    if n is None:
        return "?"
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.2f} GB"


def _symlink_relative(snap_dir: Path, rel_path: str, blob_filename: str) -> None:
    """Legt im Snapshot-Ordner einen *relativen* Symlink auf `blobs/<etag>`.

    Warum relativ: der gesamte Cache bleibt dann auch nach einem Move gueltig,
    genau so wie huggingface_hub es erzeugt.

    Formel fuer die Ebenen: 2 fuer `snapshots/<sha>/` plus Anzahl der
    Unterverzeichnisse in rel_path.

    Beispiel (flache Datei):
        snap_dir/<sha>/README.md  ->  ../../blobs/<etag>

    Beispiel (genestete Datei):
        snap_dir/<sha>/sub/tok.json  ->  ../../../blobs/<etag>
    """
    target = snap_dir / rel_path
    levels_up = 2 + rel_path.count("/")
    rel_target = "../" * levels_up + f"blobs/{blob_filename}"
    if target.is_symlink() or target.exists():
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(rel_target)


def download_model(spec: ModelSpec, cache_root: Path) -> None:
    print()
    print("=" * 72)
    print(f"Modell: {spec.repo_id}")
    print(f"Zweck : {spec.purpose}")
    print("=" * 72)

    repo_dir = repo_cache_dir(cache_root, spec.repo_id)
    blobs_dir = repo_dir / "blobs"
    snapshots_dir = repo_dir / "snapshots"
    refs_dir = repo_dir / "refs"

    sha = resolve_revision(spec.repo_id, spec.revision)
    print(f"Revision: {spec.revision} -> {sha}")

    files = fetch_tree(spec.repo_id, sha)
    total_size = sum(int(f.get("size") or 0) for f in files)
    print(f"Dateien : {len(files)}  (insgesamt {_fmt_size(total_size)})")

    blobs_dir.mkdir(parents=True, exist_ok=True)
    snap_dir = snapshots_dir / sha
    snap_dir.mkdir(parents=True, exist_ok=True)
    refs_dir.mkdir(parents=True, exist_ok=True)

    t_start = time.monotonic()
    n_downloaded = 0
    n_skipped = 0

    for entry in files:
        rel_path: str = entry["path"]
        size: int | None = int(entry["size"]) if "size" in entry else None
        etag = blob_etag(entry)

        blob_path = blobs_dir / etag
        snap_path = snap_dir / rel_path

        already_ok = (
            blob_path.is_file()
            and (size is None or blob_path.stat().st_size == size)
        )

        label = f"  {rel_path:<40s} {_fmt_size(size):>10s}"
        if already_ok:
            print(f"{label}  [cache]")
            n_skipped += 1
        else:
            cur = blob_path.stat().st_size if blob_path.is_file() else 0
            if cur > 0:
                print(f"{label}  [resume {_fmt_size(cur)}]")
            else:
                print(f"{label}  [download]")
            url = f"{HF_RESOLVE}/{spec.repo_id}/resolve/{sha}/{rel_path}"
            # Progress-Bar ab > 5 MB — bei kleinen Configs nur Rauschen.
            show_progress = (size or 0) > 5 * 1024 * 1024
            curl_download(url, blob_path, show_progress=show_progress)
            # Sanity: Groesse pruefen
            if size is not None and blob_path.stat().st_size != size:
                raise RuntimeError(
                    f"Groessen-Mismatch bei {rel_path}: "
                    f"erwartet {size}, geladen {blob_path.stat().st_size}"
                )
            n_downloaded += 1

        # Snapshot-Symlink (idempotent)
        _symlink_relative(snap_dir, rel_path, etag)

    # refs/<rev> schreiben. Falls die Eingabe schon ein SHA war, legen wir
    # "main" an — das ist die Konvention, nach der Docling nachschlaegt.
    ref_name = "main" if len(spec.revision) == 40 else spec.revision
    (refs_dir / ref_name).write_text(sha)

    dt = time.monotonic() - t_start
    print(
        f"\nFertig: {n_downloaded} geladen, {n_skipped} bereits im Cache  "
        f"(Dauer: {dt:.1f}s)"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _disable_offline_flags() -> None:
    """Entfernt HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE / HF_DATASETS_OFFLINE.

    Disco laeuft per Default mit allen drei Flags auf 1 (siehe .env + config.py
    `_apply_offline_env`). Das ist bewusst so, damit Flow-Worker nicht beim
    gecachten Modell-Laden einen Online-Check machen und haengen.

    Dieses Skript ist die EINZIGE legitime Stelle, an der Disco online
    Modelle zieht. Deshalb entfernen wir die Flags hier lokal im Prozess —
    Subprozesse (curl) sehen dann die Welt ohne Offline-Zwang.
    Wichtig: unser Prozess-Env, nicht das globale .env — also wirkt das nur
    fuer genau diesen Python-Lauf.
    """
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
        if os.environ.pop(key, None) is not None:
            print(f"  offline-flag {key} fuer diesen Lauf deaktiviert")


def main() -> int:
    _disable_offline_flags()

    cache_root = hf_cache_root()
    print(f"HuggingFace-Cache: {cache_root}")
    if not cache_root.parent.is_dir():
        cache_root.parent.mkdir(parents=True, exist_ok=True)

    for spec in MODELS:
        try:
            download_model(spec, cache_root)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip() if hasattr(exc, "stderr") else ""
            print(f"\nFEHLER: curl ist fehlgeschlagen (Exit {exc.returncode}).")
            if stderr:
                print(f"  stderr: {stderr}")
            return 2
        except Exception as exc:  # noqa: BLE001
            print(f"\nFEHLER bei {spec.repo_id}: {type(exc).__name__}: {exc}")
            return 1

    print("\nAlle Modelle sind im HuggingFace-Cache verfuegbar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
