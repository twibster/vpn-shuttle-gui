import subprocess
import threading
import shlex
import signal
import os
import re
import time
from typing import Callable, Optional


class VPNBackend:
    def __init__(self, config):
        self.config = config
        self._sshuttle_proc = None
        self._vpn_up_proc = None
        self._connected = False
        self._active_config = None
        self._connect_time = None
        self._log_callback = None
        self._status_callback = None
        self._lock = threading.Lock()

    def set_log_callback(self, callback: Callable[[str], None]):
        self._log_callback = callback

    def set_status_callback(self, callback: Callable[[str, Optional[str]], None]):
        self._status_callback = callback

    def _log(self, message: str):
        if self._log_callback:
            self._log_callback(message)

    def _set_status(self, status: str, config_name: Optional[str] = None):
        self._status_callback(status, config_name) if self._status_callback else None

    def _ssh_cmd(self, command: str, timeout: int = 15) -> tuple[int, str]:
        ssh = [
            "ssh", "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=no",
            "-i", self.config.ssh_key_path,
            self.config.jump_host,
            command,
        ]
        try:
            result = subprocess.run(
                ssh, capture_output=True, text=True, timeout=timeout
            )
            output = result.stdout + result.stderr
            return result.returncode, output.strip()
        except subprocess.TimeoutExpired:
            return -1, "SSH command timed out"
        except Exception as e:
            return -1, str(e)

    def list_configs(self) -> list[str]:
        code, output = self._ssh_cmd(
            "ls /etc/wireguard/*.conf 2>/dev/null | xargs -I{} basename {} .conf"
        )
        if code != 0 or not output:
            return []
        return [line.strip() for line in output.splitlines() if line.strip()]

    def connect(self, config_name: str, subnets: list[str]):
        thread = threading.Thread(
            target=self._connect_thread, args=(config_name, subnets), daemon=True
        )
        thread.start()

    def _connect_thread(self, config_name: str, subnets: list[str]):
        with self._lock:
            if self._connected:
                self._log("Already connected. Disconnecting first...")
                self._disconnect_internal()

            self._set_status("connecting", config_name)
            self._log(f"Activating VPN '{config_name}' on jump host...")

            code, output = self._ssh_cmd(f"vpn-manage up {config_name}", timeout=30)
            for line in output.splitlines():
                self._log(line)

            if code != 0:
                self._log(f"Failed to activate VPN: exit code {code}")
                self._set_status("disconnected")
                return

            self._log("")
            self._log("Starting sshuttle...")

            route_args = []
            for s in subnets:
                route_args.append(s)

            sshuttle_cmd = [
                "sudo", "sshuttle",
                "-r", self.config.jump_host,
                "--dns",
                "-x", f"{self.config.jump_host_ip}/32",
                "-e", f"ssh -i {self.config.ssh_key_path} -o StrictHostKeyChecking=no",
            ] + route_args

            self._log(f"Routes: {', '.join(subnets)}")

            try:
                self._sshuttle_proc = subprocess.Popen(
                    sshuttle_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    preexec_fn=os.setsid,
                )
            except Exception as e:
                self._log(f"Failed to start sshuttle: {e}")
                self._ssh_cmd(f"vpn-manage down {config_name}")
                self._set_status("disconnected")
                return

            self._connected = True
            self._active_config = config_name
            self._connect_time = time.time()

        self._set_status("connected", config_name)

        try:
            for line in self._sshuttle_proc.stdout:
                self._log(line.rstrip())
        except Exception:
            pass

        self._sshuttle_proc.wait()
        exit_code = self._sshuttle_proc.returncode
        self._log(f"sshuttle exited (code {exit_code})")

        with self._lock:
            self._connected = False
            self._active_config = None
            self._connect_time = None
            self._sshuttle_proc = None

        self._log("Cleaning up VPN on jump host...")
        self._ssh_cmd(f"vpn-manage down {config_name}")
        self._log("Disconnected.")
        self._set_status("disconnected")

    def disconnect(self):
        thread = threading.Thread(target=self._disconnect_thread, daemon=True)
        thread.start()

    def _disconnect_thread(self):
        with self._lock:
            self._disconnect_internal()

    def _disconnect_internal(self):
        if self._sshuttle_proc and self._sshuttle_proc.poll() is None:
            self._log("Stopping sshuttle...")
            try:
                os.killpg(os.getpgid(self._sshuttle_proc.pid), signal.SIGTERM)
                self._sshuttle_proc.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(os.getpgid(self._sshuttle_proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def active_config(self) -> Optional[str]:
        return self._active_config

    @property
    def uptime_seconds(self) -> int:
        if self._connect_time:
            return int(time.time() - self._connect_time)
        return 0

    def get_vpn_endpoint(self, config_name: str) -> str:
        code, output = self._ssh_cmd(
            f"grep -i '^Endpoint' /etc/wireguard/{config_name}.conf 2>/dev/null"
        )
        if code == 0 and output:
            match = re.search(r"Endpoint\s*=\s*(.+)", output, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return "Unknown"

    def upload_config(self, local_path: str, config_name: str) -> tuple[bool, str]:
        scp_cmd = [
            "scp", "-i", self.config.ssh_key_path,
            "-o", "StrictHostKeyChecking=no",
            local_path,
            f"{self.config.jump_host}:/etc/wireguard/{config_name}.conf",
        ]
        try:
            result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                return False, f"SCP failed: {result.stderr}"
        except Exception as e:
            return False, str(e)

        code, output = self._ssh_cmd(
            f"sed -i '/^DNS/d' /etc/wireguard/{config_name}.conf && "
            f"grep -q 'Table' /etc/wireguard/{config_name}.conf || "
            f"sed -i '/^\\[Interface\\]/a Table = off' /etc/wireguard/{config_name}.conf && "
            f"echo 'Config prepared successfully'"
        )
        if code != 0:
            return False, f"Config preparation failed: {output}"
        return True, "Config uploaded and prepared"

    def delete_config(self, config_name: str) -> tuple[bool, str]:
        code, output = self._ssh_cmd(
            f"rm -f /etc/wireguard/{config_name}.conf && echo 'Deleted'"
        )
        if code != 0:
            return False, f"Delete failed: {output}"
        return True, "Config deleted"
