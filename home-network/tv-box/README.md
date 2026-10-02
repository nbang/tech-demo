# TX3 mini-A → Armbian home server

Runbook for turning an old Tanix TX3 mini-A Android TV box into a headless
Debian server by booting Armbian from an SD card. Android stays on the eMMC
untouched until we deliberately decide otherwise.

## The box

Probed over `adb`, not assumed:

| | |
|---|---|
| LAN address | `192.168.2.205` (Android, DHCP) — MAC `e0:76:d0:61:80:6a` |
| SoC | **Amlogic S905W** — `ro.board.platform=gxl`, DT id `gxl_p281_2g`, chip RevD |
| CPU / GPU | 4× Cortex-A53, Mali-450 |
| RAM / eMMC | 2 GB / 16 GB (`mmcblk0`, 15.4 GB) |
| Wi-Fi / BT | **AMPAK AP6330 = Broadcom BCM4330** (SDIO `02d0:4330`) — mainline `brcmfmac` |
| Ethernet | 100 Mbit (internal PHY) |
| Android | 9, 32-bit userland, reseller ROM `TX3 MINI Boxtruyenhinh 20200808`, kernel 4.9.113 |
| Root | none — no `su`; `adb root` refused ("production build") despite `buildvariant=userdebug` |

"TX3 mini" is sold with at least five different SoCs under one name (S905W,
S905W2, H313, S905L2-B, RK3228A). Only the original S905W runs Armbian well —
S905W2 boxes are CoreELEC-only. **Check `ro.board.platform` before following
this guide on another unit.**

## Finding it on the network — the red herring

The first sweep found a host with a Wi-Fi-module MAC (`14:0a:02`, Shenzhen
Bilian) and nothing open, which looked exactly like the box. It wasn't. The real
box only appeared after it was plugged in, with an AMPAK MAC. A MAC vendor
tells you "some cheap embedded device", not which one — confirm with ADB.

Sweep without nmap:

```bash
for i in $(seq 1 254); do ping -c1 -W300 192.168.2.$i >/dev/null 2>&1 & done; wait
arp -a | grep -v incomplete
for ip in $(arp -a | grep -oE '192\.168\.2\.[0-9]+'); do nc -z -G1 $ip 5555 && echo "ADB: $ip"; done
```

## ADB on this ROM

There is **no "network debugging" toggle**. Turning on *USB debugging*
(Settings → About → tap Build 7× → Developer options) also opens TCP 5555:

```bash
brew install --cask android-platform-tools
adb connect 192.168.2.205:5555     # accept the prompt on the TV
adb shell getprop ro.board.platform
```

## Why Armbian, and which build

| Option | On S905W | Verdict |
|---|---|---|
| **Armbian** (ophub) | stable, SD boot, mainline kernel | ✅ chosen — general Linux server |
| LibreELEC 12 AMLGX | maintained, mainline | Kodi-only appliance |
| CoreELEC 21 Omega | best video, but **22 dropped GXL** | dead end |

Image (ophub release `Armbian_trixie_arm64_server_2026.09`):

```
Armbian_26.11.0_amlogic_s905w_trixie_6.12.109_server_2026.09.14.img.gz
sha256 4955e1f456d725f7dcd7cfd36a961c32fd232b8a163bcb39041330657d8870ea
```

- **Debian 13 trixie** (current stable) over Ubuntu `noble`/`resolute`
- **6.12 LTS** kernel over 6.18 — boring is the point for a server
- Generic `s905w` image, not `s905w-x96-mini`

Download and verify:

```bash
curl -LO https://github.com/ophub/amlogic-s9xxx-armbian/releases/download/Armbian_trixie_arm64_server_2026.09/Armbian_26.11.0_amlogic_s905w_trixie_6.12.109_server_2026.09.14.img.gz
echo "4955e1f456d725f7dcd7cfd36a961c32fd232b8a163bcb39041330657d8870ea  Armbian_26.11.0_amlogic_s905w_trixie_6.12.109_server_2026.09.14.img.gz" | shasum -a 256 -c
```

### DTB

ophub's `model_database.conf` maps the S905W image to entry **111 TX3-Mini →
`meson-gxl-s905w-tx3-mini.dtb`** (stable). It inherits the p212 reference
layout, which already declares the SDIO `brcmfmac` node, so the BCM4330 should
probe. Fallback if Wi-Fi or Ethernet misbehave: `meson-gxl-s905w-p281.dtb`
(entry 112, same `gxl_p281_2g` board as this unit). Switch by editing the
`FDT=` line in `uEnv.txt` on the SD card's BOOT partition.

## Flashing (macOS)

The card shows up as an external removable disk — on this Mac, `disk4`
(31.6 GB, NTFS). **Always re-check with `diskutil list external` first.**

```bash
./flash-sd.sh Armbian_26.11.0_amlogic_s905w_trixie_6.12.109_server_2026.09.14.img.gz disk4
```

[flash-sd.sh](flash-sd.sh) refuses non-external, non-removable or >128 GB disks,
makes you retype the disk id, writes to `/dev/rdiskN` (several times faster
than `/dev/diskN`), then **reads the first 16 MiB back** and fails if they do
not match. Balena Etcher / Raspberry Pi Imager "Use custom" work too (both
verify by default).

**Trap — cards that eat writes.** The first card (31.6 GB, exFAT) took a full
3.69 GB `dd` at 18 MB/s with no error, yet both the box and the Mac still saw
the old single exFAT partition afterwards. Worn-out cards lock themselves
read-only and counterfeit ones drop writes, and the controller still ACKs, so
`dd` cannot tell. Symptom on the box: `dmesg` shows `mmcblk1: p1` instead of
`p1 p2`. Check the adapter's lock switch, then replace the card.

The second card ("33.6 GB" — above the nominal 32 GB, a counterfeit hint)
wrote at 3.9 MB/s and came back **partially** written: the partition table and
BOOT/ROOTFS appeared, but 178 of 238 BOOT files read back as all zeros and
`zImage`, `uInitrd` and `vmlinuz` were missing altogether. Two cards failing
through the same USB microSD dongle makes the dongle a suspect too — try a
different reader before blaming a third card. A pretty partition table in
`diskutil list` proves nothing; compare file contents against the image.

`flash-sd.sh`'s own verify never ran on this card: macOS auto-mounted the new
BOOT volume straight after `dd` and Spotlight (`mds_stores`) blocked the
unmount, so `set -e` stopped the script first.

**Trap — macOS makes whole-disk verification lie.** Mounting the FAT BOOT
partition writes `.fseventsd`/`.Spotlight-V100` into it, so a checksum of the
whole device never matches the image. A good Kingston DataTraveler G3 (8 GB,
11 MB/s) "failed" that way while all 238 BOOT files were byte-identical. The
script now compares BOOT file by file and hashes only the regions outside it
(MBR, u-boot area, ext4 ROOTFS — which macOS cannot mount). The two SD cards
above were genuinely bad: their damage was all-zero files, not Mac metadata.

A USB stick is a fine substitute for the SD card: ophub images boot from USB
as well as SD, and `adb reboot update` triggers the same autoscripts for both.

## Booting from SD

Amlogic's stock u-boot only looks at the SD card after an "update" boot. Either:

- **From the Mac** (no toothpick): with the card inserted and Android running,
  `adb reboot update`
- **By hand**: power off, hold the reset button inside the AV jack with a
  toothpick, power on, release after ~5 s

That one-time trigger sets the u-boot env; later reboots boot the SD card
automatically while it is inserted. Pull the card and Android comes back.

First boot takes 1–3 min (filesystem resize). Find the new address (Armbian gets
a new DHCP lease, often a different MAC than Android's `e0:76:d0:…`), then:

```bash
ssh root@<ip>        # password 1234 — forced change on first login
```

## Post-install checklist

1. Non-root sudo user; SSH key auth; `PasswordAuthentication no`
2. Static IP or DHCP reservation on the router
3. `timedatectl set-timezone Asia/Ho_Chi_Minh`
4. `apt update && apt full-upgrade`; `unattended-upgrades` for security updates
5. Check hardware: `ip link` (eth0, wlan0), `dmesg | grep -iE 'brcm|mmc|eth'`,
   `armbian-monitor -m` for temperature — S905W in a sealed plastic box runs
   hot under sustained load
6. Wi-Fi only if needed: `nmtui` (wired is more reliable for a server)
7. Log2ram/zram are on by default in Armbian — keep them, SD cards wear out

### If Wi-Fi does not come up

`brcmfmac` needs `/lib/firmware/brcm/brcmfmac4330-sdio.bin` plus an NVRAM
`.txt`. armbian-firmware ships the `.bin`; the board-specific NVRAM is often
missing. The AP6330 NVRAM pulled from Android is in
[wifi-ap6330/brcmfmac4330-sdio.txt](wifi-ap6330/brcmfmac4330-sdio.txt):

```bash
scp wifi-ap6330/brcmfmac4330-sdio.txt root@<ip>:/lib/firmware/brcm/
ssh root@<ip> 'rmmod brcmfmac && modprobe brcmfmac && dmesg | tail'
```

(The Android firmware blob `fw_bcm40183b2.bin` is kept locally but not
committed — it is proprietary and armbian-firmware carries an equivalent.)

## Before ever installing to eMMC

`armbian-install` would overwrite Android permanently, and the reseller ROM is
not downloadable anywhere. Android has no root, so the backup has to happen
**from Armbian booted off SD**. Identify the eMMC (it is the device that has
`boot0`/`boot1` partitions — numbering differs from Android's), then stream it
to the Mac:

```bash
ssh root@<ip> lsblk
ssh root@<ip> 'dd if=/dev/mmcblkX bs=4M status=none | gzip -1' > tx3mini-emmc-android9.img.gz
```

Running from SD is fine for a light server; eMMC is faster and does not wear
like an SD card, so it is worth doing once the setup has proved stable.

## Restoring Android later

The installed ROM (`TX3 MINI Boxtruyenhinh 20200808`) is a Vietnamese reseller
re-skin and **is not published anywhere** — boxtruyenhinh.com/.vn do not
respond. The only way to get *that* ROM back is a dump of `mmcblk2` (below).
Otherwise, in order of preference (researched 2026-09-24):

| # | Image | Android | Source | Notes |
|---|---|---|---|---|
| 1 | Factory `p281-userdebug 9 PPR1.180610.011 20191008` | 9 | [androidpctv post](https://androidpctv.com/firmware-android-9-tanix-tx3-mini/) → [Mega](https://mega.nz/file/EqRBGCaI#GfD4jOPiuCQpIrwUFJhl6X3Vai2mabN7fBzdcZnvnP8) | **Closest to what is on the box** — same Oct 2019 kernel base the reseller ROM was built on. One image for 1G/2G. Mega file not verified to still exist |
| 2 | Tanix official `TX3Mini-905w8.1-20221123.img` | 8.1 | [Tanix firmware centre](https://www.tanixtvbox.com/firmware-centre/) → [Google Drive](https://drive.google.com/file/d/1sxcA-HAjXOF5-EyaQEqxpZLGZw043DOU/view) | First-party and most trustworthy, but a downgrade to 8.1; AP6330 support not stated (probably fine — Tanix's latest image) |
| 3 | Same 20191008 Android 9 build, mirror | 9 | [chinagadgetsreviews](https://chinagadgetsreviews.com/download-android-9-stock-firmware-for-tanix-tx3-mini-tv-box.html) | Ad-heavy file hosts (DailyUploads/FileFactory) — check the build string after download |
| 4 | Custom Android TV 9 (aidan's ATV / SlimBOX) | 9 ATV | [i12bretro tutorial](https://i12bretro.github.io/tutorials/0393.html), [XDA SlimBOX](https://xdaforums.com/t/project-slimboxtv.4152049/), [4pda Tanix thread](https://4pda.to/forum/index.php?showtopic=910528) | Real Android TV launcher instead of a phone UI; community ROMs, not a stock restore. XDA/4pda not fetch-verified |

**Archived copies (2026-09-24) in `gdrive:backups/tx3-mini/android-firmware/`**
— Mega and Drive links rot:

| File | Source | Check |
|---|---|---|
| `TX3Mini-905w8.1-20221123.img` (1,431,788,200 B) | #2 Tanix official, server-side `rclone backend copyid` | Amlogic image v2 magic `0x27B51956`; header size field = file size |
| `Tanix-TX3mini-S905W-Android9-p281-userdebug-20191008-factory.rar` (692,806,452 B) | #1 androidpctv → Mega, streamed with `megatools dl --path - … \| rclone rcat` | RAR5; contains `TX3Mini-20191008-Custom-2.img` (1,418,737,144 B, Dec 2019) + readme/links. "Custom-2" is androidpctv's name — may be lightly modified from pure stock |

Preference for restoring stock Android: the **20191008 Android 9** (same base
as the reseller ROM) over the Tanix 8.1. The exact reseller ROM exists only as
the eMMC dump next to these files. `tanix-box.com` (the old official domain in many guides) is dead.

Variant guide: the Vietnamese [tinhte.vn thread](https://tinhte.vn/thread/tong-hop-cac-ban-firmware-cua-android-tv-box-tx3-mini.3022766/)
classifies TX3 mini batches. This unit is **"Phase 3" (Jul–Dec 2019, TX3
mini-A, dual-band AP6330)**, and it warns that cross-phase firmware can brick.
Its download links (fshare) are dead, but the variant table is the reference.
**Do not** use images for the S9012P or SSV6051 Wi-Fi batches, or for the TX3
Mini+ (S905W2), Mini-L or Mini-H.

### Flashing an Android .img

All sources above ship **Amlogic USB Burning Tool `.img`** files, not recovery
`update.zip`s:

1. Windows PC, USB Burning Tool v2.1.6 or v2.2.0; rename the image to
   `update.img` (non-ASCII filenames break the tool)
2. USB **A-to-A** cable into the box's USB port next to the TF slot
3. Hold the reset button in the AV jack, apply power, release when the tool
   detects the device, then Start
4. Leave **"Erase bootloader"** unticked — a full erase can wipe the MAC /
   keys on some boxes

No cable: Amlogic **Burn_Card_Maker** writes the `.img` to a microSD for an
SD-card update boot instead.

Or skip all of that and just **pull the Armbian USB stick**: as long as
nothing was installed to eMMC, the box boots the original Android as before.

### Dumping the current ROM (do this first)

**Backup location: Google Drive, `gdrive:backups/tx3-mini/`** (rclone remote
`gdrive:` on the Mac). Not kept on the Mac — the stream passes through it
with `rclone rcat` and is never written to its disk.

| File | What |
|---|---|
| `tx3mini-emmc-android9-boxtruyenhinh-20200808.img.zst` (2,386,340,290 B) | whole eMMC (`mmcblk2`, 15,758,000,128 bytes), zstd -3. **Restore-tested 2026-09-24**: streamed back from Drive → decompresses to raw sha256 `c26d8c967a311382822dd0290cd12213f69de19a33e4a75b2a4b09c5974ccb34` |
| `…-boot0.bin`, `…-boot1.bin` | eMMC hardware boot partitions (4 MiB each) |
| `…-info.txt` | SHA-256 of the raw eMMC + `fdisk -l` |

**Trap — a streamed backup can be silently truncated.** The first attempt piped
`ssh … dd | zstd` straight into `rclone rcat`; the SSH stream reset after a
minute, rclone saved the 622 MB it had, and the `&&` chain carried on because
a pipeline's exit status is rclone's. Streaming it back showed 3.1 of 15.8 GB.
What worked: compress to a file on the box under `nohup` (8 min, no network),
`zstd -dc | sha256sum` it there, upload with rclone's SFTP backend (retries,
resumable chunks — 7 min), then restore-test from Drive. Never call a backup
done from a file listing.

The first-attempt commands, kept for reference (don't use as-is — see trap):

```bash
N=tx3mini-emmc-android9-boxtruyenhinh-20200808; D=gdrive:backups/tx3-mini
ssh root@192.168.2.20 'bash -c "dd if=/dev/mmcblk2 bs=4M status=none | tee >(sha256sum > /root/emmc.sha256) | zstd -T4 -3 -q -c"' \
  | rclone rcat "$D/$N.img.zst"
for p in boot0 boot1; do ssh root@192.168.2.20 "dd if=/dev/mmcblk2$p bs=1M status=none" | rclone rcat "$D/$N-$p.bin"; done
ssh root@192.168.2.20 'cat /root/emmc.sha256; fdisk -l /dev/mmcblk2' | rclone rcat "$D/$N-info.txt"
```

Restore (from Armbian on USB, before or instead of the eMMC install):

```bash
rclone cat "$D/$N.img.zst" | ssh root@192.168.2.20 'zstd -d -c | dd of=/dev/mmcblk2 bs=4M conv=fsync'
```

Then check `sha256sum /dev/mmcblk2` against `…-info.txt`. The Mac's
`gdrive:` token expires if unused for a while — `rclone config reconnect
gdrive:` renews it (browser sign-in).

## Status

Done:
- Box identified and probed (S905W, 2 GB, AP6330)
- Armbian trixie 6.12.109 image selected; AP6330 NVRAM backed up from Android

- Image downloaded and verified (sha256 + `gzip -t`)
- First SD card flashed — **silently discarded the write**; needs replacing
- Second SD card flashed — **partially written, kernel files missing**; card or dongle bad

- 8 GB Kingston USB stick flashed; BOOT verified file-by-file (238/238)
- **Booted from USB** via `adb reboot update` — SSH up ~70 s later on
  `192.168.2.20` (same MAC as Android's eth0, `06:42:00:80:93:c1`, so same lease)
- First login scripted with `expect`: root password set, user creation skipped
  (Ctrl-C), Mac's `id_ed25519` in `/root/.ssh/authorized_keys`
- Timezone `Asia/Shanghai` (image default) → `Asia/Ho_Chi_Minh`

Probed on Armbian:

| | |
|---|---|
| OS / kernel | Armbian 26.11.0 trixie, `6.12.109-ophub`, DT model "Oranth Tanix TX3 Mini" |
| Root | `/dev/sda2` on the USB stick, auto-grown to 7 GB; `/boot` = `sda1` |
| eMMC | **`mmcblk2`** (14.7 GB, has `boot0`/`boot1`) — Android, untouched |
| Ethernet | `eth0` up, 100 Mb/s |
| Wi-Fi | `brcmfmac` loaded AP6330 firmware from armbian-firmware, `wlan0` present (down). The `p2p-dev-wlan0 … err=-5` line is harmless — no NVRAM fix needed |
| RAM / temp | 1.8 GB, ~250 MB used idle; 54 °C |
| systemd | no failed units |

**Trap — host key changes after first boot.** Armbian's first-run service
regenerates SSH host keys, so a connection made in the first minute records a
key that is gone a minute later and SSH screams MITM. Same MAC + same banner →
`ssh-keygen -R 192.168.2.20` and reconnect.

- **Installed to eMMC 2026-09-24** (after the restore-tested Drive backup):
  `printf "111\n1\n" | armbian-install -m no` under `nohup` — board 111
  TX3-Mini, ext4, vendor bootloader kept (`mybox-bootloader.img`, the eMMC's
  own first 4 MiB, written back after `ampart` repartitioning). Copies the
  *running* system (`etc home opt root srv usr var`), so Hermes and its secrets
  carried over. Now boots with no USB: root `mmcblk2p2` (14.1 GB ext4, label
  `ROOTFS_EMMC`), `/boot` `mmcblk2p1`; Hermes gateway auto-starts via linger
  and reconnects to Slack ~1 min after power-on. Android is gone from the box
  — restore from `gdrive:backups/tx3-mini/`. The USB stick is no longer needed
  (it held the older USB system as a rescue boot until 2026-10-02, when it was
  overwritten with the MX Linux installer for the mini PC — re-flash from
  ophub if a rescue boot is ever needed).
- No RTC: the clock boots at the last saved time and NTP corrects it, so
  systemd "active since" times right after boot can look an hour off.
- **Boot race, self-healing:** the gateway is a systemd *user* unit, so it can
  start before the network is up. First boot in the new location logged
  `slack error: slack connect timed out after 30s` → "queued for retry" →
  connected 40 s later on its own. Not an outage; if it ever needs fixing, add
  an `ExecStartPre` that waits for `getent hosts slack.com`.
- Moved into the Orange Pi's place 2026-09-24; Orange Pi powered off (SD card
  kept as rollback).

Still needed:
- DHCP reservation for `192.168.2.20` ↔ `06:42:00:80:93:c1` on the router
- `apt full-upgrade`, unattended-upgrades, non-root user,
  `PasswordAuthentication no` (root password is weak)
- eMMC backup (`mmcblk2`) before any `armbian-install`
- `adb reboot update`, first login, post-install checklist
- eMMC backup before any `armbian-install`
