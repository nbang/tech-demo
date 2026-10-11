# Chainedbox L1 Pro — Media / NAS Box (`192.168.2.10`, MAC `66:c9:1c:46:67:db`)

Always-on home NAS, download and DLNA box. `ssh root@192.168.2.10` (key auth).
OMV UI: <http://192.168.2.10:88>. AdGuard UI: <http://192.168.2.10:8080>.

**The address comes from DHCP**, with a reservation for `.10` on the mesh main
router. Don't set a static IP on the box. If it's missing, find it by MAC:
`arp -an | grep 66:c9:1c:46:67:db`.

## Hardware

| | |
|---|---|
| SoC | Rockchip RK3328, `aarch64`, 4× Cortex-A53 @ 1.5 GHz. Board DT `pine64,rock64` |
| RAM | **971 MB**, no swap. The hard limit on this box |
| NIC | **`end0`**, 1 Gb/s. **No permanent MAC** (`66:c9:…` is assigned at boot) |
| Root FS | eMMC `mmcblk0p7`, 7.1 G, ~58 % used |
| Boot | ayufan U-Boot 2017.09 → `/boot/extlinux/extlinux.conf` on p7. **No SD slot, no SPI** |
| Temp | Idles at 60–70 °C (throttle trip 70 °C). `fan.service` (`/sbin/fan`) drives the fan |

### Disks (both USB)

| Dev | Label / mount | Drive | Size | Health |
|-----|---------------|-------|------|--------|
| `sda1` | `agent` → `/srv/dev-disk-by-label-agent` | Seagate ST9500325AS 2.5" (FreeAgent Go, USB `0bc2:2100`) | 458 G, ~37 % | **Failing**: reallocated + pending sectors, 5190 Reported_Uncorrect, ~63k h |
| `sdb1` | `data` → `/srv/dev-disk-by-label-data` | Toshiba DT01ACA200 (inside the case, USB `05e3:0735`) | 1.8 T, ~60 % | OK, 0 reallocated |

- `data`: `media/` (`videos`, `torrent`, `movies`, `musics`, `clips`) and `bk/`.
- `agent`: `backup/` and `tmp/`. Keep it read-only and outside OMV until it's
  replaced. `agent:/tmp/` was already copied to `data:/bk/` once.
- **To do: copy anything still needed off `agent`, then replace the drive.**
  [`copy-agent-backup.sh`](copy-agent-backup.sh) rsyncs a folder from `agent`
  to `data` (`SRC`/`DST` env vars). It resumes, skips unreadable files and
  logs failures to `/root/`.

## Software

| Component | Version | Notes |
|-----------|---------|-------|
| Debian | 12 "bookworm" | security via Debian LTS until ~mid-2028 |
| OpenMediaVault | 7 (Sandworm) | EOL, but works |
| Kernel | `5.3.0-1119-ayufan` (2019) | **held on purpose**; the ayufan repo is dead |
| U-Boot | `2017.09-rockchip-ayufan` | frozen |

The upgrade stops here by the owner's choice. No kernel swap, no Debian 13 /
OMV 8. apt uses `deb.debian.org` bookworm(-updates), `security.debian.org`
bookworm-security and OMV `sandworm`. The ayufan list is
`ayufan-rock64.list.disabled`. Never `apt` with `--allow-change-held-packages`.

## Services

| Port | Service | Notes |
|------|---------|-------|
| 22 | sshd | key auth |
| 53, 8080 | AdGuard Home | DNS + web UI. The LAN's DHCP hands out 8.8.8.8/1.1.1.1, so **nothing uses it yet** |
| 88 | OMV 7 UI | nginx + php8.2-fpm |
| 21 | ProFTPD (`openmediavault-ftp`) | ⚠️ anonymous login on, no TLS |
| 139, 445 | Samba | one share, `tmp` → `agent:/tmp/`, guest OK, no Samba users |
| 8200, 1900 | MiniDLNA | no OMV plugin; edit `/etc/minidlna.conf` by hand (7 `media_dir`s on `data`, name "OMV"). The LG TV uses it |
| 9091, 51413 | Transmission (Entware, `/opt`) | RPC auth required; the Hermes Slack bot uses it |
| 111, 2049 | NFS | exports still scoped to a dead `192.168.31.0/24` |
| 3702, 5357, 5353 | WSD, avahi | discovery |

The Entware bundle in `/opt` is started from `/etc/rc.local` →
`/opt/entware_init.sh`. Everything in it is disabled (`chmod -x` on the
`S*` scripts, lines commented out) **except `S88transmission`**. Off in OMV:
`nmbd`, performance graphs (`collectd`/`rrdcached`) and SMART monitoring.
No Docker, no Jellyfin.

### Security

No firewall (`iptables` INPUT is empty, policy ACCEPT), EOL OMV, a 2019
kernel, anonymous FTP and an unaudited root Transmission. **Keep it LAN-only.
Never port-forward anything to it.**

## Gotchas

- **Network files that must stay.** OMV 7's netplan matches the NIC by
  *permanent* MAC, which this NIC lacks, so an OMV-only config boots with no
  network. The fallback is `/etc/systemd/network/05-chainedbox-end0.network`
  (`Name=end0 eth0`, `DHCP=ipv4`, `ClientIdentifier=mac`). OMV redeploys don't
  delete it. Keep `dhcpcd` and `NetworkManager` disabled: one DHCP client only.
- **AdGuard and port 53.** `/etc/systemd/resolved.conf.d/adguard.conf`
  (`DNSStubListener=no`) frees port 53. `/etc/resolv.conf` →
  `/run/systemd/resolve/resolv.conf`, and `/etc/default/openmediavault` sets
  `OMV_SYSTEMD_NETWORKD_RESOLVCONF_TARGET` to the same path, otherwise OMV puts
  the stub symlink back.
- `/etc/default/openmediavault` also sets `OMV_APT_USE_OS_SECURITY="no"` and
  `OMV_APT_USE_KERNEL_BACKPORTS="no"`. Keep both.
- Don't purge `board-package-rock64` (`rc` state). Its conffiles hold network
  config.
- No RTC. If the clock is far off after boot, force a sync (chrony; untested
  on this box): `systemctl stop chrony; chronyd -q; systemctl start chrony`.
- Before removing an OMV plugin, `apt-mark manual` its daemon, or autoremove
  takes it too (this happened to `minidlna`).
- No tmux on the box. Run long jobs with `systemd-run` so they survive an SSH
  drop. Inside `ssh '…'`, `pkill -f <path>` can kill the remote shell; use
  `pkill -x`.

## Recovery (rescue USB stick)

`/boot.scr` on p7 is [`usb-shim.cmd`](usb-shim.cmd), built with
`mkimage -C none -A arm -T script`. U-Boot runs it before extlinux. It
chain-loads an Armbian stick if one is plugged in, otherwise the eMMC boots
as normal.

1. The stick holds Armbian 26.11 trixie, kernel 6.18 (ophub, Chainedbox build),
   patched with `usbstoragequirks=…,0x05e3:0x0735:iu,0x0bc2:0x2100:iu` so both
   data disks stay hidden.
2. `poweroff`, unplug `agent`, put the stick in the OTG port, power on.
3. The stick system gets **a different MAC and a new DHCP address**. Find it
   by SSH banner (`OpenSSH_10.0`), not by MAC. If it isn't up in ~5 min, pull
   the stick and power-cycle.
4. On the stick system **the stick is `sda`. Never write to `sd*`.** The eMMC
   is `mmcblk0`. You can read its journal or restore an image:
   `gunzip -c <img>.gz | ssh root@<stick-ip> 'dd of=/dev/mmcblk0 bs=4M conv=fsync'`,
   then check it with a sha256 read back with `iflag=direct`.

The only full eMMC image (`~/omv-chainedbox-upgrade/phase1/` on the Mac) is
from **before** the upgrade (Debian 9 / OMV 4). Restoring it means redoing the
upgrade. Upgrade logs and config backups live in `/root/upgrade-logs/`.

## History

- 2019: reflashed with ayufan's Rock64 Debian + OMV 4 + the wdmomo Entware
  bundle.
- 2026-08-22: removed `ttyd` (an unauthenticated web terminal) and qBittorrent
  (default `admin` password, ran as root).
- 2026-10-10/11: upgraded in place, Debian 9→12 and OMV 4→7, one release at a
  time. A failed first attempt was rolled back by restoring the eMMC from the
  stick. The Entware services (except Transmission), netatalk/AFP, MySQL, aria2
  and FileBrowser were disabled or removed. The NIC became `end0` and moved to
  DHCP. A reflash to a modern Armbian was considered and rejected: no SD slot,
  and the `data` disk is inside the case.
