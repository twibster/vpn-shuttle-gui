import gi
import threading
import json
import urllib.request

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib


class DnsLeakDialog(Adw.Window):
    def __init__(self, parent):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_title("DNS Leak Test")
        self.set_default_size(450, 400)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        header = Adw.HeaderBar()
        main_box.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_start(16)
        content.set_margin_end(16)
        content.set_margin_top(12)
        content.set_margin_bottom(12)

        self._results_group = Adw.PreferencesGroup()
        self._results_group.set_title("Results")
        self._results_group.set_description("Click Run Test to check for DNS leaks")
        content.append(self._results_group)

        self._run_btn = Gtk.Button(label="Run Test")
        self._run_btn.add_css_class("suggested-action")
        self._run_btn.connect("clicked", self._on_run)
        content.append(self._run_btn)

        self._spinner = Gtk.Spinner()
        content.append(self._spinner)

        main_box.append(content)
        self.set_content(main_box)

    def _on_run(self, button):
        self._run_btn.set_sensitive(False)
        self._spinner.start()
        self._clear_results()
        self._results_group.set_description("Testing...")

        threading.Thread(target=self._run_test, daemon=True).start()

    def _run_test(self):
        try:
            req = urllib.request.Request(
                "https://ipleak.net/json/",
                headers={"User-Agent": "VPNShuttle/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            GLib.idle_add(self._show_results, data, None)
        except Exception as e:
            GLib.idle_add(self._show_results, None, str(e))

    def _clear_results(self):
        while True:
            child = self._results_group.get_first_child()
            if child is None:
                break
            self._results_group.remove(child)

    def _show_results(self, data, error):
        self._spinner.stop()
        self._run_btn.set_sensitive(True)
        self._clear_results()

        if error:
            self._results_group.set_description(f"Error: {error}")
            return

        if not data:
            self._results_group.set_description("No data received")
            return

        self._results_group.set_description("")

        ip = data.get("ip", "Unknown")
        row_ip = Adw.ActionRow()
        row_ip.set_title("Public IP")
        row_ip.set_subtitle(ip)
        self._results_group.add(row_ip)

        country = data.get("country_name", "Unknown")
        country_code = data.get("country_code", "")
        row_country = Adw.ActionRow()
        row_country.set_title("Country")
        row_country.set_subtitle(f"{country} ({country_code})" if country_code else country)
        self._results_group.add(row_country)

        isp = data.get("isp", "Unknown")
        row_isp = Adw.ActionRow()
        row_isp.set_title("ISP")
        row_isp.set_subtitle(isp)
        self._results_group.add(row_isp)

        reverse = data.get("reverse", "")
        if reverse:
            row_reverse = Adw.ActionRow()
            row_reverse.set_title("Reverse DNS")
            row_reverse.set_subtitle(reverse)
            self._results_group.add(row_reverse)

        return False
