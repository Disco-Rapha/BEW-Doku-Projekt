"""PathResolver — Brücke zwischen kanonischen Disco-Pfaden und Filesystem-Pfaden.

Hintergrund: Disco-DB haelt Pfade in kanonischer Form (NFC, mit '/' als
Trenner, mit Trailing-Dots wo SharePoint sie haette). Das Filesystem auf
macOS speichert Strings in NFD, OneDrive ersetzt SharePoint-interne
Slashes durch ' : ' (Space-Colon-Space). Dieses Modul kapselt die
Konvertierung in beide Richtungen.

Beispiele (macOS):

    canonical:  '10 Dokumentation/10.04 Projektdoku/Übersicht.pdf'
                (NFC, Slash-Trenner)

    fs_actual:  '10 Dokumentation : 10.04 Projektdoku/Übersicht.pdf'
                (NFD, ': '-Trenner)

Auf Linux/Windows: Resolver ist Identity (NFC + '/' bleibt unverändert).

USAGE:
    from disco.fs.path_resolver import PathResolver

    resolver = PathResolver()  # auto-detected per Plattform

    fs_path = resolver.to_fs(canonical_path)        # für open(), os.stat() etc.
    canonical = resolver.to_canonical(fs_path)      # für DB-Inserts

    # Bei Scans:
    for entry in os.scandir(...):
        canon = resolver.to_canonical(entry.name)
        ...
"""

from __future__ import annotations

import os
import sys
import unicodedata
from pathlib import Path
from typing import Iterable


# Trenner-Substitution auf macOS:
# OneDrive ersetzt SharePoint-interne '/' in Folder-Namen durch ' : '
# (mit Leerzeichen drumherum). Auf Linux/Windows passiert das nicht.
_MAC_FOLDER_SEP_SUBSTITUTE = " : "


class PathResolver:
    """Konvertiert zwischen canonical (DB) und FS-Pfad (Disk).

    Args:
        platform: Override fuer Plattform-Erkennung. Default: sys.platform.
                  Erlaubt: 'darwin' (macOS), 'linux', 'win32'.
                  Andere Plattformen werden als 'linux' behandelt (Pass-Through).
    """

    def __init__(self, platform: str | None = None):
        self.platform = (platform or sys.platform).lower()

    @property
    def is_mac(self) -> bool:
        return self.platform == "darwin"

    # -----------------------------------------------------------------
    # canonical → fs (zum oeffnen, stat etc.)
    # -----------------------------------------------------------------

    def to_fs(self, canonical_path: str) -> str:
        """canonical → FS-Repraesentation (NFD + Folder-Sep-Substitution auf macOS).

        Idempotent bei Linux/Windows. Auf macOS:
        - Slash-Trenner in Folder-Komponenten werden durch ' : ' ersetzt,
          **aber nur in Folder-Namen die einen '/' enthalten**. Pfad-Trenner
          (Folder-Boundaries) bleiben echte '/' — das versteht Python's
          pathlib auch auf macOS.

        Beispiel canonical: 'A/B with / in name/C.pdf'
        wird zu FS-actual: 'A/B with : in name/C.pdf'

        Aber Disco-typisch ist es einfacher:
        canonical: '10 Dokumentation/10.04 Projektdoku/x.pdf'
        Hier ist '10 Dokumentation/10.04 Projektdoku' EIN SharePoint-Ordner
        der OneDrive-seitig zu '10 Dokumentation : 10.04 Projektdoku' wird.
        Wir koennen das ohne Kontext nicht eindeutig erkennen.

        DESHALB: Wir geben dem Resolver eine Hilfsmethode `to_fs_with_hint`
        (siehe unten), die das Mapping aus DB-Daten nimmt. Hier nur die
        triviale Identitaet + NFD.
        """
        if not canonical_path:
            return canonical_path
        if self.is_mac:
            return unicodedata.normalize("NFD", canonical_path)
        return canonical_path

    def to_fs_resolved(self, canonical_path: str, project_root: Path) -> Path:
        """Resolved canonical → existierender FS-Pfad unter project_root.

        Versucht in Reihenfolge:
        1. canonical (NFC) direkt unter project_root
        2. NFD-Variante
        3. Falls Folder-Komponenten ein '/' enthalten koennten, das in ' : '
           umsetzen (Mac-OneDrive-Quirk).
        4. Wenn nichts passt: gibt den NFD-Pfad zurueck — Caller-Code
           wirft dann FileNotFoundError.

        Returns:
            Path (existent wenn moeglich, sonst best-guess).
        """
        if not canonical_path:
            return project_root

        candidates = self._fs_candidates(canonical_path)
        for candidate in candidates:
            p = project_root / candidate
            if p.exists():
                return p
        # Best-guess: erste Variante zurueckgeben (NFD auf mac)
        return project_root / candidates[0]

    def _fs_candidates(self, canonical_path: str) -> list[str]:
        """Generiert alle FS-Form-Kandidaten fuer einen canonical-Pfad.

        Reihenfolge: wahrscheinlichste zuerst.
        Auf Mac werden Varianten mit NFD und ' : '-Substitution erzeugt.
        """
        nfc = unicodedata.normalize("NFC", canonical_path)
        nfd = unicodedata.normalize("NFD", canonical_path)

        if not self.is_mac:
            # Linux/Windows: NFC ist nativ, keine Substitution
            seen = []
            for v in [nfc, nfd]:
                if v not in seen:
                    seen.append(v)
            return seen

        # macOS: NFD ist FS-nativ. Plus ' : '-Substitution in Folder-Parts.
        nfd_with_colon = self._slash_to_colon_in_folders(nfd)
        nfc_with_colon = self._slash_to_colon_in_folders(nfc)

        candidates = [nfd_with_colon, nfd, nfc_with_colon, nfc]
        seen: list[str] = []
        for c in candidates:
            if c not in seen:
                seen.append(c)
        return seen

    def _slash_to_colon_in_folders(self, path_str: str) -> str:
        """Ersetzt '/' in Folder-Namen durch ' : ' — als Mac-OneDrive-Quirk.

        Das ist ambig: ohne Kontext koennen wir nicht wissen ob ein
        bestimmter '/' ein Folder-Trenner oder Teil eines Folder-Namens ist.
        Heuristik: probieren wir aus, indem to_fs_resolved beide Varianten
        gegen das echte Filesystem checkt.

        Diese Methode nimmt das gesamte path_str und macht alle inneren '/'
        zu ' : ' — extreme Variante. Wird mit Original kombiniert.
        """
        # Konservativ: kombiniert nur, wenn Pfad ueberhaupt '/' hat.
        if "/" not in path_str:
            return path_str
        return path_str.replace("/", _MAC_FOLDER_SEP_SUBSTITUTE)

    # -----------------------------------------------------------------
    # fs → canonical (beim Scannen)
    # -----------------------------------------------------------------

    def to_canonical(self, fs_path: str) -> str:
        """FS-Repraesentation → canonical (NFC, ' : '-Substitution rueckwaerts).

        Auf macOS:
        - NFD → NFC (composing)
        - ' : ' (Mac-OneDrive-Folder-Slash-Sub) → '/'
          (Heuristik: jedes ' : ' wird als '/' interpretiert.
          Wenn ein Folder echt ein ' : ' enthielte, wuerde das hier falsch
          kollabieren. Real-Daten in Disco zeigen aber kein solches Beispiel
          — Trade-off bewusst akzeptiert.)

        Auf Linux/Windows: NFC-Normalisierung (sicher), kein Sep-Replace.
        """
        if not fs_path:
            return fs_path
        nfc = unicodedata.normalize("NFC", fs_path)
        if self.is_mac:
            nfc = nfc.replace(_MAC_FOLDER_SEP_SUBSTITUTE, "/")
        return nfc

    # -----------------------------------------------------------------
    # Convenience
    # -----------------------------------------------------------------

    def is_canonical(self, path_str: str) -> bool:
        """True wenn der Pfad bereits in canonical-Form ist (NFC, kein ' : ')."""
        if not path_str:
            return True
        if unicodedata.normalize("NFC", path_str) != path_str:
            return False
        if self.is_mac and _MAC_FOLDER_SEP_SUBSTITUTE in path_str:
            return False
        return True


# Singleton — Resolver ist plattform-fest, kein State pro Aufruf.
_default_resolver: PathResolver | None = None


def get_resolver() -> PathResolver:
    """Liefert den Default-Resolver (plattform-auto-detected)."""
    global _default_resolver
    if _default_resolver is None:
        _default_resolver = PathResolver()
    return _default_resolver
