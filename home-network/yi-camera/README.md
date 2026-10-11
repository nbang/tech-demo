# Yi Home 720p cameras (×2), first generation

Two Xiaomi/Yi "Yi Home 720p" cameras on Wi-Fi, both running the
[wanwaner/xiaoyi1.8.7.0C_hack](https://github.com/wanwaner/xiaoyi1.8.7.0C_hack)
SD hack (`test/` folder only), so both serve RTSP.

## Identity

| | camera-01 | camera-02 |
|---|---|---|
| IP | `192.168.2.153` (DHCP, no reservation) | `192.168.2.222` (DHCP, no reservation) |
| MAC | `b0:d5:9d:29:93:25` | `b0:d5:9d:4d:6e:59` |
| Firmware | `1.8.7.0C_201705091058` | `1.8.7.0C_201705091058` |
| Wi-Fi SSID | `Router03` | — |

Hardware: HiSilicon **Hi3518 V100** (ARM926EJ-S, 40 MB RAM), Linux 3.0.8 (uClibc),
MediaTek MT7601 USB Wi-Fi, 16 MB SPI NOR.

**yi-hack-v5 / v3 / v4 don't support this model** (they target the later Hi3518ev200).
fritz-smh/yi-hack doesn't run on 1.8.7.0A+. Don't flash wanwaner's modified `home` image.
The `test/` folder alone is enough.

## Installing the hack (re-do after a reset)

1. Use an SD card of 16 GB or less, or a 16 GB FAT32 (MBR) partition:
   `diskutil partitionDisk diskN MBR FAT32 YIHACK 16G "Free Space" FREE R`.
2. Copy only `test/` and strip macOS `._*` files (the script globs `logo/*.bmp`):
   ```bash
   git clone --depth 1 https://github.com/wanwaner/xiaoyi1.8.7.0C_hack.git
   cp -R xiaoyi1.8.7.0C_hack/test /Volumes/YIHACK/ && dot_clean -m /Volumes/YIHACK
   diskutil eject /Volumes/YIHACK
   ```
3. Power off, insert the card, power on. It reboots once, then goes solid blue (~3 min).
   The script deletes `test/` from the card, so copy it again for the next camera.

The changes persist in flash without the card: `S88telnet` (telnetd), `S89ftp`
(anonymous **writable** FTP on `/`), `/home/rtspsvr`, blank logo BMPs, a `/home/cloudAPI`
wrapper that bypasses the cloud ID check (real binary: `cloudAPI_real`), and
`S50nochina` removed.

## Using it

| What | How |
|---|---|
| RTSP 720p | `rtsp://<ip>:554/ch0_0.h264` (H.264 1280×720 + AAC 8 kHz) |
| RTSP 360p | `rtsp://<ip>:554/ch0_1.h264` (H.264 640×360 + AAC 8 kHz) |
| Telnet :23 | `telnet <ip>`, user `root` (default firmware password, still unchanged) |
| FTP :21 | `ftp://<ip>/`, anonymous, whole filesystem |
| HTTP :80 | `403 File is protected` on every path |

Use RTSP over TCP (`VLC --rtsp-tcp rtsp://…`). Quick check:

```bash
ffprobe -v error -rtsp_transport tcp -show_entries stream=codec_name,width,height \
  -of compact rtsp://192.168.2.222:554/ch0_0.h264
```

## Slack bot and motion clips

The Hermes bot on the TX3 serves these in the owner's DM, via the plugin
[`../tv-box/hermes/plugins/camera-snapshots`](../tv-box/hermes/plugins/camera-snapshots/__init__.py)
(names and IPs are hard-coded there; update it if an IP changes):

- `!check camera-01|camera-02 [count] [interval_s]`: JPEGs, default 12 × 5 s. Bypasses the model.
- `!watch camera-01 [hours]` (default/max 24): a 5 s 360p clip per motion event.
  `!watch camera-01 stop` ends it, `!watch` lists them. A gateway restart silently ends all watches.
- Test without Hermes: `python3 -I ../tv-box/hermes/plugins/camera-snapshots/__init__.py camera-01 3 2 /tmp/cam`

Motion detection runs on the camera (configured in the Yi Home app) and only logs
`got a new motion start` lines to `/tmp/log.txt` (a ~100 KB ring buffer). `!watch`
re-reads that log over anonymous FTP every 3 s and diffs timestamps, so **turning
off FTP breaks `!watch`**. Untested: whether motion is still logged with no internet.

## Security

- Telnet and anonymous root FTP are open to the whole LAN; FTP is writable.
  Anyone can read the Wi-Fi password from `RT2870STA.dat`.
- `/tmp/log.txt` contains the Yi cloud key and signed upload URLs. Don't paste it anywhere.
- The cameras still talk to Yi's cloud (events upload to Xiaomi storage).
- With an SD card in, the camera writes debug tarballs containing the Wi-Fi config.
  Wipe the card before reusing it.

## Open items

- [ ] **.153 is offline**: no DHCP lease since at least 2026-10-11 (12 h+). Check power/Wi-Fi.
- [ ] Reserve `.153` / `.222` for their MACs on the router
- [ ] Change the root password (`passwd` over telnet) on both
- [ ] Move both to a guest/IoT Wi-Fi, or block their internet on the router
- [ ] See a real `!watch` clip arrive in Slack (none yet)
- [ ] Optional: feed RTSP into an NVR (Frigate / Home Assistant / Synology)
