# VPN Shuttle

A GTK 4 / libadwaita desktop app for Linux that routes your traffic through WireGuard VPNs via SSH jump hosts using [sshuttle](https://github.com/sshuttle/sshuttle).

## What It Does

VPN Shuttle lets you tunnel traffic through a remote WireGuard VPN **without installing WireGuard locally**. It works by:

1. SSHing into your jump host and bringing up a WireGuard interface there
2. Running `sshuttle` locally to forward your chosen traffic through the SSH tunnel
3. The jump host forwards that traffic out through WireGuard into the VPN network

```
Your Machine ──SSH tunnel──▶ Jump Host ──WireGuard──▶ VPN Network
```

## Features

- **Multiple jump hosts** — add, edit, remove, and switch between hosts
- **One-click host setup** — installs WireGuard, enables IP forwarding, deploys routing scripts
- **VPN config management** — upload, list, and delete WireGuard `.conf` files on remote hosts
- **Flexible routing** — route all traffic or only specific subnets (saved per config)
- **Auto-connect on startup** — reconnects to the last used config
- **Desktop notifications** — alerts on connect/disconnect
- **Export/import settings** — backup and restore your configuration
- **Import routes from file** — load subnet lists from text files

## Requirements

### Your machine

- Python 3.10+
- GTK 4 and libadwaita 1.x
- PyGObject (`python3-gi`)
- `sshuttle`
- `ssh` and `scp` (OpenSSH)
- `sudo` (sshuttle needs it)

### Jump host

- Linux with SSH access (root or sudo user)
- Internet access (for WireGuard installation during setup)
- At least one WireGuard `.conf` file

## Install

### From source (Debian/Ubuntu)

```bash
# Install dependencies
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 sshuttle

# Clone and run
git clone https://github.com/twibster/vpn-shuttle-gui.git
cd vpn-shuttle-gui
python3 -m vpn_shuttle
```

### AppImage

```bash
# Build
./build-appimage.sh

# Run
chmod +x build/VPN_Shuttle-x86_64.AppImage
./build/VPN_Shuttle-x86_64.AppImage
```

> The AppImage bundles only the app code. System libraries (GTK 4, libadwaita, Python, sshuttle) must be installed on the host.

## Getting Started

1. **Launch the app**
2. Click the **gear icon** and go to the **Hosts** tab
3. Click **Add Host** — enter display name, IP, SSH user, and key path
4. Expand your host and click **Setup Host** — this installs WireGuard and configures the server
5. Click **Manage VPN Configs** and upload a WireGuard `.conf` file
6. Close settings — select your host and config from the header dropdowns
7. Choose **All Traffic** or **Specific IPs** routing
8. Click **Connect**

## How It Works

### Connection flow

When you click Connect, the app:

1. Runs `vpn-manage up <config>` on the jump host via SSH, which:
   - Brings up the WireGuard interface with `wg-quick`
   - Creates a separate routing table (table 100) for forwarded traffic
   - Adds policy routing rules so the jump host's own traffic stays on the default interface
2. Launches `sshuttle` locally with `--dns` and the chosen subnets
3. Streams sshuttle output to the log viewer in real-time

On disconnect, it kills sshuttle and runs `vpn-manage down` to tear everything down.

### Routing

The jump host uses split routing so its SSH connection doesn't get routed into the VPN (which would break the tunnel). Traffic from your machine goes through sshuttle → SSH → WireGuard. Traffic originating from the jump host itself goes out the default interface.

### Config storage

Settings are stored at `~/.config/vpn-shuttle/settings.json`:

```json
{
  "hosts": {
    "a1b2c3d4": {
      "name": "My Server",
      "ip": "203.0.113.10",
      "user": "root",
      "ssh_key_path": "/home/user/.ssh/id_rsa",
      "setup_complete": true,
      "saved_routes": {
        "wg0": ["10.0.0.0/8"]
      }
    }
  },
  "active_host": "a1b2c3d4",
  "last_config": "wg0",
  "routing_mode": "specific",
  "auto_connect": false,
  "notifications": true
}
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "No host selected" | Add a host in Settings > Hosts |
| "No VPN config selected" | Upload a `.conf` file via Settings > Hosts > Manage VPN Configs |
| sshuttle fails to start | Check `which sshuttle` and that `sudo` works without blocking |
| SSH connection fails | Verify key path and permissions (`chmod 600 ~/.ssh/id_rsa`) |
| Setup fails at WireGuard install | Jump host needs internet access for apt |
| WireGuard module issue | Reboot the jump host after setup |

## Project Structure

```
vpn_shuttle/
  __init__.py         # App constants
  __main__.py         # Entry point
  app.py              # Main window, CSS, header bar
  backend.py          # SSH/SCP/sshuttle management
  config.py           # JSON settings persistence
  widgets/
    status.py         # Live status panel with stats
    routing.py        # Routing mode toggle and subnet editor
    logs.py           # Color-coded log viewer
    settings.py       # Settings dialog (General + Hosts)
    host_setup.py     # Host add/edit/setup/config dialogs
```
