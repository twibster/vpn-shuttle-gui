import gi
import os

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio


class SettingsDialog(Adw.PreferencesWindow):
    def __init__(self, parent, config, backend, on_config_changed=None):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_title("Settings")
        self.set_default_size(500, 500)

        self._config = config
        self._backend = backend
        self._on_config_changed = on_config_changed

        conn_page = Adw.PreferencesPage()
        conn_page.set_title("Connection")
        conn_page.set_icon_name("network-server-symbolic")

        conn_group = Adw.PreferencesGroup()
        conn_group.set_title("Jump Host")

        self._ip_row = Adw.EntryRow()
        self._ip_row.set_title("Host IP")
        self._ip_row.set_text(config.get("jump_host_ip"))
        conn_group.add(self._ip_row)

        self._user_row = Adw.EntryRow()
        self._user_row.set_title("SSH User")
        self._user_row.set_text(config.get("jump_host_user"))
        conn_group.add(self._user_row)

        self._key_row = Adw.EntryRow()
        self._key_row.set_title("SSH Key Path")
        self._key_row.set_text(config.get("ssh_key_path"))
        conn_group.add(self._key_row)

        test_btn = Gtk.Button(label="Test Connection")
        test_btn.add_css_class("suggested-action")
        test_btn.set_margin_top(8)
        test_btn.connect("clicked", self._on_test_connection)
        conn_group.add(test_btn)

        self._test_label = Gtk.Label(label="")
        self._test_label.set_margin_top(4)
        conn_group.add(self._test_label)

        conn_page.add(conn_group)
        self.add(conn_page)

        config_page = Adw.PreferencesPage()
        config_page.set_title("VPN Configs")
        config_page.set_icon_name("document-properties-symbolic")

        self._config_group = Adw.PreferencesGroup()
        self._config_group.set_title("WireGuard Configs on Jump Host")

        upload_btn = Gtk.Button(label="Upload New Config")
        upload_btn.add_css_class("suggested-action")
        upload_btn.connect("clicked", self._on_upload_config)
        self._config_group.add(upload_btn)

        config_page.add(self._config_group)
        self.add(config_page)

        self._load_remote_configs()

        self.connect("close-request", self._on_close)

    def _load_remote_configs(self):
        import threading

        def load():
            configs = self._backend.list_configs()
            from gi.repository import GLib

            GLib.idle_add(self._populate_configs, configs)

        threading.Thread(target=load, daemon=True).start()

    def _populate_configs(self, configs):
        for name in configs:
            row = Adw.ActionRow()
            row.set_title(name)
            row.set_subtitle("WireGuard configuration")

            delete_btn = Gtk.Button()
            delete_btn.set_icon_name("user-trash-symbolic")
            delete_btn.add_css_class("flat")
            delete_btn.set_valign(Gtk.Align.CENTER)
            delete_btn.connect("clicked", self._on_delete_config, name)
            row.add_suffix(delete_btn)

            self._config_group.add(row)

    def _on_test_connection(self, button):
        self._test_label.set_label("Testing...")
        import threading

        def test():
            import subprocess
            try:
                result = subprocess.run(
                    [
                        "ssh", "-o", "ConnectTimeout=5",
                        "-o", "StrictHostKeyChecking=no",
                        "-i", self._key_row.get_text(),
                        f"{self._user_row.get_text()}@{self._ip_row.get_text()}",
                        "echo 'Connection successful'",
                    ],
                    capture_output=True, text=True, timeout=10,
                )
                msg = "Connected!" if result.returncode == 0 else f"Failed: {result.stderr.strip()}"
            except Exception as e:
                msg = f"Error: {e}"
            from gi.repository import GLib
            GLib.idle_add(self._test_label.set_label, msg)

        threading.Thread(target=test, daemon=True).start()

    def _on_upload_config(self, button):
        dialog = Gtk.FileDialog()
        conf_filter = Gtk.FileFilter()
        conf_filter.set_name("WireGuard configs (*.conf)")
        conf_filter.add_pattern("*.conf")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(conf_filter)
        dialog.set_filters(filters)
        dialog.open(self, None, self._on_upload_file_selected)

    def _on_upload_file_selected(self, dialog, result):
        try:
            file = dialog.open_finish(result)
            if file:
                path = file.get_path()
                name = os.path.splitext(os.path.basename(path))[0]

                if len(name) > 15:
                    dlg = Adw.MessageDialog.new(
                        self,
                        "Name Too Long",
                        f"'{name}' is {len(name)} chars. Linux interface names max 15 chars. Rename the file first.",
                    )
                    dlg.add_response("ok", "OK")
                    dlg.present()
                    return

                import threading

                def upload():
                    ok, msg = self._backend.upload_config(path, name)
                    from gi.repository import GLib
                    GLib.idle_add(self._on_upload_done, ok, msg, name)

                threading.Thread(target=upload, daemon=True).start()
        except Exception:
            pass

    def _on_upload_done(self, ok, msg, name):
        if ok:
            row = Adw.ActionRow()
            row.set_title(name)
            row.set_subtitle("WireGuard configuration")
            delete_btn = Gtk.Button()
            delete_btn.set_icon_name("user-trash-symbolic")
            delete_btn.add_css_class("flat")
            delete_btn.set_valign(Gtk.Align.CENTER)
            delete_btn.connect("clicked", self._on_delete_config, name)
            row.add_suffix(delete_btn)
            self._config_group.add(row)
            if self._on_config_changed:
                self._on_config_changed()

    def _on_delete_config(self, button, name):
        dlg = Adw.MessageDialog.new(
            self, "Delete Config?", f"Remove '{name}' from the jump host?"
        )
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("delete", "Delete")
        dlg.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.connect("response", self._on_delete_response, name, button)
        dlg.present()

    def _on_delete_response(self, dialog, response, name, button):
        if response == "delete":
            import threading

            def delete():
                ok, msg = self._backend.delete_config(name)
                from gi.repository import GLib
                if ok:
                    GLib.idle_add(self._remove_config_row, button)
                    if self._on_config_changed:
                        GLib.idle_add(self._on_config_changed)

            threading.Thread(target=delete, daemon=True).start()

    def _remove_config_row(self, button):
        row = button.get_parent()
        if row:
            self._config_group.remove(row)

    def _on_close(self, window):
        self._config.set("jump_host_ip", self._ip_row.get_text())
        self._config.set("jump_host_user", self._user_row.get_text())
        self._config.set("ssh_key_path", self._key_row.get_text())
        return False
