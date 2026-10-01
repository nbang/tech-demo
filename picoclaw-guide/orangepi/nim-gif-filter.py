#!/usr/bin/env python3
"""Strip data:image/gif parts from requests on their way to NVIDIA NIM.

Why this exists
---------------
picoclaw's web_fetch scrapes images out of fetched pages and injects them into the
next LLM request as `image_url` content parts. News pages are full of 1x1 GIF
tracking pixels. NVIDIA NIM accepts PNG/JPEG/WEBP but answers `data:image/gif`
with `415 Unsupported Media Type`, which kills the entire agent turn — the daily
digest then posts nothing, while the cron job still records lastStatus "ok".

meta/muse-glimmer-30b IS vision-capable (verified: it reads PNG/JPEG/WEBP
correctly), so this deliberately removes ONLY GIF parts. Every other image format
passes through untouched and the model keeps full vision.

Deps: stdlib only — the board is 32-bit ARMv7 with 991 MB RAM.
"""
import http.server
import json
import socketserver
import sys
import urllib.error
import urllib.request

UPSTREAM = "https://integrate.api.nvidia.com"
LISTEN = ("127.0.0.1", 8899)
GIF_PREFIX = "data:image/gif"
PLACEHOLDER = "[Loaded image from tool result above]"


def log(msg):
    # journald captures stdout; keep it to counts, never bodies or headers,
    # so the API key and page content never reach the logs.
    print(msg, flush=True)


def strip_gifs(payload):
    """Remove GIF image parts. Returns (payload, n_stripped, n_msgs_dropped)."""
    msgs = payload.get("messages")
    if not isinstance(msgs, list):
        return payload, 0, 0

    stripped = 0
    kept_msgs = []
    dropped = 0

    for m in msgs:
        content = m.get("content")
        if not isinstance(content, list):
            kept_msgs.append(m)
            continue

        parts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "image_url":
                url = (p.get("image_url") or {}).get("url", "")
                if isinstance(url, str) and url.startswith(GIF_PREFIX):
                    stripped += 1
                    continue
            parts.append(p)

        has_image = any(
            isinstance(p, dict) and p.get("type") == "image_url" for p in parts
        )
        only_placeholder = all(
            isinstance(p, dict)
            and p.get("type") == "text"
            and p.get("text", "").strip() == PLACEHOLDER
            for p in parts
        ) if parts else True

        # A message that existed solely to carry a now-removed GIF is noise;
        # forwarding a bare "[Loaded image from tool result above]" would just
        # confuse the model into describing an image it never received.
        if not has_image and only_placeholder:
            dropped += 1
            continue

        m = dict(m)
        m["content"] = parts
        kept_msgs.append(m)

    payload["messages"] = kept_msgs
    return payload, stripped, dropped


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "nim-gif-filter"

    def log_message(self, *a):
        pass  # suppress default per-request noise

    def _proxy(self, body):
        req = urllib.request.Request(UPSTREAM + self.path, data=body, method="POST")
        for h in ("Authorization", "Content-Type", "Accept"):
            v = self.headers.get(h)
            if v:
                req.add_header(h, v)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except Exception as e:
            log("upstream error: %s" % e)
            return 502, json.dumps({"error": "proxy upstream failure"}).encode()

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))

        # Fail open: anything unparseable is forwarded untouched rather than
        # dropped, so this filter can never be the reason a request dies.
        try:
            payload = json.loads(body)
            payload, n, dropped = strip_gifs(payload)
            if n:
                body = json.dumps(payload).encode()
                log("stripped %d GIF part(s), dropped %d empty message(s)" % (n, dropped))
        except Exception as e:
            log("passthrough (unparsed): %s" % e)

        status, resp = self._proxy(body)
        if status == 415:
            log("WARNING: upstream still returned 415 after filtering")

        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        except (BrokenPipeError, ConnectionResetError):
            # picoclaw went away mid-response — usually a service restart that
            # killed an in-flight turn. Nothing to recover; don't dump a traceback.
            log("client disconnected before response was written")


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    log("nim-gif-filter listening on %s:%d -> %s" % (LISTEN[0], LISTEN[1], UPSTREAM))
    try:
        Server(LISTEN, Handler).serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
