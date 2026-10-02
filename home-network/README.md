# Home network

Runbooks and surveys for the boxes on the home LAN (`192.168.2.0/24`, gateway
`192.168.2.1`). One folder per device; each README is the source of truth for
that box.

## Devices

| Box | IP | Hardware | OS | Role | Status | Docs |
|-----|----|----------|----|------|--------|------|
| **TX3 mini** | `192.168.2.20` | Amlogic S905W, 4× A53, 2 GB | Armbian trixie (eMMC) | Hermes Slack team bot | **always-on** | [tv-box/](tv-box/README.md) |
| **Chainedbox L1 Pro** ("the OMV") | `192.168.2.14` | Rockchip RK3328, 4× A53, 1 GB, 500 G + 2 T HDD | Debian 9 + OMV 4 (EOL) | NAS, downloads, DLNA, AdGuard DNS | **always-on** | [omv-chainedbox/](omv-chainedbox/README.md) |
| **Mini PC** `mx` | `192.168.2.114` | Xeon E-2176M 6C/12T, 16 GB, 256 G SSD | MX Linux 25.3 Xfce | GUI + heavy background jobs | **on-demand** | [mini-pc/](mini-pc/README.md) |
| **Orange Pi PC** | `192.168.2.180` | Allwinner H3, ARMv7 32-bit, 1 GB | Armbian trixie | was the picoclaw Slack bot | **retired** 2026-09-24 (SD kept as rollback) | [orangepi/](orangepi/README.md) |
| **D905** retro box | — | Amlogic S905L | EmuELEC (SD) / Android (eMMC) | retro gaming | broken — SD failing, eMMC boot-loops | backup scripts in [tv-box/](tv-box/) |

The two always-on boxes are the same low-power quad-A53 class; the mini PC is
~10× either of them and is only powered up when needed.

## Access

| Box | Login |
|-----|-------|
| TX3 | `ssh root@192.168.2.20` (key) |
| Chainedbox | `ssh root@192.168.2.14` (key) · OMV UI `http://192.168.2.14:88` (port 80 is the 粒子云 launcher) |
| Mini PC | `ssh bang@192.168.2.114` (key; sudo needs password) |

All addresses are DHCP. **Reserve them on the router** — the mini PC already
moved once (`.28` → `.114`) after its reinstall. Lost a box? Find it by MAC:

```bash
for i in $(seq 1 254); do ping -c1 -W300 192.168.2.$i >/dev/null 2>&1 & done; wait
arp -an | grep -iE '06:42:00:80:93:c1|66:c9:1c:46:67:db|6c:4b:90:1a:68:bb'
```

| MAC | Box |
|-----|-----|
| `06:42:00:80:93:c1` | TX3 |
| `66:c9:1c:46:67:db` | Chainedbox |
| `6c:4b:90:1a:68:bb` | Mini PC |

## Open issues

- **Chainedbox `sda` is failing** (9 reallocated + 3 pending sectors, ~63k h,
  2026-10-02). Copy `/srv/dev-disk-by-label-agent` off and replace the drive.
- Chainedbox security to-dos still open: aria2 RPC has no token, FileBrowser
  default creds, no firewall, whole stack EOL.
- DHCP reservations for all three live boxes.
- TX3: `apt full-upgrade`, non-root user, `PasswordAuthentication no`.

## Shared gear

- **Kingston DataTraveler G3 8 GB USB stick** — was the TX3's Armbian rescue
  boot; since 2026-10-02 it is the **MX Linux 25.3 installer**.
- Backups of the TV boxes' Android eMMC/SD live in `gdrive:backups/`
  (`tx3-mini`, `d905`).
