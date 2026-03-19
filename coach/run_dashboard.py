#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SailAnalytics/coach/run_dashboard.py

One-command dashboard runner:
- Kills any existing listener on PORT before starting.
- Loads FastAPI app via package import: app.backend.app
- Uses create_app() factory if present.
- Starts uvicorn.
- Auto-opens browser to http://127.0.0.1:8000/
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import threading
import webbrowser
from pathlib import Path
from typing import List

HOST = "127.0.0.1"
PORT = 8000

COACH_DIR = Path(__file__).resolve().parent      # .../SailAnalytics/coach
REPO_ROOT = COACH_DIR.parent                     # .../SailAnalytics


# -------------------------
# Port cleanup (macOS)
# -------------------------
def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def pids_listening_on_port(port: int) -> List[int]:
    cp = _run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"])
    if cp.returncode != 0:
        return []
    pids: List[int] = []
    for line in cp.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pids.append(int(line))
        except ValueError:
            pass
    return sorted(set(pids))


def kill_port_listeners(port: int, timeout_s: float = 1.5) -> None:
    """Kill processes currently LISTENING on the target port (before uvicorn starts)."""
    me = os.getpid()
    pids = [p for p in pids_listening_on_port(port) if p != me]
    if not pids:
        return

    # SIGTERM first
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    # Wait briefly
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        still = [p for p in pids_listening_on_port(port) if p != me]
        if not still:
            return
        time.sleep(0.1)

    # Escalate to SIGKILL
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


# -------------------------
# Backend loader (PACKAGE import only)
# -------------------------
def load_asgi_app():
    """
    Load ASGI app from app/backend/app.py via package import.
    Prefers create_app() factory.
    """
    if str(COACH_DIR) not in sys.path:
        sys.path.insert(0, str(COACH_DIR))
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    import importlib
    mod = importlib.import_module("app.backend.app")

    if hasattr(mod, "create_app") and callable(mod.create_app):
        return mod.create_app()
    if hasattr(mod, "app"):
        return mod.app

    raise RuntimeError("app.backend.app defines neither create_app() nor app.")


def open_browser_soon(url: str, delay_s: float = 0.8) -> None:
    """Open a browser tab after a short delay."""
    def _go():
        try:
            webbrowser.open_new_tab(url)
        except Exception:
            pass

    threading.Timer(delay_s, _go).start()


def main() -> None:
    # ✅ FIXED: run from project root (NOT coach)
    os.chdir(str(REPO_ROOT))

    # Kill old server BEFORE starting
    kill_port_listeners(PORT)

    # Load backend ASGI app
    asgi_app = load_asgi_app()

    # Auto-open browser
    url = f"http://{HOST}:{PORT}/"
    open_browser_soon(url, delay_s=0.8)

    # Run uvicorn (blocking)
    import uvicorn
    uvicorn.run(
        asgi_app,
        host=HOST,
        port=PORT,
        reload=False,
        workers=1,
        log_level="info",
    )


if __name__ == "__main__":
    main()