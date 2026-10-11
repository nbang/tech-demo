# Upgrade plan: Chainedbox OMV box (`192.168.2.14`)

**Goal:** Debian 9 + OMV 4 + kernel 5.3 → Debian 13 + OMV 8 + kernel 6.18,
in place, one release at a time, **without touching either data disk.**

## Status (2026-10-10)

🛑 **Upgrade stopped at Debian 12.15 + OMV 7.7.24, kernel 5.3 (user's
decision, 2026-10-11).** Steps 3b (kernel) and 4 (Debian 13 + OMV 8) are not
planned. OMV 7 is EOL; Debian 12 security comes via LTS until mid-2028;
kernel 5.3 is held and unpatched (LAN-only box). To resume later, 3b must
come before 4 (trixie's systemd wants kernel ≥ 5.4). Box address: DHCP
(`.161` as of 2026-10-11). Leftovers are under "Open" at the end of Step 3.

✅ **Recovery R1 done (2026-10-10 ~20:00).** The eMMC was restored from this
morning's image and verified by sha256; the box is back on Debian 9.13 + OMV
4.1.36 with a clean `dpkg --audit`. The USB stick boot path is proven. Next:
redo the pre-step-1 cleanup, reinstall the shim, then redo Step 1 under the
rules below. (The "What's wrong" section below is the history of the failed
attempt.)

## Done

- **Phase 0, inventory:** `~/omv-chainedbox-upgrade/phase0/inventory.txt` (Mac).
- **Phase 1, backups:** `~/omv-chainedbox-upgrade/phase1/` (mode 700, holds
  `/etc/shadow`):
  - `omv-config-2026-10-10.tgz`
  - `chainedbox-emmc-2026-10-10.img.gz`: 3.17 GB, decompresses to exactly
    7820083200 bytes (all of `mmcblk0`), `gzip -t` OK, `.sha256` alongside.
    Taken live, so it's crash-consistent. **This is the rollback.**
- **D3 rescue copy:** `agent:/tmp/` (177 GB) is on `data:/bk/` (rsync exit 0).
- **Pre-step-1 cleanup:**
  - Entware services stopped and kept from starting at boot (MySQL, nginx/PHP,
    aria2, Seafile, snmpd, FileBrowser, easy-explorer). RAM used fell from 407
    to 288 MB.
  - Dead ayufan apt list disabled.
  - netatalk (AFP) purged.
  - *(The restore in R1 undoes all three. Redo them afterwards.)*

## What's wrong

Everything below was done by the agent, over plain SSH, on 2026-10-10:

1. **Step 1 broke partway.** `apt full-upgrade` ran with no tty and without
   `DEBIAN_FRONTEND=noninteractive`. It stopped at the libc debconf prompt.
   `omv-release-upgrade` doesn't exist on OMV 4, and the box was rebooted
   anyway. `lsb_release` showed "10.13" (only `base-files` had upgraded), and
   that was wrongly read as success. **OMV 5 was never installed.**
2. **"Step 2" was started on top of that.** The sources were switched to
   bullseye and OMV `shaitan`, with a wrong security line
   (`bullseye/updates`; the right one is `bullseye-security`).
3. **`apt --fix-broken install` ran against the bullseye sources.** It
   unpacked bullseye libc and openssh, and marked OMV 4 for removal. The session
   dropped mid-run.
4. SSH then reset every new connection until the user rebooted the box. It
   works now.
5. **The `/boot.scr` USB "shim" on the eMMC is useless.** It only looks for a
   stick and prints a message. It never boots from USB. Right now **there is
   no working way to boot the box from USB.**

**Current state** (read-only check after the reboot):

| | |
|---|---|
| Userland | still stretch: 234 `deb9u` packages, 12 `deb10`, 5 `deb11`; `apt` 1.4, `systemd` 232 |
| `libc6` | **2.31 (bullseye), half-configured**. `libc-bin` still 2.24 |
| Unpacked, not configured | bullseye `libssl1.1`, `openssh-server` 8.4, `locales`, `resolvconf` and 9 more libraries |
| **Marked for removal** | `openmediavault` 4.1.36, `-minidlna`, `-omvextrasorg`, `-flashmemory`, `quota`. **The next `apt` run would remove OMV.** |
| apt sources | bullseye + `shaitan` |
| Services | OMV UI, SMB, FTP, NFS, DLNA, DNS and Transmission all up. Kernel unchanged (5.3, held) |

libc 2.31 can't safely be downgraded, and stretch→bullseye with OMV 4→6 in
one jump isn't a supported path. So: **restore the image.**

## Next: Recovery R1 (proposed, not started; each stage needs a go-ahead)

1. **P0 ✓ (2026-10-10):** `unattended-upgrades` isn't installed, and every
   `APT::Periodic` setting is `"0"`, so the `apt-daily` timers do nothing. Still
   unread: `/etc/cron.daily/openmediavault-cron-apt`. The box doesn't see the
   stick; it's in the Mac as `disk4` (8 GB).
2. **USB stick, written on the Mac.** On the box, `sda`/`sdb` are the data
   disks, so writing the stick from there risks hitting the wrong one. Inspect
   the patched ophub image first (partitions, location of `boot.scr`), then
   `dd` it to the stick's `/dev/rdiskN`, checked by size and model.
   **✓ (2026-10-10):** wrote `armbian-chainedbox-trixie-6.18.54-quirks.img`
   (sha256 `9acbc4c0…1003` verified OK; **not** the original `.img.gz`, which
   lacks the quirks) to `disk4` with `sudo dd … bs=4m`, run by the user:
   3699376128 bytes, the exact image size. Stick now shows GPT with
   p1 535.8 MB + p2 3.1 GB, matching the image. Booting from it is untested.
3. **Real shim.** Replace `/boot.scr` with a chain-loader: `usb start`; for
   each USB dev/part, if `boot.scr` exists, set `devtype`/`devnum`/
   `distro_bootpart` and `source` it. If nothing loads, it returns and the
   eMMC boots as now.
   *Facts from the stick image (read on the Mac):* its `boot.cmd` calls
   `load ${devtype} ${devnum} …` with **no partition**, so the shim sets
   `devnum=<d>:1`. Its BOOT fs is ext4 with `64bit metadata_csum orphan_file`,
   so U-Boot 2017.09 must read that (compare with `mmcblk0p7`, which it already
   boots). Kernel 43.8 MB at `0x02000000`, initrd at `0x06000000`, script
   `load_addr 0x39000000`.
   - **3a, read-only on the box:** current `/boot.scr` source; U-Boot default
     env (from the bootloader on the eMMC: scan order, `scriptaddr`,
     `fdt_addr_r`); `p7` ext4 features; is `mkimage` there.
   - **3b, the write:** keep the old one as `/boot.scr.old-shim`, install the
     new `/boot.scr` (built on the Mac, uploaded with `scp`), then `sync`.
     No `apt`. Undo: `mv /boot.scr.old-shim /boot.scr`.
   - **Shim must restore `devtype`/`devnum`/`prefix`** if the stick fails, or
     the eMMC fallback breaks.
   - **3a ✓ (2026-10-10), findings:**
     - The old shim has a syntax error (`for x in 0 1 2 3` with no `; do`),
       so it never ran properly. **There is no evidence that `usb start`
       works without hanging.**
     - U-Boot default env is in `mmcblk0p1`. Only `p7` is
       `LegacyBIOSBootable`. On p7, U-Boot checks prefix `/` first:
       `/extlinux/extlinux.conf` is absent, so `/boot.scr` runs **before**
       `/boot/extlinux/extlinux.conf`. Confirmed.
     - `scriptaddr=0x00500000` (the shim itself runs from here, so the stick
       script loads at `0x00600000`). `fdt_addr_r=0x01f00000`,
       `kernel_addr_r=0x02000000`, `ramdisk_addr_r=0x04000000`.
     - The eMMC extlinux uses `devicetreedir`, which picks the DTB by
       `${fdtfile}`. The stick's `armbianEnv.txt` overwrites `fdtfile` and
       `ramdisk_addr_r`, so **the shim also saves and restores
       `fdtfile`/`kernel_addr_r`/`ramdisk_addr_r`.**
     - p7 ext4 already has `64bit metadata_csum`, the same as the stick
       except for `metadata_csum_seed`/`orphan_file`.
     - `mkimage`/`dumpimage` are on the box. The stick is `sdc` (511M BOOT +
       3G ROOTFS) on the `dwc2` OTG port. Whether 2017.09 U-Boot drives that
       port is unknown; if not, the shim finds nothing and the eMMC boots,
       and we try another port.
   - **3b ✓ (2026-10-10 19:24):** source is [`usb-shim.cmd`](usb-shim.cmd),
     built on the box with `mkimage -C none -A arm -T script` (`dumpimage`:
     "ARM Linux Script", 1364 B) and installed as `/boot.scr`. The old shim
     is kept as `/boot.scr.old-shim`; undo with `mv /boot.scr.old-shim
     /boot.scr`. Not yet exercised by a reboot.
4. **Boot the stick.** *Booted (2026-10-10 ~19:30):* clean `poweroff` at
   19:25 (eMMC system MAC `66:c9:1c:46:67:db`), `agent` unplugged, stick on
   the OTG port. The stick system came up at **`192.168.2.154`** (MAC
   `4a:c3:2e:07:2e:f6`, a different MAC, so a new DHCP lease), SSH banner
   `OpenSSH_10.0p2 Debian-7+deb13u4`. So the shim chain-load works, and
   U-Boot 2017.09 reads the stick's ext4. **Gate ✓:** Armbian 26.11 trixie,
   kernel 6.18.54-ophub. `lsblk` shows only `sda` (the stick, DataTraveler G3,
   `/` and `/boot`) and `mmcblk0` (not mounted). The `data` disk is
   `usb-storage 4-1.1: device ignored`. **On the stick system the stick is
   `sda`, so never write to `sd*` here.** The
   image's `usbstoragequirks` hide the data disks. If the box isn't up within
   ~5 min: pull the stick and power-cycle.
5. **Restore** from the Mac:
   `gunzip -c chainedbox-emmc-2026-10-10.img.gz | ssh root@<stick-ip> 'dd of=/dev/mmcblk0 bs=4M conv=fsync'`.
   Then compare a hash of `/dev/mmcblk0` against a hash of the decompressed
   image.
   *Prepared (2026-10-10):* `.gz` sha256 OK. Decompressed: **7820083200 bytes
   = `mmcblk0` exactly**, raw sha256 `2b27537a…ccd7`
   (`2b27537a0718d355a1fb155d718c81a09cf60bbd8b30281b558270ae6a05ccd7`).
   The `.gz` is sent over SSH and decompressed on the box (less network
   traffic). Read back with `iflag=direct` so the hash comes from the eMMC,
   not the page cache. If the write is interrupted, just rerun it: the box
   runs from the stick, so a half-written eMMC is harmless until the reboot.
   **✓ Done (2026-10-10):** guards passed, 7820083200 bytes written in 866 s
   (~9 MB/s, eMMC-bound), `sync`. Read-back with `iflag=direct` after
   `drop_caches`: sha256 `2b27537a…ccd7` **matches**.
6. **Pull the stick and reboot.** Redo the pre-step-1 cleanup and reinstall the
   fixed shim (the image predates both).
   **✓ Booted (2026-10-10 19:59):** stick pulled, `agent` replugged. `.14` is
   back with MAC `66:c9:1c:46:67:db` and `OpenSSH_7.4p1 Debian-10+deb9u7`.
   Journal replay: "7 orphan inodes deleted, recovery complete".
   Health: `dpkg --audit` empty; non-`ii` only `rc board-package-rock64`
   and `hi linux-image-5.3.0-1119` (both expected); `libc6`/`libc-bin`
   2.24-11+deb9u4; `openmediavault` 4.1.36-1 + minidlna + omvextrasorg;
   sources stretch + arrakis; both data disks mounted; OMV, nginx, SMB,
   ProFTPD, MiniDLNA, AdGuard and the fan active; ports 21/22/53/88/139/445/
   8200/9091 open. No `/boot.scr` (expected).
   **Open:** `transmission-daemon` is inactive but `:9091` listens (probably the
   Entware build), so check the Slack bot's `torrent_list`. The clock read
   04:17 right after boot (no RTC): confirm NTP sync before any `apt`.
   Still to do: cleanup (Entware services, dead ayufan list, netatalk) and
   reinstall [`usb-shim.cmd`](usb-shim.cmd) as `/boot.scr`.

Fallback if the stick won't boot: a monitor and keyboard on the box, or
maskrom over USB A–A (unknown whether that works without opening the case).

## Cleanup redo (after R1, 2026-10-10)

The user approved running cleanup → shim → Step 1 in sequence. Each one still
gets a check and a record here.

- **C0 clock:** right after boot the box was 15 h 42 m behind (fake-hwclock
  restored the image's time). `ntpd` won't step an offset that large by
  itself. Fix: `systemctl stop ntp; ntpd -gq; systemctl start ntp`.
- **C1 Entware:** started by `/etc/rc.local` → `/opt/entware_init.sh`, which
  runs `rc.unslung start` (every **executable** `/opt/etc/init.d/S*`) and
  then `onmp start`, `filebrowser.sh` and `easy-explorer-arm &` directly.
  - For each of `S47snmpd S66seafile S67seahub S70mysqld S79php7-fpm S80nginx
    S81aria2`: run `stop`, then `chmod -x`.
  - **Keep `S88transmission`**, the Entware Transmission on `:9091` that the
    Slack bot uses. Debian `transmission-daemon` is unused (inactive).
  - Back up `entware_init.sh` to `.orig`, comment out the `onmp`,
    `filebrowser` and `easy-explorer` lines, then kill those two processes.
  - Debian `nginx`/`php7.0-fpm` are the OMV web UI: **don't touch them.**
- **C2 apt list:** `ayufan-rock64.list` → `.list.disabled` (the repo is
  dead; kernel and board packages are held or `rc` anyway).
- **C3 netatalk:** `apt-get -s purge netatalk openmediavault-netatalk` first.
  Stop if anything besides those two is removed. Then run it for real with
  `DEBIAN_FRONTEND=noninteractive`.
- **No tmux on the box.** Long jobs (C3, Step 1) run under `systemd-run`
  (a transient unit, so they survive an SSH drop), logged to
  `/root/upgrade-logs/`.

**Results (all ✓, 2026-10-10 20:05–20:09):**
- C0: `ntpd -gq` stepped the clock +56498 s and it matches the Mac; `ntp`
  is active again.
- C1: the 7 `S*` scripts are `-x`; `entware_init.sh.orig` is kept, and the
  diff is just the 3 lines commented out. Left running: Transmission (`:9091`,
  RPC returns 401 = up with auth) and the OMV UI (Debian nginx + php7.0-fpm,
  `:88` → 200). RAM used 350 → 248 MB.
  *Gotcha:* `pkill -f /opt/easyexplorer/…` inside `ssh '…'` matched and
  killed the remote shell itself. Use `pkill -x` or `pgrep` by `comm`.
- C2: `ayufan-rock64.list.disabled`.
- C3: the simulation listed only the 2 packages. The real run exited 0,
  `dpkg --audit` is clean, `:548` is closed. The warning "/var/lib/netatalk/CNID
  busy" is an empty `folder2ram` tmpfs (flashmemory plugin), which is
  harmless. The Python 3.5 `weakref` tracebacks at exit are harmless.
- Shim: [`usb-shim.cmd`](usb-shim.cmd) rebuilt with `mkimage` and installed
  as `/boot.scr` (it didn't exist after the restore). The installed text
  matches the source byte for byte.

## Step 1 redo: Debian 10 + OMV 5 (2026-10-10)

- **Prep ✓:** `/etc/apt` backed up to `/root/upgrade-logs/etc-apt-stretch.tgz`.
  `sources.list` → `archive.debian.org` buster + `debian-security
  buster/updates`; `openmediavault.list` arrakis → usul;
  `99archive-no-valid-until` added (`Check-Valid-Until "false"`). The buster
  archive keys were already present. `apt-get update` OK.
- **Simulation ✓** (`/root/upgrade-logs/s1-simulate.txt`): 502 upgraded,
  145 new, 4 removed (`libtirpc1`, `libcurl3`, `libsensors4`, `ntp`, the last
  replaced by `chrony`). **`openmediavault` 4.1.36 → 5.6.26**, not removed.
  libc 2.28, systemd 241, php7.3, nginx 1.14, samba 4.9, openssh 7.9.
  The `flashmemory` 4.2.2, `omvextrasorg` 4.1.16 and `minidlna` 3.3.11 plugins
  **stay at 4.x** (no usul builds in the configured sources, and the omv-extras
  key has expired). Afterwards, check they don't break `omv-engined`; if they
  do, `apt-get remove` (not purge) them.
- **Run:** `systemd-run --unit=s1-upgrade` with `DEBIAN_FRONTEND=noninteractive`,
  `UCF_FORCE_CONFFOLD=1`, `APT_LISTCHANGES_FRONTEND=none`, `--force-confdef
  --force-confold`. Log: `/root/upgrade-logs/s1-dist-upgrade.log`.
- **Gate after:** `dpkg --audit` empty, `apt-get check` clean,
  `openmediavault` 5.x, `omv-salt deploy run` (OMV 5 configures via salt),
  services up, then reboot (the stick stays out; the shim falls through to eMMC).
- **Result:** `dist-upgrade` ran 20:12–20:29 and exited 100. All of Debian
  10.13 configured, but **`openmediavault` postinst failed** at "Processing
  system modifications". Cause: OMV 5's salt `apt` state writes
  `security.debian.org buster/updates` and `httpredir … buster-backports`
  lists (both gone from the mirrors, now on `archive.debian.org`), and the
  salt `refresh_db` fails on them.
  **Fix:** add `OMV_APT_USE_KERNEL_BACKPORTS="no"` and
  `OMV_APT_USE_OS_SECURITY="no"` to `/etc/default/openmediavault` (backup in
  `/root/upgrade-logs/`; security is still covered by the `archive.debian.org`
  line in `sources.list`). Then `omv-salt stage run deploy` (exit 0),
  `omv-salt deploy run apt cronapt` (exit 0), then `dpkg --configure -a`
  (exit 0). **Keep these two settings for later steps too**, since each
  release ends up in the archive.
- **Gate ✓ (20:43):** `dpkg --audit` empty, `apt-get check` clean.
  `openmediavault` **5.6.26-1 ii**, Debian 10.13. The old 4.x plugins
  (flashmemory, minidlna, omvextrasorg) are installed and `omv-engined` logs
  no errors. Active: engined, nginx, php7.3-fpm, smbd/nmbd, proftpd, minidlna,
  AdGuard, chrony (in sync), fan, monit. Ports 21/22/53/88/139/445/8200/9091;
  web UI 200; Transmission RPC 401. `agent` and `data` are mounted.
  Leftover `rc` entries: `ntp`, `libtirpc1`, `libsensors4`.

## After Step 1: network (2026-10-10 20:45–20:57)

The first reboot on OMV 5 came up on DHCP `.159` + `.160` instead of `.14`:
three DHCP clients (ifupdown `dhclient`, the board image's `dhcpcd` +
`NetworkManager`, OMV 5's `systemd-networkd`). The OMV db had eth0 =
`dhcp`. Changes made (the user later said network changes need asking first):
OMV eth0 set **static `192.168.2.14/24`, gw `192.168.2.1`, DNS
`8.8.8.8,1.1.1.1`**; `/etc/network/interfaces.d/eth0` and
`/etc/netplan/eth0.yaml` moved to `/root/upgrade-logs/net-old/`;
`dhcpcd` and `NetworkManager` **disabled** (not removed). Result: only `.14`,
route `proto static`. **Don't touch the network without asking.** Optional:
a router DHCP reservation for `66:c9:1c:46:67:db` → `.14`.
Open: `watchdog`/`wd_keepalive` fail to start (not blocking).

## Step 2: Debian 11 + OMV 6 (user approved 2026-10-10, MiniDLNA option 2)

- **MiniDLNA without the plugin:** `/etc/minidlna.conf` is owned by Debian
  `minidlna`. The plugin postrm does nothing on `remove`. So `apt-get remove
  openmediavault-minidlna` keeps the daemon and its config (7 `media_dir`,
  `friendly_name=OMV`, port 8200). From now on, edit `/etc/minidlna.conf`
  by hand.
- **omvextrasorg 4.x:** remove (postrm only deletes its lists). Install
  omv-extras 6 after the upgrade.
- **flashmemory 4.2.2:** **don't remove.** Its prerm on `remove` calls
  `omv-mkconf`, which OMV 5 lacks, so the removal would fail. Upgrade it in
  place to 6.x from omv-extras later (prerm `upgrade` is a no-op).
  `folder2ram` is a separate package.
- **Repos (checked from the Mac, all 200):** `deb.debian.org` bullseye,
  `security.debian.org` bullseye-security, `shaitan` on both OMV repos, and
  omv-extras `shaitan`.
- **`omv-release-upgrade` uses whiptail** (interactive), so run its steps by
  hand: `omv-upgrade`, `run-parts --exit-on-error pre.d`, then **rewrite
  `sources.list`** (`pre.d/20` would turn ours into
  `archive…/debian-security bullseye/updates`, which doesn't exist), then
  `apt-get update`, simulate, `dist-upgrade` with the tool's options, then
  `run-parts post.d`.
- **No eMMC backup of the OMV 5 state** (the user's call). The stick can still
  restore only the morning OMV 4 image, so a step 2 failure gets fixed
  forward.
- **Done:** plugins `minidlna` + `omvextrasorg` removed (MiniDLNA still
  active on :8200, conf unchanged, backup `minidlna.conf.bak`).
  `etc-apt-buster.tgz` backup taken. `omv-upgrade` and `pre.d` OK.
  `sources.list` set to `deb.debian.org` bullseye + bullseye-updates +
  `security.debian.org` bullseye-security.
- **Simulation:** 503 upgraded, 95 new, 87 removed (old PHP 7.0/7.3, Python
  2/3.7, gcc-8 and other libraries). **`openmediavault` 5.6.26 → 6.9.16.**
  PHP 7.4, samba 4.13, salt 3006, openssh 8.4. **`proftpd-basic` gets
  removed: OMV 6 moved FTP into the official plugin `openmediavault-ftp`
  6.0.7.** The FTP config in the db is kept (`conf.service.ftp`, enabled,
  port 21). `flashmemory` 4.2.2, `folder2ram` and the `minidlna` daemon stay.
  `dhcpcd5`/`network-manager` get upgraded but stay disabled (verify only,
  no network changes).
- **Order:** `dist-upgrade` → `apt-get install openmediavault-ftp` →
  `run-parts post.d` (post.d's proftpd deploy needs the plugin's salt state).
- **Run 1 (21:12) failed in download, nothing installed:**
  `security.debian.org` still serves the bullseye-security *index* but the
  pool files 404 (bullseye LTS ended 2026-08). Fix: all three bullseye lines
  on **`archive.debian.org`** (debian bullseye, bullseye-updates,
  debian-security bullseye-security). Re-simulation is the same, and
  `--download-only` fetched everything with 0 errors.
- **Mistake: `omv-upgrade` (prep) ran `--auto-remove`** and removed
  `minidlna` (installed only as the old plugin's dependency) plus ~100 old
  libs, `acpid`, `ifenslave`, `pm-utils`. DLNA has been down since ~21:10.
  `/etc/minidlna.conf` is intact (rc state). Fix: `minidlna` added to the
  `install openmediavault-ftp` line, so it reinstalls with `--force-confold`.
  **Before removing a plugin, `apt-mark manual` its daemon.**
- **Run 2 started 21:19** (unit `s2-upgrade2`). `dist-upgrade` EXIT 0 (OMV 6
  postinst passed; `--force-confold` kept our `/etc/default/openmediavault`),
  `openmediavault-ftp` + `minidlna` EXIT 0. `post.d` EXIT 1: only
  `50-rebuild-proftpd-conf` failed, because monit didn't know `proftpd` yet.
  Fix: `omv-salt deploy run monit`, then `proftpd` again **in a separate run**
  (in one run the monitor state fires before monit reloads). Both are clean
  now.
- **Gate ✓ after reboot (21:41):** **Debian 11.11, OMV 6.9.16**, kernel 5.3
  (held), `dpkg --audit` empty, `systemctl is-system-running` = **running**
  (the watchdog failure is gone too). Active: engined, nginx, php7.4-fpm,
  smbd/nmbd, proftpd, minidlna 1.3.0, AdGuard, chrony (synced), fan, monit,
  folder2ram (2 tmpfs). Ports 21/22/53/88/139/445/8200/9091. Web UI 200,
  Transmission 401. MiniDLNA rescanning (133 videos so far). eth0 only
  `192.168.2.14`, route `proto static`, `dhcpcd`/`NetworkManager` still
  disabled. Both data disks are mounted. Root 52% (3.3 GB free). RAM used
  177 MB.
- **Left for step 2:** `openmediavault-flashmemory` is still 4.2.2. Install
  omv-extras 6, then upgrade flashmemory to 6.x (prerm `upgrade` = no-op).

## Step 3: Debian 12 + OMV 7 (user said "move on", 2026-10-10)

- **flashmemory stays 4.2.2 until the final release** (an inert plugin;
  `folder2ram` works on its own). Install omv-extras + flashmemory once, on
  OMV 8. `apt-mark manual folder2ram` done.
- **Repos (from the Mac, all 200):** `deb.debian.org` bookworm +
  bookworm-updates, `security.debian.org` bookworm-security, `sandworm` on
  both OMV repos. Simulated autoremove: nothing.
- **OMV 6 `omv-release-upgrade`** (whiptail again): `omv-upgrade` → `pre.d`
  (also stops cron/anacron/monit) → `apt-get update` → `dist-upgrade` →
  `post.d` (deploy config, restart engined) → `omv-upgrade`. Run by hand
  **without `--allow-change-held-packages`** (keeps the 5.3 kernel hold).
  After `pre.d`, rewrite `sources.list` to `deb.debian.org` bookworm,
  bookworm-updates and `security.debian.org` bookworm-security
  (`main contrib non-free non-free-firmware`); `pre.d` would otherwise
  produce `archive.debian.org bookworm`, which doesn't exist.
- **Prep ✓:** `etc-apt-bullseye.tgz`; `omv-upgrade` removed nothing; `pre.d` OK.
  **Simulation:** 545 upgraded, 128 new, 81 removed. **`openmediavault`
  6.9.16 → 7.7.24-7**, `openmediavault-ftp` → 7.0.2. libc 2.36, systemd 252,
  samba 4.17, nginx 1.22, php8.2-fpm, openssh 9.2, minidlna and proftpd
  upgraded in place. Replacements: `resolvconf` → **`systemd-resolved`**,
  `cron-apt` → `apticron`, `fuse` → `fuse3`. `hdparm`/`fdisk` were only
  autoremove candidates, so `apt-mark manual` keeps them. `--download-only`
  OK.
- **Known follow-up (user: "fix AdGuard later"):** `systemd-resolved`'s
  stub listener (127.0.0.53:53) conflicts with AdGuard on `*:53`. Fix:
  `/etc/systemd/resolved.conf.d/adguard.conf` with `DNSStubListener=no`.
  The LAN uses 8.8.8.8/1.1.1.1, so it isn't blocking.
- **Run started 21:52** (unit `s3-upgrade`): dist-upgrade → post.d →
  omv-upgrade. All three EXIT 0; Debian 12.15, OMV 7.7.24-7, `dpkg --audit`
  clean.
- **Reboot → box gone from the LAN (overnight until 2026-10-11 07:27).** It
  booted but never configured its NIC. Two causes stacked: systemd 252
  renamed the NIC **`eth0` → `end0`**, and **netplan 0.106 (bookworm) matches
  `match: macaddress` as `PermanentMACAddress=`**. This board's NIC has
  **no permanent MAC** (`ethtool -P`: not set; `66:c9:…` is assigned at
  boot), so nothing matched. Diagnosed from the stick (rescue at `.191`
  with a random MAC, so search by SSH banner rather than MAC) by reading
  the eMMC journal, and by running the eMMC's own `netplan generate` into a
  tmpfs.
- **Fix (user: no static IP, DHCP from the router):** backups in
  `/root/upgrade-logs/net-fix-20261011-*`. OMV db interface →
  `devicename end0`, `method dhcp`, address/netmask/gateway/DNS emptied.
  `20-openmediavault-eth0.yaml` replaced by `20-openmediavault-end0.yaml`
  (`match: name: end0`, `dhcp4: true`). **New
  `/etc/systemd/network/05-chainedbox-end0.network`** (`Name=end0 eth0`,
  `DHCP=ipv4`, `ClientIdentifier=mac`) as the name-based fallback, because
  any OMV redeploy writes a MAC match again. `dhcpcd`/`NetworkManager` stay
  disabled (one DHCP client only). No static `.14` remains in live config.
- **Up (07:27) on DHCP `192.168.2.161`**, `end0` routable, DNS from DHCP
  8.8.8.8/1.1.1.1. `is-system-running` = running, all services active except
  **AdGuardHome "activating"** (port 53 taken by the `systemd-resolved`
  stub, the known follow-up). Web UI 200, Transmission 401, both data disks
  mounted, root 58%.
- **Open:** (1) **the address changed `.14` → `.161`.** Anything that uses the
  IP (the Hermes Slack bot's Transmission RPC, SMB/FTP bookmarks) needs a
  router DHCP reservation for `66:c9:1c:46:67:db` or updating. (2) AdGuard
  vs `systemd-resolved` stub. (3) monit still references `php7.4-fpm`.

## Final cleanup and check (2026-10-11 07:35–07:50)

- **AdGuard fixed:** `/etc/systemd/resolved.conf.d/adguard.conf`
  (`DNSStubListener=no`), `/etc/resolv.conf` →
  `/run/systemd/resolve/resolv.conf`, and
  `OMV_SYSTEMD_NETWORKD_RESOLVCONF_TARGET` set to that path in
  `/etc/default/openmediavault` (otherwise OMV's `90resolv_conf` salt state
  puts the stub symlink back). AdGuard holds `*:53` UDP+TCP and answers from
  the Mac. Backups: `/root/upgrade-logs/adguard-fix/`.
- **OMV pending changes applied:** `omv-salt stage run prepare` + `deploy`:
  247 states, 0 failed. This also fixed monit's php-fpm. OMV's netplan
  cleanup only deletes `*openmediavault-*` files, so
  `05-chainedbox-end0.network` survives. `dirtymodules.json` reset to `[]`
  (a CLI deploy doesn't clear it; backup kept).
- **Cleanup:** 63 `rc` remnants purged (kept: `board-package-rock64`,
  `resolvconf`, `openmediavault-minidlna`, `openmediavault-omvextrasorg`).
  The `/var/tmp/tmp.*` release-upgrade dirs are removed. The
  `99archive-no-valid-until` apt override and the `/root/usb-shim.*` copies
  are moved into `/root/upgrade-logs/` (2.6 MB, kept as the record).
  `apt-get clean`.
- **Reboot test ✓ (07:46):** back on DHCP `.161` in about 1 min,
  `is-system-running` = running, no pending OMV changes, `dpkg --audit`
  clean. All services up: OMV, nginx, php8.2-fpm, smbd, proftpd, minidlna
  (1198 audio / 1361 video), AdGuard, Transmission (401), chrony (synced),
  fan, monit, folder2ram (8 mounts). Ports 21/22/53/88/139/445/8200/9091 are
  reachable from the Mac. `data` 64 %, `agent` 37 %, eMMC 58 %.
- **Intentionally off (OMV settings, unchanged):** `nmbd`,
  `collectd`/`rrdcached` (perf stats), `smartd` (SMART monitoring).
- **Pre-existing, not changed:** FTP **anonymous login enabled, no TLS**
  (`anonymous=1` already in the OMV 5/6 config). D2's "FTPS on" never matched
  the box. Decide in OMV → Services → FTP.

## Rules for every step from now on

- Run on the box **inside `tmux`**, logged with `script`. Never in an SSH heredoc.
- `DEBIAN_FRONTEND=noninteractive` with `--force-confdef --force-confold`.
- Simulate first (`apt-get -s dist-upgrade`). **Stop if `openmediavault` is
  in the removal list.**
- Gate on facts, not `lsb_release`: `dpkg --audit` empty, `apt-get check`
  clean, `openmediavault` at the target major version.
- Show the user the exact script before it runs. One step per session.

## Upgrade path (after R1)

| Step | Debian | OMV | Notes |
|---|---|---|---|
| 1 | 10 buster | 5 usul | Manual on OMV 4: sources `stretch→buster` (`archive.debian.org`, security `buster/updates`), `arrakis→usul`, dist-upgrade, then `omv-salt deploy`. Every repo was checked and returns 200 |
| 2 | 11 bullseye | 6 shaitan | `omv-release-upgrade` exists from OMV 5 on. Security suite `bullseye-security` |
| 3 | 12 bookworm | 7 sandworm | OMV 7 is EOL; only a stop on the way |
| 3b | 12 | 7 | **kernel 5.3 → ophub 6.18 LTS** + `rk3328-l1pro-1296mhz.dtb` |
| 4 | 13 trixie | 8 synchrony | systemd 257 wants kernel ≥ 5.4, hence 3b first |

**Kernel (3b):** test the ophub trixie image from the stick first. Install it
via a `/boot.scr` that sets `ramdisk_addr_r=0x06000000`: the 6.18 Image is
43.8 MB and overlaps the initrd at U-Boot's default addresses. Keep the 5.3
files and `/boot/extlinux/extlinux.conf` as the fallback. Kernel updates are
manual (new ophub tarballs).

## Box facts

- **Disks are USB.** `sdb` `data` (Toshiba 2 TB, Genesys `05e3:0735`, inside
  the case). `sda` `agent` (Seagate FreeAgent Go `0bc2:2100`, **failing**:
  5190 Reported_Uncorrect).
- **Boot:** ayufan U-Boot 2017.09. No saved env; order `mmc0 (eMMC) mmc1 usb0`.
  It boots `/boot/extlinux/extlinux.conf` on `mmcblk0p7`. A `/boot.scr` there
  is scanned first. **No SD slot.** A plugged-in stick doesn't auto-boot.
- **Stick image:** `Armbian_26.11.0_rockchip_chainedbox_trixie_6.18.54_server_2026.10.01.img.gz`
  (sha256 `fb1453b3…c846`, matches GitHub). Patched copy adds
  `usbstoragequirks=…,0x05e3:0x0735:iu,0x0bc2:0x2100:iu` to hide both data
  disks.
- **Don't purge `board-package-rock64` (`rc`):** its conffiles include the
  network config.
- **Fan:** `fan.service` (`/sbin/fan`, Rock64 GPIO numbering). Check it after
  every step; the l1pro dtb replaces it at 3b.
- **Shares on `data`:** `media/` (+ `videos`, `torrent`, `movies`, `musics`,
  `clips`), `bk/`. On `agent`: `backup/`, `tmp/` (the only SMB share, guest).
  No NAS or Samba users.

## Decisions

- **D1:** ~~end state OMV 8 on Debian 13~~ → **revised 2026-10-11: stay on
  OMV 7 / Debian 12 / kernel 5.3** (good enough; skip the kernel work).
- **D2:** keep SMB, FTP (FTPS on), AdGuard, Transmission (empty list, no
  seeding; the Hermes Slack bot uses its RPC on :9091) and MiniDLNA (the LG TV
  is DLNA-only). Drop AFP, NFS, MySQL/nginx/PHP, aria2, Seafile, FileBrowser
  and the Entware bundle.
- **D3:** `agent` stays read-only, outside OMV, until it's replaced.
- **D4:** LAN DNS already points at 8.8.8.8/1.1.1.1, so reboots don't break
  name resolution.
- **D5 (open):** new home for the SMB share: `data:bk/` or `data:media/`, no
  guest access.

## End-state checks

- [ ] `lsblk -f` UUIDs and labels match Phase 0; `smartctl` no worse
- [ ] SMB reachable, Vietnamese file names correct
- [ ] Transmission empty, the Slack bot's `torrent_list` works, a finished download stops seeding
- [ ] FTPS login works, anonymous refused
- [ ] AdGuard answers on :53; DLNA visible on the TV; fan runs
- [ ] Survives a cold reboot
