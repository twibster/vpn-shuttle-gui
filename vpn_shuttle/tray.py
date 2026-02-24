from gi.repository import Gio, GLib

from vpn_shuttle import APP_ID

SNI_IFACE = "org.kde.StatusNotifierItem"
SNI_PATH = "/StatusNotifierItem"
WATCHER_IFACE = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
MENU_IFACE = "com.canonical.dbusmenu"
MENU_PATH = "/MenuBar"

SNI_XML = f"""<node>
  <interface name="{SNI_IFACE}">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <method name="Activate">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <method name="ContextMenu">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <signal name="NewIcon"/>
    <signal name="NewToolTip"/>
    <signal name="NewStatus">
      <arg type="s"/>
    </signal>
  </interface>
</node>"""

MENU_XML = f"""<node>
  <interface name="{MENU_IFACE}">
    <method name="GetLayout">
      <arg type="i" name="parentId" direction="in"/>
      <arg type="i" name="recursionDepth" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="u" name="revision" direction="out"/>
      <arg type="(ia{{sv}}av)" name="layout" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="eventId" direction="in"/>
      <arg type="v" name="data" direction="in"/>
      <arg type="u" name="timestamp" direction="in"/>
    </method>
    <method name="AboutToShow">
      <arg type="i" name="id" direction="in"/>
      <arg type="b" name="needUpdate" direction="out"/>
    </method>
    <signal name="LayoutUpdated">
      <arg type="u" name="revision"/>
      <arg type="i" name="parent"/>
    </signal>
    <property name="Version" type="u" access="read"/>
    <property name="Status" type="s" access="read"/>
  </interface>
</node>"""


class TrayIcon:
    def __init__(self, window):
        self._window = window
        self._connected = False
        self._icon_name = "network-offline-symbolic"
        self._tooltip = "VPN Shuttle - Disconnected"
        self._revision = 1
        self._bus_name = None
        self._sni_reg_id = None
        self._menu_reg_id = None

        self._bus = Gio.bus_get_sync(Gio.BusType.SESSION)

        self._bus_name = self._bus.call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus",
            "org.freedesktop.DBus", "RequestName",
            GLib.Variant("(su)", (APP_ID + ".tray", 0x4)),
            GLib.VariantType("(u)"), Gio.DBusCallFlags.NONE, -1, None
        )

        sni_info = Gio.DBusNodeInfo.new_for_xml(SNI_XML)
        self._sni_reg_id = self._bus.register_object(
            SNI_PATH, sni_info.interfaces[0],
            self._on_sni_method, self._on_sni_get_property, None
        )

        menu_info = Gio.DBusNodeInfo.new_for_xml(MENU_XML)
        self._menu_reg_id = self._bus.register_object(
            MENU_PATH, menu_info.interfaces[0],
            self._on_menu_method, self._on_menu_get_property, None
        )

        self._bus.call_sync(
            WATCHER_IFACE, WATCHER_PATH, WATCHER_IFACE,
            "RegisterStatusNotifierItem",
            GLib.Variant("(s)", (SNI_PATH,)),
            None, Gio.DBusCallFlags.NONE, -1, None
        )

    def _on_sni_method(self, connection, sender, path, iface, method, params, invocation):
        if method == "Activate":
            GLib.idle_add(self._toggle_window)
            invocation.return_value(None)
        elif method == "ContextMenu":
            invocation.return_value(None)
        else:
            invocation.return_value(None)

    def _on_sni_get_property(self, connection, sender, path, iface, prop):
        if prop == "Category":
            return GLib.Variant("s", "Communications")
        elif prop == "Id":
            return GLib.Variant("s", APP_ID)
        elif prop == "Title":
            return GLib.Variant("s", "VPN Shuttle")
        elif prop == "Status":
            return GLib.Variant("s", "Active")
        elif prop == "IconName":
            return GLib.Variant("s", self._icon_name)
        elif prop == "ItemIsMenu":
            return GLib.Variant("b", False)
        elif prop == "Menu":
            return GLib.Variant("o", MENU_PATH)
        elif prop == "ToolTip":
            return GLib.Variant("(sa(iiay)ss)", ("", [], "VPN Shuttle", self._tooltip))
        return None

    def _on_menu_method(self, connection, sender, path, iface, method, params, invocation):
        if method == "GetLayout":
            layout = self._build_menu_layout()
            invocation.return_value(GLib.Variant("(u(ia{sv}av))", (self._revision, layout)))
        elif method == "Event":
            item_id, event_id, data, timestamp = params.unpack()
            if event_id == "clicked":
                self._handle_menu_click(item_id)
            invocation.return_value(None)
        elif method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))
        else:
            invocation.return_value(None)

    def _on_menu_get_property(self, connection, sender, path, iface, prop):
        if prop == "Version":
            return GLib.Variant("u", 3)
        elif prop == "Status":
            return GLib.Variant("s", "normal")
        return None

    def _build_menu_layout(self):
        show_label = "Hide Window" if self._window.get_visible() else "Show Window"
        status_label = "Connected" if self._connected else "Disconnected"

        children = [
            GLib.Variant("v", GLib.Variant("(ia{sv}av)", (1, {
                "label": GLib.Variant("s", show_label),
                "enabled": GLib.Variant("b", True),
            }, []))),
            GLib.Variant("v", GLib.Variant("(ia{sv}av)", (2, {
                "label": GLib.Variant("s", f"Status: {status_label}"),
                "enabled": GLib.Variant("b", False),
            }, []))),
            GLib.Variant("v", GLib.Variant("(ia{sv}av)", (3, {
                "type": GLib.Variant("s", "separator"),
            }, []))),
            GLib.Variant("v", GLib.Variant("(ia{sv}av)", (4, {
                "label": GLib.Variant("s", "Quit"),
                "enabled": GLib.Variant("b", True),
            }, []))),
        ]

        return (0, {"children-display": GLib.Variant("s", "submenu")}, children)

    def _handle_menu_click(self, item_id):
        if item_id == 1:
            GLib.idle_add(self._toggle_window)
        elif item_id == 4:
            GLib.idle_add(self._do_quit)

    def _toggle_window(self):
        if self._window.get_visible():
            self._window.set_visible(False)
        else:
            self._window.set_visible(True)
            self._window.present()
        self._revision += 1
        self._emit_layout_updated()
        return False

    def _do_quit(self):
        self._window.get_application().quit()
        return False

    def _emit_layout_updated(self):
        self._bus.emit_signal(
            None, MENU_PATH, MENU_IFACE, "LayoutUpdated",
            GLib.Variant("(ui)", (self._revision, 0))
        )

    def _emit_new_icon(self):
        self._bus.emit_signal(
            None, SNI_PATH, SNI_IFACE, "NewIcon", None
        )
        self._bus.emit_signal(
            None, SNI_PATH, SNI_IFACE, "NewToolTip", None
        )

    def update_status(self, connected):
        self._connected = connected
        if connected:
            self._icon_name = "network-vpn-symbolic"
            self._tooltip = "VPN Shuttle - Connected"
        else:
            self._icon_name = "network-offline-symbolic"
            self._tooltip = "VPN Shuttle - Disconnected"
        self._revision += 1
        self._emit_new_icon()
        self._emit_layout_updated()
