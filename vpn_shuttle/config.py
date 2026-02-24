import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "vpn-shuttle"
CONFIG_FILE = CONFIG_DIR / "settings.json"

DEFAULTS = {
    "jump_host_ip": "144.91.114.117",
    "jump_host_user": "root",
    "ssh_key_path": str(Path.home() / ".ssh" / "id_rsa"),
    "last_config": "",
    "routing_mode": "all",
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
                self._data.update(stored)
            except (json.JSONDecodeError, OSError):
                pass

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key):
        return self._data.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        self._data[key] = value
        self.save()

    @property
    def jump_host(self):
        return f"{self.get('jump_host_user')}@{self.get('jump_host_ip')}"

    @property
    def jump_host_ip(self):
        return self.get("jump_host_ip")

    @property
    def ssh_key_path(self):
        return self.get("ssh_key_path")

    def get_routes_for_config(self, config_name):
        routes = self.get("saved_routes")
        return routes.get(config_name, [])

    def set_routes_for_config(self, config_name, routes):
        saved = self.get("saved_routes")
        saved[config_name] = routes
        self.set("saved_routes", saved)
