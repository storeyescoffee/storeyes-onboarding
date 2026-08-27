"""Wrappers around the `rpi-connect` CLI.

Runs as the current login user (no sudo) so it shares that user's systemd/DBus
session, which is where the `rpi-connect` agent lives.

`signin()` blocks until `rpi-connect signin` exits (v1 decision). While it runs,
the verification URL it prints is published via `signin_progress()` so the page
can show it to the user without waiting for the POST to return.
"""

from __future__ import annotations

import re
import subprocess
import threading
import time

from app.shell import run

try:  # select works on pipes on POSIX; on Windows we fall back to blocking reads
    import select

    _HAVE_SELECT = hasattr(select, "select")
except ImportError:  # pragma: no cover
    _HAVE_SELECT = False

VERIFY_RE = re.compile(r"https://connect\.raspberrypi\.com/\S+")

_lock = threading.Lock()
_progress = {"running": False, "url": None}


def installed() -> bool:
    return run(["which", "rpi-connect"]).returncode == 0


def _parse_status(text: str) -> dict:
    def find(label: str) -> str | None:
        m = re.search(
            rf"^{re.escape(label)}\s*:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE
        )
        return m.group(1).strip() if m else None

    signed = find("Signed in")
    signed_yes = (signed or "").lower().startswith(("yes", "true"))
    return {
        "signed_in": signed_yes,
        "account": signed if (signed and not signed_yes and signed.lower() != "no") else None,
        "screen_sharing": find("Screen sharing"),
        "remote_shell": find("Remote shell"),
        "raw": text.strip(),
    }


def status() -> dict:
    if not installed():
        return {"installed": False}
    proc = run(["rpi-connect", "status"], timeout=15)
    return {"installed": True, **_parse_status(proc.stdout + proc.stderr)}


def signin_progress() -> dict:
    with _lock:
        return dict(_progress)


def _read_line(stdout, remaining: float) -> str | None:
    """Return the next line, "" on EOF, or None if nothing arrived in time."""
    if _HAVE_SELECT:
        ready, _, _ = select.select([stdout], [], [], min(remaining, 1.0))
        if not ready:
            return None
    return stdout.readline()


def signin(timeout: float = 300) -> dict:
    with _lock:
        if _progress["running"]:
            raise RuntimeError("A sign-in is already in progress")
        _progress.update(running=True, url=None)

    proc: subprocess.Popen | None = None
    captured: list[str] = []
    url: str | None = None
    try:
        proc = subprocess.Popen(
            ["rpi-connect", "signin"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                proc.kill()
                return {"ok": False, "url": url,
                        "error": "Timed out waiting for verification"}

            line = _read_line(proc.stdout, remaining)
            if line is None:
                if proc.poll() is not None:
                    break
                continue
            if line == "":
                break  # EOF

            captured.append(line)
            if url is None:
                m = VERIFY_RE.search(line)
                if m:
                    url = m.group(0)
                    with _lock:
                        _progress["url"] = url

        proc.wait(timeout=10)
        ok = proc.returncode == 0
        return {
            "ok": ok,
            "url": url,
            "output": "".join(captured).strip(),
            "error": None if ok else f"rpi-connect signin exited with code {proc.returncode}",
        }
    finally:
        if proc and proc.poll() is None:
            proc.kill()
        with _lock:
            _progress.update(running=False, url=None)


def enable() -> None:
    run(["rpi-connect", "on"], check=True, timeout=20)


def disable() -> None:
    run(["rpi-connect", "off"], check=True, timeout=20)
