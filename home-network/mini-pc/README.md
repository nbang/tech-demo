# Mini PC (`mx`) — home LAN box

Old Intel mini PC running a light Xfce desktop plus background jobs.
**On-demand, not always-on**: power it up when needed. The always-on box is
the TX3 (`192.168.2.9`).

## Access

| | |
|---|---|
| IP | `192.168.2.11`, DHCP reservation on the mesh main (earlier `.28`, then `.114`) |
| Hostname | `mx` (also `mx.local` via mDNS) |
| SSH | `ssh bang@192.168.2.11`, key auth from the Mac; sudo needs a password |
| Ethernet | wired, eth0 MAC `6c:4b:90:1a:68:bb` (Wi-Fi unused) |

## Hardware and OS

| | |
|---|---|
| CPU | Intel Xeon E-2176M, 6C/12T, Coffee Lake, UHD P630 iGPU |
| RAM / disk | 16 GB / 256 GB SATA SSD |
| Firmware | Lenovo BIOS `FWKTB3A`, board `30D2`, UEFI |
| OS | MX Linux 25.3 Xfce x64 (Debian 13 trixie), systemd |

## Gotchas

- **ufw is on by default.** A fresh install drops SSH (it *times out*, not
  refused) until `sudo ufw allow ssh`. Every new service port needs its own
  `ufw allow`.
- **DMI says Lenovo ThinkCentre M700**, which never shipped with this Xeon.
  Look up drivers/BIOS by CPU and board ID, not "M700".
- **MX installs can boot sysVinit.** This one runs systemd; check with
  `ps -p 1 -o comm=`, switch in MX Tools → Boot Options.
- **Lost the IP?** Find it by MAC: `arp -an | grep -i 6c:4b:90`.
- **Xfce idle-suspend is on.** Long jobs can be cut off; wrap them in
  `systemd-inhibit <cmd>` or change Power Manager.

## To do

- [ ] Optional Wake-on-LAN: enable in BIOS, `sudo ethtool -s eth0 wol g`,
      wake with `wakeonlan 6c:4b:90:1a:68:bb`
- [ ] Install Docker if needed
