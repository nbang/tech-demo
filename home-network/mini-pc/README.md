# Mini PC (`mx`) — home LAN box

Old Intel mini PC, revived and reinstalled on 2026-10-02: light desktop (Xfce)
plus background jobs. **On-demand, not always-on** — powered up when needed;
the always-on role belongs to the TX3 box (`192.168.2.20`).

## Access

| | |
|---|---|
| IP | `192.168.2.114` (DHCP — reserve it on the router) |
| Hostname | `mx` (also `mx.local` via mDNS) |
| SSH | `ssh bang@192.168.2.114` — key auth from the Mac (`~/.ssh/id_ed25519`) |
| User | `bang` (sudo needs password) |
| Ethernet MAC | `6c:4b:90:1a:68:bb` (eth0) |
| Wi-Fi MAC | `52:0f:31:61:ca:8e` (wlan0, unused) |

Firewall (ufw) is on by default in MX; SSH was opened with `sudo ufw allow ssh`.
Any new service port needs its own `ufw allow`.

## Hardware

| | |
|---|---|
| CPU | Intel Xeon E-2176M — 6C/12T, 2.7 GHz, Coffee Lake (8th gen) |
| GPU | Intel UHD Graphics P630 (iGPU) |
| RAM | 16 GB |
| Disk | LiteOn CV8-8E256 256 GB SATA SSD |
| Ethernet | Intel I219-V |
| Wi-Fi | Qualcomm Atheros QCA9377 (802.11ac) |
| Display | DisplayPort |
| Firmware | Lenovo BIOS `FWKTB3A` (2020-10-30), board `30D2`, UEFI boot |

DMI reports **Lenovo ThinkCentre M700 (10J0S40N00)**, but the M700 is a
Skylake machine and never shipped with this Xeon. The DMI strings are
unreliable — look up drivers/BIOS by the CPU and board ID, not "M700".

## OS

| | |
|---|---|
| Distro | MX Linux 25.3 "Infinity" Xfce x64 (Debian 13 trixie) |
| Kernel | 6.12.107+deb13-amd64 |
| Init | systemd |
| Layout | `sda1` 256 MB vfat `/boot/efi`, `sda2` 238 GB ext4 `/` |

## History / gotchas

- **Before the reinstall** it ran an older MX (Debian 11, Samba 4.13) at
  `192.168.2.28` with SSH off, and showed **no picture over DisplayPort**
  although it was fully booted on the network. The MX-25 live USB displayed
  fine on the same port and cable, so it was the old install, not hardware.
- **IP changes after a reinstall**: the router handed out `.114` instead of
  `.28`. Find it again by MAC: `arp -an | grep -i 6c:4b:90`.
- **MX boots sysVinit by default** on installed systems; this install came up
  on systemd. Verify with `ps -p 1 -o comm=`; switch via MX Tools → Boot Options.
- **MX firewall drops SSH** after a fresh install (connection *times out*
  rather than being refused) until `sudo ufw allow ssh`.
- **Installer USB**: Kingston DataTraveler G3 8 GB, written with
  `dd` from `MX-25.3_Xfce_x64.iso` (SHA256
  `25b5ce20caeee1b0e50507291df5ac8a8211b1b9999d8dd7416da9b66ed9fbf9`).
  It previously held the ophub Armbian installer for the Amlogic TV boxes.
  SourceForge mirrors drop mid-download — resume with a `curl -C -` loop,
  not `curl --retry` (which rewinds to its starting offset).

## To do

- [ ] DHCP reservation for `192.168.2.114` on the router
- [ ] Optional: Wake-on-LAN so it can be powered up from the Mac
      (enable in BIOS, then `sudo ethtool -s eth0 wol g`; wake with
      `wakeonlan 6c:4b:90:1a:68:bb`)
- [ ] Xfce idle-suspend is on by default — fine for on-demand use, but a
      long-running job can be cut off by it; inhibit with
      `systemd-inhibit <cmd>` or adjust Power Manager
- [ ] Install Docker (MX Package Installer or `apt`) if needed
