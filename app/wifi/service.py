"""NetworkManager (nmcli) operations. Pure logic; no FastAPI here.

The connect flow never puts the Wi-Fi PSK on a command line: the app renders a
NetworkManager keyfile, drops it in place (root-owned, 0600) via the allowlisted
`sudo tee` / `sudo chmod`, then activates it with `nmcli connection up <label>`.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.shell import CommandError, run, sudo

SYSTEM_CONNECTIONS = Path("/etc/NetworkManager/system-connections")
LABEL_PREFIX = "pi-console-"


# --- `nmcli -t` output parsing -------------------------------------------
def _split(line: str) -> list[str]:
    """Split one line of terse nmcli output, honoring `\\` escapes."""
    fields: list[str] = []
    cur: list[str] = []
    esc = False
    for ch in line:
        if esc:
            cur.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            fields.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    fields.append("".join(cur))
    return fields


def _nmcli(fields: str, *args: str, timeout: float = 20) -> list[list[str]]:
    proc = run(["nmcli", "-t", "-f", fields, *args], check=True, timeout=timeout)
    return [_split(line) for line in proc.stdout.splitlines() if line.strip()]


# --- queries ------------------------------------------------------------
def status() -> dict:
    device = state = connection = None
    for row in _nmcli("TYPE,STATE,CONNECTION,DEVICE", "device", "status"):
        if len(row) >= 4 and row[0] == "wifi":
            _, state, conn, device = row[:4]
            connection = None if conn in ("", "--") else conn
            break

    ssid = signal = None
    if connection:
        for row in _nmcli("IN-USE,SSID,SIGNAL", "device", "wifi"):
            if len(row) >= 3 and row[0] == "*":
                ssid = row[1] or None
                signal = int(row[2]) if row[2].isdigit() else None
                break

    ip = None
    if device:
        for row in _nmcli("IP4.ADDRESS", "device", "show", device):
            if len(row) >= 2 and row[0].startswith("IP4.ADDRESS"):
                ip = row[1].split("/")[0]
                break

    return {
        "device": device,
        "state": state,
        "connection": connection,
        "ssid": ssid or connection,
        "signal": signal,
        "ip": ip,
        "connected": state == "connected",
    }


def scan(rescan: bool = True) -> list[dict]:
    args = ["device", "wifi", "list"]
    if rescan:
        args += ["--rescan", "yes"]

    best: dict[str, dict] = {}
    for row in _nmcli("IN-USE,SSID,SIGNAL,SECURITY", *args, timeout=25):
        if len(row) < 4:
            continue
        in_use, ssid, signal_s, security = row[:4]
        if not ssid:
            continue  # hidden network
        signal = int(signal_s) if signal_s.isdigit() else 0
        entry = {
            "ssid": ssid,
            "signal": signal,
            "security": security or "open",
            "secured": bool(security),
            "active": in_use == "*",
        }
        if ssid not in best or signal > best[ssid]["signal"]:
            best[ssid] = entry
    return sorted(best.values(), key=lambda n: (-n["signal"], n["ssid"].lower()))


def saved() -> list[str]:
    return [
        row[0]
        for row in _nmcli("NAME,TYPE", "connection", "show")
        if len(row) >= 2 and row[1] == "802-11-wireless"
    ]


# --- mutations --------------------------------------------------------
def _slug(ssid: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", ssid).strip("-").lower()
    return s or "network"


def label_for(ssid: str) -> str:
    ssid = ssid.strip()
    return ssid if ssid.startswith(LABEL_PREFIX) else LABEL_PREFIX + _slug(ssid)


def _validate(ssid: str, password: str | None) -> None:
    if not ssid or len(ssid.encode()) > 32 or any(ord(c) < 32 for c in ssid):
        raise ValueError("SSID must be 1-32 bytes and contain no control characters")
    if password is not None:
        if not 8 <= len(password) <= 63:
            raise ValueError("WPA passphrase must be 8-63 characters")
        if any(ord(c) < 32 for c in password):
            raise ValueError("Passphrase contains control characters")


def _keyfile(label: str, ssid: str, password: str | None) -> str:
    blocks = [
        ["[connection]", f"id={label}", "type=wifi", "autoconnect=true"],
        ["[wifi]", "mode=infrastructure", f"ssid={ssid}"],
    ]
    if password:
        blocks.append(["[wifi-security]", "key-mgmt=wpa-psk", f"psk={password}"])
    blocks.append(["[ipv4]", "method=auto"])
    blocks.append(["[ipv6]", "method=auto", "addr-gen-mode=default"])
    return "\n\n".join("\n".join(b) for b in blocks) + "\n"


def _redact(text: str, secret: str | None) -> str:
    return text.replace(secret, "***") if secret else text


def connect(ssid: str, password: str | None) -> dict:
    ssid = ssid.strip()
    password = (password or "").strip() or None
    _validate(ssid, password)

    label = label_for(ssid)
    path = SYSTEM_CONNECTIONS / f"{label}.nmconnection"

    sudo(
        ["tee", str(path)],
        input_text=_keyfile(label, ssid, password),
        check=True,
        timeout=10,
    )
    sudo(["chmod", "600", str(path)], check=True, timeout=10)
    sudo(["nmcli", "connection", "reload"], check=True, timeout=15)

    up = sudo(["nmcli", "connection", "up", label], timeout=60)
    if up.returncode != 0:
        sudo(["nmcli", "connection", "delete", label], timeout=15)
        raise CommandError(
            ["nmcli", "connection", "up", label],
            up.returncode,
            _redact(up.stderr or up.stdout, password),
        )
    return {"label": label, "ssid": ssid}


def forget(ssid: str) -> dict:
    label = label_for(ssid)
    sudo(["nmcli", "connection", "down", label], timeout=15)
    res = sudo(["nmcli", "connection", "delete", label], timeout=15)
    if res.returncode != 0:
        raise CommandError(
            ["nmcli", "connection", "delete", label], res.returncode, res.stderr
        )
    return {"label": label}
