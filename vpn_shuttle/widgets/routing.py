import gi
import re

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio


class RoutingEditor(Gtk.Frame):
    def __init__(self):
        super().__init__()
        self.add_css_class("routing-card")
        self.set_label_widget(None)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_start(4)
        box.set_margin_end(4)
        box.set_margin_top(4)
        box.set_margin_bottom(4)

        mode_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        label = Gtk.Label(label="Routing")
        label.add_css_class("title-4")
        label.set_hexpand(True)
        label.set_xalign(0)
        mode_row.append(label)

        toggle_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        toggle_box.add_css_class("linked")

        self._all_btn = Gtk.ToggleButton(label="All Traffic")
        self._all_btn.set_active(True)
        self._all_btn.add_css_class("mode-toggle")
        self._all_btn.connect("toggled", self._on_all_toggled)
        toggle_box.append(self._all_btn)

        self._specific_btn = Gtk.ToggleButton(label="Specific IPs")
        self._specific_btn.add_css_class("mode-toggle")
        self._specific_btn.connect("toggled", self._on_specific_toggled)
        toggle_box.append(self._specific_btn)

        mode_row.append(toggle_box)
        box.append(mode_row)

        self._ip_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_min_content_height(120)
        scrolled.set_max_content_height(200)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._ip_listbox = Gtk.ListBox()
        self._ip_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._ip_listbox.add_css_class("boxed-list")
        scrolled.set_child(self._ip_listbox)
        self._ip_frame.append(scrolled)

        add_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._ip_entry = Gtk.Entry()
        self._ip_entry.set_placeholder_text("e.g. 10.0.0.0/8")
        self._ip_entry.set_hexpand(True)
        self._ip_entry.connect("activate", self._on_add_ip)
        add_box.append(self._ip_entry)

        add_btn = Gtk.Button(label="Add")
        add_btn.add_css_class("suggested-action")
        add_btn.connect("clicked", self._on_add_ip)
        add_box.append(add_btn)

        import_btn = Gtk.Button(label="Import File")
        import_btn.connect("clicked", self._on_import_file)
        add_box.append(import_btn)

        self._ip_frame.append(add_box)
        box.append(self._ip_frame)

        self.set_child(box)
        self._ip_frame.set_visible(False)

    def _on_all_toggled(self, button):
        if button.get_active():
            self._specific_btn.set_active(False)
            self._ip_frame.set_visible(False)

    def _on_specific_toggled(self, button):
        if button.get_active():
            self._all_btn.set_active(False)
            self._ip_frame.set_visible(True)
        elif not self._all_btn.get_active():
            self._all_btn.set_active(True)

    def _on_add_ip(self, widget):
        text = self._ip_entry.get_text().strip()
        if text and self._validate_ip(text):
            self._add_ip_row(text)
            self._ip_entry.set_text("")
        else:
            self._ip_entry.add_css_class("error")
            self._ip_entry.grab_focus()

    def _validate_ip(self, text):
        pattern = r"^(\d{1,3}\.){3}\d{1,3}(/\d{1,2})?$"
        return bool(re.match(pattern, text))

    def _add_ip_row(self, ip: str):
        for i in range(1000):
            row = self._ip_listbox.get_row_at_index(i)
            if row is None:
                break
            if row.get_child().ip_text == ip:
                return

        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row_box.set_margin_start(12)
        row_box.set_margin_end(8)
        row_box.set_margin_top(6)
        row_box.set_margin_bottom(6)
        row_box.ip_text = ip

        label = Gtk.Label(label=ip)
        label.set_xalign(0)
        label.set_hexpand(True)
        label.set_selectable(True)
        row_box.append(label)

        remove_btn = Gtk.Button()
        remove_btn.set_icon_name("window-close-symbolic")
        remove_btn.add_css_class("flat")
        remove_btn.add_css_class("circular")
        remove_btn.connect("clicked", self._on_remove_ip, row_box)
        row_box.append(remove_btn)

        self._ip_listbox.append(row_box)
        self._ip_entry.remove_css_class("error")

    def _on_remove_ip(self, button, row_box):
        row = row_box.get_parent()
        self._ip_listbox.remove(row)

    def _on_import_file(self, button):
        dialog = Gtk.FileDialog()
        txt_filter = Gtk.FileFilter()
        txt_filter.set_name("Text files")
        txt_filter.add_pattern("*.txt")
        all_filter = Gtk.FileFilter()
        all_filter.set_name("All files")
        all_filter.add_pattern("*")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(txt_filter)
        filters.append(all_filter)
        dialog.set_filters(filters)
        dialog.open(self.get_root(), None, self._on_file_selected)

    def _on_file_selected(self, dialog, result):
        try:
            file = dialog.open_finish(result)
            if file:
                path = file.get_path()
                with open(path) as f:
                    for line in f:
                        line = line.split("#")[0].strip()
                        if line and self._validate_ip(line):
                            self._add_ip_row(line)
        except Exception:
            pass

    def get_subnets(self) -> list[str]:
        if self._all_btn.get_active():
            return ["0/0"]

        subnets = []
        for i in range(1000):
            row = self._ip_listbox.get_row_at_index(i)
            if row is None:
                break
            subnets.append(row.get_child().ip_text)

        return subnets if subnets else ["0/0"]

    def set_subnets(self, subnets: list[str]):
        while True:
            row = self._ip_listbox.get_row_at_index(0)
            if row is None:
                break
            self._ip_listbox.remove(row)

        if not subnets or subnets == ["0/0"]:
            self._all_btn.set_active(True)
        else:
            self._specific_btn.set_active(True)
            for s in subnets:
                self._add_ip_row(s)

    @property
    def is_all_traffic(self):
        return self._all_btn.get_active()
