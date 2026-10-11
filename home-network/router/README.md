# Router: Viettel ONT + mesh

```
fiber ─▶ DASAN H646W ONT 192.168.1.1        (NAT #1, PPPoE)
           └─ 192.168.1.2 = mesh main 192.168.2.1   (NAT #2, DHCP/DNS for the LAN)
                 ├─ mesh node 2  192.168.2.2   (wired 1 Gbps backhaul)
                 └─ mesh node 3  192.168.2.3   (wired 1 Gbps backhaul)
```

- **No public IPv4.** The PPPoE address is `10.135.140.151` (Viettel CGNAT),
  so port forwarding can't work. Inbound access needs IPv6 or a tunnel
  (Tailscale, Cloudflare Tunnel).
- **IPv6** is live on the ONT (PD `2402:800:62a7:8912::/64`), but the mesh
  main's DHCPv6 WAN is down, so the LAN has no IPv6.

## Devices

| Box | IP | MAC | Model | S/N | Made |
|-----|----|-----|-------|-----|------|
| ONT | `192.168.1.1` | WAN `18:d0:71:44:fb:31` | DASAN **H646W** (`DPW-G-P-H646W0-G1`), HW `DS-E5-583-A1` | `MJ1RRDG312B2215`, GPON `DSNW6944fb30` | 2017-01 |
| Mesh main | `192.168.2.1` (WAN `.1.2`) | `24:0b:2a:d6:ce:5c` | Viettel **vAP-32X6V1** | `VTGRB2D6CE5C` | 2024-11 |
| Mesh node 2 | `192.168.2.2` | `24:0b:2a:d5:c7:38` | vAP-32X6V1 | `VTGRB2D5C738` | 2024-10 |
| Mesh node 3 | `192.168.2.3` | `24:0b:2a:d7:08:6c` | vAP-32X6V1 | `VTGRB2D7086C` | 2024-11 |

## ONT (H646W)

- Firmware `H646W VT5.2.3070104`, xPON `RP0201`. GPON to a DASAN OLT (slot 10,
  port 2, ONU 2). Optics Rx −19.6 dBm / Tx +2.3 dBm (healthy).
- LAN `192.168.1.0/24`, DHCP on. Only port 1 is used (to the mesh main).
- Its Wi-Fi is **off**, UPnP is off. TR-069 status: ConnectError.

## Mesh (vAP-32X6V1)

- MediaTek MT7981, OpenWrt 21.02, kernel 5.4, Viettel firmware **V1.6.6_VN**.
  Ports: WAN, LAN1, LAN2, WPS, Reset, DC.
- EasyMesh R2: `.1` is the controller, nodes 2 and 3 are agents. Band
  steering on. Wired backhaul, with a hidden 5 GHz backhaul as fallback.
- Wi-Fi: `Router03` (2.4 + 5 GHz) and `Router03_5G`, WPA2/WPA3 mixed.
  Channels 11 (2.4 GHz) and 48 (5 GHz, 80 MHz).
- Services on every node: DNS, HTTP/HTTPS. SSH (TCP 62222) and telnet
  (TCP 62323) run but are firewalled from the LAN. `obuspa` (TR-369) is
  Viettel's remote-management agent.

### DHCP on the mesh main

- Pool `.2`–`.251`, lease 12 h, domain `lan`.
- DNS handed out: `8.8.8.8`, `1.1.1.1`. Clients **bypass** the Chainedbox
  AdGuard.
- No port forwards; UPnP and DDNS off.

**Address plan:** `.1`–`.3` router and mesh; `.9`–`.16` wired boxes; the rest
dynamic.

| Reserved | Host | MAC |
|----------|------|-----|
| `.2` | mesh-node-2 | `24:0b:2a:d5:c7:38` |
| `.3` | mesh-node-3 | `24:0b:2a:d7:08:6c` |
| `.9` | tx3 | `06:42:00:80:93:c1` |
| `.10` | chainedbox | `66:c9:1c:46:67:db` |
| `.11` | mx (mini PC) | `6c:4b:90:1a:68:bb` |

A host picks up its reservation at its next DHCP renewal, or immediately on
reboot. Next free wired slot: `.12`.

## To do

- [ ] Reserve addresses for the LG TV, Yi cams and air purifier.
- [ ] Decide whether DHCP should hand out AdGuard (`192.168.2.10`) as DNS.
- [ ] Optional: turn on IPv6 on the mesh main.
- [ ] Optional: remove the double NAT. Either bridge the ONT and run PPPoE on
      the mesh main (needs the PPPoE details from Viettel), or put the mesh
      main in AP mode. The CGNAT stays either way.
