import gi
import threading
import sys

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gdk, Gio

from vpn_shuttle import APP_ID, APP_NAME
from vpn_shuttle.config import AppConfig
from vpn_shuttle.backend import VPNBackend
from vpn_shuttle.widgets.status import StatusPanel
from vpn_shuttle.widgets.logs import LogViewer
from vpn_shuttle.widgets.routing import RoutingEditor
from vpn_shuttle.widgets.settings import SettingsDialog

CSS = """
.connect-btn { min-width: 120px; }

.status-card {
    border-radius: 12px;
    padding: 16px;
    transition: background 200ms ease;
}
.status-card-disconnected {
    background: alpha(@error_color, 0.08);
    border: 1px solid alpha(@error_color, 0.15);
}
.status-card-connected {
    background: alpha(@success_color, 0.08);
    border: 1px solid alpha(@success_color, 0.15);
}
.status-card-connecting {
    background: alpha(@warning_color, 0.08);
    border: 1px solid alpha(@warning_color, 0.15);
}
.status-icon-disconnected { color: #ff6b6b; }
.status-icon-connected { color: @success_color; }
.status-icon-connecting { color: @warning_color; }
.status-value { font-weight: bold; }

.routing-card {
    border-radius: 12px;
    padding: 16px;
    background: alpha(@card_bg_color, 0.5);
    border: 1px solid alpha(@borders, 0.5);
}
.mode-toggle {
    min-width: 100px;
}

.log-frame {
    border-radius: 12px;
    background: alpha(@card_bg_color, 0.5);
    border: 1px solid alpha(@borders, 0.5);
}
.log-header {
    padding: 10px 16px;
}
.log-view {
    font-size: 12px;
    padding: 8px 16px;
    background: transparent;
}
"""


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title(APP_NAME)
        self.set_icon_name(APP_ID)
        self.set_default_size(700, 700)

        self._config = AppConfig()
        self._backend = VPNBackend(self._config)
        self._host_ids = []
        self._switching_host = False
        self._pending_reconnect = False
        self._build_ui()

        self._backend.set_log_callback(self._log_viewer.append_log)
        self._backend.set_status_callback(self._on_status_changed)

        self._refresh_hosts()

        if self._config.get("routing_mode") != "all":
            self._routing_editor._specific_btn.set_active(True)

        self._pending_auto_connect = bool(self._config.get("auto_connect"))

    def _build_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label())

        settings_btn = Gtk.Button()
        settings_btn.set_icon_name("emblem-system-symbolic")
        settings_btn.set_tooltip_text("Settings")
        settings_btn.connect("clicked", self._on_settings_clicked)
        header.pack_start(settings_btn)

        host_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        host_label = Gtk.Label(label="Host:")
        host_label.add_css_class("dim-label")
        host_box.append(host_label)
        self._host_dropdown = Gtk.DropDown()
        self._host_dropdown.set_size_request(140, -1)
        self._host_dropdown.connect("notify::selected", self._on_host_changed)
        host_box.append(self._host_dropdown)
        header.pack_start(host_box)

        vpn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        vpn_label = Gtk.Label(label="VPN:")
        vpn_label.add_css_class("dim-label")
        vpn_box.append(vpn_label)
        self._config_dropdown = Gtk.DropDown()
        self._config_dropdown.set_size_request(150, -1)
        self._config_dropdown.connect("notify::selected", self._on_config_changed)
        vpn_box.append(self._config_dropdown)
        refresh_btn = Gtk.Button()
        refresh_btn.set_icon_name("view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Refresh")
        refresh_btn.connect("clicked", lambda b: self._refresh_hosts())
        vpn_box.append(refresh_btn)
        header.pack_start(vpn_box)

        self._connect_btn = Gtk.Button(label="Connect")
        self._connect_btn.add_css_class("suggested-action")
        self._connect_btn.add_css_class("connect-btn")
        self._connect_btn.connect("clicked", self._on_connect_clicked)
        header.pack_end(self._connect_btn)

        main_box.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_start(16)
        content.set_margin_end(16)
        content.set_margin_top(12)
        content.set_margin_bottom(12)

        self._status_panel = StatusPanel()
        content.append(self._status_panel)

        self._routing_editor = RoutingEditor()
        self._routing_editor.set_on_changed(self._on_routing_changed)
        content.append(self._routing_editor)

        self._log_viewer = LogViewer()
        self._log_viewer.set_vexpand(True)
        content.append(self._log_viewer)

        main_box.append(content)
        self.set_content(main_box)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

    def _on_key_pressed(self, ctrl, keyval, keycode, state):
        if not (state & Gdk.ModifierType.CONTROL_MASK):
            return False
        if keyval == Gdk.KEY_d and not self._backend.is_connected and self._connect_btn.get_sensitive():
            self._on_connect_clicked(self._connect_btn)
            return True
        if keyval == Gdk.KEY_c and self._backend.is_connected and self._connect_btn.get_sensitive():
            self._on_connect_clicked(self._connect_btn)
            return True
        return False

    def _reconnect(self):
        self._pending_reconnect = True
        self._connect_btn.set_label("Reconnecting...")
        self._connect_btn.set_sensitive(False)
        self._backend.disconnect()

    def _on_config_changed(self, dropdown, param):
        if self._switching_host:
            return
        if dropdown.get_selected() == Gtk.INVALID_LIST_POSITION:
            return
        if self._backend.is_connected:
            self._reconnect()

    def _on_routing_changed(self):
        self._config.set(
            "routing_mode",
            "all" if self._routing_editor.is_all_traffic else "specific",
        )
        if self._backend.is_connected:
            self._reconnect()

    def _try_auto_connect(self):
        if self._config.jump_host and not self._backend.is_connected:
            item = self._config_dropdown.get_selected_item()
            if item and item.get_string():
                self._on_connect_clicked(self._connect_btn)

    def _refresh_hosts(self):
        hosts = self._config.get_hosts()
        self._host_ids = list(hosts.keys())

        model = Gtk.StringList()
        for host_id in self._host_ids:
            host = hosts[host_id]
            model.append(host.get("name", host.get("ip", "Unknown")))

        self._switching_host = True
        self._host_dropdown.set_model(model)

        active_id = self._config.get_active_host_id()
        if active_id in self._host_ids:
            self._host_dropdown.set_selected(self._host_ids.index(active_id))
        elif self._host_ids:
            self._host_dropdown.set_selected(0)
            self._config.set_active_host(self._host_ids[0])
        self._switching_host = False

        self._refresh_configs()

    def _on_host_changed(self, dropdown, param):
        if self._switching_host:
            return
        idx = dropdown.get_selected()
        if idx < len(self._host_ids):
            was_connected = self._backend.is_connected
            host_id = self._host_ids[idx]
            self._config.set_active_host(host_id)
            if was_connected:
                self._pending_reconnect = True
                self._connect_btn.set_label("Reconnecting...")
                self._connect_btn.set_sensitive(False)
                self._backend.disconnect()
            self._refresh_configs()

    def _refresh_configs(self):
        if not self._config.jump_host:
            self._config_dropdown.set_model(Gtk.StringList())
            return

        def load():
            configs = self._backend.list_configs()
            GLib.idle_add(self._populate_config_dropdown, configs)

        threading.Thread(target=load, daemon=True).start()

    def _populate_config_dropdown(self, configs):
        model = Gtk.StringList()
        for name in configs:
            model.append(name)
        self._config_dropdown.set_model(model)

        last = self._config.get("last_config")
        if last and last in configs:
            self._config_dropdown.set_selected(configs.index(last))

        last_config = self._config.get("last_config")
        if last_config:
            routes = self._config.get_routes_for_config(last_config)
            if routes:
                self._routing_editor.set_subnets(routes)

        if self._pending_auto_connect:
            self._pending_auto_connect = False
            self._try_auto_connect()

    def _get_selected_config(self) -> str:
        item = self._config_dropdown.get_selected_item()
        if item:
            return item.get_string()
        return ""

    def _on_connect_clicked(self, button):
        if self._backend.is_connected:
            self._connect_btn.set_sensitive(False)
            self._connect_btn.set_label("Disconnecting...")
            self._backend.disconnect()
        else:
            if not self._config.jump_host:
                self._log_viewer.append_log("No host selected. Add one in Settings.")
                return

            config_name = self._get_selected_config()
            if not config_name:
                self._log_viewer.append_log("No VPN config selected.")
                return

            subnets = self._routing_editor.get_subnets()
            if not subnets:
                self._log_viewer.append_log("No routes specified.")
                return

            self._config.set("last_config", config_name)
            self._config.set(
                "routing_mode",
                "all" if self._routing_editor.is_all_traffic else "specific",
            )
            if not self._routing_editor.is_all_traffic:
                self._config.set_routes_for_config(config_name, subnets)

            self._connect_btn.set_sensitive(False)
            self._connect_btn.set_label("Connecting...")
            self._status_panel.update_status(
                "connecting",
                config_name=config_name,
                jump_host=self._config.jump_host_ip,
            )

            def get_endpoint_and_connect():
                endpoint = self._backend.get_vpn_endpoint(config_name)
                GLib.idle_add(
                    self._status_panel.update_status,
                    "connecting",
                    config_name,
                    self._config.jump_host_ip,
                    endpoint,
                )
                self._backend.connect(config_name, subnets)

            threading.Thread(target=get_endpoint_and_connect, daemon=True).start()

    def _on_status_changed(self, status, config_name=None):
        GLib.idle_add(self._update_ui_status, status, config_name)

    def _update_ui_status(self, status, config_name):
        if status == "connected":
            self._connect_btn.set_label("Disconnect")
            self._connect_btn.remove_css_class("suggested-action")
            self._connect_btn.add_css_class("destructive-action")
            self._connect_btn.set_sensitive(True)
            self._status_panel.update_status(
                "connected",
                config_name=config_name,
                jump_host=self._config.jump_host_ip,
            )
            self._status_panel.start_stats(self._backend)
            self._send_notification("VPN Connected", f"Connected to {config_name}")
        elif status == "connecting":
            self._connect_btn.set_label("Connecting...")
            self._connect_btn.set_sensitive(False)
        else:
            self._status_panel.update_status("disconnected")
            self._status_panel.stop_stats()
            if self._pending_reconnect:
                self._pending_reconnect = False
                self._on_connect_clicked(self._connect_btn)
                return
            self._connect_btn.set_label("Connect")
            self._connect_btn.remove_css_class("destructive-action")
            self._connect_btn.add_css_class("suggested-action")
            self._connect_btn.set_sensitive(True)
            self._send_notification("VPN Disconnected", "Connection ended")

    def _send_notification(self, title, body):
        if not self._config.get("notifications"):
            return
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        self.get_application().send_notification(None, notification)

    def _on_settings_clicked(self, button):
        dialog = SettingsDialog(
            self, self._config, self._backend, on_hosts_changed=self._refresh_hosts
        )
        dialog.present()


class VPNShuttleApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        Gtk.Window.set_default_icon_name(APP_ID)
        display = Gdk.Display.get_default()
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(CSS, -1)
        Gtk.StyleContext.add_provider_for_display(
            display, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        win = self.get_active_window()
        if not win:
            win = MainWindow(self)
        win.present()


def main():
    app = VPNShuttleApp()
    app.run(sys.argv)
