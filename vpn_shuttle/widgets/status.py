import gi
import threading

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GLib, Pango


class StatusPanel(Gtk.Frame):
    def __init__(self):
        super().__init__()
        self.add_css_class("status-card")
        self.add_css_class("status-card-disconnected")
        self.set_label_widget(None)

        self._uptime_timer_id = None
        self._stats_timer_id = None
        self._backend = None
        self._current_state_class = "status-card-disconnected"

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_start(4)
        box.set_margin_end(4)
        box.set_margin_top(4)
        box.set_margin_bottom(4)

        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        self._icon = Gtk.Image()
        self._icon.set_from_icon_name("network-wired-disconnected-symbolic")
        self._icon.set_pixel_size(32)
        self._icon.add_css_class("status-icon-disconnected")
        self._current_icon_class = "status-icon-disconnected"
        status_row.append(self._icon)

        self._status_label = Gtk.Label(label="Disconnected")
        self._status_label.set_xalign(0)
        self._status_label.set_hexpand(True)
        self._status_label.add_css_class("title-2")
        status_row.append(self._status_label)

        box.append(status_row)

        self._grid = Gtk.Grid()
        self._grid.set_column_spacing(16)
        self._grid.set_row_spacing(6)

        labels = ["Jump Host:", "VPN Endpoint:", "Uptime:", "Latency:", "Transfer:"]
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
            value.add_css_class("status-value")
            self._grid.attach(value, 1, i, 1, 1)
            self._value_labels[label_text] = value

        box.append(self._grid)
        self.set_child(box)

    def _set_state(self, state):
        self.remove_css_class(self._current_state_class)
        new_class = f"status-card-{state}"
        self.add_css_class(new_class)
        self._current_state_class = new_class

        self._icon.remove_css_class(self._current_icon_class)
        new_icon_class = f"status-icon-{state}"
        self._icon.add_css_class(new_icon_class)
        self._current_icon_class = new_icon_class

    def update_status(self, status: str, config_name=None, jump_host=None, endpoint=None):
        if status == "connected":
            self._set_state("connected")
            self._icon.set_from_icon_name("network-vpn-symbolic")
            self._status_label.set_label(f"Connected via {config_name or 'Unknown'}")
            self._start_uptime_timer()
        elif status == "connecting":
            self._set_state("connecting")
            self._icon.set_from_icon_name("network-vpn-acquiring-symbolic")
            self._status_label.set_label(f"Connecting to {config_name or ''}...")
            self._value_labels["Uptime:"].set_label("-")
        else:
            self._set_state("disconnected")
            self._icon.set_from_icon_name("network-wired-disconnected-symbolic")
            self._status_label.set_label("Disconnected")
            self._stop_uptime_timer()
            self._value_labels["Uptime:"].set_label("-")
            self._value_labels["Latency:"].set_label("-")
            self._value_labels["Transfer:"].set_label("-")

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

    def start_stats(self, backend):
        self.stop_stats()
        self._backend = backend
        self._stats_timer_id = GLib.timeout_add_seconds(5, self._poll_stats)
        self._poll_stats()

    def stop_stats(self):
        if self._stats_timer_id:
            GLib.source_remove(self._stats_timer_id)
            self._stats_timer_id = None
        self._backend = None

    def _poll_stats(self):
        if not self._backend or not self._backend.is_connected:
            return False

        backend = self._backend
        config = backend.active_config

        def fetch():
            latency = backend.get_latency()
            transfer = backend.get_wg_transfer(config)
            GLib.idle_add(self._update_stats_labels, latency, transfer)

        threading.Thread(target=fetch, daemon=True).start()
        return True

    def _update_stats_labels(self, latency, transfer):
        if latency is not None:
            self._value_labels["Latency:"].set_label(f"{latency:.1f} ms")
        else:
            self._value_labels["Latency:"].set_label("-")

        if transfer:
            rx, tx = transfer
            self._value_labels["Transfer:"].set_label(
                f"\u2193 {self._format_bytes(rx)} / \u2191 {self._format_bytes(tx)}"
            )
        else:
            self._value_labels["Transfer:"].set_label("-")
        return False

    @staticmethod
    def _format_bytes(b):
        if b < 1024:
            return f"{b} B"
        elif b < 1024 * 1024:
            return f"{b / 1024:.1f} KB"
        elif b < 1024 * 1024 * 1024:
            return f"{b / (1024 * 1024):.1f} MB"
        return f"{b / (1024 * 1024 * 1024):.2f} GB"
