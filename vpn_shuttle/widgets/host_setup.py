import gi
import threading
import os

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio


class AddHostDialog(Adw.MessageDialog):
    def __init__(self, parent, config, backend, on_done=None, edit_host_id=None):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self._config = config
        self._backend = backend
        self._on_done = on_done
        self._edit_host_id = edit_host_id

        if edit_host_id:
            self.set_heading("Edit Host")
            host = config.get_host(edit_host_id)
        else:
            self.set_heading("Add Jump Host")
            host = {}

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_start(8)
        content.set_margin_end(8)

        self._name_entry = Adw.EntryRow()
        self._name_entry.set_title("Display Name")
        self._name_entry.set_text(host.get("name", ""))

        self._ip_entry = Adw.EntryRow()
        self._ip_entry.set_title("Host IP")
        self._ip_entry.set_text(host.get("ip", ""))

        self._user_entry = Adw.EntryRow()
        self._user_entry.set_title("SSH User")
        self._user_entry.set_text(host.get("user", "root"))

        self._key_entry = Adw.EntryRow()
        self._key_entry.set_title("SSH Key Path")
        self._key_entry.set_text(host.get("ssh_key_path", str(os.path.expanduser("~/.ssh/id_rsa"))))

        group = Adw.PreferencesGroup()
        group.add(self._name_entry)
        group.add(self._ip_entry)
        group.add(self._user_entry)
        group.add(self._key_entry)
        content.append(group)

        self._test_label = Gtk.Label(label="")
        self._test_label.set_wrap(True)
        content.append(self._test_label)

        test_btn = Gtk.Button(label="Test Connection")
        test_btn.add_css_class("flat")
        test_btn.connect("clicked", self._on_test)
        content.append(test_btn)

        self.set_extra_child(content)

        self.add_response("cancel", "Cancel")
        if edit_host_id:
            self.add_response("save", "Save")
            self.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        else:
            self.add_response("add", "Add Host")
            self.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)

        self.connect("response", self._on_response)

    def _on_test(self, button):
        ip = self._ip_entry.get_text().strip()
        user = self._user_entry.get_text().strip()
        key = self._key_entry.get_text().strip()

        if not ip or not user or not key:
            self._test_label.set_label("Fill in all fields first")
            return

        self._test_label.set_label("Testing...")

        def test():
            ok, msg = self._backend.test_host_connection(ip, user, key)
            GLib.idle_add(self._test_label.set_label, msg)

        threading.Thread(target=test, daemon=True).start()

    def _on_response(self, dialog, response):
        if response in ("add", "save"):
            name = self._name_entry.get_text().strip()
            ip = self._ip_entry.get_text().strip()
            user = self._user_entry.get_text().strip()
            key = self._key_entry.get_text().strip()

            if not name or not ip:
                return

            if self._edit_host_id:
                self._config.update_host(self._edit_host_id, name=name, ip=ip, user=user, ssh_key_path=key)
            else:
                self._config.add_host(name, ip, user, key)

            if self._on_done:
                self._on_done()


class HostSetupDialog(Adw.Window):
    def __init__(self, parent, config, backend, host_id, on_done=None):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_title("Host Setup")
        self.set_default_size(550, 500)

        self._config = config
        self._backend = backend
        self._host_id = host_id
        self._on_done = on_done

        host = config.get_host(host_id)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)
        main_box.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_start(16)
        content.set_margin_end(16)
        content.set_margin_top(12)
        content.set_margin_bottom(12)

        info_label = Gtk.Label(
            label=f"Setting up: {host.get('name', '')} ({host.get('ip', '')})"
        )
        info_label.add_css_class("title-3")
        info_label.set_xalign(0)
        content.append(info_label)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self._log_view = Gtk.TextView()
        self._log_view.set_editable(False)
        self._log_view.set_cursor_visible(False)
        self._log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._log_view.set_monospace(True)
        self._log_buffer = self._log_view.get_buffer()
        scrolled.set_child(self._log_view)
        content.append(scrolled)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)

        self._setup_btn = Gtk.Button(label="Start Setup")
        self._setup_btn.add_css_class("suggested-action")
        self._setup_btn.connect("clicked", self._on_start_setup)
        btn_box.append(self._setup_btn)

        self._close_btn = Gtk.Button(label="Close")
        self._close_btn.connect("clicked", lambda b: self.close())
        btn_box.append(self._close_btn)

        content.append(btn_box)
        main_box.append(content)
        self.set_content(main_box)

    def _append_log(self, text):
        GLib.idle_add(self._append_log_idle, text)

    def _append_log_idle(self, text):
        end_iter = self._log_buffer.get_end_iter()
        self._log_buffer.insert(end_iter, text + "\n")
        end_mark = self._log_buffer.create_mark(None, self._log_buffer.get_end_iter(), False)
        self._log_view.scroll_mark_onscreen(end_mark)
        self._log_buffer.delete_mark(end_mark)

    def _on_start_setup(self, button):
        self._setup_btn.set_sensitive(False)
        self._setup_btn.set_label("Setting up...")

        def run_setup():
            success = self._backend.setup_host(self._host_id, log_callback=self._append_log)
            GLib.idle_add(self._on_setup_complete, success)

        threading.Thread(target=run_setup, daemon=True).start()

    def _on_setup_complete(self, success):
        if success:
            self._setup_btn.set_label("Setup Complete")
            if self._on_done:
                self._on_done()
        else:
            self._setup_btn.set_label("Setup Failed - Retry")
            self._setup_btn.set_sensitive(True)


class HostConfigsDialog(Adw.Window):
    def __init__(self, parent, config, backend, host_id, on_done=None):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_title("Manage VPN Configs")
        self.set_default_size(450, 400)

        self._config = config
        self._backend = backend
        self._host_id = host_id
        self._on_done = on_done
        self._host = config.get_host(host_id)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        header = Adw.HeaderBar()
        main_box.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_start(16)
        content.set_margin_end(16)
        content.set_margin_top(12)
        content.set_margin_bottom(12)

        self._config_group = Adw.PreferencesGroup()
        self._config_group.set_title(f"Configs on {self._host.get('name', '')}")

        upload_btn = Gtk.Button(label="Upload New Config")
        upload_btn.add_css_class("suggested-action")
        upload_btn.connect("clicked", self._on_upload)
        self._config_group.add(upload_btn)

        content.append(self._config_group)

        self._status_label = Gtk.Label(label="")
        content.append(self._status_label)

        main_box.append(content)
        self.set_content(main_box)

        self._load_configs()

    def _load_configs(self):
        def load():
            configs = self._backend.list_configs(host_override=self._host)
            GLib.idle_add(self._populate_configs, configs)

        threading.Thread(target=load, daemon=True).start()

    def _populate_configs(self, configs):
        for name in configs:
            row = Adw.ActionRow()
            row.set_title(name)

            delete_btn = Gtk.Button()
            delete_btn.set_icon_name("user-trash-symbolic")
            delete_btn.add_css_class("flat")
            delete_btn.set_valign(Gtk.Align.CENTER)
            delete_btn.connect("clicked", self._on_delete, name, row)
            row.add_suffix(delete_btn)

            self._config_group.add(row)

    def _on_upload(self, button):
        dialog = Gtk.FileDialog()
        conf_filter = Gtk.FileFilter()
        conf_filter.set_name("WireGuard configs (*.conf)")
        conf_filter.add_pattern("*.conf")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(conf_filter)
        dialog.set_filters(filters)
        dialog.open(self, None, self._on_file_selected)

    def _on_file_selected(self, dialog, result):
        try:
            file = dialog.open_finish(result)
            if not file:
                return
            path = file.get_path()
            name = os.path.splitext(os.path.basename(path))[0]

            if len(name) > 15:
                self._status_label.set_label(f"'{name}' is {len(name)} chars (max 15)")
                return

            self._status_label.set_label(f"Uploading {name}...")

            def upload():
                ok, msg = self._backend.upload_config(path, name, host_override=self._host)
                GLib.idle_add(self._on_upload_done, ok, msg, name)

            threading.Thread(target=upload, daemon=True).start()
        except Exception:
            pass

    def _on_upload_done(self, ok, msg, name):
        self._status_label.set_label(msg)
        if ok:
            row = Adw.ActionRow()
            row.set_title(name)
            delete_btn = Gtk.Button()
            delete_btn.set_icon_name("user-trash-symbolic")
            delete_btn.add_css_class("flat")
            delete_btn.set_valign(Gtk.Align.CENTER)
            delete_btn.connect("clicked", self._on_delete, name, row)
            row.add_suffix(delete_btn)
            self._config_group.add(row)
            if self._on_done:
                self._on_done()

    def _on_delete(self, button, name, row):
        def delete():
            ok, msg = self._backend.delete_config(name, host_override=self._host)
            if ok:
                GLib.idle_add(self._config_group.remove, row)
                if self._on_done:
                    GLib.idle_add(self._on_done)

        threading.Thread(target=delete, daemon=True).start()
