"""camera_snapshots — a burst of JPEG frames from a Yi camera's RTSP stream.

"check camera-01" in the owner's Slack DM → the agent calls camera_snapshots →
every 5 s a short ffmpeg run connects to rtsp://<ip>:554/ch0_0.h264, saves the
first keyframe and exits (~2.5 s on the TX3) → each frame is uploaded to the
chat as soon as it lands, not after the whole burst.

Delivery does not depend on the model. The uploads go straight through the
Slack adapter, using the gateway that the pre_gateway_dispatch hook records.
If no gateway has been seen yet, the paths are parked per session and a
transform_llm_output hook appends MEDIA: tags to the final reply (Hermes only
auto-attaches MEDIA from built-in tools, and free models garble 12 paths).

`!check camera-01 [count] [interval]` skips the model altogether: a
pre_gateway_dispatch hook catches it before the agent, captures in a worker
thread and uploads through the Slack adapter. Free openrouter models sometimes
web-search "check camera-01" instead of calling the tool, so this is the
reliable path.

`!watch camera-01 [hours]` (default and max 24 h) uses the camera's own motion
detection: its firmware logs "got a new motion start" to /tmp/log.txt, which
the hack's anonymous FTP serves. Every few seconds the watch re-reads that log
(a ~100 KB ring buffer, so new lines are found by timestamp, not by offset); on
a new event it records a 5 s 360p clip (ffmpeg stream copy, no re-encode) and posts
it as a video. `!watch camera-01 stop` ends it, `!watch` lists the running ones.
Watches live in the gateway process: a restart ends them silently.

Home-camera images, so all paths fail closed outside Slack + OWNER_ID + DM
(same rule as dm-only-tools). The Slack toolset must list "camera".
"""

import asyncio
import datetime
import ftplib
import io
import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
import threading
import time

log = logging.getLogger("camera-snapshots")

OWNER_ID = os.getenv("CAMERA_SNAPSHOTS_OWNER", os.getenv("DM_ONLY_TOOLS_OWNER", "U17599QLT"))

# Inventory: home-network/yi-camera/README.md. Both streams are already upright
# (checked 2026-10-08 — flipping one here turned the OSD clock upside down).
CAMERAS = {
    "camera-01": {"ip": "192.168.2.153", "rotate180": False},
    "camera-02": {"ip": "192.168.2.222", "rotate180": False},
}
STREAM = "rtsp://{ip}:554/ch0_0.h264"  # 720p, for stills
CLIP_STREAM = "rtsp://{ip}:554/ch0_1.h264"  # 360p, for motion clips
DEFAULT_COUNT, MAX_COUNT = 12, 20
DEFAULT_INTERVAL, MAX_INTERVAL = 5, 60
KEEP_SECONDS = 24 * 3600
FILE_RE = re.compile(r"^camera-\d\d-\d{8}-\d{6}-(\d\d\.jpg|motion\.mp4)$")

_pending = {}  # session_id -> [jpeg paths] waiting for the final reply
_pending_lock = threading.Lock()
_camera_locks = {name: threading.Lock() for name in CAMERAS}  # the Yi RTSP server is tiny


def _session(name):
    try:
        from gateway.session_context import get_session_env
        return get_session_env(name, "")
    except Exception:  # not running inside the gateway
        return os.getenv(name, "")


def _out_dir():
    """A dir the gateway is allowed to upload MEDIA from (~/.hermes/cache/images)."""
    try:
        from gateway.platforms.base import get_image_cache_dir
        path = pathlib.Path(get_image_cache_dir())
    except Exception:
        path = pathlib.Path.home() / ".hermes" / "cache" / "images"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _prune(out_dir):
    cutoff = time.time() - KEEP_SECONDS
    for f in out_dir.iterdir():
        if FILE_RE.match(f.name) and f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)


def _resolve(camera):
    """'camera-01', 'camera 1', '01', '153', '192.168.2.153' -> 'camera-01'."""
    key = str(camera or "camera-01").strip().lower()
    for name, cam in CAMERAS.items():
        if key in (name, cam["ip"], cam["ip"].rsplit(".", 1)[1]):
            return name
    digits = re.sub(r"\D", "", key)
    if digits:
        name = f"camera-{int(digits):02d}"
        if name in CAMERAS:
            return name
    return None


def _clamp(value, default, low, high):
    try:
        return max(low, min(int(value), high))
    except (TypeError, ValueError):
        return default


GRAB_TIMEOUT = 20  # one connect + first keyframe; ~2.5 s on the TX3


def _grab(cam, path):
    """Connect, decode the first keyframe, write one JPEG, disconnect."""
    cmd = [
        shutil.which("ffmpeg") or "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-rtsp_transport", "tcp", "-timeout", "10000000",  # 10 s socket timeout (µs)
        "-i", STREAM.format(ip=cam["ip"]), "-an",
        *(["-vf", "hflip,vflip"] if cam["rotate180"] else []),
        "-frames:v", "1", "-q:v", "4", "-y", str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=GRAB_TIMEOUT)
    if proc.returncode != 0 or not path.exists():
        raise RuntimeError((proc.stderr or "").strip()[-400:] or f"ffmpeg exited {proc.returncode}")


CLIP_SECONDS = 5
LOG_PATH = "/tmp/log.txt"  # firmware log, served by the hack's anonymous FTP
MOTION_RE = re.compile(r"\[\./rmm\]\[([\d/:]+)\]: got a new motion start")


def motion_events(ip, timeout=10):
    """Timestamps of the 'motion start' lines still in the camera's log.

    The log is a ring buffer that wraps in place, so the caller diffs these
    sets instead of tracking a file offset. A line cut by the wrap point loses
    its prefix or its tail and doesn't match.
    """
    buf = io.BytesIO()
    with ftplib.FTP(ip, timeout=timeout) as ftp:
        ftp.login()
        ftp.retrbinary(f"RETR {LOG_PATH}", buf.write)
    return set(MOTION_RE.findall(buf.getvalue().decode("latin-1")))


def record_clip(name, seconds=CLIP_SECONDS, out_dir=None):
    """Record `seconds` of 360p H.264 + AAC as-is (no re-encode) into an MP4."""
    cam = CAMERAS[name]
    out_dir = out_dir or _out_dir()
    _prune(out_dir)
    path = out_dir / f"{name}-{datetime.datetime.now():%Y%m%d-%H%M%S}-motion.mp4"
    cmd = [
        shutil.which("ffmpeg") or "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-rtsp_transport", "tcp", "-timeout", "10000000",
        *(["-display_rotation", "180"] if cam["rotate180"] else []),
        "-i", CLIP_STREAM.format(ip=cam["ip"]), "-t", str(seconds),
        "-c", "copy", "-movflags", "+faststart", "-y", str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=GRAB_TIMEOUT + seconds)
    if proc.returncode != 0 or not path.exists():
        raise RuntimeError((proc.stderr or "").strip()[-400:] or f"ffmpeg exited {proc.returncode}")
    return path


def capture(name, count=DEFAULT_COUNT, interval=DEFAULT_INTERVAL, out_dir=None, on_frame=None):
    """One short ffmpeg run per frame, started every `interval` s; return the JPEGs written.
    on_frame(path, index) runs right after each JPEG lands, for live posting.

    Reconnecting per frame keeps the box idle between shots instead of decoding
    a minute of 720p. Grabs are scheduled at fixed offsets, so a slow one does
    not push the rest back. A failed grab is skipped; all failing raises.
    """
    cam = CAMERAS[name]
    out_dir = out_dir or _out_dir()
    _prune(out_dir)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    frames, errors = [], []
    t0 = time.monotonic()
    for i in range(count):
        time.sleep(max(0.0, t0 + i * interval - time.monotonic()))
        path = out_dir / f"{name}-{stamp}-{i + 1:02d}.jpg"
        try:
            _grab(cam, path)
            frames.append(path)
            if on_frame is not None:
                on_frame(path, i)
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            errors.append(str(e))
            if not frames and len(errors) >= 2:  # camera unreachable: don't wait a minute
                break
    if not frames:
        raise RuntimeError(errors[-1] if errors else "no frames")
    return frames


_live = {"gateway": None, "loop": None}  # set by _dispatch on every inbound message


def _adapter(gateway, platform_value):
    """Live adapter for a platform name ("slack"). Works on 0.21.3 and 0.21.4:
    both keep the single-profile map in gateway.adapters, keyed by Platform."""
    for key, adapter in (getattr(gateway, "adapters", None) or {}).items():
        if getattr(key, "value", key) == platform_value:
            return adapter
    return None


class _Poster:
    """Uploads each frame as it is captured: on_frame runs in the capture thread
    and hands the upload to the gateway's event loop without waiting for it."""

    def __init__(self, adapter, loop, chat_id, thread_id, name, count):
        self.adapter, self.loop, self.chat_id, self.name, self.count = adapter, loop, chat_id, name, count
        self.meta = {"thread_id": thread_id} if thread_id else None
        self.futures = []

    def __call__(self, path, i):
        caption = f"*{self.name}* · {i + 1}/{self.count} · {datetime.datetime.now():%H:%M:%S}"
        coro = self.adapter.send_image_file(self.chat_id, str(path), caption=caption, metadata=self.meta)
        self.futures.append(asyncio.run_coroutine_threadsafe(coro, self.loop))

    def failed(self, timeout=60):
        """Wait for outstanding uploads (call from a worker thread); return error strings."""
        errors = []
        for f in self.futures:
            try:
                res = f.result(timeout=timeout)
                if not getattr(res, "success", True):
                    errors.append(str(getattr(res, "error", "upload failed")))
            except Exception as e:
                errors.append(str(e))
        return errors


def _tool(args, **kwargs):
    platform = _session("HERMES_SESSION_PLATFORM")
    user = _session("HERMES_SESSION_USER_ID")
    chat_type = _session("HERMES_SESSION_CHAT_TYPE")
    if not (platform == "slack" and user == OWNER_ID and chat_type == "dm"):
        log.warning("blocked (platform=%r user=%r chat_type=%r)", platform, user, chat_type)
        return json.dumps({"error": "Camera snapshots are only available in the owner's direct message with the bot."})

    name = _resolve(args.get("camera"))
    if name is None:
        return json.dumps({"error": f"Unknown camera {args.get('camera')!r}. Known: {', '.join(CAMERAS)}."})
    count = _clamp(args.get("count"), DEFAULT_COUNT, 1, MAX_COUNT)
    interval = _clamp(args.get("interval_seconds"), DEFAULT_INTERVAL, 1, MAX_INTERVAL)

    lock = _camera_locks[name]
    if not lock.acquire(blocking=False):
        return json.dumps({"error": f"{name} is already being captured; try again in a minute."})
    started = datetime.datetime.now()
    adapter = _adapter(_live["gateway"], "slack")
    chat_id = _session("HERMES_SESSION_CHAT_ID")
    poster = (_Poster(adapter, _live["loop"], chat_id, _session("HERMES_SESSION_THREAD_ID"), name, count)
              if adapter is not None and _live["loop"] is not None and chat_id else None)
    try:
        frames = capture(name, count, interval, on_frame=poster)
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"{name} ({CAMERAS[name]['ip']}) did not deliver frames in time. Is it powered and on Wi-Fi?"})
    except Exception as e:
        log.warning("capture %s failed: %s", name, e)
        return json.dumps({"error": f"Could not read {name} ({CAMERAS[name]['ip']}): {e}"})
    finally:
        lock.release()

    if poster is not None:
        errors = poster.failed()
        delivery = ("Every photo is already posted in the chat. Do NOT write MEDIA: tags or file paths. "
                    "Reply with one short line: camera, start time, frame count."
                    + (f" {len(errors)} upload(s) failed: {errors[-1]}" if errors else ""))
    else:  # gateway not seen yet: attach at the end via the transform_llm_output hook
        with _pending_lock:
            _pending.setdefault(_session("HERMES_SESSION_ID"), []).extend(str(f) for f in frames)
        delivery = ("The images are attached to your reply automatically. Do NOT write MEDIA: tags "
                    "or file paths. Reply with one short line: camera, start time, frame count.")
    return json.dumps({
        "camera": name,
        "ip": CAMERAS[name]["ip"],
        "frames": len(frames),
        "requested": count,
        "interval_seconds": interval,
        "started_at": started.strftime("%d/%m/%Y %H:%M:%S"),
        "paths": [str(f) for f in frames],
        "delivery": delivery,
    })


def _attach(response_text=None, session_id="", **kwargs):
    with _pending_lock:
        paths = _pending.pop(session_id or "", None)
        if paths is None and len(_pending) == 1 and "" in _pending:
            paths = _pending.pop("")  # tool ran without a bound session id
    if not paths:
        return None
    # drop any MEDIA: tags the model wrote for these files, then add ours once
    text = response_text or ""
    for p in paths:
        text = re.sub(r"[`*_]{0,3}MEDIA:\s*" + re.escape(p) + r"[`*_]{0,3}", "", text)
    return text.rstrip() + "\n\n" + "\n".join(f"MEDIA:{p}" for p in paths)


SCHEMA = {
    "name": "camera_snapshots",
    "description": (
        "Take a burst of still photos from a home security camera (Yi Home, RTSP) and post them "
        "to the chat. Use when the user asks to check, look at, or see a camera "
        f"({', '.join(CAMERAS)}). Default: 12 photos, 5 seconds apart (takes about 1 minute)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "camera": {"type": "string", "enum": list(CAMERAS), "description": "Which camera. camera-01 = 192.168.2.153, camera-02 = 192.168.2.222."},
            "count": {"type": "integer", "description": f"Number of photos (1-{MAX_COUNT}, default {DEFAULT_COUNT})."},
            "interval_seconds": {"type": "integer", "description": f"Seconds between photos (1-{MAX_INTERVAL}, default {DEFAULT_INTERVAL})."},
        },
        "required": ["camera"],
    },
}


def _available():
    return shutil.which("ffmpeg") is not None


CHECK_RE = re.compile(r"^\s*!check\b\s*(\S+)?(?:\s+(\d+))?(?:\s+(\d+))?\s*$", re.IGNORECASE)
WATCH_RE = re.compile(r"^\s*!watch\b\s*(\S+)?(?:\s+(\S+))?\s*$", re.IGNORECASE)
WATCH_HOURS = 24  # default and max
POLL_SECONDS = 3
FAIL_NOTICE = 10  # consecutive failed log reads (~1 min) before warning in the chat
_tasks = set()  # keep background capture tasks referenced until they finish


def _owner_dm(source):
    platform = getattr(getattr(source, "platform", None), "value", "")
    return platform == "slack" and source.user_id == OWNER_ID and source.chat_type == "dm"


async def _run_check(adapter, source, name, count, interval):
    meta = {"thread_id": source.thread_id} if source.thread_id else None
    lock = _camera_locks[name]
    if not lock.acquire(blocking=False):
        await adapter.send(source.chat_id, f"{name} is already being captured; try again in a minute.", metadata=meta)
        return
    try:
        secs = (count - 1) * interval
        await adapter.send(source.chat_id, f"📷 *{name}*: {count} photos, {interval} s apart (~{secs} s)…", metadata=meta)
        loop = asyncio.get_running_loop()
        poster = _Poster(adapter, loop, source.chat_id, source.thread_id, name, count)
        try:
            frames = await loop.run_in_executor(None, lambda: capture(name, count, interval, on_frame=poster))
        except Exception as e:
            log.warning("!check %s failed: %s", name, e)
            await adapter.send(source.chat_id, f"Could not read *{name}* ({CAMERAS[name]['ip']}): {e}", metadata=meta)
            return
        errors = await loop.run_in_executor(None, poster.failed)
    finally:
        lock.release()
    if errors or len(frames) < count:
        note = f"*{name}*: {len(frames)}/{count} photos captured"
        if errors:
            note += f", {len(errors)} upload(s) failed: {errors[-1]}"
        await adapter.send(source.chat_id, note, metadata=meta)


_watches = {}  # camera name -> _Watch


class _Watch:
    """Polls one camera's motion log until `until`; posts a clip per new event."""

    def __init__(self, adapter, source, name, hours):
        self.adapter, self.chat_id, self.name = adapter, source.chat_id, name
        self.meta = {"thread_id": source.thread_id} if source.thread_id else None
        self.until = datetime.datetime.now() + datetime.timedelta(hours=hours)
        self.events = self.clips = 0
        self.task = None

    async def say(self, text):
        try:
            await self.adapter.send(self.chat_id, text, metadata=self.meta)
        except Exception as e:
            log.warning("!watch %s: send failed: %s", self.name, e)

    def status(self):
        return f"👀 *{self.name}* until {self.until:%d/%m %H:%M} · {self.events} motion events, {self.clips} clips"

    async def run(self):
        loop = asyncio.get_running_loop()
        ip = CAMERAS[self.name]["ip"]
        ended = "watch ended"
        try:
            try:
                seen = await loop.run_in_executor(None, motion_events, ip)
            except Exception as e:
                ended = f"could not read the camera log ({e}); watch not started"
                return
            failures = 0
            while datetime.datetime.now() < self.until:
                await asyncio.sleep(POLL_SECONDS)
                try:
                    stamps = await loop.run_in_executor(None, motion_events, ip)
                except Exception as e:
                    failures += 1
                    if failures == FAIL_NOTICE:
                        await self.say(f"⚠️ *{self.name}*: can't read the camera log ({e}); still trying.")
                    continue
                if failures >= FAIL_NOTICE:
                    await self.say(f"*{self.name}*: camera log is readable again.")
                failures = 0
                new = stamps - seen
                seen |= stamps
                if new:  # several lines in one poll = one clip
                    self.events += 1
                    await self.on_motion(loop)
        except asyncio.CancelledError:
            ended = "watch stopped"
        finally:
            if _watches.get(self.name) is self:
                del _watches[self.name]
            await self.say(f"*{self.name}*: {ended} · {self.events} motion events, {self.clips} clips.")

    async def on_motion(self, loop):
        at = f"{datetime.datetime.now():%H:%M:%S}"
        lock = _camera_locks[self.name]
        if not lock.acquire(blocking=False):  # a !check burst holds the stream
            await self.say(f"🚶 *{self.name}* · motion · {at} (camera busy, no clip)")
            return
        try:
            path = await loop.run_in_executor(None, record_clip, self.name)
        except Exception as e:
            log.warning("!watch %s: clip failed: %s", self.name, e)
            await self.say(f"🚶 *{self.name}* · motion · {at} (clip failed: {e})")
            return
        finally:
            lock.release()
        res = await self.adapter.send_video(self.chat_id, str(path), caption=f"🚶 *{self.name}* · motion · {at}",
                                            metadata=self.meta)
        if getattr(res, "success", True):
            self.clips += 1
        else:
            log.warning("!watch %s: upload failed: %s", self.name, getattr(res, "error", ""))


WATCH_USAGE = (f"Usage: `!watch <camera> [hours]` (max {WATCH_HOURS}), `!watch <camera> stop`, "
               f"`!watch` for status — cameras: {', '.join(CAMERAS)}")


def _watch_command(adapter, source, m):
    """Start, stop or list watches; returns the reply text (None = the watch task replies)."""
    if not m.group(1):
        return "\n".join(w.status() for w in _watches.values()) or "No camera is being watched."
    name = _resolve(m.group(1))
    arg = (m.group(2) or "").lower()
    if name is None or not (arg in ("", "stop", "off") or arg.isdigit()):
        return WATCH_USAGE
    current = _watches.get(name)
    if arg in ("stop", "off"):
        if current is None:
            return f"*{name}* is not being watched."
        current.task.cancel()
        return None
    if current is not None:
        return f"{current.status()}. Stop it first: `!watch {name} stop`"
    hours = _clamp(arg or None, WATCH_HOURS, 1, WATCH_HOURS)
    watch = _Watch(adapter, source, name, hours)
    _watches[name] = watch
    watch.task = asyncio.get_running_loop().create_task(watch.run())
    _tasks.add(watch.task)
    watch.task.add_done_callback(_tasks.discard)
    return (f"👀 Watching *{name}* for {hours} h (until {watch.until:%d/%m %H:%M}). Each motion event "
            f"the camera detects posts a {CLIP_SECONDS} s clip here. Stop: `!watch {name} stop`")


def _dispatch(event=None, gateway=None, **kwargs):
    if gateway is not None:  # lets the camera_snapshots tool post frames live too
        _live["gateway"], _live["loop"] = gateway, asyncio.get_running_loop()
    text = getattr(event, "text", "") or ""
    m = CHECK_RE.match(text)
    w = None if m else WATCH_RE.match(text)
    if not (m or w):
        return None
    source = event.source
    adapter = _adapter(gateway, getattr(source.platform, "value", source.platform))
    if adapter is None:
        log.warning("!check/!watch: no adapter for %r", getattr(source, "platform", None))
        return None
    if not _owner_dm(source):
        log.warning("!check/!watch denied (user=%r chat_type=%r)", source.user_id, source.chat_type)
        reply = "Cameras are only available in the owner's direct message with the bot."
    elif w:
        reply = _watch_command(adapter, source, w)
        if reply is None:
            return {"action": "skip", "reason": "camera-snapshots !watch"}
    else:
        name = _resolve(m.group(1)) if m.group(1) else None
        reply = None if name else f"Usage: `!check <camera> [count] [interval_s]` — cameras: {', '.join(CAMERAS)}"
    loop = asyncio.get_running_loop()
    if reply:
        task = loop.create_task(adapter.send(source.chat_id, reply,
                                             metadata={"thread_id": source.thread_id} if source.thread_id else None))
    else:
        count = _clamp(m.group(2), DEFAULT_COUNT, 1, MAX_COUNT)
        interval = _clamp(m.group(3), DEFAULT_INTERVAL, 1, MAX_INTERVAL)
        task = loop.create_task(_run_check(adapter, source, name, count, interval))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"action": "skip", "reason": "camera-snapshots !check/!watch"}


def register(ctx):
    ctx.register_tool(name="camera_snapshots", toolset="camera", schema=SCHEMA, handler=_tool,
                      check_fn=_available, emoji="📷",
                      description="Burst of photos from a home camera (owner DM only).")
    ctx.register_hook("transform_llm_output", _attach)
    ctx.register_hook("pre_gateway_dispatch", _dispatch)


if __name__ == "__main__":  # local test: python __init__.py camera-01 [count] [interval] [out_dir]
    import sys                # or:         python __init__.py watch camera-01 [seconds] [out_dir]
    if len(sys.argv) > 1 and sys.argv[1] == "watch":
        target = _resolve(sys.argv[2] if len(sys.argv) > 2 else "camera-01")
        end = time.time() + (int(sys.argv[3]) if len(sys.argv) > 3 else 300)
        out = pathlib.Path(sys.argv[4]) if len(sys.argv) > 4 else pathlib.Path.cwd()
        seen = motion_events(CAMERAS[target]["ip"])
        print(f"{target}: {len(seen)} old events in the log; watching", file=sys.stderr)
        while time.time() < end:
            time.sleep(POLL_SECONDS)
            stamps = motion_events(CAMERAS[target]["ip"])
            new, seen = stamps - seen, seen | stamps
            if new:
                print(f"motion {sorted(new)} -> {record_clip(target, out_dir=out)}")
        sys.exit()
    target = _resolve(sys.argv[1] if len(sys.argv) > 1 else "camera-01")
    n = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_COUNT
    gap = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_INTERVAL
    out = pathlib.Path(sys.argv[4]) if len(sys.argv) > 4 else pathlib.Path.cwd()
    t0 = time.time()
    for f in capture(target, n, gap, out):
        print(f)
    print(f"{time.time() - t0:.1f}s", file=sys.stderr)
