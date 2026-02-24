import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GLib, Pango


class StatusPanel(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_margin_start(16)
        self.set_margin_end(16)
        self.set_margin_top(12)
        self.set_margin_bottom(12)

        self._uptime_timer_id = None

        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._indicator = Gtk.Label(label="\u25cf")
        self._indicator.add_css_class("status-disconnected")
        status_row.append(self._indicator)

        self._status_label = Gtk.Label(label="Disconnected")
        self._status_label.set_xalign(0)
        self._status_label.add_css_class("title-3")
        status_row.append(self._status_label)
        self.append(status_row)

        self._grid = Gtk.Grid()
        self._grid.set_column_spacing(12)
        self._grid.set_row_spacing(4)

        labels = ["Jump Host:", "VPN Endpoint:", "Uptime:"]
        self._value_labels = {}
        for i, label_text in enumerate(labels):
            label = Gtk.Label(label=label_text)
            label.set_xalign(0)
            label.add_css_class("dim-label")
            self._grid.attach(label, 0, i, 1, 1)

            value = Gtk.Label(label="-")
            value.set_xalign(0)
            value.set_hexpand(True)
            value.set_ellipsize(Pango.EllipsizeMode.END)
            self._grid.attach(value, 1, i, 1, 1)
            self._value_labels[label_text] = value

        self.append(self._grid)

    def update_status(self, status: str, config_name=None, jump_host=None, endpoint=None):
        if status == "connected":
            self._indicator.set_label("\u25cf")
            self._indicator.remove_css_class("status-disconnected")
            self._indicator.remove_css_class("status-connecting")
            self._indicator.add_css_class("status-connected")
            self._status_label.set_label(f"Connected via {config_name or 'Unknown'}")
            self._start_uptime_timer()
        elif status == "connecting":
            self._indicator.set_label("\u25cf")
            self._indicator.remove_css_class("status-disconnected")
            self._indicator.remove_css_class("status-connected")
            self._indicator.add_css_class("status-connecting")
            self._status_label.set_label(f"Connecting to {config_name or ''}...")
            self._value_labels["Uptime:"].set_label("-")
        else:
            self._indicator.set_label("\u25cf")
            self._indicator.remove_css_class("status-connected")
            self._indicator.remove_css_class("status-connecting")
            self._indicator.add_css_class("status-disconnected")
            self._status_label.set_label("Disconnected")
            self._stop_uptime_timer()
            self._value_labels["Uptime:"].set_label("-")

        if jump_host:
            self._value_labels["Jump Host:"].set_label(jump_host)
        if endpoint:
            self._value_labels["VPN Endpoint:"].set_label(endpoint)

    def _start_uptime_timer(self):
        self._stop_uptime_timer()
        self._uptime_start = GLib.get_monotonic_time()
        self._uptime_timer_id = GLib.timeout_add_seconds(1, self._update_uptime)

    def _stop_uptime_timer(self):
        if self._uptime_timer_id:
            GLib.source_remove(self._uptime_timer_id)
            self._uptime_timer_id = None

    def _update_uptime(self):
        elapsed = (GLib.get_monotonic_time() - self._uptime_start) // 1_000_000
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        self._value_labels["Uptime:"].set_label(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        return True
