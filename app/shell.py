"""Subprocess helpers. Every system call in the app funnels through here.

`run()` for read-only commands, `sudo()` for the allowlisted mutations in
`deploy/sudoers.d/pi-console`. Always pass argv as a list; never `shell=True`.
"""

from __future__ import annotations

import shlex
import subprocess

# -n: never prompt for a password. If no NOPASSWD rule matches, sudo fails
# immediately instead of hanging on a TTY prompt that will never come.
SUDO = ["sudo", "-n"]


class CommandError(RuntimeError):
    def __init__(self, cmd: list[str], returncode: int, stderr: str):
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = (stderr or "").strip()
        super().__init__(
            f"`{shlex.join(cmd)}` exited {returncode}"
            + (f": {self.stderr}" if self.stderr else "")
        )


def run(
    cmd: list[str],
    *,
    timeout: float = 30,
    check: bool = False,
    input_text: str | None = None,
) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_text,
            check=False,
        )
    except FileNotFoundError:
        # Missing binary (e.g. nmcli/vcgencmd on a non-Pi host). Present it like
        # a shell "command not found" so callers that inspect .returncode keep
        # working and `check=True` raises a clean CommandError.
        proc = subprocess.CompletedProcess(
            cmd, 127, "", f"{cmd[0]}: command not found"
        )
    if check and proc.returncode != 0:
        raise CommandError(cmd, proc.returncode, proc.stderr or proc.stdout)
    return proc


def sudo(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return run([*SUDO, *cmd], **kwargs)
