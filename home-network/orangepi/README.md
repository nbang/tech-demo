# PicoClaw on Orange Pi — NVIDIA NIM + Slack daily news

Runbook for the agent running on `root@192.168.2.180`.

## The board

Probed, not assumed:

| | |
|---|---|
| Host | `orangepipc` — Orange Pi PC, Allwinner sunxi |
| Arch | **ARMv7 32-bit** (`armv7l`, kernel 6.18.29-current-sunxi) — *not* arm64 |
| CPU / RAM | 4 cores / 991 MB |
| Disk | 30 GB, 10% used |
| OS | Armbian community 26.2.0 (Debian trixie) |
| Timezone | `Asia/Ho_Chi_Minh` (was `Etc/UTC`; changed so cron expressions mean local time) |
| Egress | `integrate.api.nvidia.com` 200, `slack.com` 200 |

The 32-bit userland is the one detail that bites: the release asset is
`picoclaw_Linux_armv7.tar.gz`. The arm64 build will not run here.

## What is already done

- picoclaw upgraded **0.2.8 → 0.3.1**. Old binary kept at
  `/usr/local/bin/picoclaw.0.2.8.bak`.
- `picoclaw onboard` run — `/root/.picoclaw/{config.json,.security.yml,workspace}` exist.
- `config.json` patched by [patch_config.py](patch_config.py) (backup at
  `config.json.pre-nim.bak`).
- `picoclaw.service` installed to `/etc/systemd/system/`, validated with
  `systemd-analyze verify`. **Deliberately not enabled or started** — it would
  crash-loop until the tokens are in place.

- NVIDIA key and Slack tokens installed in `.security.yml`; gateway enabled and
  running; Slack connected over Socket Mode as `openclaw_devbot`
  (`U0AF54ZCGTS`) in team `8-group` (`T176QB33R`).

## What is still needed

1. **Invite the bot to the target channel** — `/invite @openclaw_devbot`.
   It cannot post to a channel it has not joined.
2. **Digest topics and time** — what the daily post should cover, and when
3. **Possibly widen the Slack scopes** — see below

## Slack token schema — the one real trap

Channel tokens belong at `channel_list.<name>.settings.*` in `.security.yml`.
Two documented alternatives are both wrong for v0.3.1:

| Where | Source | Result |
|---|---|---|
| `channel_list.slack.settings.bot_token` | what `onboard` generates | ✅ works |
| `channels.slack.bot_token` | `docs/security/security_configuration.md` | ❌ silently ignored |
| `channel_list.slack.bot_token` (inline in config.json) | `docs/channels/slack/README.md` | ❌ hard-fails on load |

The first wrong form is the dangerous one: the gateway logs `No channels enabled`
/ `enabled_channels=0` and raises **no error**, because `manager.go` treats an
empty `BotToken` as "not ready" and skips the channel. Treat `onboard`'s generated
files as the schema source of truth; the prose docs lag the binary.

There is also an env-var escape hatch if the file mapping ever misbehaves:
`PICOCLAW_CHANNELS_SLACK_BOT_TOKEN` / `PICOCLAW_CHANNELS_SLACK_APP_TOKEN`.

## Slack scopes actually granted

The installed app carries only:

```
app_mentions:read, channels:history, chat:write
```

That is enough to post the digest into a public channel it has been invited to
and to answer `@`-mentions there. It is *not* enough for:

- `channels:read` — the bot cannot list or inspect channels
  (`users.conversations` and `conversations.info` both return `missing_scope`)
- `im:history` / `im:write` — **DMs to the bot will not work**
- `groups:*` — private channels will not work
- `users:read` — cannot resolve user IDs to names in summaries

To widen: api.slack.com/apps → your app → **OAuth & Permissions** → add scopes →
**reinstall to workspace** (scope changes need a reinstall) → the `xoxb-` token
changes, so update `.security.yml` and restart the service.

### Scopes are not enough for DMs — the Messages tab (2026-08-23)

Adding `im:history` / `im:read` / `im:write` and the `message.im` event
subscription still left the DM composer disabled:

```
Sending messages to this app has been turned off.
```

That string is **not** a permissions error, and no amount of reinstalling fixes
it. Slack defaults the App Home Messages tab to *read-only* when the manifest
carries no `features.app_home` block — which the original manifest did not.

Fix: api.slack.com/apps → your app → **App Home** → Show Tabs → **Messages
Tab** on → check **"Allow users to send Slash commands and messages from the
messages tab"**. Then **reload the Slack client** (⌘R); the disabled composer is
cached client-side and keeps showing the old banner otherwise.

`slack-app-manifest.yml` now pins the block so a fresh install lands writable:

```yaml
features:
  app_home:
    home_tab_enabled: false
    messages_tab_enabled: true
    messages_tab_read_only_enabled: false
```

Worth remembering *why* this hid so well: the 08:30 digest kept working
throughout. It is an outbound `chat:write` publish and never touches the inbound
Socket Mode path, so a healthy digest says nothing about whether DMs are
deliverable.

The gateway also warns `Channel allows EVERYONE (allow_from is empty)`. That is
intended here — the whole team should be able to talk to it. Set `allow_from`
to `["*"]` to acknowledge it explicitly and silence the warning.

## Config decisions

`config.json` (`version: 3`) holds no secrets; everything sensitive lives in
`.security.yml`, which picoclaw merges by field name.

```json
{
  "model_name": "nim-primary",
  "provider": "nvidia",
  "model": "meta/muse-glimmer-30b",
  "api_base": "https://integrate.api.nvidia.com/v1",
  "enabled": true,
  "request_timeout": 120
}
```

Verified on 2026-08-13 against the account's actual entitlements (102 models on
this key), not just assumed from the docs:

```bash
curl -s https://integrate.api.nvidia.com/v1/models \
  -H "Authorization: Bearer $NVIDIA_API_KEY" | jq -r '.data[].id' | sort
```

`meta/muse-glimmer-30b` emits well-formed parallel `tool_calls`, which is the
property that actually matters here — a digest is useless without `web_search`.
End-to-end on the board it searched, fetched and answered in ~56s.

One observation worth keeping: that run took 14 agent iterations for a single
headline. The model explores rather than converging fast, so keep the digest
prompt tight and specific about how many items you want.

Other settings that matter:

- `channel_list.slack.enabled: true`, `allow_from: ["*"]` (whole team may talk to
  it; `["*"]` over `[]` so the startup EVERYONE warning stays silenced)
- `tools.web.duckduckgo.enabled: true` — search with no extra API key. The
  `web_search` tool takes `range: "d"`, which is what makes "today's news" work.
- `tools.web.format: "markdown"` — far cleaner input to the model than plaintext
- `request_timeout: 120` — a 4-core ARMv7 board is slow to stream long completions

### Hardening — read this before widening anything

picoclaw ships `tools.exec.allow_remote: true` and `tools.cron.allow_command: true`.
In a shared Slack channel that means **any teammate could get shell on the board**
by asking the agent nicely. Both are turned off, and `command_allowed_remotes` is
pinned to `[]`:

```json
"exec": { "allow_remote": false },
"cron": { "allow_command": false, "command_allowed_remotes": [] }
```

The daily digest needs neither. Only relax this if you decide you want remote
shell, and if you do, scope `command_allowed_remotes` to one exact
`slack:<channel_id>` rather than `*`.

The unit also sets `MemoryMax=300M` so a runaway page fetch cannot OOM a 991 MB board.

## Bring-up

```bash
# 1. secrets
cp security.yml.example security.yml.filled     # fill in the three tokens
scp security.yml.filled root@192.168.2.180:/root/.picoclaw/.security.yml
ssh root@192.168.2.180 'chmod 600 /root/.picoclaw/.security.yml'
rm security.yml.filled

# 2. prove the model works before involving Slack
ssh root@192.168.2.180 'picoclaw --no-color agent -m "Reply with OK and your model name."'

# 3. start the gateway
ssh root@192.168.2.180 'systemctl enable --now picoclaw && systemctl status picoclaw --no-pager'
ssh root@192.168.2.180 'journalctl -u picoclaw -f'
```

Then say hello to the bot in Slack. If it answers, the Socket Mode connection is live.

## The daily digest cron

Schedule it **from inside the target Slack channel**, not over SSH. picoclaw binds
a job's delivery target to `payload.channel` / `payload.to` of the conversation that
created it; a job created on the CLI has no Slack target and the digest goes nowhere.

Message the bot in the channel, roughly:

> Create a cron job named "daily-news". Every day at 08:30, search the web for the
> last 24 hours of news on `<TOPICS>`, then post a digest to this channel: 5–7
> items, one line each, with a link, newest first. Skip anything older than a day.

Verify and manage:

```bash
ssh root@192.168.2.180 'picoclaw --no-color cron list'
ssh root@192.168.2.180 'cat /root/.picoclaw/workspace/cron/jobs.json | jq'
```

Note `deliver: false` is what you want — the job runs a full agent turn (search,
fetch, summarize) and posts the result. `deliver: true` would post the prompt text
verbatim without thinking about it.

To reschedule, have the agent do `list -> get -> update`. Never `remove -> add`:
recreating a job drops its saved delivery target.

### Cron expressions are LOCAL time — do not let the agent "convert to UTC"

The scheduler evaluates against the process timezone (`Asia/Ho_Chi_Minh`), not UTC.
This is the trap that silently killed the digest on 2026-08-20:

```
Aug 20 08:41:38  Tool call: cron({"action":"update","cron_expr":"30 1 * * 1-5",...})
```

Asked in Slack why the 08:30 post had not arrived, the agent diagnosed a timezone
bug that did not exist, rewrote `30 8` as `30 1` "= 01:30 UTC", and reported success.
It fired the next morning at **01:30 +07**. Measured both ways:

| expr | observed fire |
|---|---|
| `30 8 * * 1-5` | 08:30:00 **+07** |
| `30 1 * * 1-5` | 01:30:00 **+07** |

So write the wall-clock time you actually want. If you edit `jobs.json` by hand,
also delete `state.nextRunAtMs` — it is a cached absolute epoch and the new
expression will not take effect until it is recomputed.

Nothing in `cron list` reveals the mistake: it prints the expression and a
`Next run` with no timezone, so a wrong-by-seven-hours job looks perfectly healthy.

## The digest job — as built

Job `ban-tin-sang` (`bab2ac6db0dd86da`), cron `30 8 * * *` (daily; was `30 8 * * 1-5`
until 2026-08-22), delivering to
`slack` / `C0BPXMNJ9PU` (`#daily`). Prompt source: `/root/digest_prompt.txt`,
modelled on `ban-tin-sang-2026-08-12.md` — four sections, bold lead sentence,
concrete numbers, sourced link per item.

**Slack needs mrkdwn, not markdown.** `slack.go` hands the agent's text straight
to `PostMessageContext` with no conversion, so the prompt must demand Slack's own
syntax: `*bold*` (single asterisk) and `<url|label>` links. Standard
`**bold**` / `[label](url)` would render as literal punctuation.

**The CLI cannot set a delivery target.** `picoclaw cron add` writes a payload
with no `channel`/`to`, so the job would run and post nowhere. Either create the
job by talking to the bot in the destination channel, or patch
`workspace/cron/jobs.json` directly (stop the service first — it rewrites that
file):

```json
"payload": { "kind": "agent_turn", "channel": "slack", "to": "C0BPXMNJ9PU" }
```

### Dry-run result, 2026-08-13 — works, but the sourcing is weak

4433 chars in ~2.5 min over 20 iterations. Formatting was correct. Content was
not up to the reference standard:

- **`Việt Nam` came back empty** (`_không có tin nổi bật_`). The Vietnamese-language
  searches returned ~85 bytes — essentially nothing. DuckDuckGo is poor at
  Vietnamese news, and this is the section most likely to matter to the team.
- **`Kỹ thuật phần mềm` had 2 items**, both actually AI-business stories, and both
  from the same aggregator. No CVEs, no releases — the reference had four.
- **Source quality dropped** to aggregators (`techbytes.app`, `note.com`) where the
  reference used Reuters/TechCrunch/Al Jazeera tier.
- One English fragment leaked into the Vietnamese text ("whichever is higher").

The mechanism is sound; the search backend is the bottleneck. To fix, enable a
stronger provider under `tools.web` — **Tavily** (free tier, good recall) or
**Brave** — and set `provider` accordingly. Both take a key in `.security.yml`
under `web.<name>.api_keys`. Adding explicit Vietnamese sources (VnExpress,
CafeF, Báo Chính phủ) for the agent to `web_fetch` directly would also help more
than any prompt tweak.

## Images from Slack — two bugs, and why the trigger is `!bot`

Sending the bot an image does nothing unless **both** of these are handled.

### 1. `files:read` scope (Slack side)

Slack attachments live behind `url_private`. Without `files:read` the download
returns **HTTP 200 with a ~61 KB HTML sign-in page** — not a 401 — so picoclaw
stores HTML, attaches no media, and logs nothing. `media_count=0` on every turn is
the tell. Add `files:read`, then **reinstall** the app (scope changes require it).

### 2. picoclaw drops attachments on the mention path

Two handlers, and only one of them works with files:

| Handler | Sees mentions | Downloads files |
|---|---|---|
| `handleMessageEvent` (line 313) | **no** — line 357 calls `ShouldRespondInGroup(false, …)` with `isMentioned` hard-coded `false`, and line 353 strips `<@BOTID>` *before* the check | **yes** (line 383) |
| `handleAppMention` (line 436) | yes | **no** — line 507 passes `nil` for media and never reads `ev.Files` |

So `mention_only: true` makes images impossible: tag the bot and the file is
discarded; don't tag it and the message is dropped. Not caused by `mention_only`,
but closed off by it.

**Workaround: use `prefixes` instead of `mention_only`.**

```json
"group_trigger": { "mention_only": false, "prefixes": ["!bot"] }
```

`prefixes` are evaluated inside `handleMessageEvent` — the file-downloading path.
Net behaviour:

- plain chatter → still ignored (prefixes set, no match)
- `@bot question` → still answered, text only, via `handleAppMention`
- `!bot what is this?` + image → **works**, because it routes through the message path

A prefix works where a mention cannot, because line 353 strips the mention from
the text before matching, so `"<@U0AF54ZCGTS>"` as a prefix would never fire.

Size is not a constraint: a 2.2 MB PNG (2.9 MB request) is accepted by NIM and
answered correctly. PNG/JPEG/WEBP all pass the GIF filter untouched.

### Verified working 2026-08-13 16:55

`!bot đây là hình ở đâu?` + `image.png` (3 MB) → `media_count=1` →
`load_image(/tmp/picoclaw_media/…)` → correct answer in 10 s, reading the signage
*inside* the photo (event name and dates). Genuine vision, not inference from
filename or context.

Note this depends on `tools.load_image.enabled` being **true** — the agent calls
`load_image` on the downloaded path. That is picoclaw's default; the earlier
attempt to disable it would have broken Slack image input as a side effect.

## Slack formatting applies to chat too, not just the digest

picoclaw sends raw text to `PostMessageContext` with no markdown conversion, so
`**bold**` renders literally in Slack. The digest prompt covers the cron job only;
ad-hoc replies needed the same rule, so the mrkdwn conventions were added as a
`## Slack formatting` section in `workspace/AGENT.md` (backup: `AGENT.md.bak`).
That file is part of the agent identity and applies to every reply.

## Superseded: mention-only replies

By default picoclaw answers **every** message in a channel. `base.go` is explicit
about it: *"No group_trigger configured → respond to all (permissive default)"* —
and `onboard` generates `"group_trigger": {}`, so the default applies.

```json
"channel_list": { "slack": { "group_trigger": { "mention_only": true } } }
```

`ShouldRespondInGroup` checks `isMentioned` first and returns early, so mentions
always get through; everything else is dropped. Set on 2026-08-13, then **replaced
the same day** by the `prefixes` form above once it turned out `mention_only`
makes image input impossible. Kept here because the reasoning still applies if you
never need images.

This affects **inbound replies only**. The scheduled digest is an outbound publish
and is unaffected — it still posts at 08:30 without anyone mentioning the bot.

`group_trigger` also accepts `prefixes` (e.g. `["!bot "]`) as an alternative
trigger. Mentions still work when prefixes are set.

## Root cause: HTTP 415 killed every scheduled run

The first two live fires died with `Status: 415 {"message":"Unsupported Media Type"}`
and posted nothing, while the identical prompt worked from the CLI. Two plausible
theories were both **disproved** by measurement before the real one was found:

- *Payload size* — a raw size sweep against the endpoint returned 200 at 417 KB;
  oversize fails as `400 VLLMValidationError: maximum context length`, never 415.
  The failing request was only 58 KB.
- *Multimodal content in general* — a hand-built request with a text+`image_url`
  content array returned 200.

Capturing the exact request through a logging proxy (`api_base` pointed at a local
forwarder) showed the real culprit as message 23 of the failing call:

```json
{"role":"user","content":[
  {"type":"text","text":"[Loaded image from tool result above]"},
  {"type":"image_url","image_url":{"url":"data:image/gif;base64,R0lGODlhAQABAAAA..."}}]}
```

`R0lGODlhAQABAAAA…` is a **1×1 transparent GIF tracking pixel**. Confirmed against
the endpoint directly, same model, same key:

| Content | Result |
|---|---|
| `data:image/png;base64,…` | 200 |
| `data:image/gif;base64,…` | **415 Unsupported Media Type** |

The scope is narrow: **only GIF**. Tested against the endpoint with realistic
512px images, same model and key:

| Format | Result | Model's answer to "what colour is the background?" |
|---|---|---|
| PNG | 200 | `red` / `green` — correct, discriminates |
| JPEG | 200 | `red` — correct |
| WEBP | 200 | `red` — correct |
| **GIF** | **415** | never reaches inference |

So `meta/muse-glimmer-30b` **is vision-capable** and NVIDIA accepts every common
format except GIF.

> A wrong turn worth recording: an earlier test used a 24×24 solid-colour swatch,
> the model guessed, and that was misread as "the model is blind". A degenerate
> input is not a capability test — use a realistic image with a subject before
> concluding anything about vision.
>
> `tools.load_image.enabled: false` was also briefly believed to be the fix. It is
> not: runs at 15:39 and 15:46 still emitted `[Loaded image from tool result above]`
> with the setting verified `false`. The one run that succeeded under it simply
> never hit a GIF.

The failure chain:

1. picoclaw's `web_fetch` scrapes images out of the fetched page
2. it injects them into the next request as `image_url` parts
3. news pages are full of 1×1 GIF tracking pixels
4. NVIDIA 415s the whole request; the turn dies with `final_len=0`

**Fix: [nim-gif-filter.py](nim-gif-filter.py)** — a stdlib-only local proxy
(`nim-gif-filter.service`, enabled at boot, `Before=picoclaw.service`) that strips
`data:image/gif` parts and drops messages left carrying nothing but the
`[Loaded image from tool result above]` placeholder. Everything else passes
through untouched, so PNG/JPEG/WEBP vision still works — verified after install:
a green PNG through the proxy still returns `green`.

`model_list[0].api_base` points at `http://127.0.0.1:8899/v1`. The filter fails
open: an unparseable body is forwarded unmodified, so it can never itself be the
reason a request dies. It logs counts only — never bodies or the `Authorization`
header.

Beware `jobs.json` `lastStatus: "ok"` — it means "job dispatched", not "delivered".
It read `ok` on every run that posted nothing. Trust `Published outbound response`
in the journal, or query the channel, instead.

### Verified working 2026-08-13 16:31

Scheduled fire → 9 iterations → `Published outbound response ... content_len=5962`
→ 3885 chars live in `#daily`. Zero upstream 415s; filter logged
`stripped 1 GIF part(s), dropped 1 empty message(s)` twice.

## Second cause of silent mornings: `request_timeout: 120`

The GIF filter fixed the 415s, but four of the next six scheduled runs still ended
`final_len=0` and posted nothing:

| Date | Result |
|---|---|
| Aug 14 08:30 | ✅ 5773 chars |
| Aug 17 08:30 | ❌ `final_len=0` after 1064 s |
| Aug 18 08:30 | ✅ 5944 chars |
| Aug 19 08:30 | ❌ died on iteration **1** |
| Aug 20 08:30 | ❌ `final_len=0` after 1085 s |
| Aug 21 01:30 | ❌ `final_len=0` after 1108 s |

Not GIFs this time — the client-side deadline:

```
agent.llm.retry error="Post \"http://127.0.0.1:8899/v1/chat/completions\":
  context deadline exceeded (Client.Timeout exceeded while awaiting headers)"
  attempt=1 → attempt=2 → agent.error → turn.end final_len=0
```

Aug 19 logged 34 of these, Aug 20 16, Aug 17 14. The proxy confirms from its own
side with `upstream error: The read operation timed out` and `client disconnected
before response was written`. Once the digest conversation reaches ~29 messages
with `max_tokens=32768`, a single completion exceeds 120 s, all attempts blow, and
the turn dies before publishing.

**Fix (2026-08-22): `model_list[0].request_timeout` 120 → 300.** Backup at
`config.json.pre-timeout-fix.bak`. The proxy's own upstream read timeout is also
300 s (`nim-gif-filter.py:101`) — if you raise the client past 300 s, raise the
proxy first, so the proxy stays the outer bound and returns a real error instead
of racing the client.

Retries live somewhere non-obvious — **`agents.defaults`**, not the model entry:

```json
"agents": { "defaults": { "max_llm_retries": 3, "llm_retry_backoff_secs": 2 } }
```

Raised 2 → 3 on 2026-08-22 (backup `config.json.pre-retries-fix.bak`). Note the
budget this buys is small: backoff is linear from a 2 s base, so three attempts
span only ~15 s of waiting. That is ample for a transient blip and useless against
a rate-limit window measured in minutes — see the MiniMax note below.

Note the two failure modes look identical from `jobs.json` (`lastStatus: "ok"`
either way). Distinguish them in the journal: 415 → `Status: 415` from the
endpoint; timeout → `Client.Timeout exceeded while awaiting headers`.

## Current model: moonshotai/kimi-k3 (switched 2026-08-28)

`nim-primary` = `moonshotai/kimi-k3`. Backup: `config.json.pre-kimi.bak`.
Verified the same day via `picoclaw agent -m "Reply with exactly: KIMI_OK"` →
correct reply in 13.2 s with all 22 tools presented and correct direct-answer
convergence (no spurious tool calls).

### Timeouts are per-model, and they are NOT uniform

`request_timeout` lives on each `model_list` entry, so entries drift apart
silently. Do not assume one value governs the board — read all of them:

```bash
python3 -c 'import json;c=json.load(open("/root/.picoclaw/config.json"));
[print(m["model_name"], m.get("request_timeout")) for m in c["model_list"]
 if m.get("provider")=="nvidia"]'
```

State as of 2026-08-28: `nim-primary` **300s** (raised by an earlier timeout fix,
`config.json.pre-timeout-fix.bak`), `nim-fallback` and `laguna-eval` **180s**
(raised from 120s the same day). Backup: `config.json.pre-timeout180.bak`.

**Retries multiply the timeout — this is the part that bites.** With
`agents.defaults.max_llm_retries: 3` and `llm_retry_backoff_secs: 2`, the worst
case for a *single* LLM call is roughly `4 × request_timeout + backoff`:

| Model | timeout | worst case per call |
|---|---|---|
| `nim-primary` | 300s | ~20 min |
| `nim-fallback` | 180s | ~12 min |

A digest turn makes 2+ LLM calls, so raising `request_timeout` raises the ceiling
on how long a Slack user stares at nothing. If bounded waits matter more than
surviving a slow model, lower `max_llm_retries` rather than trimming the timeout —
retries are what turn one slow call into a multi-minute stall. Note the historical
"5–18 minute digest turns" in this README came from exactly this multiplication,
not from a single slow response.

`agents.defaults.subturn.default_timeout_minutes` is `0` (no cap) and
`tools.cron.exec_timeout_minutes: 5` applies to *command* cron jobs, which are
disabled here (`allow_command: false`) — the scheduled digest is a prompt job, so
neither bounds the turn. Unverified whether any prompt-job cap exists at all.

### NVIDIA EOLs models out from under this board

This is the **most common cause of a "bot is down" report, and it never actually
takes the service down.** systemd stays `active (running)`, Slack stays connected,
MCP stays healthy — and the bot *replies*, with the upstream API error as its
message text. Two occurrences so far:

| Model | Killed by | Date |
|---|---|---|
| `deepseek-v4-flash` / `-pro` | `410 Gone` | 2026-08-07 |
| `stepfun-ai/step-3.7-flash` | `410 Gone` — "reached its end of life" | 2026-08-28 |

Triage command, before touching anything else:

```bash
journalctl -u picoclaw --no-pager -n 40 | grep -E "LLM call failed|Status: [0-9]+"
```

A `410` means pick a new model id and restart; nothing on the board is broken.

### `nim-fallback` = deepseek-ai/deepseek-v4-pro-0813 (fixed 2026-08-28)

`nim-fallback` is now `deepseek-ai/deepseek-v4-pro-0813`, replacing
`meta/muse-glimmer-30b`. Backups: `config.json.pre-dsfallback.bak`,
`.security.yml.pre-dsfallback.bak`.

**It had never worked before this.** `picoclaw agent --model nim-fallback`
returned **`401 Header of type authorization was missing`**, because
`.security.yml` carried an empty `nim-fallback:0: {}` while only `nim-primary:0`
had an `api_keys` list. A fallback without a credential cannot rescue anything.
Note the `:0` index suffix on those keys — that is the shape `picoclaw onboard`
generates, and the entry must be `nim-fallback:0`, not `nim-fallback`.

It also never engaged: the step-3.7-flash EOL surfaced as
`fallback: unclassified error from nvidia/stepfun-ai/step-3.7-flash ... Status: 410`
— the wrapper classified a *permanent* 410 as "unclassified" and did not fail
over. So the fallback chain has never once been exercised successfully on this
board; treat it as unproven in production until an outage actually proves it.

**`api_base` matters here too.** Like every NIM entry on this box it must point at
`http://127.0.0.1:8899/v1`, not `integrate.api.nvidia.com` — otherwise it bypasses
the GIF filter and reintroduces the `415` from [[nvidia-nim-gif-415]].

**Watch the latency.** Verified working (`Response: OK`) but it took **59 s on a
two-word prompt**, against kimi-k3's 13.2 s. With `request_timeout: 120`, a real
digest prompt could plausibly exceed the timeout — so the fallback may time out
precisely when it is finally needed. Earlier NIM DeepSeek V4 snapshots were worse:
`-pro`/`-flash` were 410'd on 2026-08-07 and the `-0731` snapshot hung outright.
`-0813` is the first one that responds.

**Residual risk:** now that the fallback is keyed and reachable for the first
time, the cooldown bug in [[picoclaw-model-fallbacks-broken]] becomes live rather
than theoretical. Watch for `all N candidates failed ... skipped (cooldown)` on
every turn while both models test fine individually; the fix remains deleting
`agents.defaults.model_fallbacks`.

### Superseded: stepfun-ai/step-3.7-flash (2026-08-22 → 2026-08-28)

Killed by the 410 above. Retained below because the convergence analysis is what
governs model choice on this board — muse-glimmer's failure to converge is the
reason a fallback to it would be undesirable even if it were keyed.

It is a **native vision-language model** — 196B language backbone + 1.8B vision
encoder at 728×728, ~11B active per token, 256K context — and NVIDIA scopes it at
"multimodal understanding, agentic workflows, tool calling, GUI-oriented tasks
using text and screenshots". Both workloads here (digest tool loop, Slack images)
are design targets rather than side effects.

Measured against muse-glimmer on this key:

| | step-3.7-flash | muse-glimmer-30b |
|---|---|---|
| warm latency, trivial prompt | 11.4 s median | 1.4–3.3 s |
| parallel tool calls | ✅ 2, correct `range:"d"` | ✅ 2 |
| query strategy | English for world/AI, **Vietnamese** for VN | both Vietnamese |
| **given tool results** | ✅ `finish=stop`, **converged** | ❌ `finish=tool_calls`, `len=0` |
| Slack mrkdwn, unprompted | ✅ correct | not reached |
| vision (colour discrimination) | ✅ red/green/stripe-position all correct | ✅ |
| rate limit @ 1 call / 8 s | **8/8, zero 429** | 10/10, zero 429 |

It is ~4× slower per call but converges in **1–2 iterations** where muse-glimmer
took 14–50. On a live CLI run it searched and produced correct mrkdwn in one
iteration:

```
• *LG công bố công nghệ OLED mới ...* <https://www.engadget.com|Engadget>
```

Three things to know:

- **The GIF proxy is still mandatory.** step-3.7-flash returns the same
  `415 Unsupported Media Type` on `data:image/gif` that muse-glimmer did. Keep
  `api_base` on `http://127.0.0.1:8899/v1` for *both* entries.
- **It is a reasoning model and spends ~110 tokens thinking before answering.**
  Cap `max_tokens` too low and `content` comes back empty while
  `reasoning_content` is populated — a 64-token cap made it look blind when it was
  not. `agents.defaults.max_tokens` is 32768, so this only bites synthetic tests.
- **`load_image` cannot be tested from the CLI** — `picoclaw agent` has no media
  store (`Tool execution failed error="media store not configured"`). Only the
  Slack path exercises vision. The model degraded gracefully there, reporting the
  error in 2 iterations rather than looping.

`model_fallbacks` is configured **despite** the defect documented below, on the
explicit call that failover is worth the risk. Watch for it: the symptom is
`fallback: all 2 candidates failed ... skipped (cooldown)` on *every* turn, with
both models healthy on a direct curl. If that appears, delete
`agents.defaults.model_fallbacks` and restart — that is the whole fix.

## MiniMax M3 + model_fallbacks — attempted 2026-08-22, reverted

`minimaxai/minimax-m3` is entitled on this key and is the **better digest model on
merit**. Handed tool results it converges immediately, where muse-glimmer does not:

| | minimax-m3 | muse-glimmer-30b |
|---|---|---|
| trivial prompt | 0.8 s, returns `OK` | 3.3 s, returns *nothing* (spends the budget on hidden reasoning) |
| parallel tool calls | ✅ 2, correct `range:"d"` | ✅ 2 |
| given tool results | **`finish=stop`, 8.2 s, writes the digest** | `finish=tool_calls`, `len=0`, calls more tools |
| Slack mrkdwn | ✅ correct unprompted | not reached |

That second-to-last row is the whole ballgame — it is the same non-convergence that
drives 5–18 minute turns, the 300 s timeouts, and the 48× identical `cron get` loop.

**It was still reverted, for two reasons.**

*1. A much tighter rate limit than muse-glimmer, on the same key.* Measured:

| test | minimax-m3 | muse-glimmer-30b |
|---|---|---|
| 12 calls, unpaced | ok=4, **429=8** | — |
| 1 call / 8 s, ×10 | ok=7, 429=3 | **ok=10, 429=0** |
| recovery after saturation | ~17 s | n/a |

So the throttling is model-specific, not the key. A short burst budget refills in
~17 s, but sustained use hits a longer window: after a day of probing, minimax
returned 429 to *every* request for over an hour while muse-glimmer stayed 200.

*2. `model_fallbacks` poisons the whole chain.* The intent was minimax primary,
muse-glimmer fallback, so a 429 could not kill a turn. Two traps:

- **The key does not live on the model entry.** `model_list[0].model_fallbacks` is
  rejected — `unknown field(s)` — and because the unit is `Restart=always`, the
  gateway crash-loops instead of failing once. It belongs on `agents.defaults`.
- **A healthy fallback still gets benched.** Failover fires correctly the first
  time (`minimax → 429 ×3 → meta/muse-glimmer-30b`), but afterwards:

```
LLM call failed: fallback: all 2 candidates failed:
  [1] nvidia/minimaxai/minimax-m3:  skipped (cooldown)
  [2] nvidia/meta/muse-glimmer-30b: skipped (cooldown)
```

  muse-glimmer answered **HTTP 200 in 1.4 s** on a direct curl at that same moment.
  The cooldown did not clear in 4.5 minutes of polling, and **survived a service
  restart**. The agent was completely dead until the fallback config was removed.
  Compare upstream [#2334](https://github.com/sipeed/picoclaw/issues/2334)
  ("model fallbacks don't work") and
  [#2140](https://github.com/sipeed/picoclaw/issues/2140).

**Do not configure `model_fallbacks` on 0.3.1.** One model with no fallback is
strictly safer than a chain that can bench a healthy candidate. The attempted
config is kept at `config.json.minimax-attempt.bak` if a later release fixes this.

Also still unverified: **minimax vision**. Every probe (PNG colour discrimination,
stripe location, GIF) was rate-limited out, so whether `!bot` + image survives the
switch is unknown. Do not switch without testing it — muse-glimmer's vision is
confirmed working (2026-08-22 08:58, `media_count=1` → `load_image` → published).

## DeepSeek V4 Flash — evaluated 2026-08-22, not usable

Investigated as a replacement for `meta/muse-glimmer-30b`. **Both V4 ids are
retired on `integrate.api.nvidia.com`:**

```
POST /v1/chat/completions  model=deepseek-ai/deepseek-v4-flash
HTTP 410 Gone — "reached its end of life on 2026-08-07T09:00:00Z"
```

`deepseek-ai/deepseek-v4-pro` returns the identical 410. The only V4 id still in
`/v1/models` on this key is the dated snapshot `deepseek-ai/deepseek-v4-flash-0731`,
and it **hangs** — no HTTP status line at all:

| Request | Result |
|---|---|
| `-0731` streaming, trivial prompt | 0 bytes in 100 s |
| `-0731` non-streaming | `HTTP=000` after **180 s** |
| `-0731` + documented `chat_template_kwargs.thinking` | `HTTP=000` after 90 s |
| `meta/muse-glimmer-30b`, same board/key/second | **1.4 s**, 6 SSE chunks |

Same board, same key, same minute — so this is not egress or entitlement. The id
is listed but no backend answers it. NVIDIA's own docs still document the
unsuffixed id and have not caught up with the 410, so do not trust the model page.

Two reasons not to chase it even if it returns: it is a 284B MoE **reasoning**
model, which makes the timeout problem above worse rather than better; and the one
published openclaw write-up for it reports that thinking mode produces provider
400s and **requests that stop after a tool call** — exactly what a 16-tool digest
turn does on every iteration.

> Knock-on: `.claude/skills/srt-translate-vi` still has
> `DEFAULT_MODEL = "deepseek-ai/deepseek-v4-flash"` (`scripts/translate_srt.py:37`).
> That skill is broken by the same 410 and needs a new default model.

## Transmission control from Slack — MCP server (added 2026-08-22)

Lets the bot answer "what's downloading?" and "add this magnet" for the
Chainedbox NAS at `192.168.2.14` (see [../omv-chainedbox/README.md](../omv-chainedbox/README.md)).

```
Slack DM → picoclaw agent (Orange Pi) → MCP stdio → Transmission RPC (192.168.2.14:9091)
```

### Why MCP and not `tools.exec`

The obvious route is flipping `exec.allow_remote: true`, and it is the wrong
one. That grants **arbitrary shell** to satisfy a five-verb need, and it undoes
the hardening above. MCP exposes a **fixed verb list** instead — `torrent_add`
takes a magnet URI and nothing else, so no Slack phrasing can become a shell
command. `exec.allow_remote` stays `false`.

### Files

| Path | Notes |
|---|---|
| `/root/.picoclaw/mcp/transmission_mcp.py` | the server, mode `700` |
| `/root/.picoclaw/mcp/transmission.env` | RPC credentials, mode `600` |

**Stdlib only** — no `mcp` SDK. armv7 wheel availability is unreliable, and MCP
over stdio is just newline-delimited JSON-RPC 2.0 (~350 lines). Same reasoning
that made the NAS `hev1`→`hvc1` byte patch better than installing ffmpeg there.

### Tools

`torrent_list` (status filter, 25-row cap) · `torrent_add` (magnet or http
.torrent) · `torrent_pause` / `torrent_resume` (ids or `all`) ·
`torrent_remove` · `disk_free`

Deliberately **not** exposed: anything that sets `download-dir` or
`script-torrent-done`. That last one runs a command as root on torrent
completion — the same RCE shape as qBittorrent's `autorun_program`, which is
why qBittorrent was removed from the NAS. It is currently `False`; keep it that
way.

`torrent_remove` defaults to `delete_data: false` and **refuses `ids: "all"`** —
the one destructive verb needs explicit ids.

### Registration

```bash
picoclaw mcp add --force --transport stdio \
  --env-file /root/.picoclaw/mcp/transmission.env \
  --no-deferred \
  transmission /usr/bin/python3 /root/.picoclaw/mcp/transmission_mcp.py

picoclaw mcp test transmission     # expect: reachable (6 tools)
picoclaw mcp show transmission     # lists the tools and their schemas
```

`--env-file` rather than `-e`: `mcp add` saves `-e` values into `config.json`,
which would put the RPC password in a world-readable file.

### Access control — this is the whole security model

**Current state (2026-08-28) — open sender list, mention-gated:**

```json
"channel_list": { "slack": {
  "allow_from": ["*"],
  "group_trigger": { "mention_only": true, "prefixes": ["!bot"] }
}}
```

`mention_only` was briefly set `false` on 2026-08-28 and reverted the same day by
preference. The documented consequence stands — with `mention_only: true`, tagging
the bot with an image silently discards the attachment, because `handleAppMention`
never reads `ev.Files` (see the handler table above). Use `!bot` for images.

`allow_from` is checked in `pkg/channels/base.go` **before** any `group_trigger`
logic, and a denial is **not logged at `info`**. That combination is the single
most confusing failure mode on this box: a non-allowlisted teammate `@`-mentions
the bot, everything about the mention is valid, and the gateway produces *no log
line whatsoever*. The only tell is that every `Processing message from slack:…`
entry carries the same `sender_id`.

`["*"]` is picoclaw's own wildcard form, not a literal member ID — the binary's
own hint string is `Set allow_from to your ID, or use '*' to explicitly
acknowledge open access.` Using `["*"]` rather than `[]` also silences the
startup `SECURITY: Channel allows EVERYONE` warning, so an empty list and an
acknowledged-open list are distinguishable at a glance in the log.

**Superseded: single-user lockdown.** From 2026-08-22 this was
`allow_from: ["U17599QLT"]` with `mention_only: true` — only that one member
could invoke the bot anywhere, which is what kept the torrent verbs private, and
it was the load-bearing control. Reverted on 2026-08-28 because it silently ate
every teammate's mention (see above) and the channel is meant to be a shared team
assistant. The reasoning still applies if the board is ever repurposed.

**The cost of reverting, stated plainly:** picoclaw has no per-user *or*
per-channel tool scoping — `mcp add` has no channel flag and `agents` only has a
`defaults` block, so "these tools only exist in a DM" and "only this user gets
the torrent verbs" are both inexpressible. With `allow_from: ["*"]` and
`transmission` registered non-deferred, **anyone in the workspace can drive the
torrent client in plain language.** What limits the blast radius is only
`torrent_remove`'s own defaults (`delete_data: false`, refuses `ids: "all"`).

If that becomes unacceptable, the options in increasing order of friction are:
re-register the MCP with `--deferred` (per-session activation), narrow
`allow_from` back to an explicit ID list, or write a `hooks` interceptor — noting
it is still unverified whether picoclaw exposes channel type to hooks.

### Two traps worth recording

**Transmission's 409 handshake.** Every RPC call must first take a
`409 Conflict` carrying `X-Transmission-Session-Id`, then retry with that
header echoed back. The id also rotates, so *any* later call can 409 — the
server refreshes and retries once. This is Transmission's analogue of the
qBittorrent Referer/origin trap.

**Echo the client's protocol version.** `initialize` must reply with the
version the client asked for, not a hardcoded one. picoclaw negotiated
`protocol=2025-11-25` while the server's own default constant is `2024-11-05`;
returning the constant risks a version mismatch.

### Verified 2026-08-22

```
picoclaw mcp test  → reachable (6 tools)
startup log        → MCP tools registered  unique_tools=6, connected=1
disk_free          → 790.0 GB free, Transmission 2.94 (rpc 15)
torrent_list       → 114 total: downloading 2, stopped 112
```

`MemoryCurrent` is ~7 MB against the unit's `MemoryMax=300M`, so the stdio child
process has ample headroom — no bump needed.

### Outstanding

**Transmission RPC is `admin:admin`** with `rpc-whitelist-enabled: false`, so
any LAN host can drive the torrent client, and `transmission-daemon` runs as
root. The credential now lives only in `transmission.env`, so nothing has to
retype it — make it strong. Requires a daemon stop, since Transmission
rewrites `settings.json` on exit.

### Rollback

```bash
ssh root@192.168.2.180 '
  systemctl stop picoclaw
  picoclaw mcp remove transmission
  cp /root/.picoclaw/config.json.pre-transmission-mcp.bak /root/.picoclaw/config.json
  rm -rf /root/.picoclaw/mcp
  systemctl start picoclaw
'
```

## Rollback

```bash
ssh root@192.168.2.180 '
  systemctl disable --now picoclaw
  cp /root/.picoclaw/config.json.pre-nim.bak /root/.picoclaw/config.json
  cp /usr/local/bin/picoclaw.0.2.8.bak /usr/local/bin/picoclaw   # only if 0.3.1 misbehaves
  timedatectl set-timezone Etc/UTC                                # if the TZ change is unwanted
'
```

Narrower rollbacks for the 2026-08-22 changes — stop the service first, it rewrites
`jobs.json` on exit:

```bash
ssh root@192.168.2.180 '
  systemctl stop picoclaw
  cp /root/.picoclaw/config.json.pre-timeout-fix.bak /root/.picoclaw/config.json
  cp /root/.picoclaw/workspace/cron/jobs.json.pre-schedule-fix.bak \
     /root/.picoclaw/workspace/cron/jobs.json
  systemctl start picoclaw
'
```
