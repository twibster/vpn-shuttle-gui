import json
import uuid
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "vpn-shuttle"
CONFIG_FILE = CONFIG_DIR / "settings.json"

DEFAULTS = {
    "hosts": {},
    "active_host": "",
    "last_config": "",
    "routing_mode": "all",
}

HOST_DEFAULTS = {
    "name": "",
    "ip": "",
    "user": "root",
    "ssh_key_path": str(Path.home() / ".ssh" / "id_rsa"),
    "setup_complete": False,
    "saved_routes": {},
}


class AppConfig:
    def __init__(self):
        self._data = dict(DEFAULTS)
        self.load()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    stored = json.load(f)
                self._migrate(stored)
                self._data.update(stored)
            except (json.JSONDecodeError, OSError):
                pass

    def _migrate(self, stored):
        if "jump_host_ip" in stored and "hosts" not in stored:
            host_id = str(uuid.uuid4())[:8]
            stored["hosts"] = {
                host_id: {
                    "name": "Default",
                    "ip": stored.pop("jump_host_ip", ""),
                    "user": stored.pop("jump_host_user", "root"),
                    "ssh_key_path": stored.pop("ssh_key_path", HOST_DEFAULTS["ssh_key_path"]),
                    "setup_complete": True,
                    "saved_routes": stored.pop("saved_routes", {}),
                }
            }
            stored["active_host"] = host_id
            stored.pop("jump_host_ip", None)
            stored.pop("jump_host_user", None)

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key):
        return self._data.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        self._data[key] = value
        self.save()

    def get_hosts(self) -> dict:
        return self._data.get("hosts", {})

    def get_host(self, host_id: str) -> dict:
        return self._data.get("hosts", {}).get(host_id, {})

    def get_active_host(self) -> dict:
        host_id = self._data.get("active_host", "")
        return self.get_host(host_id)

    def get_active_host_id(self) -> str:
        return self._data.get("active_host", "")

    def set_active_host(self, host_id: str):
        self.set("active_host", host_id)

    def add_host(self, name, ip, user, ssh_key_path) -> str:
        host_id = str(uuid.uuid4())[:8]
        hosts = self._data.get("hosts", {})
        hosts[host_id] = {
            "name": name,
            "ip": ip,
            "user": user,
            "ssh_key_path": ssh_key_path,
            "setup_complete": False,
            "saved_routes": {},
        }
        self._data["hosts"] = hosts
        if not self._data.get("active_host"):
            self._data["active_host"] = host_id
        self.save()
        return host_id

    def update_host(self, host_id: str, **kwargs):
        hosts = self._data.get("hosts", {})
        if host_id in hosts:
            hosts[host_id].update(kwargs)
            self._data["hosts"] = hosts
            self.save()

    def remove_host(self, host_id: str):
        hosts = self._data.get("hosts", {})
        hosts.pop(host_id, None)
        self._data["hosts"] = hosts
        if self._data.get("active_host") == host_id:
            self._data["active_host"] = next(iter(hosts), "")
        self.save()

    @property
    def jump_host(self):
        host = self.get_active_host()
        if host:
            return f"{host.get('user', 'root')}@{host.get('ip', '')}"
        return ""

    @property
    def jump_host_ip(self):
        host = self.get_active_host()
        return host.get("ip", "") if host else ""

    @property
    def ssh_key_path(self):
        host = self.get_active_host()
        return host.get("ssh_key_path", HOST_DEFAULTS["ssh_key_path"]) if host else HOST_DEFAULTS["ssh_key_path"]

    def get_routes_for_config(self, config_name):
        host = self.get_active_host()
        if host:
            return host.get("saved_routes", {}).get(config_name, [])
        return []

    def set_routes_for_config(self, config_name, routes):
        host_id = self.get_active_host_id()
        if host_id:
            hosts = self._data.get("hosts", {})
            if host_id in hosts:
                if "saved_routes" not in hosts[host_id]:
                    hosts[host_id]["saved_routes"] = {}
                hosts[host_id]["saved_routes"][config_name] = routes
                self._data["hosts"] = hosts
                self.save()
