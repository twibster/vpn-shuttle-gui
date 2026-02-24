import gi
import threading
import sys

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gdk

from vpn_shuttle import APP_ID, APP_NAME
from vpn_shuttle.config import AppConfig
from vpn_shuttle.backend import VPNBackend
from vpn_shuttle.widgets.status import StatusPanel
from vpn_shuttle.widgets.logs import LogViewer
from vpn_shuttle.widgets.routing import RoutingEditor
from vpn_shuttle.widgets.settings import SettingsDialog

CSS = """
.status-connected { color: #2ec27e; font-size: 24px; }
.status-connecting { color: #e5a50a; font-size: 24px; }
.status-disconnected { color: #c01c28; font-size: 24px; }
.log-view {
    font-size: 12px;
    padding: 8px;
    background: rgba(0,0,0,0.05);
}
.connect-btn { min-width: 120px; }
"""


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title(APP_NAME)
        self.set_default_size(700, 700)

        self._config = AppConfig()
        self._backend = VPNBackend(self._config)
        self._host_ids = []
        self._switching_host = False

        self._build_ui()

        self._backend.set_log_callback(self._log_viewer.append_log)
        self._backend.set_status_callback(self._on_status_changed)

        self._refresh_hosts()

        if self._config.get("routing_mode") == "specific":
            self._routing_editor._specific_radio.set_active(True)

    def _build_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        header = Adw.HeaderBar()

        selector_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        host_label = Gtk.Label(label="Host:")
        selector_box.append(host_label)
        self._host_dropdown = Gtk.DropDown()
        self._host_dropdown.set_size_request(150, -1)
        self._host_dropdown.connect("notify::selected", self._on_host_changed)
        selector_box.append(self._host_dropdown)

        vpn_label = Gtk.Label(label="VPN:")
        selector_box.append(vpn_label)
        self._config_dropdown = Gtk.DropDown()
        self._config_dropdown.set_size_request(160, -1)
        selector_box.append(self._config_dropdown)

        refresh_btn = Gtk.Button()
        refresh_btn.set_icon_name("view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Refresh")
        refresh_btn.connect("clicked", lambda b: self._refresh_hosts())
        selector_box.append(refresh_btn)

        header.pack_start(selector_box)

        self._connect_btn = Gtk.Button(label="Connect")
        self._connect_btn.add_css_class("suggested-action")
        self._connect_btn.add_css_class("connect-btn")
        self._connect_btn.connect("clicked", self._on_connect_clicked)
        header.pack_end(self._connect_btn)

        settings_btn = Gtk.Button()
        settings_btn.set_icon_name("emblem-system-symbolic")
        settings_btn.set_tooltip_text("Settings")
        settings_btn.connect("clicked", self._on_settings_clicked)
        header.pack_end(settings_btn)

        main_box.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self._status_panel = StatusPanel()
        content.append(self._status_panel)

        content.append(Gtk.Separator())

        self._routing_editor = RoutingEditor()
        content.append(self._routing_editor)

        content.append(Gtk.Separator())

        self._log_viewer = LogViewer()
        self._log_viewer.set_vexpand(True)
        content.append(self._log_viewer)

        main_box.append(content)
        self.set_content(main_box)

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
            host_id = self._host_ids[idx]
            self._config.set_active_host(host_id)
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
            self._host_dropdown.set_sensitive(False)
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
            self._host_dropdown.set_sensitive(False)
            self._config_dropdown.set_sensitive(False)
            self._routing_editor.set_sensitive(False)
            self._status_panel.update_status(
                "connected",
                config_name=config_name,
                jump_host=self._config.jump_host_ip,
            )
        elif status == "connecting":
            self._connect_btn.set_label("Connecting...")
            self._connect_btn.set_sensitive(False)
        else:
            self._connect_btn.set_label("Connect")
            self._connect_btn.remove_css_class("destructive-action")
            self._connect_btn.add_css_class("suggested-action")
            self._connect_btn.set_sensitive(True)
            self._host_dropdown.set_sensitive(True)
            self._config_dropdown.set_sensitive(True)
            self._routing_editor.set_sensitive(True)
            self._status_panel.update_status("disconnected")

    def _on_settings_clicked(self, button):
        dialog = SettingsDialog(
            self, self._config, self._backend, on_hosts_changed=self._refresh_hosts
        )
        dialog.present()


class VPNShuttleApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
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
