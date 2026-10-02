# Migration plan — picoclaw (Orange Pi) → Hermes Agent (TX3 mini)

Replace the picoclaw team bot on the Orange Pi (`192.168.2.180`) with Hermes
Agent on the TX3 mini Armbian box (`192.168.2.20`), without losing the 08:30
digest or handing the Slack workspace a shell.

Status (2026-09-24): **phases 0–3 done, Slack live on Hermes, picoclaw stopped
and disabled on the Pi.** Awaiting the Slack acceptance tests and the digest
cron (phase 4). Decisions taken: reuse `openclaw_devbot` (no staging app);
OpenRouter free primary + NIM fallback; team-wide access; torrent tools in the
owner's DM only.

## As built

| | |
|---|---|
| Hermes | v0.21.4, user `hermes` (no sudo), `~hermes/.hermes`, systemd **user** unit `hermes-gateway` + linger |
| Model | `openrouter/free` → fallback `nvidia: z-ai/glm-5.3-flash` (owner's pick, 2026-09-24; replaced laguna → glm-5.3) |
| Slack toolsets | `web, vision, memory, todo, clarify, session_search, transmission` — no terminal/code/file/browser/delegation/skills/cronjob |
| Slash commands | root `slack:` block: `allow_admin_from` / `group_allow_admin_from` = `U17599QLT`; others get `status usage new stop retry undo title sessions resume compress context btw queue` (+ `help`, `whoami`). **Without `allow_admin_from` every allowed user is admin** — with `SLACK_ALLOW_ALL_USERS=true` that was the whole workspace (`/update`, `/restart`, `/sethome`, `/debug`, `/platform pause`) |
| `/server` | plugin [hermes/plugins/server-status](hermes/plugins/server-status/__init__.py): uptime, load, temp, memory, disk, gateway RSS/age — reads `/proc` and `/sys` only; admin-only by default |
| Torrent guard | plugin [hermes/plugins/dm-only-tools](hermes/plugins/dm-only-tools/__init__.py): blocks `mcp__transmission__*` unless Slack + `U17599QLT` + `dm`; fails closed |
| MCP | `transmission` → `/bin/sh -c '. transmission.env; exec python3 transmission_mcp.py'` (password stays in the 600 env file) |
| Identity / digest | [hermes/SOUL.md](hermes/SOUL.md), skill [hermes/skills/ban-tin-sang](hermes/skills/ban-tin-sang/SKILL.md) |
| Config | applied by [hermes/patch_config.py](hermes/patch_config.py) (idempotent, backs up first) |
| Secrets | `~hermes/.hermes/.env` (600), piped Pi → box over SSH, never on the Mac |
| Updates | unattended-upgrades limited to `trixie-security` |
| Resources | gateway ~265 MB RSS; each CLI start costs ~40 s CPU (Python imports) |

### Things found during the build

- **NVIDIA `google/gemma-4-31b-it` is dead** (listed, hangs with 0 bytes) —
  the requested backup could not be used. A 2026-09-24 probe of NIM chat
  models: alive `laguna-xs-2.1` (1.0 s), `glm-5.3` (1.1 s),
  `deepseek-v4.1-flash` (2.5 s), `nemotron-3-super` (3.8 s); dead/hanging
  `kimi-k3`, `gpt-oss-20b`; 404 `kimi-k2.6`, `gemma-3-12b-it`, `mistral-large`.
- **laguna 503'd** `ResourceExhausted: Worker local total request limit reached
  (320/32)` minutes after answering a curl — free NIM capacity is flaky, hence
  two NIM fallbacks from different vendors.
- **MCP tool names are `mcp__<server>__<tool>`** (double underscore) in 0.21.x,
  not `mcp_<server>_<tool>` as some docs say. A guard matching the wrong prefix
  silently guards nothing.
- **`hermes config migrate` added `connections` to the Slack toolset list**
  on its own. Re-run `patch_config.py` after any migrate/update and re-check.
- **Title generation uses the main provider**, so every new session makes an
  extra LLM call; when NIM was primary this doubled the failures in the log.

### The NIM GIF pixel problem does not carry over

picoclaw needed `nim-gif-filter` because its `web_fetch` injected page images
(1×1 GIF trackers) into the next request and NIM 415'd on `data:image/gif`.
Neither half applies here:

1. Hermes' web tools replace inline `data:image/…;base64` blobs with an
   `[IMAGE]` text placeholder (`tools/web_tools_truncate.py:49-56`) — fetched
   pages never reach the model as images.
2. All current NIM fallback candidates are **text-only**: laguna, glm-5.3 and
   nemotron-3-super reject PNG *and* GIF alike (`multimodal processing is not
   enabled`). A GIF filter would change nothing.

### `!bot` is retired too

picoclaw needed the `!bot` prefix because its `handleAppMention` never read
`ev.Files`, so `@bot` + image silently dropped the attachment. Hermes' Slack
adapter downloads attachments on the mention path — verified 2026-09-24:
`@bot` + image in a channel was answered correctly. Hermes has no prefix
trigger; channels use `@bot`, DMs need nothing.

Other visible differences from picoclaw (defaults, not faults):

- **Threaded replies** — `platforms.slack.extra.reply_in_thread: true`; one
  thread = one session. `false` restores flat channel replies (shared context).
- **Some replies arrive as two messages** — `display.interim_assistant_messages:
  true` posts the model's pre-tool line ("Để mình kiểm tra…") immediately, then
  the answer. Long replies are also chunked to Slack's message size limit.

The proxy is retired with picoclaw. Residual edge: an image sent to the bot
while OpenRouter is down and a NIM fallback is answering fails regardless of
format.

## What is being migrated

Probed live on the Orange Pi 2026-09-24, plus
[orangepi/README.md](../orangepi/README.md):

| Piece | Today (picoclaw 0.3.1) | Notes |
|---|---|---|
| Services | `picoclaw.service`, `nim-gif-filter.service` | GIF proxy only exists to dodge NIM's 415 on `data:image/gif` |
| Model | default `openrouter-free` (`openrouter/free`), fallback `nim-primary` (`moonshotai/kimi-k3` via proxy) | kimi-k3 died 2026-09-14 (hangs, 0 bytes); free tier costs ~1–2 min per turn |
| Slack | Socket Mode app `openclaw_devbot` (`U0AF54ZCGTS`), team `T176QB33R` | `allow_from: ["*"]`, triggers `!bot` prefix + mentions |
| Digest | cron `ban-tin-sang` `30 8 * * *` → `slack:C0BPXMNJ9PU` (`#daily`) | prompt in `/root/digest_prompt.txt`; Vietnamese, 4 sections, Slack mrkdwn |
| Search | Tavily (`tools.web.provider: tavily`), markdown format | key in `.security.yml` |
| MCP | `transmission` — stdlib Python, 6 tools, Transmission at `192.168.2.14:9091` | `/root/.picoclaw/mcp/{transmission_mcp.py,transmission.env}` |
| Identity | `workspace/{AGENT.md,SOUL.md,USER.md,HEARTBEAT.md}`, `memory/`, `skills/` | AGENT.md carries the Slack mrkdwn rules |
| Hardening | `exec.allow_remote: false`, `cron.allow_command: false` | the whole team can talk to the bot, so no shell |

## Picoclaw → Hermes mapping

Hermes 0.21.3 (checked against the local checkout's docs):

| picoclaw | Hermes | Change in behaviour |
|---|---|---|
| `channel_list.slack` + `.security.yml` tokens | `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` in `~/.hermes/.env` | same Socket Mode app works |
| `allow_from: ["*"]` | `SLACK_ALLOWED_USERS` / `SLACK_ALLOWED_CHANNELS` | decide explicitly (see decisions) |
| `!bot` prefix + mentions | channels: **mention only**, replies in a thread; DMs: every message | no `!bot`; teach the team `@bot` |
| cron job bound to the creating chat | `hermes cron create … --deliver slack:C0BPXMNJ9PU` | explicit target — the "created over SSH posts nowhere" trap is gone |
| process TZ | `timezone: Asia/Ho_Chi_Minh` in `config.yaml` | set it; don't rely on the box's TZ |
| `model_list` + broken `model_fallbacks` | `model:` + `fallback_providers:` chain | different code — still must be tested with a dead primary |
| `picoclaw mcp add --env-file …` | `mcp_servers.transmission: {command, args, env}` | reuse `transmission_mcp.py` unchanged |
| `AGENT.md` / `SOUL.md` / `USER.md` | Hermes `SOUL.md` + memory; digest prompt → a skill | port text, don't copy files blindly |
| `tools.web` Tavily | Hermes web search toolset + Tavily key | verify provider name in `hermes tools` |
| `exec.allow_remote: false` | **toolset restriction for the Slack platform** + `approvals.mode` | see risk 1 |

## Risks — read before starting

1. **Hermes ships with terminal and file tools on.** picoclaw needed two flags
   to stop Slack users getting a shell; Hermes needs the equivalent, or anyone
   in the workspace can run commands on the box. Before Slack is connected:
   disable the terminal/code-execution/file-write toolsets for the Slack
   platform (`hermes tools` → per-platform), keep `approvals.mode` on, and run
   the gateway as an unprivileged `hermes` user, not root. Verify by asking the
   bot in Slack to run `id` — it must refuse or have no tool for it.
2. **One Slack app, two bots = random delivery.** Socket Mode spreads each event
   across *all* connected clients. If picoclaw and Hermes both use
   `openclaw_devbot`'s tokens, each message goes to one of them at random.
   Test Hermes on a **separate staging Slack app**, and only move the
   production tokens at cutover.
3. **Torrent verbs stay open to the whole workspace** unless narrowed.
   picoclaw had no per-user tool scoping; check whether Hermes' Slack allowlist
   or MCP `tools.include` lets you do better (e.g. DM-only). Transmission RPC
   is still `admin:admin` on the NAS — fix that regardless.
4. **The model is the usual cause of "bot is down".** NIM keeps EOLing models;
   `openrouter/free` is slow. Pick a primary plus a *different-vendor*
   fallback, and test the chain with the primary deliberately broken.
   The GIF proxy is only needed for NIM; drop it if NIM is not used.
5. **Storage.** Root is the 8 GB USB stick (7 GB usable). Hermes + venv is
   ~1–2 GB. Fine to start; move to eMMC later (after the eMMC backup).
6. **RAM.** 1.8 GB vs the Pi's 991 MB — more headroom, but set a systemd
   `MemoryMax` (e.g. 1G) so a runaway page fetch can't take the box down.

## Phases

Each phase is independently reversible. picoclaw keeps running until phase 5.

### 0 — Prepare the box
- [ ] Back up the Android eMMC (`mmcblk2`) — see [README](README.md)
- [ ] DHCP reservation `192.168.2.20` ↔ `06:42:00:80:93:c1`
- [ ] Restrict `unattended-upgrades` to `Debian-Security` (Armbian's default
      also auto-upgrades all of stable + the Armbian repo)
- [ ] `useradd -m -s /bin/bash hermes` (no sudo); Hermes lives in its home

### 1 — Install Hermes and prove the model
- [ ] Install Hermes as `hermes` (uv + Python 3.13 from trixie), `hermes doctor`
- [ ] Put provider keys in `~/.hermes/.env` (mode 600); choose model (decision A)
- [ ] `timezone: Asia/Ho_Chi_Minh`
- [ ] `hermes chat -q "Reply OK and your model name"`; then a tool call
      (`web search today's VnExpress headlines`) to prove tool convergence

### 2 — Identity, tools, lockdown (still no Slack)
- [ ] Port AGENT.md/SOUL.md/USER.md into Hermes' SOUL.md, including the
      **Slack mrkdwn rules** (`*bold*`, `<url|label>`) — Slack renders
      `**bold**` literally
- [ ] Turn `/root/digest_prompt.txt` into a Hermes skill (`ban-tin-sang`)
- [ ] Tavily search configured; test a Vietnamese query (DuckDuckGo returned
      nothing for Vietnamese news on the Pi)
- [ ] Copy `transmission_mcp.py` + `transmission.env` (600) → register under
      `mcp_servers`; `hermes mcp test transmission` expects 6 tools
- [ ] **Lock down Slack toolsets (risk 1)** before phase 3

### 3 — Slack shadow (staging app)
- [ ] Create `hermes-staging` app from Hermes' generated manifest (includes
      `files:read`, Messages Tab, `assistant:write`)
- [ ] Private test channel; verify: mention → thread reply, DM, image +
      question (vision), `@bot run id` → refused, torrent_list works
- [ ] systemd unit for `hermes gateway` as user `hermes`, `Restart=always`,
      `MemoryMax=1G`; survives a reboot

### 4 — Digest shadow (3–5 days)
- [ ] `hermes cron create "30 8 * * *" … --skill ban-tin-sang --deliver slack:<test-channel>`
- [ ] Each morning compare with picoclaw's `#daily` post: fired at 08:30 +07,
      all 4 sections, sources, mrkdwn renders, Vietnamese section not empty
- [ ] Check logs for "Delivery UNVERIFIED" — a fired job is not a delivered post

### 5 — Cutover
- [ ] Disable picoclaw's `ban-tin-sang`, then `systemctl disable --now picoclaw nim-gif-filter`
- [ ] Either move `openclaw_devbot`'s tokens into Hermes' `.env` (same bot
      identity, no re-invites) or keep the new app and invite it to `#daily`
      (decision B)
- [ ] Recreate the cron with `--deliver slack:C0BPXMNJ9PU`; delete the staging job
- [ ] Watch the first live 08:30 fire in the journal *and* in the channel

### 6 — Decommission the Orange Pi (after ~2 weeks clean)
- [ ] Image its SD card to the Mac, archive `~/.picoclaw` (contains secrets —
      store encrypted)
- [ ] Power off; update [orangepi/README.md](../orangepi/README.md) to say it is retired

**Rollback at any point before 6:** stop Hermes' gateway, `systemctl enable
--now nim-gif-filter picoclaw` on the Pi, re-enable `ban-tin-sang`. If the
production tokens were moved, just stop Hermes — picoclaw reconnects with the
same tokens.

## Decisions needed from you

- **A. Model** — `google/gemma-4-31b-it` on the existing NVIDIA key (3 s,
  tool calls verified on the Pi, but NIM EOL risk) vs `openrouter/free`
  (free, ~1–2 min/turn) vs a paid model. Recommendation: gemma primary,
  OpenRouter fallback.
- **B. Bot identity** — reuse `openclaw_devbot` (seamless) or a new
  "Hermes" app (clean break, re-invite to channels).
- **C. Who may use it** — whole workspace (today) or an allowlist.
- **D. Torrent tools** — keep for everyone, DM-only, or drop.
- **E. Digest content** — keep the same 4 sections, or revise while porting.
