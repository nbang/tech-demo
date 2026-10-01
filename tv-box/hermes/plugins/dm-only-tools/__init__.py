"""Allow the Transmission MCP tools only in the owner's Slack DM.

Hermes can only switch a toolset on or off for a whole platform, and it passes
no caller identity to MCP servers, so the scoping has to happen here: a
pre_tool_call hook that reads the gateway's session context and blocks unless
the call comes from Slack, from OWNER_ID, in a DM.

Fails closed: if the session context is not visible (e.g. the hook runs on a
worker thread that did not inherit the ContextVars), the tool is blocked.
"""

import logging
import os

log = logging.getLogger("dm-only-tools")

OWNER_ID = os.getenv("DM_ONLY_TOOLS_OWNER", "U17599QLT")
# Hermes 0.21 names MCP tools mcp__<server>__<tool> (tools/mcp_tool_schema.py,
# mcp_prefixed_tool_name). Older releases used a single underscore — match both,
# because a prefix that never matches silently guards nothing.
GUARDED_PREFIXES = tuple(
    p.strip()
    for p in os.getenv("DM_ONLY_TOOLS_PREFIXES", "mcp__transmission__,mcp_transmission_").split(",")
    if p.strip()
)


def _session(name):
    try:
        from gateway.session_context import get_session_env
        return get_session_env(name, "")
    except Exception:  # not running inside the gateway
        return os.getenv(name, "")


def _guard(tool_name, args, task_id="", **kwargs):
    if not tool_name.startswith(GUARDED_PREFIXES):
        return None
    platform = _session("HERMES_SESSION_PLATFORM")
    user = _session("HERMES_SESSION_USER_ID")
    chat_type = _session("HERMES_SESSION_CHAT_TYPE")
    if platform == "slack" and user == OWNER_ID and chat_type == "dm":
        return None
    log.warning("blocked %s (platform=%r user=%r chat_type=%r)", tool_name, platform, user, chat_type)
    return {
        "action": "block",
        "message": "Torrent tools are only available in the owner's direct message with the bot.",
    }


def register(ctx):
    ctx.register_hook("pre_tool_call", _guard)
