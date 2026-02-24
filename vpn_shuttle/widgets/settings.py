import gi
import threading

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from vpn_shuttle.widgets.host_setup import AddHostDialog, HostSetupDialog, HostConfigsDialog


class SettingsDialog(Adw.PreferencesWindow):
    def __init__(self, parent, config, backend, on_hosts_changed=None):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_title("Settings")
        self.set_default_size(550, 550)

        self._config = config
        self._backend = backend
        self._on_hosts_changed = on_hosts_changed
        self._parent = parent

        hosts_page = Adw.PreferencesPage()
        hosts_page.set_title("Hosts")
        hosts_page.set_icon_name("network-server-symbolic")

        self._hosts_group = Adw.PreferencesGroup()
        self._hosts_group.set_title("Jump Hosts")

        add_btn = Gtk.Button(label="Add Host")
        add_btn.add_css_class("suggested-action")
        add_btn.connect("clicked", self._on_add_host)
        self._hosts_group.add(add_btn)

        hosts_page.add(self._hosts_group)
        self.add(hosts_page)

        self._populate_hosts()

    def _populate_hosts(self):
        hosts = self._config.get_hosts()
        for host_id, host in hosts.items():
            self._add_host_row(host_id, host)

    def _add_host_row(self, host_id, host):
        row = Adw.ExpanderRow()
        row.set_title(host.get("name", "Unknown"))
        status = "Ready" if host.get("setup_complete") else "Not configured"
        row.set_subtitle(f"{host.get('ip', '')} ({host.get('user', 'root')}) — {status}")

        setup_row = Adw.ActionRow()
        setup_row.set_title("Setup Host")
        setup_row.set_subtitle("Install WireGuard, vpn-manage, enable forwarding")
        setup_btn = Gtk.Button()
        setup_btn.set_icon_name("emblem-system-symbolic")
        setup_btn.add_css_class("flat")
        setup_btn.set_valign(Gtk.Align.CENTER)
        setup_btn.connect("clicked", self._on_setup_host, host_id)
        setup_row.add_suffix(setup_btn)
        setup_row.set_activatable_widget(setup_btn)
        row.add_row(setup_row)

        configs_row = Adw.ActionRow()
        configs_row.set_title("Manage VPN Configs")
        configs_row.set_subtitle("Upload or remove WireGuard configurations")
        configs_btn = Gtk.Button()
        configs_btn.set_icon_name("document-properties-symbolic")
        configs_btn.add_css_class("flat")
        configs_btn.set_valign(Gtk.Align.CENTER)
        configs_btn.connect("clicked", self._on_manage_configs, host_id)
        configs_row.add_suffix(configs_btn)
        configs_row.set_activatable_widget(configs_btn)
        row.add_row(configs_row)

        edit_row = Adw.ActionRow()
        edit_row.set_title("Edit Host")
        edit_row.set_subtitle("Change name, IP, credentials")
        edit_btn = Gtk.Button()
        edit_btn.set_icon_name("document-edit-symbolic")
        edit_btn.add_css_class("flat")
        edit_btn.set_valign(Gtk.Align.CENTER)
        edit_btn.connect("clicked", self._on_edit_host, host_id)
        edit_row.add_suffix(edit_btn)
        edit_row.set_activatable_widget(edit_btn)
        row.add_row(edit_row)

        delete_row = Adw.ActionRow()
        delete_row.set_title("Delete Host")
        delete_btn = Gtk.Button()
        delete_btn.set_icon_name("user-trash-symbolic")
        delete_btn.add_css_class("flat")
        delete_btn.set_valign(Gtk.Align.CENTER)
        delete_btn.connect("clicked", self._on_delete_host, host_id, row)
        delete_row.add_suffix(delete_btn)
        delete_row.set_activatable_widget(delete_btn)
        row.add_row(delete_row)

        self._hosts_group.add(row)

    def _on_add_host(self, button):
        dialog = AddHostDialog(self, self._config, self._backend, on_done=self._refresh)
        dialog.present()

    def _on_setup_host(self, button, host_id):
        dialog = HostSetupDialog(self, self._config, self._backend, host_id, on_done=self._refresh)
        dialog.present()

    def _on_manage_configs(self, button, host_id):
        dialog = HostConfigsDialog(
            self, self._config, self._backend, host_id,
            on_done=lambda: self._on_hosts_changed() if self._on_hosts_changed else None
        )
        dialog.present()

    def _on_edit_host(self, button, host_id):
        dialog = AddHostDialog(self, self._config, self._backend, on_done=self._refresh, edit_host_id=host_id)
        dialog.present()

    def _on_delete_host(self, button, host_id, row):
        dlg = Adw.MessageDialog.new(self, "Delete Host?", "This will remove the host from your list.")
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("delete", "Delete")
        dlg.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.connect("response", self._on_delete_response, host_id, row)
        dlg.present()

    def _on_delete_response(self, dialog, response, host_id, row):
        if response == "delete":
            self._config.remove_host(host_id)
            self._hosts_group.remove(row)
            if self._on_hosts_changed:
                self._on_hosts_changed()

    def _refresh(self):
        to_remove = []
        child = self._hosts_group.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            if isinstance(child, Adw.ExpanderRow):
                to_remove.append(child)
            child = next_child
        for c in to_remove:
            self._hosts_group.remove(c)
        self._populate_hosts()
        if self._on_hosts_changed:
            self._on_hosts_changed()
