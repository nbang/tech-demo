# LG TV — 55UM7300PTA (Developer Mode)

Living-room TV. Developer Mode is on, so webOS apps (`.ipk`) can be sideloaded
over SSH. `ares-cli` on the Mac is paired with it as device `lgtv`.

## Identity

| | |
|---|---|
| Model | **LG 55UM7300PTA**: 55" 4K UHD, 2019 UM73 series |
| Platform | webOS TV 4.5 (`sdkVersion 4.10.0`) |
| Firmware | `05.40.97` · board `K5LP_DVB_EU` · otaId `HE_DTV_W19P_AFADABAA` |
| IP | `192.168.2.216` (DHCP on Wi-Fi, no reservation) |
| Wi-Fi MAC | `74:40:be:e3:c9:86` (wired `20:17:42:79:27:be` unused, BT `74:40:be:e3:c9:87`) |
| Dev-mode SSH host key | `SHA256:ZEKO1ecdV+nx2cOwFUCJR1cGpReoiN9HdZhEjufg1iA` (RSA 2048) |

## Ports (TV on)

| Port | What |
|------|------|
| 3000 / 3001 | webOS SSAP WebSocket (plain / TLS), used by ThinQ, Home Assistant `webostv`, `lgtv` CLIs. First connection needs a prompt accepted on the TV. |
| **9922** | **Developer Mode SSH** (`OpenSSH_6.1`), user `prisoner`, key auth only |
| 9991 | Dev Mode key server, only while "Key Server" is on in the Developer Mode app |
| 1842 / 1557 / 1270 / 1401 | UPnP: DIAL, second-screen, LG device, DLNA MediaRenderer |

When off or in standby, nothing answers and ping fails, but ARP keeps the MAC.
Wake-on-LAN over Wi-Fi needs **Settings → General → Mobile TV On → Turn on via Wi-Fi**.

## Developer Mode

- The session lasts up to 1000 h (~41 days). At zero the TV leaves Developer Mode
  and **deletes sideloaded apps**. Press **Extend Session** in the Developer Mode app.
  The CLI has no `ares-extend-dev`.
- `ares-shell` refuses the `tv` profile; use raw SSH for a shell.
- `prisoner` is a jailed, unprivileged user, not root.

## Access from the Mac

The key is in `~/.ssh/lgtv_webos` (passphrase-protected; ares-cli keeps the
passphrase in `~/.webos/tv/novacom-devices.json`).

```bash
ares-device -i -d lgtv                   # model / webOS version
ares-install -d lgtv app.ipk             # sideload
ares-install -d lgtv --list
ares-launch  -d lgtv <app-id>

ssh -i ~/.ssh/lgtv_webos -p 9922 \
  -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa \
  prisoner@192.168.2.216
```

Re-pairing (e.g. after dev mode was lost): `npm install -g @webos-tools/cli`, turn
Key Server on in the app, then
`ares-setup-device -a lgtv -i "host=192.168.2.216" -i "port=9922" -i "username=prisoner"`
and `ares-novacom --device lgtv --getkey` (asks for the passphrase shown on the TV).
:9991 takes about a minute to open after the toggle. Turn Key Server off afterwards.

## Sideloaded apps

| App id | What |
|--------|------|
| `youtube.leanback.v4` | `youtube-webos`: YouTube without ads and sponsor segments |

## Open items

- [ ] Reserve `192.168.2.216` for `74:40:be:e3:c9:86` on the router
- [ ] Turn Key Server off in the Developer Mode app
- [ ] Record the Developer Mode session expiry date here
- [ ] Consider Homebrew Channel (can auto-extend the dev session; some features need root)
