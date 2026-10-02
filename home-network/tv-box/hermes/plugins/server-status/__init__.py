"""/server — read-only health report for the box Hermes runs on.

Reads /proc and /sys only; runs no commands and takes no arguments, so it is
safe to expose. Output uses Slack mrkdwn.
"""

import os
import shutil
import socket
import time


def _read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def _fmt_secs(secs):
    secs = int(secs)
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    return (f"{d}d " if d else "") + f"{h}h {m}m"


def _gib(kib):
    return f"{kib / 1048576:.1f} GiB"


def _meminfo():
    out = {}
    for line in _read("/proc/meminfo").splitlines():
        key, _, rest = line.partition(":")
        out[key] = int(rest.split()[0]) if rest.split() else 0
    return out


def _temps():
    temps = []
    base = "/sys/class/thermal"
    for zone in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        raw = _read(f"{base}/{zone}/temp")
        if raw.lstrip("-").isdigit():
            kind = _read(f"{base}/{zone}/type", zone)
            temps.append(f"{kind} {int(raw) / 1000:.0f}°C")
    return ", ".join(temps) or "n/a"


def _gateway():
    """Memory and age of this process (the gateway runs the plugin in-process)."""
    rss_kib = 0
    for line in _read("/proc/self/status").splitlines():
        if line.startswith("VmRSS:"):
            rss_kib = int(line.split()[1])
    start_ticks = int(_read("/proc/self/stat").rsplit(")", 1)[1].split()[19])
    age = float(_read("/proc/uptime").split()[0]) - start_ticks / os.sysconf("SC_CLK_TCK")
    return f"{rss_kib / 1024:.0f} MiB, up {_fmt_secs(age)}"


def _handle(raw_args=""):
    up = float(_read("/proc/uptime", "0").split()[0])
    load = " / ".join(_read("/proc/loadavg", "? ? ?").split()[:3])
    mem = _meminfo()
    total, avail = mem.get("MemTotal", 0), mem.get("MemAvailable", 0)
    disk = shutil.disk_usage("/")
    lines = [
        f"*{socket.gethostname()}* — {time.strftime('%d/%m/%Y %H:%M %Z')}",
        f"• *Uptime:* {_fmt_secs(up)}",
        f"• *Load (1/5/15m):* {load} on {os.cpu_count()} cores",
        f"• *Temperature:* {_temps()}",
        f"• *Memory:* {_gib(total - avail)} used of {_gib(total)} ({(total - avail) * 100 // max(total, 1)}%)",
        f"• *Disk /:* {disk.used / 2**30:.1f} of {disk.total / 2**30:.1f} GiB ({disk.used * 100 // disk.total}%)",
        f"• *Hermes gateway:* {_gateway()}",
    ]
    return "\n".join(lines)


def register(ctx):
    ctx.register_command("server", handler=_handle, description="Health of the box Hermes runs on (read-only).")
