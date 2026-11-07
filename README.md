<div align="center">

# 🖥️ BuildWare VPS Bot

**Fully automated LXC/LXD VPS Discord bot**

![Python](https://img.shields.io/badge/Python-3.10+-d00000?style=for-the-badge&logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.x-5b21b6?style=for-the-badge&logo=discord&logoColor=white)
![LXD](https://img.shields.io/badge/LXC%2FLXD-Ready-d00000?style=for-the-badge&logo=linux&logoColor=white)
![Ubuntu](https://img.shields.io/badge/Ubuntu%20%7C%20Debian-Supported-5b21b6?style=for-the-badge&logo=ubuntu&logoColor=white)

</div>

---

## ✨ Features

- 🖥️ Create, delete and manage LXC/LXD VPS from Discord
- 🔄 Restart, reinstall, clone, snapshot and restore
- 🔌 Port forwarding (TCP/UDP) with per-user quotas
- 🌐 Multi-node management and VPS migration
- 📊 Server stats and resource threshold alerts
- 🛡️ Admin / main-admin permission system
- 📚 Interactive red help menu with category select
- ♻️ Runs as a systemd service that restarts itself

---

## ⚡ Installation

Run as **root** on Ubuntu or Debian:

```bash
git clone https://github.com/crimsonpardon/BuildWare-Vps-Bot.git && cd BuildWare-Vps-Bot && chmod +x install.sh && sudo ./install.sh
```

The installer will:

1. Ask for your OS (Ubuntu / Debian)
2. Install and initialise LXC/LXD
3. Create a Python virtual environment and install dependencies
4. Ask for your **Discord Bot Token** and **Main Admin ID**
5. Create and start the `bot.service` systemd service

### 🔧 Useful commands

```bash
systemctl status bot      # service status
journalctl -u bot -f      # live logs
systemctl restart bot     # restart the bot
```

---

## ⚙️ Configuration

Settings live in `.env` (created by the installer, see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `DISCORD_TOKEN` | — | Your bot token |
| `MAIN_ADMIN_ID` | — | Discord ID of the main admin |
| `PREFIX` | `!` | Command prefix |
| `BOT_NAME` | `VPS Bot` | Name shown in the help menu |
| `FOOTER` | `Made by Crimson` | Embed footer text |
| `VPS_IMAGE` | `ubuntu:22.04` | LXC image for new VPS |
| `MAX_VPS_PER_USER` | `3` | VPS limit per user |
| `PORT_QUOTA` | `5` | Default port forwards per user |
| `ALERT_THRESHOLD` | `90` | CPU/RAM/disk % that alerts the main admin |

After editing, run `systemctl restart bot`.

---

## 📜 Commands

Default prefix: `!` — type `!help` for the interactive menu.

### 👤 User

| Command | Description |
|---|---|
| `!help` | Interactive help menu |
| `!myvps` | List your VPS |
| `!manage <num>` | Manage a VPS (Start / Stop / Restart / Stats buttons) |
| `!snapshot <num\|container> [name]` | Create a snapshot |
| `!snapshots <num>` | List snapshots |
| `!restore <num\|container> <name>` | Restore a snapshot |
| `!clone <num>` | Clone a VPS |
| `!reinstall <num>` | Wipe and reinstall a VPS |
| `!serverstats` | Server statistics |

### 🔌 Ports

| Command | Description |
|---|---|
| `!ports add <vps_num> <host_port> [container_port] [tcp\|udp]` | Add a port forward |
| `!ports list` | List your forwards |
| `!ports remove <host_port>` | Remove a forward |

### 🛠️ Admin

| Command | Description |
|---|---|
| `!create <ram_gb> <cpu> <disk_gb> @user [node]` | Create a VPS |
| `!delete-vps @user <number>` | Delete a VPS |
| `!allvps` | List every VPS |
| `!migrate <container> <node>` | Move a VPS to another node |
| `!ports quota @user <n>` | Set a user's port quota |
| `!node list` | List nodes |
| `!node add <name> <lxc_remote>` | Add a node |
| `!node remove <name>` | Remove a node |

### 👑 Main admin

| Command | Description |
|---|---|
| `!admin add @user` | Add an admin |
| `!admin remove @user` | Remove an admin |
| `!admin list` | List admins |

> Extra nodes must first be added on the host with `lxc remote add`, then registered in the bot with `!node add`.

---

## 🩺 Troubleshooting

- **VPS creation fails:** run `lxc list` on the host, and `lxd init --auto` if LXD isn't initialised.
- **Bot offline:** check `journalctl -u bot -f` for errors such as a wrong token.
- **Can't SSH into a VPS:** forward the port first, e.g. `!ports add 1 2222 22`, then `ssh root@<server-ip> -p 2222`.

---

<div align="center">

Need help? Open an issue or contact the admin on Discord.

**Made with ❤️ by Crimson**

</div>
