import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Pango


class LogViewer(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_margin_start(16)
        self.set_margin_end(16)
        self.set_margin_bottom(12)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        label = Gtk.Label(label="Logs")
        label.set_xalign(0)
        label.add_css_class("title-4")
        header.append(label)

        clear_btn = Gtk.Button(label="Clear")
        clear_btn.add_css_class("flat")
        clear_btn.connect("clicked", self._on_clear)
        header.append(clear_btn)
        header.set_halign(Gtk.Align.FILL)
        label.set_hexpand(True)
        self.append(header)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(150)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self._textview = Gtk.TextView()
        self._textview.set_editable(False)
        self._textview.set_cursor_visible(False)
        self._textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._textview.set_monospace(True)
        self._textview.add_css_class("log-view")
        self._buffer = self._textview.get_buffer()

        scrolled.set_child(self._textview)
        self.append(scrolled)
        self._scrolled = scrolled

    def append_log(self, text: str):
        GLib.idle_add(self._append_log_idle, text)

    def _append_log_idle(self, text: str):
        end_iter = self._buffer.get_end_iter()
        self._buffer.insert(end_iter, text + "\n")
        end_mark = self._buffer.create_mark(None, self._buffer.get_end_iter(), False)
        self._textview.scroll_mark_onscreen(end_mark)
        self._buffer.delete_mark(end_mark)
        return False

    def _on_clear(self, button):
        self._buffer.set_text("")
