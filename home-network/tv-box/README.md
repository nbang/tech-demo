# TX3 mini — Armbian home server

Tanix TX3 mini-A TV box running Armbian from its eMMC. Always on. It runs the
Hermes Slack team bot and the air purifier poller. It took over from the Orange
Pi on 2026-09-24, when the bot also moved from picoclaw to Hermes.

## The box

| | |
|---|---|
| Address | `192.168.2.9`, DHCP reservation on the mesh main for MAC `06:42:00:80:93:c1` (was `.20`) |
| Access | `ssh root@192.168.2.9` (key auth) |
| SoC | **Amlogic S905W** (GXL, board `gxl_p281_2g`), 4× Cortex-A53, Mali-450 |
| RAM / eMMC | 2 GB / 16 GB (`mmcblk2`, with `boot0`/`boot1`) |
| Ethernet | 100 Mbit, internal PHY (`eth0`) |
| Wi-Fi | AMPAK AP6330 = Broadcom BCM4330, `brcmfmac`. `wlan0` exists but is unused |
| OS | Armbian 26.11.0 trixie (ophub), kernel `6.12.109-ophub`, DTB `meson-gxl-s905w-tx3-mini.dtb` (ophub board 111) |
| Disks | root `mmcblk2p2` (ext4, label `ROOTFS_EMMC`), `/boot` `mmcblk2p1`. Vendor bootloader kept. TZ `Asia/Ho_Chi_Minh` |

"TX3 mini" is sold with several different SoCs (S905W, S905W2, H313, S905L2-B,
RK3228A). Only the S905W runs Armbian well, so check `ro.board.platform` before
reusing these notes on another unit.

Gotchas:
- **No RTC.** The clock starts at the last saved time and NTP fixes it, so
  "active since" times right after boot can be an hour off.
- **Host key changes after a fresh install** (first-run service regenerates
  it): `ssh-keygen -R 192.168.2.9`.
- **Wi-Fi NVRAM:** if `brcmfmac` ever lacks it, copy
  [wifi-ap6330/brcmfmac4330-sdio.txt](wifi-ap6330/brcmfmac4330-sdio.txt) (pulled
  from Android) to `/lib/firmware/brcm/` and reload the module. Not needed on
  the current image; `p2p-dev-wlan0 … err=-5` is harmless.

## Services

### Hermes Slack team bot

| | |
|---|---|
| Install | Hermes v0.21.x, user `hermes` (no sudo), config in `~hermes/.hermes/` |
| Service | systemd **user** unit `hermes-gateway`, with linger. Reconnects to Slack ~1 min after power-on (an early `slack connect timed out` retries on its own). Logs as root (untested): `journalctl --user-unit hermes-gateway -f` |
| Model | `openrouter/free`, fallback NVIDIA NIM `z-ai/glm-5.3-flash` |
| Secrets | `~hermes/.hermes/.env` (mode 600). Never copied to the Mac |
| Transmission MCP | `~hermes/.hermes/mcp/transmission_mcp.py` + `transmission.env` (600). RPC host must be the Chainedbox at **`192.168.2.10`** |
| Digest | cron `ban-tin-sang`, `30 8 * * *` local time, delivered to `#daily` |

Files in [hermes/](hermes/):

| Path | What |
|---|---|
| [patch_config.py](hermes/patch_config.py) | Sets model, toolsets, MCP, slash-command tiers in `config.yaml`. Idempotent, backs up first. **Re-run after any `hermes config migrate` or update** (migrate re-adds toolsets on its own) |
| [SOUL.md](hermes/SOUL.md) | Bot identity and Slack formatting rules |
| [skills/ban-tin-sang](hermes/skills/ban-tin-sang/SKILL.md) | Daily Vietnamese morning digest |
| [plugins/dm-only-tools](hermes/plugins/dm-only-tools/__init__.py) | Blocks `mcp__transmission__*` outside the owner's Slack DM; fails closed |
| [plugins/camera-snapshots](hermes/plugins/camera-snapshots/__init__.py) | Yi camera RTSP snapshots, owner's DM only |
| [plugins/server-status](hermes/plugins/server-status/__init__.py) | `/server`: uptime, load, temperature, memory, disk, gateway |
| [from-picoclaw/](hermes/from-picoclaw/) | The old picoclaw prompts, kept for reference only |

Notes:
- The Slack bot is open to the whole workspace, so it has no terminal, code,
  file, browser or cron tools. Without `allow_admin_from`, every allowed user
  is an admin; `patch_config.py` sets it to the owner only.
- MCP tool names are `mcp__<server>__<tool>` (double underscore). A guard that
  matches a different prefix guards nothing.

### Air purifier poller

systemd *system* unit `purifier-poller` (user `purifier`). Code and venv in
`/opt/purifier-poller`, config and secrets in `/etc/purifier-poller.env`
(`root:purifier 0640`). Reads the Xiaomi purifier at `.139` every 30 s and
POSTs to the [purifier-dashboard](../../purifier-dashboard/README.md) Worker.
Logs: `journalctl -u purifier-poller -f`.

## Android eMMC backup

Android is gone from the box; the original reseller ROM (`TX3 MINI
Boxtruyenhinh 20200808`, Android 9) exists only as this dump. Everything is in
**`gdrive:backups/tx3-mini/`** (rclone remote on the Mac):

| File | What |
|---|---|
| `tx3mini-emmc-android9-boxtruyenhinh-20200808.img.zst` | Whole `mmcblk2` (15,758,000,128 B), zstd. Restore-tested 2026-09-24 |
| `…-boot0.bin`, `…-boot1.bin` | eMMC hardware boot partitions |
| `…-info.txt` | SHA-256 of the raw eMMC + `fdisk -l` |
| `android-firmware/` | Stock images: Tanix official `TX3Mini-905w8.1-20221123.img` (8.1) and the factory Android 9 `p281-userdebug 20191008` build (closest to the reseller ROM) |

Restore the dump (this wipes Armbian; boot Armbian from USB/SD first, since you
can't overwrite the disk you're running from):

```bash
N=tx3mini-emmc-android9-boxtruyenhinh-20200808; D=gdrive:backups/tx3-mini
rclone cat "$D/$N.img.zst" | ssh root@<ip> 'zstd -d -c | dd of=/dev/mmcblk2 bs=4M conv=fsync'
```

Then compare `sha256sum /dev/mmcblk2` with `…-info.txt`. The stock `.img` files
need the Amlogic USB Burning Tool (Windows, A-to-A cable, reset button held; leave
"Erase bootloader" unticked). Use only Phase 3 / S905W images.

**Don't stream `ssh … dd | rclone rcat` for a new backup:** an SSH reset once
truncated it silently. Compress to a file on the box, check it, upload, then
restore-test from Drive. Expired `gdrive:` token: `rclone config reconnect gdrive:`.

## Reinstalling Armbian

1. Image: ophub `amlogic-s9xxx-armbian`, the generic `s905w` trixie server build
   (last used `Armbian_26.11.0_amlogic_s905w_trixie_6.12.109_server_2026.09.14.img.gz`).
2. Flash a USB stick or SD card with [flash-sd.sh](flash-sd.sh) `<image> diskN`. It
   refuses non-removable disks, writes `/dev/rdiskN`, and verifies BOOT file by
   file (macOS writes Spotlight files into FAT, so whole-disk hashes never match).
   Cheap SD cards here silently dropped writes; a USB stick worked.
3. Boot it: hold the reset button in the AV jack while powering on (~5 s). Later
   boots use USB/SD automatically while it's inserted. First login `root` / the
   ophub default, forced change.
4. Install to eMMC: `printf "111\n1\n" | armbian-install -m no` (board 111, ext4,
   keep the vendor bootloader).

## Open items

- [ ] Point the Transmission MCP at the Chainedbox's new address: set the RPC
      host in `~hermes/.hermes/mcp/transmission.env` to `192.168.2.10`, then
      restart `hermes-gateway`.
- [ ] Confirm SSH hardening: `PasswordAuthentication no` and a strong root
      password (the old notes said the root password was weak).
