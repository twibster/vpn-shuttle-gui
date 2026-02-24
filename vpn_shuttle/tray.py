import gi

gi.require_version("Gtk", "4.0")

try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
    HAS_INDICATOR = True
except (ValueError, ImportError):
    HAS_INDICATOR = False

if HAS_INDICATOR:
    from gi.repository import Gtk, GLib

from vpn_shuttle import APP_ID


class TrayIcon:
    def __init__(self, window):
        if not HAS_INDICATOR:
            raise ImportError("AyatanaAppIndicator3 not available")

        self._window = window
        self._connected = False

        self._indicator = AppIndicator.Indicator.new(
            APP_ID,
            "network-offline-symbolic",
            AppIndicator.IndicatorCategory.APPLICATION_STATUS,
        )
        self._indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)

        self._menu = Gtk.Menu()

        self._show_item = Gtk.MenuItem(label="Show Window")
        self._show_item.connect("activate", self._on_show)
        self._menu.append(self._show_item)

        self._status_item = Gtk.MenuItem(label="Status: Disconnected")
        self._status_item.set_sensitive(False)
        self._menu.append(self._status_item)

        separator = Gtk.SeparatorMenuItem()
        self._menu.append(separator)

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self._on_quit)
        self._menu.append(quit_item)

        self._menu.show_all()
        self._indicator.set_menu(self._menu)

    def _on_show(self, item):
        GLib.idle_add(self._toggle_window)

    def _toggle_window(self):
        if self._window.get_visible():
            self._window.set_visible(False)
            self._show_item.set_label("Show Window")
        else:
            self._window.set_visible(True)
            self._window.present()
            self._show_item.set_label("Hide Window")
        return False

    def _on_quit(self, item):
        GLib.idle_add(self._do_quit)

    def _do_quit(self):
        self._window.get_application().quit()
        return False

    def update_status(self, connected):
        self._connected = connected
        if connected:
            self._indicator.set_icon_full("network-vpn-symbolic", "VPN Connected")
            self._status_item.set_label("Status: Connected")
        else:
            self._indicator.set_icon_full("network-offline-symbolic", "VPN Disconnected")
            self._status_item.set_label("Status: Disconnected")
