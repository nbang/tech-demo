# Xiaomi Mi Air Purifier 2 mini

Xiaomi air purifier on Wi-Fi, paired with the Mi Home app. It speaks local
**miIO** on UDP 54321, so [python-miio](https://github.com/rytilahti/python-miio)
can read and control it from the LAN with its device token.

## Identity

| | |
|---|---|
| Model | `zhimi.airpurifier.m1` (Mi Air Purifier 2 mini), hardware `MC200` |
| Firmware | `1.4.3_100` |
| IP | `192.168.2.139` (DHCP, no reservation) |
| Hostname | `zhimi-airpurifier-m1_miio70938016.lan` |
| MAC | `78:11:dc:4c:30:7a` |
| miIO device ID | `70938016` (`0x043a6da0`) |
| Wi-Fi SSID | `Router03` |
| Open ports | UDP 54321 (miIO) only |

## Token

miIO needs the 32-hex device token. While paired with Mi Home, the "hello" reply
returns zeros, so get it from the Xiaomi cloud with
[Xiaomi-cloud-tokens-extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor)
(handles captcha/2FA/QR login; `miiocli cloud list` fails to log in):

```sh
git clone https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor
cd Xiaomi-cloud-tokens-extractor && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python token_extractor.py     # pick the entry with ID 70938016
```

**Don't commit the token.** It gives full LAN control and changes on every re-pair.
No-cloud fallback: reset the purifier's Wi-Fi, join its AP and read the token from
"hello" (this removes it from Mi Home).

## Reading and controlling it

`miiocli` in the current python-miio crashes (click version mismatch). Use the API:

```sh
python3 -m venv ~/miio-venv && ~/miio-venv/bin/pip install python-miio
export MIIO_TOKEN=<token>
~/miio-venv/bin/python - <<'EOF'
import os
from miio import AirPurifier
p = AirPurifier("192.168.2.139", os.environ["MIIO_TOKEN"], model="zhimi.airpurifier.m1")
s = p.status()
print(s.aqi, s.humidity, s.temperature, s.mode, s.filter_life_remaining)
# p.on() / p.off() / p.set_mode(OperationMode.Auto|Silent|Favorite)
# p.set_favorite_level(0-16) / p.set_led(bool) / p.set_buzzer(bool) / p.set_child_lock(bool)
EOF
```

| Raw key | Meaning |
|---|---|
| `aqi` / `average_aqi` | PM2.5 µg/m³, now / averaged |
| `temp_dec` | temperature × 10 (`282` = 28.2 °C) |
| `humidity` | % RH |
| `mode` / `favorite_level` | `auto`/`silent`/`favorite`; level 0–16 |
| `motor1_speed` | fan rpm |
| `filter1_life` / `f1_hour_used` / `f1_hour` | filter % left, hours used, rated hours (3,500) |
| `use_time` / `purify_volume` | total run time (s) / air cleaned (m³) |

## Live dashboard

The TX3 polls it every 30 s (`purifier-poller` service, token in
`/etc/purifier-poller.env`) and pushes to a public read-only Cloudflare Worker page.
See [purifier-dashboard/](../../purifier-dashboard/README.md).

## Open items

- [ ] **Replace the filter**: 0 % left (3,500 / 3,500 h used, ~6 years of run time).
  At 80 %+ humidity an old filter can grow mould. Buy the **2 mini** filter (smaller
  than 2/2S/3), then check `filter1_life` reads 100.
- [ ] Reserve `192.168.2.139` for `78:11:dc:4c:30:7a` on the router
