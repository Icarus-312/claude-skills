#!/usr/bin/env python3
"""Server for the screenwatch dashboard.

Three things kept the page stale, and all three are handled here.

http.server sends no cache headers, so browsers hold the first build they see
forever and the page silently goes stale (a day looks like it lost data when it
did not). Every response here is no-store.

Worse: dashboard.html used to be written only by the 4:30am cron, so the file on
disk was a snapshot no matter how fresh the browser's copy was. Every page load
now rebuilds it first. build-dashboard.py takes ~0.3s, cheap enough that a stale
dashboard is never worth the saved time.

Worst: when a rebuild fails we still serve the last good build, because a slightly
old dashboard beats a dead page. But that reproduces the exact failure the two
fixes above were meant to kill — a page that looks fine while showing old data.
So a failed build injects a banner naming the failure and the age of what you are
looking at. The dashboard is allowed to be stale. It is not allowed to be quietly
stale.
"""
import functools
import html
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler

# All paths derive from SCREENWATCH_BASE (default ~/screenwatch), so the server
# has no machine-specific paths baked in.
BASE = os.environ.get("SCREENWATCH_BASE", os.path.expanduser("~/screenwatch"))
DIRECTORY = os.path.join(BASE, "public")
BUILDER = os.path.join(BASE, "bin", "build-dashboard.py")
DASHBOARD = os.path.join(BASE, "dashboard.html")

# Loopback by default: the archive is a record of everything on your screen, so
# it must not be reachable off-box unless you deliberately opt in. Set
# SCREENWATCH_HOST to a tailnet/LAN address (and know the page has no auth) only
# if you want remote access.
HOST = os.environ.get("SCREENWATCH_HOST", "127.0.0.1")
PORT = int(os.environ.get("SCREENWATCH_PORT", "8484"))

# A browser fetching the page fires several requests at once; without this they
# would each kick off their own build over the same files.
_build_lock = threading.Lock()
_last_build = 0.0
MIN_BUILD_INTERVAL = 5.0

# Set to a human-readable reason while the builder is failing; None when healthy.
_build_error = None

# The banner is injected ahead of the first content node. build-dashboard.py emits
# a fragment (no <html>/<body>), so this is the anchor rather than a body tag.
ANCHOR = b'<div class="wrap"'

BANNER_CSS = """
<style>
  .swx-stale {
    margin: 0 0 18px; padding: 14px 18px; border-radius: 10px;
    background: #7f1d1d; color: #fff; border: 1px solid #b91c1c;
    font: 500 14px/1.5 ui-sans-serif, system-ui, sans-serif;
  }
  .swx-stale b { display: block; font-size: 15px; margin-bottom: 3px; }
  .swx-stale code { font-family: ui-monospace, monospace; font-size: 12px; opacity: .85; }
</style>
"""


def _age(seconds):
    m = int(seconds // 60)
    if m < 60:
        return f"{m}m"
    return f"{m // 60}h {m % 60:02d}m"


def banner_html(reason):
    try:
        built = os.path.getmtime(DASHBOARD)
        stamp = datetime.fromtimestamp(built).strftime("%H:%M")
        age = _age(time.time() - built)
        age_txt = f"built at {stamp} — {age} old"
    except OSError:
        age_txt = "build time unknown"
    return (
        BANNER_CSS
        + '<div class="swx-stale"><b>&#9888; Stale — the rebuild is failing.</b>'
        + f"You are looking at an old build ({html.escape(age_txt)}). "
        + "Numbers below do not include recent activity.<br>"
        + f"<code>{html.escape(reason)}</code></div>"
    ).encode()


def rebuild():
    """Rebuild dashboard.html. Never raises — records failure in _build_error."""
    global _last_build, _build_error
    with _build_lock:
        if time.time() - _last_build < MIN_BUILD_INTERVAL:
            return
        try:
            subprocess.run(
                [sys.executable, BUILDER],
                check=True,
                capture_output=True,
                timeout=60,
            )
            _last_build = time.time()
            if _build_error:
                print("rebuild recovered", flush=True)
            _build_error = None
        except subprocess.TimeoutExpired:
            _build_error = "build-dashboard.py timed out after 60s"
            print(f"rebuild failed: {_build_error}", flush=True)
        except subprocess.CalledProcessError as e:
            tail = (e.stderr or b"").decode(errors="replace").strip().splitlines()
            _build_error = (
                f"build-dashboard.py exited {e.returncode}: "
                + (tail[-1] if tail else "no stderr")
            )
            print(f"rebuild failed: {_build_error}", flush=True)


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/index.html", "/dashboard.html"):
            return super().do_GET()

        rebuild()
        if not _build_error:
            return super().do_GET()

        # Serve the last good build with the failure stated on the page itself.
        try:
            with open(DASHBOARD, "rb") as fh:
                body = fh.read()
        except OSError:
            self.send_error(503, "no dashboard build available")
            return

        banner = banner_html(_build_error)
        if ANCHOR in body:
            body = body.replace(ANCHOR, banner + ANCHOR, 1)
        else:
            body = banner + body

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


if __name__ == "__main__":
    handler = functools.partial(DashboardHandler, directory=DIRECTORY)
    print(f"serving {DIRECTORY} on http://{HOST}:{PORT}/", flush=True)
    HTTPServer((HOST, PORT), handler).serve_forever()
