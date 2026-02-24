#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
APPDIR="$BUILD_DIR/VPNShuttle.AppDir"

echo "=== Building VPN Shuttle AppImage ==="

rm -rf "$BUILD_DIR"
mkdir -p "$APPDIR"

mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/lib/vpn_shuttle"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/128x128/apps"
mkdir -p "$APPDIR/usr/share/icons/hicolor/scalable/apps"

cp -r "$SCRIPT_DIR/vpn_shuttle" "$APPDIR/usr/lib/"
find "$APPDIR/usr/lib/vpn_shuttle" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
cp -r "$SCRIPT_DIR/resources" "$APPDIR/usr/lib/resources"

cp "$SCRIPT_DIR/vpn-shuttle.desktop" "$APPDIR/usr/share/applications/"
cp "$SCRIPT_DIR/vpn-shuttle.desktop" "$APPDIR/"
cp "$SCRIPT_DIR/resources/vpn-shuttle.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/"
cp "$SCRIPT_DIR/resources/vpn-shuttle.svg" "$APPDIR/"
cp "$SCRIPT_DIR/resources/vpn-shuttle.svg" "$APPDIR/vpn-shuttle.svg"

cat > "$APPDIR/usr/bin/vpn-shuttle-gui" << 'LAUNCHER'
#!/bin/bash
SELF_DIR="$(dirname "$(readlink -f "$0")")"
export PYTHONPATH="$SELF_DIR/../lib:$PYTHONPATH"
exec python3 -m vpn_shuttle "$@"
LAUNCHER
chmod +x "$APPDIR/usr/bin/vpn-shuttle-gui"

cat > "$APPDIR/AppRun" << 'APPRUN'
#!/bin/bash
SELF="$(readlink -f "$0")"
HERE="${SELF%/*}"
export PATH="${HERE}/usr/bin:${PATH}"
export PYTHONPATH="${HERE}/usr/lib:${PYTHONPATH}"
exec python3 -m vpn_shuttle "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

APPIMAGETOOL="$BUILD_DIR/appimagetool"
if [ ! -f "$APPIMAGETOOL" ]; then
    echo "Downloading appimagetool..."
    ARCH=$(uname -m)
    curl -fsSL -o "$APPIMAGETOOL" \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    chmod +x "$APPIMAGETOOL"
fi

echo "Building AppImage..."
ARCH=$(uname -m) "$APPIMAGETOOL" "$APPDIR" "$BUILD_DIR/VPN_Shuttle-${ARCH}.AppImage"

echo ""
echo "=== Build complete ==="
echo "AppImage: $BUILD_DIR/VPN_Shuttle-$(uname -m).AppImage"
