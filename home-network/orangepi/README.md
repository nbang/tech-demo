# Orange Pi PC — retired spare

Orange Pi PC: Allwinner H3, **ARMv7 32-bit**, 1 GB RAM, 100 Mb Ethernet,
microSD boot only. **Retired since 2026-09-24** (its Slack bot moved to Hermes
on the [TX3](../tv-box/README.md)); SD card wiped 2026-10. Not on the network.

The other files here are historical picoclaw bot config, kept for reference.

## Reuse — the board is a spare

OS: **Armbian `orangepipc` community build, Minimal/IoT image, Debian trixie,
`current` kernel** (it ran Armbian 26.2 / kernel 6.18 with no board issues).
DietPi also works. No desktop: 1 GB is too little.

```bash
# image from https://www.armbian.com/orange-pi-pc/
xz -d Armbian_*_Orangepipc_trixie_current_*_minimal.img.xz   # flash-sd.sh takes .img/.img.gz, not .xz
../tv-box/flash-sd.sh Armbian_*_Orangepipc_trixie_current_*_minimal.img diskN
# first boot: ssh root@<dhcp-ip> with Armbian's default login, then set a root password and user
```

- **armv7/armhf only**, never arm64 images or release assets.
- One small daemon at most; no RTC. Use a fresh A1-class SD card.
- Add its new DHCP address and MAC to the [inventory](../README.md).
