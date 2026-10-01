# Chainedbox L1 Pro — Media / NAS Box (`192.168.2.14`)

Home media/NAS box at `root@192.168.2.14`. Originally surveyed externally
2026-08-22; **re-verified from inside the box (root SSH, key auth) the same
day**. Everything below is confirmed on-host unless marked otherwise.

## What it is

A **Chainedbox L1 Pro** (我家云 / "Particle Cloud" box) — RK3328 quad-core
ARM64 appliance, reflashed with **ayufan's Rock64 Debian image** plus
**OpenMediaVault 4** and a third-party Chinese **Entware app bundle**
(`/opt`, "EntWare扩展集合环境", made by *wdmomo*, 2019). The Entware layer is
what provides most of the visible services and its own init system.

| | |
|---|---|
| SoC / arch | Rockchip RK3328, `aarch64`, 4 cores @ 1.008 GHz |
| RAM | **971 MB** (no swap) — the hard ceiling on this box |
| Board DT | `pine64,rock64` + `rockchip,rk3328`, model string `Chainedbox` |
| NIC | `eth0` @ 1000 Mb/s |
| Root FS | eMMC `mmcblk0p7`, 7.1 G, **48 % used** |
| Boot | eMMC (`/boot/efi` + extlinux). **No SPI/MTD** — reflash is eMMC/SD only |
| Uptime | 98 days at time of check |
| Idle temp | 60–70 °C (passive throttle trip at 70 °C, critical 95 °C) |

### Storage

| Device | Model | Size | Mount | Used |
|--------|-------|------|-------|------|
| `sda1` | ST9500325AS (5400 rpm laptop drive) | 458 G | `/srv/dev-disk-by-label-agent` | 165 G / 37 % |
| `sdb1` | TOSHIBA DT01ACA200 (7200 rpm) | 1.8 T | `/srv/dev-disk-by-label-data` | **1.1 T / 57 %** |

Both drives report `SMART overall-health: PASSED`.

## Firmware / software versions (all EOL)

| Component | Version | Status |
|-----------|---------|--------|
| U-Boot | `2017.09-rockchip-ayufan-1065` (Aug 2019) | frozen, upstream gone |
| Kernel | `5.3.0-1119-ayufan` (Oct 2019) | ~7 years old |
| Debian | **9 "stretch"** | EOL since Jun 2022 (on `archive.debian.org`) |
| OpenMediaVault | **4.1.36 (Arrakis)** | EOL; current OMV is 7/8 |
| OpenSSH | 7.4p1 | EOL |
| OpenSSL | 1.1.0l / 1.0.2u | EOL |
| PHP | 7.0.33 (system), 7.x-fpm (Entware) | EOL |

`apt-get upgrade` reports **0 packages to upgrade** — not because it's current,
but because no repo has anything left to give. The ayufan kernel PPA
(`deb.ayufan.eu/orgs/ayufan-rock64/releases`) is **dead**: `no longer have a
Release file`. There is no in-place patch path for the kernel or bootloader.

## Live services (verified via `ss -lntup`)

| Port | Service | Notes |
|------|---------|-------|
| 22 | sshd | key auth now installed; password auth also on |
| 53 + 8080 | **AdGuard Home** | DNS sinkhole + its web UI (⚠️ README previously called 8080 a "React login app") |
| 80–99 | nginx (Entware `onmp`) | 我家云 launcher + AriaNg, h5ai, phpMyAdmin, etc. across ~10 vhost ports |
| 88 | **OpenMediaVault** panel | the real NAS admin UI |
| 3306 | MySQL (Entware) | **bound to all interfaces** |
| 8088 | FileBrowser | bundle docs its default creds as `root` / `omv` |
| 8899 | easy-explorer (易有云) | |
| 9091 + 51413 | **Transmission** | the sole torrent client (114 torrents); auth required |
| 6800 | **aria2 RPC** | `rpc-secret` is **commented out** → no token |
| 8200 | MiniDLNA | DLNA streaming |
| 21 | ProFTPD | |
| 139 / 445 | Samba | |
| 548 / 4700 | netatalk (AFP) | |
| 111 / 2049 | NFS | exports below |
| 5357 | WSD (python3) | Windows discovery |

**Not running despite being advertised:** Jellyfin/Emby on `:8096` — nothing
listening, connection refused. Seafile/Seahub have init scripts but no
listener. **Docker is not installed.**

### NFS exports
```
/export       192.168.31.0/24
/export/tmp   192.168.31.0/24
```
Still scoped to the **stale `192.168.31.0/24`** subnet — dead config from a
prior network.

## Change log

**2026-08-22 — `ttyd` removed.** It was `ttyd -p 4200 ssh 127.0.0.1`, started
at boot by `/opt/entware_init.sh` → `rc.unslung` → `/opt/etc/init.d/S51ttyd`
(not a systemd unit, which is why nothing in `/etc` referenced it). ttyd 1.5.1
(2019), no `-c` credential and no TLS, so the HTTP layer was open to anyone on
the LAN — though the terminal it opened ran `ssh 127.0.0.1`, which then
prompted for a password. So it was an **unauthenticated browser-based SSH
brute-force surface**, not the direct root shell the first survey assumed.

Actions taken:
- `/opt/etc/init.d/S51ttyd stop`
- `opkg remove ttyd` (removed `/opt/bin/ttyd`)
- `rm /opt/etc/init.d/S51ttyd` — the init script was **not** part of the opkg
  package (`ttyd.list` contained only the binary), so `opkg remove` left it
  behind and it would have survived a reboot as a dead-binary start attempt
- removed the two 超级终端 launcher tiles from `/opt/wwwroot/navi/index.php`
  (`php -l` clean afterwards)
- backups in `/root/backup-2026-08-22/`

Verified: `:4200` closed from the LAN, launcher (`:80`) and OMV (`:88`) still
return 200.

**2026-08-22 — qBittorrent removed, Transmission promoted to sole client.**
qBittorrent v4.1.7 held **zero torrents** — a filesystem-wide search found all
114 `.torrent` files in `/opt/etc/transmission/torrents`, no `.fastresume`
files anywhere, and an empty `BT_backup`. It had been running idle for 98 days
while presenting a serious exposure: its config was two lines
(`[Preferences]` / `WebUI\Port=9080`), so **no Web UI password was set** and
the built-in `admin` / `adminadmin` default worked. Since `qbittorrent-nox`
ran as **root** and its API exposes `autorun_program` ("run external program
on completion"), any LAN host had unauthenticated root RCE — a worse hole than
the ttyd shell removed earlier the same day.

A related trap: with no `save_path` configured it defaulted to
`$HOME/Downloads` = `/root/Downloads`, on the **7.1 GB eMMC root** rather than
the 2 TB data disk.

Actions taken:
- `/opt/etc/init.d/S89qbittorrent stop`
- `opkg remove qbittorrent` — `qbittorrent.list` contained *both* the binary
  and the init script, so unlike `ttyd` no manual `rm` was needed
- launcher `/opt/wwwroot/navi/index.php`: Transmission promoted into
  qBittorrent's tile slot (position 3) and the now-duplicate Transmission tile
  removed, across **both** layout sections; added `rel="noreferrer"`
- backups in `/root/backup-2026-08-22/`; the 88 KB
  `/opt/etc/qBittorrent_entware` config tree is left in place for rollback

Verified: `:9080` and `:8999` closed, `:9091` returns 401 (auth prompt),
launcher and OMV both 200, `php -l` clean. Note the launcher takes up to
**60 s** to reflect edits — `opcache.revalidate_freq=60`.

### Why the qBittorrent Web UI seemed unreachable

Worth recording, since it wasn't a fault in the service. Clicking the launcher
tile sent `Referer: http://192.168.2.14/` (origin `:80`) while the target
origin was `:9080`. **Different port means different origin**, so qBittorrent
4.1.7's CSRF check rejected it with 401 — while typing the URL directly
returned 200. Its log recorded the same mismatch back on 2024-12-29 from the
old `192.168.2.2` addressing. The `rel="noreferrer"` now on the Transmission
tile prevents this class of failure; Transmission does not perform that origin
check, so it is belt-and-braces.

## ⚠️ Remaining security issues

1. **aria2 RPC on `:6800` has no `rpc-secret`** — anyone on the LAN can queue
   downloads. Uncomment and set a token in `/opt/etc/aria2.conf`.
2. **FileBrowser default credentials** — the bundle's own script documents
   `root` / `omv`. Change them.
3. **No firewall at all** — `iptables -L INPUT` is empty with policy `ACCEPT`.
   ~40 listening sockets, MySQL among them, all reachable from any LAN host.
4. **Entire stack is EOL** (see firmware table). Do **not** port-forward any of
   this. Keep it LAN-only, ideally on an isolated VLAN.
5. **Third-party Chinese bundle in `/opt`** with unaudited binaries
   (`easy-explorer-arm`, `onmp`) running as root.

Cleared: **no bandwidth-sharing / phone-home daemon found** (grepped for
particle-cloud, niulink, onethingcloud, xunlei, swarm processes — nothing).

## Should you upgrade the firmware?

**Yes — but by reflashing, not by upgrading in place.**

**Why not in-place:** it would need Debian 9→10→11→12 *and* OMV 4→5→6→7, three
to four hops each, on an image that is already heavily customized (ayufan
kernel, OMV, plus the Entware overlay with its own nginx/PHP/MySQL). OMV's own
guidance for a major-version jump is a clean install, and the community writeups
of just 4→5 describe it as painful. Worse, the ayufan kernel repo is gone, so
even a successful userland upgrade leaves you on the 2019 kernel — a modern
Debian on a 5.3 kernel is the worst of both.

**What a reflash buys:** current RK3328 Armbian-derived builds (ophub /
community RK3318-RK3328 CSC images, kernel 6.12–6.18 as of 2026) give you a
maintained kernel, a Debian 12/13 base, **Docker** (so a current Jellyfin in a
container instead of the dead `:8096`), and it drops the whole unaudited
Entware bundle and its default credentials. There's no SPI flash, so the
reflash risk is contained to eMMC/SD — the box is recoverable.

**Before you do it:**
- Back up the **1.1 TB on `sdb1`** first. An ext4 data disk normally survives a
  reflash untouched, but "normally" is not a backup.
- Export OMV's config and note the share/user definitions — they won't migrate.
- Confirm the specific image boots from SD first, and only then write eMMC.

**The honest caveat:** 1 GB RAM and RK3328 mean this will never be a good
Jellyfin host — no usable hardware transcoding, so every client must direct-play.
A reflash makes it a *maintained* NAS + download + DLNA box. It does not make it
a media server.

**If you'd rather not:** the low-effort path is to accept it as an EOL appliance
— fix the three issues above, put it on an isolated VLAN, disable the services
you don't use (pick one torrent client; drop FTP, AFP, NFS, SNMP, Seafile), and
plan a hardware replacement rather than a software upgrade.

## What it's good for

- **Bulk storage** — 2.3 TB across two healthy spinning disks over gigabit, via
  SMB. Solid backup target / shared library.
- **Download box** — **Transmission** is now the single client (qBittorrent
  removed 2026-08-22). aria2 and Xunlei are still installed; retiring them too
  would cut more surface, but check first whether either holds active
  downloads, the way qBittorrent turned out to be empty.
- **DLNA** (`:8200`) for older smart TVs, where direct-play is the only mode
  anyway.
- **AdGuard Home** is already running and is arguably the best thing on the box.
- **Nextcloud / FileBrowser** — personal file sync, once creds are fixed.

### Fit with existing setup (picoclaw + OrangePi)
- Wire into the **picoclaw Slack bot**: report download queue / free disk, or
  notify on download completion (Transmission and aria2 both expose RPC).
  Mirrors the OrangePi news-bot pattern.
- Use as **always-on storage backend** for other demos (dataset caches for
  stt-bench, model files) over SMB.

---
*Verification method: root SSH (key auth), `ss`/`ps`/`dpkg`/`smartctl`/`opkg`
on-host, plus `curl`/`nc`/`dig` probes from `192.168.2.x`.*

Sources for the upgrade assessment:
[CSC Armbian for RK3318/RK3328 TV box boards](https://forum.armbian.com/topic/26978-csc-armbian-for-rk3318rk3328-tv-box-boards/) ·
[ophub/amlogic-s9xxx-armbian](https://github.com/ophub/amlogic-s9xxx-armbian) ·
[ophub/fnnas issue #560 — Chainedbox L1 Pro (RK3328)](https://github.com/ophub/fnnas/issues/560) ·
[Upgrade OMV 4 to 5: A Painful Path](https://blog.sakuragawa.moe/upgrade-omv-4-to-5-a-painful-path/) ·
[Steps to Upgrade OMV 4.x to 5.x](https://jc-lan.org/2021/01/02/upgrade-omv-4-x-to-5-x/) ·
[OMV8 released with Debian 13 base](https://alternativeto.net/news/2025/12/omv8-released-with-debian-13-base-amd64-and-arm64-support-only)
