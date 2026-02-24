#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APPIMAGE="$SCRIPT_DIR/build/VPN_Shuttle-$(uname -m).AppImage"
ICON="$SCRIPT_DIR/resources/vpn-shuttle.svg"
DESKTOP="$SCRIPT_DIR/vpn-shuttle.desktop"
APP_ID="com.vpnshuttle.app"

install_app() {
    if [ ! -f "$APPIMAGE" ]; then
        echo "AppImage not found. Run ./build-appimage.sh first."
        exit 1
    fi

    echo "Installing VPN Shuttle..."

    sudo cp "$APPIMAGE" /usr/local/bin/vpn-shuttle
    sudo chmod +x /usr/local/bin/vpn-shuttle

    sudo mkdir -p /usr/share/icons/hicolor/scalable/apps
    sudo cp "$ICON" "/usr/share/icons/hicolor/scalable/apps/${APP_ID}.svg"

    sudo cp "$DESKTOP" "/usr/share/applications/${APP_ID}.desktop"

    sudo gtk-update-icon-cache /usr/share/icons/hicolor/ 2>/dev/null || true
    update-desktop-database ~/.local/share/applications 2>/dev/null || true

    echo "Installed. Search 'VPN Shuttle' in your app launcher."
}

uninstall_app() {
    echo "Uninstalling VPN Shuttle..."

    sudo rm -f /usr/local/bin/vpn-shuttle
    sudo rm -f "/usr/share/icons/hicolor/scalable/apps/${APP_ID}.svg"
    sudo rm -f "/usr/share/applications/${APP_ID}.desktop"

    sudo gtk-update-icon-cache /usr/share/icons/hicolor/ 2>/dev/null || true

    echo "Uninstalled."
}

case "${1:-}" in
    install)
        install_app
        ;;
    uninstall|remove)
        uninstall_app
        ;;
    *)
        echo "Usage: $0 {install|uninstall}"
        echo ""
        echo "  install    - Install VPN Shuttle to system"
        echo "  uninstall  - Remove VPN Shuttle from system"
        exit 1
        ;;
esac
