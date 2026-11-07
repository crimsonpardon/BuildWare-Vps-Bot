<div align="center">

# 🖥️ VPS Bot

![Python](https://img.shields.io/badge/Python-3.10+-d00000?style=for-the-badge&logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.x-5b21b6?style=for-the-badge&logo=discord&logoColor=white)
![LXD](https://img.shields.io/badge/LXC%2FLXD-Ready-d00000?style=for-the-badge&logo=linux&logoColor=white)

Fully automated LXC/LXD VPS Discord bot • Made by Crimson

</div>

## Features
- 🖥️ Create, delete and manage LXC/LXD VPS from Discord
- 🔄 Restart, reinstall, clone, snapshot and restore
- 🔌 Port forwarding (TCP/UDP) with per-user quotas
- 🌐 Multi-node management and VPS migration
- 📊 Server stats and resource threshold alerts
- 🛡️ Admin / main-admin permission system
- 📚 Interactive red help menu with category select

## Install (run as root)
```bash
git clone <your-repo-url> && cd <repo> && chmod +x install.sh && sudo ./install.sh
```
It installs LXD, Python deps in a venv, asks for your **bot token** and **main admin ID**, and starts the `bot.service` systemd service (auto-restarts).

```bash
systemctl status bot
journalctl -u bot -f
systemctl restart bot
```

## Commands (prefix `!`)
| Command | Description |
|---|---|
| `!help` | Interactive help menu |
| `!myvps` | List your VPS |
| `!manage <num>` | Manage your VPS |
| `!create <ram_gb> <cpu> <disk_gb> @user [node]` | Create a VPS *(admin)* |
| `!delete-vps @user <number>` | Delete a VPS *(admin)* |
| `!snapshot <num\|container> [name]` | Create a snapshot |
| `!restore <num\|container> <name>` | Restore a snapshot |
| `!clone <num>` / `!reinstall <num>` | Clone / reinstall |
| `!ports add <vps_num> <host_port> [container_port] [tcp\|udp]` | Add a port forward |
| `!serverstats` | Server statistics |
| `!node list` / `add <name> <lxc_remote>` | Nodes *(admin)* |
| `!migrate <container> <node>` | Move VPS between nodes *(admin)* |
| `!admin add/remove/list` | Admins *(main admin)* |

Other nodes must first be added on the host with `lxc remote add`, then registered with `!node add`.

Settings (prefix, footer, limits, quotas) live in `.env`.
