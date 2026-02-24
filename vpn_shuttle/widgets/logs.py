import gi
import re

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gdk


LOG_RULES = [
    ("error", re.compile(r"(?i)failed|error|timed out|exit code [^0]|not found|permission denied")),
    ("success", re.compile(r"(?i)connected|complete|installed|(?<!\w)OK(?!\w)|successful|is UP|module loaded")),
    ("info", re.compile(r"(?i)^Routes:|^Starting|^Activating|^Testing|^Enabling|^Installing|^Uploading|^Cleaning")),
    ("dim", re.compile(r"^\[#\]|^\s{2,}|transfer:|keepalive|handshake|allowed ips")),
]


class LogViewer(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        frame = Gtk.Frame()
        frame.add_css_class("log-frame")
        frame.set_label_widget(None)

        frame_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.add_css_class("log-header")
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
        frame_box.append(header)

        frame_box.append(Gtk.Separator())

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

        self._setup_tags()

        scrolled.set_child(self._textview)
        frame_box.append(scrolled)
        frame.set_child(frame_box)

        self.append(frame)
        self._scrolled = scrolled

    def _setup_tags(self):
        self._buffer.create_tag("error", foreground="#e01b24")
        self._buffer.create_tag("success", foreground="#2ec27e")
        self._buffer.create_tag("info", foreground="#62a0ea")
        self._buffer.create_tag("dim", foreground="#888888")

    def _classify_line(self, text):
        for tag_name, pattern in LOG_RULES:
            if pattern.search(text):
                return tag_name
        return None

    def append_log(self, text: str):
        GLib.idle_add(self._append_log_idle, text)

    def _append_log_idle(self, text: str):
        end_iter = self._buffer.get_end_iter()
        tag_name = self._classify_line(text)
        if tag_name:
            tag = self._buffer.get_tag_table().lookup(tag_name)
            self._buffer.insert_with_tags(end_iter, text + "\n", tag)
        else:
            self._buffer.insert(end_iter, text + "\n")
        end_mark = self._buffer.create_mark(None, self._buffer.get_end_iter(), False)
        self._textview.scroll_mark_onscreen(end_mark)
        self._buffer.delete_mark(end_mark)
        return False

    def _on_clear(self, button):
        self._buffer.set_text("")
