"""Unit-Tests fuer den PathResolver. Plattform-unabhaengig — wir testen
Mac-Verhalten explizit per platform-Override.
"""

from __future__ import annotations

import unicodedata

import pytest

from disco.fs.path_resolver import PathResolver


# ----------------------------------------------------------------
# canonical → fs (NFD-Konvertierung)
# ----------------------------------------------------------------


def test_to_fs_identity_on_linux():
    r = PathResolver(platform="linux")
    assert r.to_fs("Übersicht.pdf") == "Übersicht.pdf"
    assert r.to_fs("Konformitätserklärung.pdf") == "Konformitätserklärung.pdf"


def test_to_fs_nfd_on_mac():
    r = PathResolver(platform="darwin")
    # NFC-Input → NFD-Output
    nfc = "Übersicht.pdf"
    fs = r.to_fs(nfc)
    # ü = U+00FC (NFC) wird zu u + Combining-Diaeresis (NFD)
    assert "̈" in fs  # Combining-Diaeresis muss drin sein
    assert unicodedata.normalize("NFC", fs) == nfc


def test_to_fs_empty():
    r = PathResolver(platform="darwin")
    assert r.to_fs("") == ""
    assert r.to_fs("plain ascii.pdf") == "plain ascii.pdf"


# ----------------------------------------------------------------
# fs → canonical (NFC + ' : ' Substitution rueckwaerts)
# ----------------------------------------------------------------


def test_to_canonical_nfd_to_nfc_on_mac():
    r = PathResolver(platform="darwin")
    nfd = unicodedata.normalize("NFD", "Übersicht.pdf")
    assert r.to_canonical(nfd) == "Übersicht.pdf"


def test_to_canonical_colon_to_slash_on_mac():
    r = PathResolver(platform="darwin")
    assert r.to_canonical("10 Dok : 10.04 Foo/Bar.pdf") == "10 Dok/10.04 Foo/Bar.pdf"


def test_to_canonical_no_colon_replace_on_linux():
    r = PathResolver(platform="linux")
    # Auf Linux sind ' : ' kein OneDrive-Quirk — bleiben drin.
    assert r.to_canonical("foo : bar") == "foo : bar"


def test_to_canonical_combined_on_mac():
    r = PathResolver(platform="darwin")
    nfd = unicodedata.normalize("NFD", "10 Dok : 10.04 Übersicht/datei.pdf")
    canonical = r.to_canonical(nfd)
    assert canonical == "10 Dok/10.04 Übersicht/datei.pdf"


# ----------------------------------------------------------------
# Roundtrip-Idempotency
# ----------------------------------------------------------------


@pytest.mark.parametrize(
    "canonical",
    [
        "Übersicht.pdf",
        "Konformitätserklärung_WAGO_Klemme.pdf",
        "10 Dokumentation/10.04 Projektdoku/foo.pdf",
        "Türen/Bürobereich/datei.pdf",
        "RSD_EFA010_IT-Infrastruktur Reuter REA-DeNOx Übersicht Datenverteiler_R0E_V00.pdf",
        "Müller & Söhne ½ Maß.txt",
        "plain ascii.txt",
        "",
    ],
)
def test_roundtrip_idempotent_mac(canonical):
    r = PathResolver(platform="darwin")
    fs = r.to_fs(canonical)
    canonical_again = r.to_canonical(fs)
    assert canonical_again == canonical, (
        f"Roundtrip-Fail: {canonical!r} → {fs!r} → {canonical_again!r}"
    )


@pytest.mark.parametrize(
    "canonical",
    [
        "Übersicht.pdf",
        "10 Dok/10.04 Foo/x.pdf",
        "Müller & Söhne.txt",
    ],
)
def test_roundtrip_idempotent_linux(canonical):
    r = PathResolver(platform="linux")
    fs = r.to_fs(canonical)
    canonical_again = r.to_canonical(fs)
    assert canonical_again == canonical


# ----------------------------------------------------------------
# is_canonical
# ----------------------------------------------------------------


def test_is_canonical_true_on_nfc():
    r = PathResolver(platform="darwin")
    assert r.is_canonical("Übersicht.pdf")
    assert r.is_canonical("plain ascii.txt")
    assert r.is_canonical("")


def test_is_canonical_false_on_nfd():
    r = PathResolver(platform="darwin")
    nfd = unicodedata.normalize("NFD", "Übersicht.pdf")
    assert not r.is_canonical(nfd)


def test_is_canonical_false_on_colon_sub_on_mac():
    r = PathResolver(platform="darwin")
    assert not r.is_canonical("10 Dok : 10.04 Foo/x.pdf")


def test_is_canonical_true_on_colon_sub_on_linux():
    # Auf Linux ist ' : ' kein Quirk — bleibt als valid canonical
    r = PathResolver(platform="linux")
    assert r.is_canonical("10 Dok : 10.04 Foo/x.pdf")


# ----------------------------------------------------------------
# to_fs_resolved gegen REAL-Filesystem (rea-denox)
# ----------------------------------------------------------------


def test_resolved_against_real_filesystem(tmp_path):
    """Schreibt synthetische Dateien mit NFD-Namen, prueft Resolver findet sie."""
    r = PathResolver(platform="darwin")

    # Mac-Filesystem-Bytes: NFD
    nfd_name = unicodedata.normalize("NFD", "Übersicht.pdf")
    (tmp_path / nfd_name).write_text("content")

    # Resolver findet die Datei von canonical NFC
    resolved = r.to_fs_resolved("Übersicht.pdf", tmp_path)
    assert resolved.exists(), f"Resolver fand nichts: {resolved}"
