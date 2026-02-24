import subprocess
import threading
import signal
import os
import re
import time
from typing import Callable, Optional

VPN_MANAGE_SCRIPT = r'''#!/bin/bash
set -e

ACTION=$1
CONFIG_NAME=$2
VPN_TABLE=100

if [ -z "$ACTION" ]; then
    echo "Usage: vpn-manage {up|down|status} [config-name]"
    echo "Available configs:"
    ls /etc/wireguard/*.conf 2>/dev/null | xargs -I{} basename {} .conf
    exit 0
fi

case "$ACTION" in
    up)
        if [ -z "$CONFIG_NAME" ]; then
            echo "Error: config name required"
            exit 1
        fi

        for iface in $(wg show interfaces 2>/dev/null); do
            echo "Bringing down existing interface: $iface"
            wg-quick down "$iface" 2>/dev/null || true
        done

        while ip rule del table $VPN_TABLE 2>/dev/null; do :; done
        ip route flush table $VPN_TABLE 2>/dev/null || true

        DEFAULT_GW=$(ip route | grep '^default' | head -1 | awk '{print $3}')
        DEFAULT_IF=$(ip route | grep '^default' | head -1 | awk '{print $5}')
        SERVER_IP=$(ip -4 addr show "$DEFAULT_IF" | grep -oP 'inet \K[0-9.]+')

        echo "Default gateway: $DEFAULT_GW via $DEFAULT_IF ($SERVER_IP)"

        wg-quick up "$CONFIG_NAME"

        ip route add default dev "$CONFIG_NAME" table $VPN_TABLE
        ip route add $(ip route | grep "dev $DEFAULT_IF" | grep -v default | head -1) table $VPN_TABLE 2>/dev/null || true

        ip rule del from "$SERVER_IP" table main priority 50 2>/dev/null || true
        ip rule add from "$SERVER_IP" table main priority 50
        ip rule del table $VPN_TABLE priority 100 2>/dev/null || true
        ip rule add table $VPN_TABLE priority 100

        echo "VPN $CONFIG_NAME is UP"
        echo "Routing: forwarded traffic -> VPN | server-originated ($SERVER_IP) -> eth0"
        wg show "$CONFIG_NAME"
        ;;

    down)
        while ip rule del table $VPN_TABLE 2>/dev/null; do :; done
        while ip rule del table main priority 50 2>/dev/null; do :; done
        ip route flush table $VPN_TABLE 2>/dev/null || true

        if [ -z "$CONFIG_NAME" ]; then
            for iface in $(wg show interfaces 2>/dev/null); do
                wg-quick down "$iface" 2>/dev/null || true
                echo "Brought down: $iface"
            done
        else
            wg-quick down "$CONFIG_NAME" 2>/dev/null || true
            echo "Brought down: $CONFIG_NAME"
        fi
        ;;

    status)
        echo "=== Active WireGuard Interfaces ==="
        wg show 2>/dev/null || echo "No active interfaces"
        echo ""
        echo "=== Routing Rules ==="
        ip rule show 2>/dev/null
        echo ""
        echo "=== VPN Route Table ($VPN_TABLE) ==="
        ip route show table $VPN_TABLE 2>/dev/null || echo "Empty"
        echo ""
        echo "=== Available Configs ==="
        ls /etc/wireguard/*.conf 2>/dev/null | xargs -I{} basename {} .conf
        ;;

    *)
        echo "Unknown action: $ACTION"
        exit 1
        ;;
esac
'''


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

    @staticmethod
    def _get_host_auth(host):
        auth_type = host.get("auth_type", "key")
        key = host.get("ssh_key_path", "")
        password = host.get("password", "")
        target = f"{host.get('user', 'root')}@{host.get('ip', '')}"
        return auth_type, key, password, target

    def _ssh_cmd(self, command: str, timeout: int = 15, host_override: dict = None) -> tuple[int, str]:
        if host_override:
            auth_type, key, password, target = self._get_host_auth(host_override)
        else:
            auth_type = self.config.auth_type
            key = self.config.ssh_key_path
            password = self.config.password
            target = self.config.jump_host

        ssh = [
            "ssh", "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=no",
        ]
        if auth_type == "key":
            ssh += ["-i", key]
        ssh += [target, command]

        if auth_type == "password":
            ssh = ["sshpass", "-p", password] + ssh

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

    def _scp_cmd(self, local_path: str, remote_path: str, host_override: dict = None) -> tuple[int, str]:
        if host_override:
            auth_type, key, password, target = self._get_host_auth(host_override)
        else:
            auth_type = self.config.auth_type
            key = self.config.ssh_key_path
            password = self.config.password
            target = self.config.jump_host

        scp = ["scp"]
        if auth_type == "key":
            scp += ["-i", key]
        scp += [
            "-o", "StrictHostKeyChecking=no",
            local_path,
            f"{target}:{remote_path}",
        ]

        if auth_type == "password":
            scp = ["sshpass", "-p", password] + scp

        try:
            result = subprocess.run(scp, capture_output=True, text=True, timeout=30)
            return result.returncode, (result.stdout + result.stderr).strip()
        except subprocess.TimeoutExpired:
            return -1, "SCP timed out"
        except Exception as e:
            return -1, str(e)

    @staticmethod
    def test_host_connection(ip: str, user: str, key_path: str = "", auth_type: str = "key", password: str = "") -> tuple[bool, str]:
        try:
            ssh = [
                "ssh", "-o", "ConnectTimeout=5",
                "-o", "StrictHostKeyChecking=no",
            ]
            if auth_type == "key":
                ssh += ["-i", key_path]
            ssh += [f"{user}@{ip}", "echo 'Connection successful'"]

            if auth_type == "password":
                ssh = ["sshpass", "-p", password] + ssh

            result = subprocess.run(
                ssh, capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return True, "Connection successful"
            return False, result.stderr.strip()
        except Exception as e:
            return False, str(e)

    @staticmethod
    def copy_ssh_key(ip: str, user: str, password: str, key_path: str) -> tuple[bool, str]:
        pub_path = key_path + ".pub"
        if not os.path.exists(pub_path):
            return False, f"Public key not found: {pub_path}"
        try:
            cmd = [
                "sshpass", "-p", password,
                "ssh-copy-id", "-f",
                "-i", key_path,
                "-o", "StrictHostKeyChecking=no",
                f"{user}@{ip}",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                return True, "SSH key copied successfully"
            return False, (result.stderr or result.stdout).strip()
        except Exception as e:
            return False, str(e)

    def setup_host(self, host_id: str, log_callback: Callable[[str], None] = None):
        host = self.config.get_host(host_id)
        if not host:
            if log_callback:
                log_callback("Host not found")
            return False

        log = log_callback or self._log

        log("Testing SSH connection...")
        ok, msg = self.test_host_connection(
            host["ip"], host["user"], host.get("ssh_key_path", ""),
            auth_type=host.get("auth_type", "key"), password=host.get("password", "")
        )
        if not ok:
            log(f"Connection failed: {msg}")
            return False
        log("SSH connection OK")

        log("")
        log("Installing WireGuard...")
        code, output = self._ssh_cmd(
            "apt-get update -qq && apt-get install -y -qq wireguard 2>&1 | tail -5",
            timeout=120, host_override=host
        )
        for line in output.splitlines():
            log(line)
        if code != 0:
            log("WireGuard installation failed")
            return False
        log("WireGuard installed")

        log("")
        log("Enabling IP forwarding...")
        code, output = self._ssh_cmd(
            "echo 'net.ipv4.ip_forward = 1' > /etc/sysctl.d/99-wireguard.conf && "
            "sysctl -p /etc/sysctl.d/99-wireguard.conf",
            host_override=host
        )
        for line in output.splitlines():
            log(line)
        log("IP forwarding enabled")

        log("")
        log("Installing vpn-manage script...")
        code, output = self._ssh_cmd(
            f"cat > /usr/local/bin/vpn-manage << 'SCRIPTEOF'\n{VPN_MANAGE_SCRIPT}\nSCRIPTEOF\n"
            "chmod +x /usr/local/bin/vpn-manage && echo 'vpn-manage installed'",
            timeout=10, host_override=host
        )
        for line in output.splitlines():
            log(line)
        if code != 0:
            log("Failed to install vpn-manage")
            return False

        log("")
        log("Verifying WireGuard module...")
        code, output = self._ssh_cmd(
            "modprobe wireguard 2>/dev/null && echo 'WireGuard module loaded' || echo 'Module issue (may work after reboot)'",
            host_override=host
        )
        for line in output.splitlines():
            log(line)

        self.config.update_host(host_id, setup_complete=True)
        log("")
        log("Setup complete!")
        return True

    def list_configs(self, host_override: dict = None) -> list[str]:
        code, output = self._ssh_cmd(
            "ls /etc/wireguard/*.conf 2>/dev/null | xargs -I{} basename {} .conf",
            host_override=host_override
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

            if self.config.auth_type == "password":
                ssh_e = "sshpass -e ssh -o StrictHostKeyChecking=no"
            else:
                ssh_e = f"ssh -i {self.config.ssh_key_path} -o StrictHostKeyChecking=no"

            sshuttle_cmd = ["sudo"]
            if self.config.auth_type == "password":
                sshuttle_cmd += ["env", f"SSHPASS={self.config.password}"]
            sshuttle_cmd += [
                "sshuttle",
                "-r", self.config.jump_host,
                "--dns",
                "-x", f"{self.config.jump_host_ip}/32",
                "-e", ssh_e,
            ] + list(subnets)

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

    def upload_config(self, local_path: str, config_name: str, host_override: dict = None) -> tuple[bool, str]:
        if host_override:
            target = f"{host_override.get('user', 'root')}@{host_override.get('ip', '')}"
        else:
            target = self.config.jump_host

        code, msg = self._scp_cmd(local_path, f"/etc/wireguard/{config_name}.conf", host_override=host_override)
        if code != 0:
            return False, f"SCP failed: {msg}"

        code, output = self._ssh_cmd(
            f"sed -i '/^DNS/d' /etc/wireguard/{config_name}.conf && "
            f"grep -q 'Table' /etc/wireguard/{config_name}.conf || "
            f"sed -i '/^\\[Interface\\]/a Table = off' /etc/wireguard/{config_name}.conf && "
            f"echo 'Config prepared successfully'",
            host_override=host_override
        )
        if code != 0:
            return False, f"Config preparation failed: {output}"
        return True, "Config uploaded and prepared"

    def delete_config(self, config_name: str, host_override: dict = None) -> tuple[bool, str]:
        code, output = self._ssh_cmd(
            f"rm -f /etc/wireguard/{config_name}.conf && echo 'Deleted'",
            host_override=host_override
        )
        if code != 0:
            return False, f"Delete failed: {output}"
        return True, "Config deleted"

    def get_latency(self):
        ip = self.config.jump_host_ip
        if not ip:
            return None
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", ip],
                capture_output=True, text=True, timeout=5
            )
            match = re.search(r"time=([\d.]+)\s*ms", result.stdout)
            if match:
                return float(match.group(1))
        except Exception:
            pass
        return None

    def get_wg_transfer(self, config_name):
        if not config_name:
            return None
        code, output = self._ssh_cmd(
            f"wg show {config_name} transfer 2>/dev/null",
            timeout=5
        )
        if code != 0 or not output.strip():
            return None
        parts = output.strip().split()
        if len(parts) >= 3:
            try:
                return int(parts[1]), int(parts[2])
            except ValueError:
                pass
        return None
