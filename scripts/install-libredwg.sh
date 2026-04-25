#!/usr/bin/env bash
# Installiert libredwg (GNU, GPL-3) lokal nach ~/.local/libredwg/
#
# Wir bauen aus Source, weil libredwg nicht in Homebrew-core ist und
# wir keine system-wide Installation wollen. Reversibel: einfach
# `rm -rf ~/.local/libredwg` ausfuehren.
#
# Voraussetzungen:
#   - Homebrew (system oder ~/homebrew) mit autoconf, automake, pkg-config
#   - Xcode CLT fuer gcc/clang/make
#
# Aufruf:
#   bash scripts/install-libredwg.sh           # Default-Build
#   LIBREDWG_VERSION=0.13.4 bash ...           # andere Version
set -euo pipefail

VERSION="${LIBREDWG_VERSION:-0.13.4}"
PREFIX="${HOME}/.local/libredwg"
BUILD_DIR="${TMPDIR:-/tmp}/libredwg-build-${VERSION}"
TARBALL_URL="https://github.com/LibreDWG/libredwg/releases/download/${VERSION}/libredwg-${VERSION}.tar.xz"

echo "==> libredwg ${VERSION} → ${PREFIX}"

# 1. Build-Werkzeuge pruefen
for tool in autoconf automake pkg-config make; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "FEHLER: '$tool' nicht im PATH gefunden."
    echo "  Auf macOS: brew install autoconf automake pkg-config (oder system-wide via /opt/homebrew)."
    exit 1
  fi
done

# 2. Quelldatei laden + auspacken
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"
if [ ! -f "libredwg-${VERSION}.tar.xz" ]; then
  echo "==> Lade Source-Tarball …"
  curl -sSL "$TARBALL_URL" -o "libredwg-${VERSION}.tar.xz"
fi
if [ ! -d "libredwg-${VERSION}" ]; then
  tar xJf "libredwg-${VERSION}.tar.xz"
fi

# 3. Bauen + installieren
cd "libredwg-${VERSION}"
echo "==> ./configure --prefix=$PREFIX --disable-bindings"
./configure --prefix="$PREFIX" --disable-bindings >/dev/null
echo "==> make (paralleler Build)"
make -j"$(sysctl -n hw.ncpu 2>/dev/null || echo 4)" >/dev/null
echo "==> make install"
make install >/dev/null

# 4. Smoke-Test
echo
"$PREFIX/bin/dwg2dxf" --version | head -1

echo
echo "==> libredwg installiert. Disco erkennt es automatisch unter:"
echo "    $PREFIX/bin/dwg2dxf"
echo
echo "Optional: ergaenze deine Shell-Umgebung mit"
echo "    export PATH=\"$PREFIX/bin:\$PATH\""
echo
echo "Build-Reste in $BUILD_DIR koennen geloescht werden:"
echo "    rm -rf $BUILD_DIR"
