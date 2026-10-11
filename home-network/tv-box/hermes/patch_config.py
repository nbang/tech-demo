"""Patch ~/.hermes/config.yaml for the TX3 mini team bot. Run with Hermes' venv python.

Idempotent: sets only the keys below, leaves everything else the installer wrote.
"""
import pathlib
import shutil
import time

import yaml

HOME = pathlib.Path.home() / ".hermes"
CFG = HOME / "config.yaml"

cfg = yaml.safe_load(CFG.read_text()) if CFG.exists() else {}
cfg = cfg or {}
if CFG.exists():
    shutil.copy2(CFG, CFG.with_name(f"config.yaml.bak-{time.strftime('%Y%m%d-%H%M%S')}"))

# OpenRouter free first, an NVIDIA NIM model as backup. gemma-4-31b-it was listed
# but hung (0 bytes) on 2026-09-24; the owner then picked glm-5.3-flash.
model = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
model.update({"provider": "openrouter", "default": "openrouter/free"})
cfg["model"] = model
cfg["fallback_providers"] = [{"provider": "nvidia", "model": "z-ai/glm-5.3-flash"}]

# Cron expressions and "today" are local time. picoclaw's agent once "converted"
# 08:30 to UTC and moved the digest to 01:30 — keep this explicit.
cfg["timezone"] = "Asia/Ho_Chi_Minh"

web = cfg.get("web") if isinstance(cfg.get("web"), dict) else {}
web["backend"] = "tavily"
cfg["web"] = web

# Slack is open to the whole workspace: no terminal, code, files, browser,
# subagents, skill editing or cron management. Transmission is listed but
# gated to the owner's DM by the dm-only-tools plugin; "camera" (Yi RTSP
# snapshots) gates itself to the owner's DM inside the camera-snapshots plugin.
pt = cfg.get("platform_toolsets") if isinstance(cfg.get("platform_toolsets"), dict) else {}
pt["slack"] = ["web", "vision", "memory", "todo", "clarify", "session_search", "transmission", "camera"]
cfg["platform_toolsets"] = pt

# tool_search hides every plugin/MCP tool behind a search bridge (0.21 has no
# per-tool "keep visible"). With only ~14 Slack tools the saving is ~2k tokens,
# and weak openrouter/free models never searched: "check camera-01" became a
# web_search (2026-10-08). Show all tools directly.
tools_cfg = cfg.get("tools") if isinstance(cfg.get("tools"), dict) else {}
tools_cfg["tool_search"] = {"enabled": "off"}
cfg["tools"] = tools_cfg

mcp_dir = HOME / "mcp"
servers = cfg.get("mcp_servers") if isinstance(cfg.get("mcp_servers"), dict) else {}
servers["transmission"] = {
    # source the 600-mode env file at launch so the RPC password never lands in config.yaml
    "command": "/bin/sh",
    "args": ["-c", f"set -a; . {mcp_dir}/transmission.env; exec /usr/bin/python3 {mcp_dir}/transmission_mcp.py"],
}
cfg["mcp_servers"] = servers

# Slash-command tiers. Without allow_admin_from, EVERY allowed user is admin — and
# SLACK_ALLOW_ALL_USERS=true makes that the whole workspace (/update, /restart,
# /sethome, /debug, /platform pause …). Owner is the only admin in DMs and channels;
# everyone else gets commands that only touch their own conversation.
OWNER = "U17599QLT"
USER_CMDS = ["status", "usage", "new", "stop", "retry", "undo", "title",
             "sessions", "resume", "compress", "context", "btw", "queue"]
slack = cfg.get("slack") if isinstance(cfg.get("slack"), dict) else {}
slack.update({
    "allow_admin_from": [OWNER],
    "group_allow_admin_from": [OWNER],
    "user_allowed_commands": list(USER_CMDS),  # separate copies: no YAML &anchors
    "group_user_allowed_commands": list(USER_CMDS),
    # Plain mrkdwn has no tables: pipe tables arrive as raw `| a | b |` text or a
    # monospace fence. rich_blocks sends them as native Block Kit table blocks
    # (plain-text fallback always included). Root `slack:` keys are promoted to extra.
    "rich_blocks": True,
})
cfg["slack"] = slack

plugins = cfg.get("plugins") if isinstance(cfg.get("plugins"), dict) else {}
enabled = plugins.get("enabled") or []
for name in ("dm-only-tools", "server-status", "camera-snapshots"):
    if name not in enabled:
        enabled.append(name)
plugins["enabled"] = enabled
cfg["plugins"] = plugins

CFG.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))
CFG.chmod(0o600)
print("patched", CFG)
