import gi
from datetime import datetime

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw


class HistoryDialog(Adw.Window):
    def __init__(self, parent, config):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_title("Connection History")
        self.set_default_size(500, 500)

        self._config = config

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        header = Adw.HeaderBar()
        clear_btn = Gtk.Button(label="Clear")
        clear_btn.add_css_class("destructive-action")
        clear_btn.connect("clicked", self._on_clear)
        header.pack_end(clear_btn)
        main_box.append(header)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._content.set_margin_start(16)
        self._content.set_margin_end(16)
        self._content.set_margin_top(12)
        self._content.set_margin_bottom(12)

        self._group = Adw.PreferencesGroup()
        self._content.append(self._group)

        scrolled.set_child(self._content)
        main_box.append(scrolled)
        self.set_content(main_box)

        self._populate()

    def _populate(self):
        history = self._config.get_history()
        if not history:
            self._group.set_description("No connections yet")
            return

        for entry in history:
            row = Adw.ActionRow()
            row.set_title(entry.get("config_name", "Unknown"))

            host_name = entry.get("host_name", "")
            host_ip = entry.get("host_ip", "")
            started = entry.get("started_at", "")
            duration = entry.get("duration_seconds", 0)
            status = entry.get("status", "")

            try:
                dt = datetime.fromisoformat(started)
                time_str = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                time_str = started

            hours, remainder = divmod(duration, 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours:
                dur_str = f"{hours}h {minutes}m"
            elif minutes:
                dur_str = f"{minutes}m {seconds}s"
            else:
                dur_str = f"{seconds}s"

            subtitle = f"{host_name} ({host_ip}) - {time_str} - {dur_str}"
            if status == "failed":
                subtitle += " [FAILED]"
            row.set_subtitle(subtitle)

            icon = Gtk.Image()
            if status == "failed":
                icon.set_from_icon_name("dialog-error-symbolic")
            else:
                icon.set_from_icon_name("emblem-ok-symbolic")
            icon.set_pixel_size(16)
            row.add_prefix(icon)

            self._group.add(row)

    def _on_clear(self, button):
        self._config.clear_history()
        while True:
            child = self._group.get_first_child()
            if child is None:
                break
            self._group.remove(child)
        self._group.set_description("No connections yet")
