# Home network

Home LAN `192.168.2.0/24`, gateway `192.168.2.1`. One folder per device; each
README is the source of truth for that box.

## Devices

| Box | IP | MAC | What | Status | Docs |
|-----|----|-----|------|--------|------|
| Viettel ONT | `192.168.1.1` | — | DASAN H646W fiber modem, PPPoE behind CGNAT | always-on | [router/](router/README.md) |
| Mesh main | `.1` | `24:0b:2a:d6:ce:5c` | Viettel vAP-32X6V1: gateway, DHCP, DNS | always-on | [router/](router/README.md) |
| Mesh node 2 / 3 | `.2` / `.3` | `24:0b:2a:d5:c7:38` / `…d7:08:6c` | vAP-32X6V1 satellites, wired backhaul | always-on | [router/](router/README.md) |
| **TX3 mini** | `.9` | `06:42:00:80:93:c1` | S905W, 2 GB, Armbian: Hermes Slack bot, purifier poller | always-on | [tv-box/](tv-box/README.md) |
| **Chainedbox** ("the OMV") | `.10` | `66:c9:1c:46:67:db` | RK3328, 1 GB, Debian 12 + OMV 7: NAS, downloads, DLNA, AdGuard | always-on | [omv-chainedbox/](omv-chainedbox/README.md) |
| **Mini PC** `mx` | `.11` | `6c:4b:90:1a:68:bb` | Xeon E-2176M, 16 GB, MX Linux 25.3 | on-demand | [mini-pc/](mini-pc/README.md) |
| LG TV 55UM7300PTA | `.216` | `74:40:be:e3:c9:86` | webOS 4.5, Developer Mode | when on | [lg-tv/](lg-tv/README.md) |
| Yi Home cam #1 / #2 | `.153` / `.222` | `b0:d5:9d:29:93:25` / `…4d:6e:59` | Hi3518 V100 + SD hack, RTSP :554 | always-on | [yi-camera/](yi-camera/README.md) |
| Mi Air Purifier 2 mini | `.139` | `78:11:dc:4c:30:7a` | `zhimi.airpurifier.m1`, miIO UDP 54321 | always-on | [air-purifier/](air-purifier/README.md) |
| D905 retro box | — | — | S905L, EmuELEC SD / Android NAND | broken | [tv-box/D905.md](tv-box/D905.md) |
| Orange Pi PC | — | — | H3, ARMv7, SD wiped | spare | [orangepi/](orangepi/README.md) |

**Addressing:** everything is DHCP. `.1`–`.3` is the router and mesh, and
`.9`–`.16` is reserved for wired boxes (next free: `.12`). The rest is
dynamic. To find a box that moved:

```bash
for i in $(seq 1 254); do ping -c1 -W300 192.168.2.$i >/dev/null 2>&1 & done; wait
arp -an | grep -i <mac>
```

## Access

| Box | How |
|-----|-----|
| TX3 | `ssh root@192.168.2.9` (key) |
| Chainedbox | `ssh root@192.168.2.10` (key) · OMV `http://192.168.2.10:88` · AdGuard `:8080` |
| Mini PC | `ssh bang@192.168.2.11` (key; sudo needs a password) |
| Yi cams | `rtsp://192.168.2.{153,222}:554/ch0_0.h264` (TCP) |
| Air purifier | python-miio API + token from the Xiaomi cloud |
| LG TV | Dev Mode SSH `prisoner@192.168.2.216 -p 9922` (key `~/.ssh/lgtv_webos`) or `ares-* -d lgtv` |

## Open issues

- **Chainedbox `sda` is failing.** Copy `/srv/dev-disk-by-label-agent` off and
  replace the drive.
- **Hermes bot:** point its Transmission RPC host at `192.168.2.10`.
- **Air purifier filter is used up** (0 %). Replace it with a 2 mini filter.
- **Yi cam `.153` is offline** (no DHCP lease since at least 2026-10-11).
- Yi cams expose anonymous FTP and telnet. Isolate them on a guest/IoT Wi-Fi.
- Chainedbox: anonymous FTP on, no firewall, OMV 7 on a held 2019 kernel.
- Nothing uses AdGuard: the router hands out `8.8.8.8`/`1.1.1.1` as DNS.
- Reserve addresses for the LG TV, Yi cams and air purifier.
- LG TV Developer Mode session expires (~1000 h). Extend it, or sideloaded
  apps get wiped.
- TX3: `apt full-upgrade`, add a non-root user, set `PasswordAuthentication no`.

## Shared gear

- **Kingston DataTraveler G3 8 GB USB stick**: the Chainedbox rescue stick
  (patched Armbian trixie 6.18; hides both data disks).
- Android eMMC/SD backups of the TV boxes: `gdrive:backups/{tx3-mini,d905}`.
