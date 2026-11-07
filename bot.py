import os, shutil, json, time, time as _t, random, string, asyncio, sqlite3
import discord
from discord.ext import commands, tasks
import psutil
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN", "")
MAIN_ADMIN = int(os.getenv("MAIN_ADMIN_ID", "0"))
PREFIX = os.getenv("PREFIX", "!")
BOT_NAME = os.getenv("BOT_NAME", "VPS Bot")
FOOTER = os.getenv("FOOTER", "Made by Crimson")
IMAGE = os.getenv("VPS_IMAGE", "ubuntu:22.04")
MAX_VPS = int(os.getenv("MAX_VPS_PER_USER", "3"))
DEFAULT_PORT_QUOTA = int(os.getenv("PORT_QUOTA", "5"))
THRESHOLD = int(os.getenv("ALERT_THRESHOLD", "90"))
RED = 0xD00000
START = _t.time()
os.environ["PATH"] = os.environ.get("PATH", "") + ":/snap/bin:/usr/local/bin:/usr/bin"
LXC = shutil.which("lxc") or next((p for p in ("/snap/bin/lxc", "/usr/bin/lxc", "/usr/local/bin/lxc") if os.path.exists(p)), None)

db = sqlite3.connect("data.db")
db.row_factory = sqlite3.Row
db.executescript("""
CREATE TABLE IF NOT EXISTS vps(id INTEGER PRIMARY KEY AUTOINCREMENT, owner INTEGER, container TEXT,
  node TEXT, ram INTEGER, cpu INTEGER, disk INTEGER, created INTEGER);
CREATE TABLE IF NOT EXISTS admins(user_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS nodes(name TEXT PRIMARY KEY, remote TEXT);
CREATE TABLE IF NOT EXISTS ports(id INTEGER PRIMARY KEY AUTOINCREMENT, owner INTEGER, container TEXT,
  host_port INTEGER, cont_port INTEGER, proto TEXT);
CREATE TABLE IF NOT EXISTS quotas(user_id INTEGER PRIMARY KEY, quota INTEGER);
INSERT OR IGNORE INTO nodes(name, remote) VALUES('local', '');
""")
db.commit()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)


# ---------- helpers ----------
def emb(title, desc="", color=RED):
    e = discord.Embed(title=title, description=desc, color=color)
    e.set_footer(text=FOOTER)
    return e

def is_admin(uid):
    return uid == MAIN_ADMIN or db.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,)).fetchone() is not None

def admin_only():
    async def p(ctx):
        if not is_admin(ctx.author.id):
            raise commands.CheckFailure("Admins only.")
        return True
    return commands.check(p)

def main_admin_only():
    async def p(ctx):
        if ctx.author.id != MAIN_ADMIN:
            raise commands.CheckFailure("Main admin only.")
        return True
    return commands.check(p)

async def run(*cmd, timeout=300):
    cmd = list(cmd)
    if cmd[0] == "lxc":
        if not LXC:
            return 127, "lxc is not installed on this host. Run: snap install lxd && lxd init --auto, then restart the bot."
        cmd[0] = LXC
    try:
        p = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    except Exception as ex:
        return 127, f"could not run command: {ex}"
    try:
        out, _ = await asyncio.wait_for(p.communicate(), timeout)
    except asyncio.TimeoutError:
        p.kill()
        return 1, "timed out"
    return p.returncode, out.decode(errors="ignore").strip()

def remote_of(node):
    r = db.execute("SELECT remote FROM nodes WHERE name=?", (node,)).fetchone()
    return (r["remote"] if r and r["remote"] else "local")

def tgt(v):
    return f"{remote_of(v['node'])}:{v['container']}"

def user_vps(uid):
    return db.execute("SELECT * FROM vps WHERE owner=? ORDER BY id", (uid,)).fetchall()

def resolve(ctx, ref):
    ref = str(ref)
    if ref.isdigit():
        rows = user_vps(ctx.author.id)
        n = int(ref)
        return rows[n - 1] if 1 <= n <= len(rows) else None
    v = db.execute("SELECT * FROM vps WHERE container=?", (ref,)).fetchone()
    if v and (v["owner"] == ctx.author.id or is_admin(ctx.author.id)):
        return v
    return None

async def status_of(v):
    rc, out = await run("lxc", "query", f"{remote_of(v['node'])}:/1.0/instances/{v['container']}")
    try:
        return json.loads(out)["status"]
    except Exception:
        return "Unknown"

def pw():
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(14))

async def build(v):
    t = tgt(v)
    steps = [
        ["lxc", "init", IMAGE, t],
        ["lxc", "config", "set", t, "limits.memory", f"{v['ram']}GB"],
        ["lxc", "config", "set", t, "limits.cpu", str(v["cpu"])],
        ["lxc", "config", "set", t, "boot.autostart", "true"],
        ["lxc", "config", "set", t, "security.nesting", "true"],
    ]
    for s in steps:
        rc, out = await run(*s)
        if rc != 0:
            return None, f"`{' '.join(s[:3])}` failed:\n{out[-800:]}"
    size = f"size={v['disk']}GB"
    rc, out = await run("lxc", "config", "device", "override", t, "root", size)
    if rc != 0:
        rc, out = await run("lxc", "config", "device", "add", t, "root", "disk", "path=/", "pool=default", size)
        if rc != 0:
            return None, f"Disk limit failed:\n{out[-800:]}"
    rc, out = await run("lxc", "start", t)
    if rc != 0:
        return None, f"Start failed:\n{out[-800:]}"
    for _ in range(30):
        rc, _o = await run("lxc", "exec", t, "--", "true", timeout=15)
        if rc == 0:
            break
        await asyncio.sleep(2)
    password = pw()
    script = (f"echo root:{password} | chpasswd; "
              "sed -i 's/^#\\?PermitRootLogin.*/PermitRootLogin yes/;s/^#\\?PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config; "
              "systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null || true")
    await run("lxc", "exec", t, "--", "sh", "-c", script, timeout=60)
    return password, None

async def destroy(v):
    t = tgt(v)
    await run("lxc", "stop", t, "--force")
    rc, out = await run("lxc", "delete", t, "--force")
    db.execute("DELETE FROM ports WHERE container=?", (v["container"],))
    db.execute("DELETE FROM vps WHERE id=?", (v["id"],))
    db.commit()
    return rc, out

def vps_embed(v, num=None, status=None):
    e = emb(f"VPS {num}" if num else v["container"])
    e.add_field(name="Container", value=f"`{v['container']}`")
    e.add_field(name="Node", value=v["node"])
    e.add_field(name="Status", value=status or "?")
    e.add_field(name="RAM", value=f"{v['ram']} GB")
    e.add_field(name="CPU", value=f"{v['cpu']} cores")
    e.add_field(name="Disk", value=f"{v['disk']} GB")
    return e

def quota_of(uid):
    r = db.execute("SELECT quota FROM quotas WHERE user_id=?", (uid,)).fetchone()
    return r["quota"] if r else DEFAULT_PORT_QUOTA


# ---------- help ----------
HELP = {
    "User": [("help", "Interactive help menu"), ("myvps", "List your VPS"), ("manage <num>", "Manage a VPS (buttons)"),
             ("snapshot <num|container> [name]", "Create a snapshot"), ("snapshots <num>", "List snapshots"),
             ("restore <num|container> <name>", "Restore a snapshot"), ("clone <num>", "Clone your VPS"),
             ("reinstall <num>", "Reinstall (wipes data)"), ("serverstats", "Host statistics")],
    "Ports": [("ports add <vps_num> <host_port> [container_port] [tcp|udp]", "Add a port forward"),
              ("ports list", "List your forwards"), ("ports remove <host_port>", "Remove a forward")],
    "Admin": [("create <ram_gb> <cpu> <disk_gb> @user [node]", "Create a VPS"), ("delete-vps @user <number>", "Delete a VPS"),
              ("allvps", "List every VPS"), ("migrate <container> <node>", "Move VPS to another node"),
              ("ports quota @user <n>", "Set port quota"), ("node list | add <name> <lxc_remote> | remove <name>", "Manage nodes")],
    "Main Admin": [("admin add @user", "Add admin"), ("admin remove @user", "Remove admin"), ("admin list", "List admins")],
}

def help_embed(cat=None):
    if cat is None:
        e = emb(f"{BOT_NAME} — Help", f"Prefix: `{PREFIX}`\nPick a category from the menu below.")
        for c, items in HELP.items():
            e.add_field(name=c, value=f"{len(items)} commands")
        return e
    e = emb(f"{cat} commands")
    e.description = "\n".join(f"`{PREFIX}{c}` — {d}" for c, d in HELP[cat])
    return e

class HelpView(discord.ui.View):
    def __init__(self, uid):
        super().__init__(timeout=180)
        self.uid = uid
        sel = discord.ui.Select(placeholder="Choose a category", options=[discord.SelectOption(label=c) for c in HELP])
        sel.callback = self.cb
        self.sel = sel
        self.add_item(sel)
    async def cb(self, i: discord.Interaction):
        if i.user.id != self.uid:
            return await i.response.send_message("Not your menu.", ephemeral=True)
        await i.response.edit_message(embed=help_embed(self.sel.values[0]), view=self)

@bot.command()
async def help(ctx):
    await ctx.send(embed=help_embed(), view=HelpView(ctx.author.id))


# ---------- user commands ----------
@bot.command()
async def myvps(ctx):
    rows = user_vps(ctx.author.id)
    if not rows:
        return await ctx.send(embed=emb("My VPS", "You have no VPS."))
    e = emb("My VPS")
    for n, v in enumerate(rows, 1):
        e.add_field(name=f"#{n} — {v['container']}", value=f"{v['ram']}GB RAM • {v['cpu']} CPU • {v['disk']}GB disk • node `{v['node']}`", inline=False)
    await ctx.send(embed=e)

class ManageView(discord.ui.View):
    def __init__(self, v, uid):
        super().__init__(timeout=300)
        self.v, self.uid = v, uid
    async def _act(self, i, action):
        if i.user.id != self.uid and not is_admin(i.user.id):
            return await i.response.send_message("Not your VPS.", ephemeral=True)
        await i.response.defer(ephemeral=True)
        t = tgt(self.v)
        if action == "stats":
            rc, out = await run("lxc", "exec", t, "--", "sh", "-c",
                "free -m | awk 'NR==2{print \"RAM: \"$3\"/\"$2\" MB\"}'; df -h / | awk 'NR==2{print \"Disk: \"$3\"/\"$2}'; uptime -p")
            return await i.followup.send(embed=emb("Stats", f"```{out[-900:]}```"), ephemeral=True)
        rc, out = await run("lxc", action, t) if action != "stop" else await run("lxc", "stop", t, "--force")
        await i.followup.send(embed=emb(action.title(), "Done." if rc == 0 else f"Failed:\n```{out[-900:]}```"), ephemeral=True)
    @discord.ui.button(label="Start", style=discord.ButtonStyle.success)
    async def b1(self, i, b): await self._act(i, "start")
    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger)
    async def b2(self, i, b): await self._act(i, "stop")
    @discord.ui.button(label="Restart", style=discord.ButtonStyle.primary)
    async def b3(self, i, b): await self._act(i, "restart")
    @discord.ui.button(label="Stats", style=discord.ButtonStyle.secondary)
    async def b4(self, i, b): await self._act(i, "stats")

@bot.command()
async def manage(ctx, ref: str = "1"):
    v = resolve(ctx, ref)
    if not v:
        return await ctx.send(embed=emb("Manage", "VPS not found."))
    st = await status_of(v)
    await ctx.send(embed=vps_embed(v, ref if ref.isdigit() else None, st), view=ManageView(v, v["owner"]))

@bot.command()
async def snapshot(ctx, ref: str, name: str = None):
    v = resolve(ctx, ref)
    if not v:
        return await ctx.send(embed=emb("Snapshot", "VPS not found."))
    name = name or f"snap-{int(time.time())}"
    rc, out = await run("lxc", "snapshot", tgt(v), name)
    await ctx.send(embed=emb("Snapshot", f"Created `{name}`." if rc == 0 else f"Failed:\n```{out[-900:]}```"))

@bot.command()
async def snapshots(ctx, ref: str):
    v = resolve(ctx, ref)
    if not v:
        return await ctx.send(embed=emb("Snapshots", "VPS not found."))
    rc, out = await run("lxc", "query", f"{remote_of(v['node'])}:/1.0/instances/{v['container']}/snapshots")
    try:
        names = [p.rsplit("/", 1)[-1] for p in json.loads(out)]
    except Exception:
        names = []
    await ctx.send(embed=emb("Snapshots", "\n".join(f"• `{n}`" for n in names) or "None."))

@bot.command()
async def restore(ctx, ref: str, name: str):
    v = resolve(ctx, ref)
    if not v:
        return await ctx.send(embed=emb("Restore", "VPS not found."))
    rc, out = await run("lxc", "restore", tgt(v), name)
    await ctx.send(embed=emb("Restore", "Restored." if rc == 0 else f"Failed:\n```{out[-900:]}```"))

@bot.command()
async def clone(ctx, ref: str):
    v = resolve(ctx, ref)
    if not v:
        return await ctx.send(embed=emb("Clone", "VPS not found."))
    if len(user_vps(v["owner"])) >= MAX_VPS and not is_admin(ctx.author.id):
        return await ctx.send(embed=emb("Clone", f"VPS limit reached ({MAX_VPS})."))
    cur = db.execute("INSERT INTO vps(owner,container,node,ram,cpu,disk,created) VALUES(?,?,?,?,?,?,?)",
                     (v["owner"], "pending", v["node"], v["ram"], v["cpu"], v["disk"], int(time.time())))
    name = f"vps-{cur.lastrowid}"
    db.execute("UPDATE vps SET container=? WHERE id=?", (name, cur.lastrowid)); db.commit()
    r = remote_of(v["node"])
    m = await ctx.send(embed=emb("Clone", "⏳ Cloning..."))
    rc, out = await run("lxc", "copy", tgt(v), f"{r}:{name}")
    if rc == 0:
        await run("lxc", "start", f"{r}:{name}")
        await m.edit(embed=emb("Clone", f"Cloned as `{name}`."))
    else:
        db.execute("DELETE FROM vps WHERE id=?", (cur.lastrowid,)); db.commit()
        await m.edit(embed=emb("Clone", f"Failed:\n```{out[-900:]}```"))

@bot.command()
async def reinstall(ctx, ref: str):
    v = resolve(ctx, ref)
    if not v:
        return await ctx.send(embed=emb("Reinstall", "VPS not found."))
    m = await ctx.send(embed=emb("Reinstall", "⏳ Wiping and reinstalling..."))
    t = tgt(v)
    await run("lxc", "stop", t, "--force")
    await run("lxc", "delete", t, "--force")
    password, err = await build(v)
    if err:
        return await m.edit(embed=emb("Reinstall", f"Failed:\n```{err}```"))
    try:
        await ctx.author.send(embed=emb("VPS reinstalled", f"`{v['container']}` root password: `{password}`"))
        await m.edit(embed=emb("Reinstall", "Done. New root password sent by DM."))
    except discord.Forbidden:
        await m.edit(embed=emb("Reinstall", "Done, but I can't DM you. Enable DMs and run again."))

@bot.command()
async def serverstats(ctx):
    e = emb("Server stats")
    e.add_field(name="CPU", value=f"{psutil.cpu_percent(interval=0.5)}%")
    m = psutil.virtual_memory()
    e.add_field(name="RAM", value=f"{m.used/1e9:.1f}/{m.total/1e9:.1f} GB")
    d = psutil.disk_usage("/")
    e.add_field(name="Disk", value=f"{d.used/1e9:.0f}/{d.total/1e9:.0f} GB")
    e.add_field(name="VPS", value=str(db.execute("SELECT COUNT(*) c FROM vps").fetchone()["c"]))
    e.add_field(name="Host uptime", value=f"{int((time.time()-psutil.boot_time())//3600)}h")
    e.add_field(name="Bot uptime", value=f"{int((time.time()-START)//3600)}h")
    await ctx.send(embed=e)


# ---------- ports ----------
@bot.group(invoke_without_command=True)
async def ports(ctx):
    await ctx.send(embed=help_embed("Ports"))

@ports.command(name="add")
async def ports_add(ctx, vps_num: int, host_port: int, cont_port: int = None, proto: str = "tcp"):
    proto = proto.lower()
    cont_port = cont_port or host_port
    v = resolve(ctx, vps_num)
    if not v:
        return await ctx.send(embed=emb("Ports", "VPS not found."))
    if proto not in ("tcp", "udp") or not (1024 <= host_port <= 65535) or not (1 <= cont_port <= 65535):
        return await ctx.send(embed=emb("Ports", "Host port must be 1024–65535, protocol tcp or udp."))
    used = db.execute("SELECT COUNT(*) c FROM ports WHERE owner=?", (ctx.author.id,)).fetchone()["c"]
    if used >= quota_of(ctx.author.id) and not is_admin(ctx.author.id):
        return await ctx.send(embed=emb("Ports", f"Port quota reached ({quota_of(ctx.author.id)})."))
    if db.execute("SELECT 1 FROM ports WHERE host_port=? AND proto=?", (host_port, proto)).fetchone():
        return await ctx.send(embed=emb("Ports", "That host port is already taken."))
    rc, out = await run("lxc", "config", "device", "add", tgt(v), f"fwd-{proto}-{host_port}", "proxy",
                        f"listen={proto}:0.0.0.0:{host_port}", f"connect={proto}:127.0.0.1:{cont_port}")
    if rc != 0:
        return await ctx.send(embed=emb("Ports", f"Failed:\n```{out[-900:]}```"))
    db.execute("INSERT INTO ports(owner,container,host_port,cont_port,proto) VALUES(?,?,?,?,?)",
               (ctx.author.id, v["container"], host_port, cont_port, proto)); db.commit()
    await ctx.send(embed=emb("Ports", f"Forwarding `{proto}` host `{host_port}` → VPS `{cont_port}`."))

@ports.command(name="list")
async def ports_list(ctx):
    rows = db.execute("SELECT * FROM ports WHERE owner=?", (ctx.author.id,)).fetchall()
    txt = "\n".join(f"`{r['proto']}` {r['host_port']} → {r['cont_port']} ({r['container']})" for r in rows)
    await ctx.send(embed=emb("Ports", f"{txt or 'None.'}\n\nQuota: {len(rows)}/{quota_of(ctx.author.id)}"))

@ports.command(name="remove")
async def ports_remove(ctx, host_port: int, proto: str = "tcp"):
    r = db.execute("SELECT * FROM ports WHERE host_port=? AND proto=?", (host_port, proto.lower())).fetchone()
    if not r or (r["owner"] != ctx.author.id and not is_admin(ctx.author.id)):
        return await ctx.send(embed=emb("Ports", "Forward not found."))
    v = db.execute("SELECT * FROM vps WHERE container=?", (r["container"],)).fetchone()
    if v:
        await run("lxc", "config", "device", "remove", tgt(v), f"fwd-{r['proto']}-{host_port}")
    db.execute("DELETE FROM ports WHERE id=?", (r["id"],)); db.commit()
    await ctx.send(embed=emb("Ports", "Removed."))

@ports.command(name="quota")
@admin_only()
async def ports_quota(ctx, member: discord.Member, n: int):
    db.execute("INSERT OR REPLACE INTO quotas(user_id,quota) VALUES(?,?)", (member.id, n)); db.commit()
    await ctx.send(embed=emb("Ports", f"{member.mention} quota set to {n}."))


# ---------- admin ----------
@bot.command()
@admin_only()
async def create(ctx, ram: int, cpu: int, disk: int, member: discord.Member, node: str = "local"):
    if not (1 <= ram <= 256 and 1 <= cpu <= 64 and 1 <= disk <= 2000):
        return await ctx.send(embed=emb("Create", "Values out of range."))
    if not db.execute("SELECT 1 FROM nodes WHERE name=?", (node,)).fetchone():
        return await ctx.send(embed=emb("Create", f"Node `{node}` not found."))
    if len(user_vps(member.id)) >= MAX_VPS:
        return await ctx.send(embed=emb("Create", f"{member.mention} already has {MAX_VPS} VPS."))
    cur = db.execute("INSERT INTO vps(owner,container,node,ram,cpu,disk,created) VALUES(?,?,?,?,?,?,?)",
                     (member.id, "pending", node, ram, cpu, disk, int(time.time())))
    name = f"vps-{cur.lastrowid}"
    db.execute("UPDATE vps SET container=? WHERE id=?", (name, cur.lastrowid)); db.commit()
    v = db.execute("SELECT * FROM vps WHERE id=?", (cur.lastrowid,)).fetchone()
    m = await ctx.send(embed=emb("Create", "⏳ Creating VPS, this can take a few minutes..."))
    password, err = await build(v)
    if err:
        await run("lxc", "delete", tgt(v), "--force")
        db.execute("DELETE FROM vps WHERE id=?", (v["id"],)); db.commit()
        return await m.edit(embed=emb("Create failed", f"```{err}```\nRun `lxc list` and `lxd init --auto` on the host if LXD isn't ready."))
    try:
        await member.send(embed=emb("Your VPS is ready", f"Container: `{name}`\nRAM {ram}GB • CPU {cpu} • Disk {disk}GB\nRoot password: `{password}`\n\nUse `{PREFIX}ports add <num> <host_port> 22` to open SSH."))
        note = "Details sent to the user by DM."
    except discord.Forbidden:
        note = f"Couldn't DM the user. Root password: `{password}`"
    await m.edit(embed=emb("VPS created", f"`{name}` for {member.mention}\n{note}"))

@bot.command(name="delete-vps")
@admin_only()
async def delete_vps(ctx, member: discord.Member, number: int):
    rows = user_vps(member.id)
    if not (1 <= number <= len(rows)):
        return await ctx.send(embed=emb("Delete", "VPS not found."))
    v = rows[number - 1]
    rc, out = await destroy(v)
    await ctx.send(embed=emb("Delete", f"Deleted `{v['container']}`." if rc == 0 else f"Removed from DB; lxc said:\n```{out[-700:]}```"))

@bot.command()
@admin_only()
async def allvps(ctx):
    rows = db.execute("SELECT * FROM vps ORDER BY id").fetchall()
    txt = "\n".join(f"`{v['container']}` <@{v['owner']}> {v['ram']}G/{v['cpu']}C/{v['disk']}G @{v['node']}" for v in rows[:40])
    await ctx.send(embed=emb(f"All VPS ({len(rows)})", txt or "None."))

@bot.command()
@admin_only()
async def migrate(ctx, container: str, node: str):
    v = db.execute("SELECT * FROM vps WHERE container=?", (container,)).fetchone()
    if not v or not db.execute("SELECT 1 FROM nodes WHERE name=?", (node,)).fetchone():
        return await ctx.send(embed=emb("Migrate", "VPS or node not found."))
    m = await ctx.send(embed=emb("Migrate", "⏳ Moving..."))
    src, dst = tgt(v), f"{remote_of(node)}:{container}"
    await run("lxc", "stop", src, "--force")
    rc, out = await run("lxc", "move", src, dst, timeout=1800)
    if rc == 0:
        db.execute("UPDATE vps SET node=? WHERE id=?", (node, v["id"])); db.commit()
        await run("lxc", "start", dst)
        await m.edit(embed=emb("Migrate", f"Moved `{container}` to `{node}`."))
    else:
        await run("lxc", "start", src)
        await m.edit(embed=emb("Migrate", f"Failed:\n```{out[-900:]}```"))

@bot.group(invoke_without_command=True)
@admin_only()
async def node(ctx):
    await ctx.send(embed=help_embed("Admin"))

@node.command(name="list")
async def node_list(ctx):
    rows = db.execute("SELECT * FROM nodes").fetchall()
    txt = "\n".join(f"`{r['name']}` → remote `{r['remote'] or 'local'}` ({db.execute('SELECT COUNT(*) c FROM vps WHERE node=?', (r['name'],)).fetchone()['c']} VPS)" for r in rows)
    await ctx.send(embed=emb("Nodes", txt))

@node.command(name="add")
async def node_add(ctx, name: str, remote: str):
    rc, out = await run("lxc", "list", f"{remote}:", "--format", "csv")
    if rc != 0:
        return await ctx.send(embed=emb("Nodes", f"Remote `{remote}` not reachable. Add it first with `lxc remote add`.\n```{out[-500:]}```"))
    db.execute("INSERT OR REPLACE INTO nodes(name,remote) VALUES(?,?)", (name, remote)); db.commit()
    await ctx.send(embed=emb("Nodes", f"Node `{name}` added."))

@node.command(name="remove")
async def node_remove(ctx, name: str):
    if name == "local" or db.execute("SELECT 1 FROM vps WHERE node=?", (name,)).fetchone():
        return await ctx.send(embed=emb("Nodes", "Can't remove local node or a node that still has VPS."))
    db.execute("DELETE FROM nodes WHERE name=?", (name,)); db.commit()
    await ctx.send(embed=emb("Nodes", "Removed."))

@bot.group(name="admin", invoke_without_command=True)
@main_admin_only()
async def admin_grp(ctx):
    await ctx.send(embed=help_embed("Main Admin"))

@admin_grp.command(name="add")
async def admin_add(ctx, member: discord.Member):
    db.execute("INSERT OR IGNORE INTO admins VALUES(?)", (member.id,)); db.commit()
    await ctx.send(embed=emb("Admin", f"{member.mention} is now an admin."))

@admin_grp.command(name="remove")
async def admin_remove(ctx, member: discord.Member):
    db.execute("DELETE FROM admins WHERE user_id=?", (member.id,)); db.commit()
    await ctx.send(embed=emb("Admin", f"{member.mention} removed."))

@admin_grp.command(name="list")
async def admin_list(ctx):
    rows = db.execute("SELECT user_id FROM admins").fetchall()
    await ctx.send(embed=emb("Admins", f"Main: <@{MAIN_ADMIN}>\n" + "\n".join(f"<@{r['user_id']}>" for r in rows)))


# ---------- background ----------
last_alert = 0

@tasks.loop(seconds=60)
async def watchdog():
    global last_alert
    cpu, mem, disk = psutil.cpu_percent(), psutil.virtual_memory().percent, psutil.disk_usage("/").percent
    if max(cpu, mem, disk) >= THRESHOLD and time.time() - last_alert > 1800 and MAIN_ADMIN:
        last_alert = time.time()
        try:
            u = await bot.fetch_user(MAIN_ADMIN)
            await u.send(embed=emb("⚠️ Resource alert", f"CPU {cpu}% • RAM {mem}% • Disk {disk}%"))
        except Exception:
            pass

@tasks.loop(seconds=30)
async def presence():
    n = db.execute("SELECT COUNT(*) c FROM vps").fetchone()["c"]
    await bot.change_presence(activity=discord.Game(f"{n} VPS • {PREFIX}help"))

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    if not watchdog.is_running(): watchdog.start()
    if not presence.is_running(): presence.start()

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        msg = f"Missing argument `{error.param.name}`. See `{PREFIX}help`."
    elif isinstance(error, (commands.BadArgument, commands.MemberNotFound)):
        msg = "Invalid argument."
    elif isinstance(error, commands.CheckFailure):
        msg = str(error) or "You can't use this."
    else:
        msg = f"Error: `{error}`"
    await ctx.send(embed=emb("Error", msg))

if not TOKEN:
    raise SystemExit("DISCORD_TOKEN missing. Run install.sh or create .env")
bot.run(TOKEN)
