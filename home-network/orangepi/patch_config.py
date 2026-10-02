#!/usr/bin/env python3
"""Idempotent patch of ~/.picoclaw/config.json for the NVIDIA NIM + Slack news bot.

Only touches the keys it owns; every other picoclaw default is left alone.
Safe to re-run.
"""
import json
import os
import shutil
import sys

CFG = os.path.expanduser("~/.picoclaw/config.json")
MODEL_NAME = "nim-primary"
# Placeholder NIM model id; confirmed against /v1/models once the API key exists.
NIM_MODEL = os.environ.get("NIM_MODEL", "openai/gpt-oss-120b")

with open(CFG) as f:
    cfg = json.load(f)

shutil.copy2(CFG, CFG + ".pre-nim.bak")

# 1. NVIDIA NIM model entry (api_key stays in .security.yml)
entry = {
    "model_name": MODEL_NAME,
    "provider": "nvidia",
    "model": NIM_MODEL,
    "api_base": "https://integrate.api.nvidia.com/v1",
    "enabled": True,
    "request_timeout": 120,
}
models = [m for m in cfg["model_list"] if m.get("model_name") != MODEL_NAME]
cfg["model_list"] = [entry] + models

# 2. Make it the default agent model
cfg["agents"]["defaults"]["model_name"] = MODEL_NAME
cfg["agents"]["defaults"]["provider"] = "nvidia"

# 3. Slack channel on; tokens stay in .security.yml
slack = cfg["channel_list"]["slack"]
slack["enabled"] = True
slack["type"] = "slack"
slack.setdefault("allow_from", [])

# 4. Web search: DuckDuckGo needs no key, markdown fetch reads far better for news
web = cfg["tools"]["web"]
web["enabled"] = True
web["duckduckgo"]["enabled"] = True
web["duckduckgo"]["max_results"] = 10
web["format"] = "markdown"

# 5. Harden: this bot lives in a shared team channel, so no remote shell access.
#    Defaults ship exec.allow_remote=true / cron.allow_command=true, which would let
#    anyone in the Slack channel run commands on the board.
cfg["tools"]["exec"]["allow_remote"] = False
cfg["tools"]["cron"]["allow_command"] = False
cfg["tools"]["cron"]["command_allowed_remotes"] = []

# 6. Readable logs for first bring-up
cfg["gateway"]["log_level"] = "info"

with open(CFG, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
os.chmod(CFG, 0o600)

print("patched:", CFG)
print("  model :", MODEL_NAME, "->", NIM_MODEL)
print("  slack :", cfg["channel_list"]["slack"]["enabled"])
print("  ddg   :", web["duckduckgo"]["enabled"])
print("  exec.allow_remote     :", cfg["tools"]["exec"]["allow_remote"])
print("  cron.allow_command    :", cfg["tools"]["cron"]["allow_command"])
