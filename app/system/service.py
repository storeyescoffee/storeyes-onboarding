"""Read-only device information. No sudo, no mutations."""

from __future__ import annotations

import getpass
import re
import shutil
import socket
from pathlib import Path

from app.shell import run


def _model() -> str | None:
    try:
        return Path("/proc/device-tree/model").read_text().strip("\x00").strip() or None
    except OSError:
        return None


def _ips() -> list[str]:
    proc = run(["hostname", "-I"])
    return proc.stdout.split() if proc.returncode == 0 else []


def _temperature_c() -> float | None:
    proc = run(["vcgencmd", "measure_temp"])
    if proc.returncode == 0:
        m = re.search(r"[\d.]+", proc.stdout)
        if m:
            return float(m.group())
    try:
        milli = Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()
        return round(int(milli) / 1000, 1)
    except (OSError, ValueError):
        return None


def _uptime() -> str | None:
    proc = run(["uptime", "-p"])
    return proc.stdout.strip() or None


def _disk() -> dict:
    total, used, free = shutil.disk_usage("/")
    gb = 1_000_000_000
    return {
        "total_gb": round(total / gb, 1),
        "used_gb": round(used / gb, 1),
        "free_gb": round(free / gb, 1),
        "percent": round(used / total * 100) if total else None,
    }


def info() -> dict:
    return {
        "hostname": socket.gethostname(),
        "user": getpass.getuser(),
        "model": _model(),
        "ips": _ips(),
        "temperature_c": _temperature_c(),
        "uptime": _uptime(),
        "disk": _disk(),
    }
