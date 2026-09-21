"""Triggers an immediate storeyes-agent (https://github.com/storeyescoffee/storeyes-agent)
run instead of waiting for the next cron minute.

Fire-and-forget: a single agent pass can legitimately run for several minutes (its own
timeout_seconds, 10 minutes by default, if it picks up an INSTALL command), so this never
waits for it to exit. The agent already logs to /var/log/storeyes-agent.log and reports its
result back to the backend on its own regardless of how it was started. We only wait a beat
to catch the fast-failing case (no sudoers rule installed, agent missing) so the caller gets
a real error instead of a false "triggered".
"""

from __future__ import annotations

import subprocess
import time

from app.shell import SUDO

AGENT_MAIN = "/opt/storeyes-agent/main.py"
FAST_FAIL_WINDOW_SECONDS = 0.3


def trigger() -> dict:
    try:
        proc = subprocess.Popen(
            [*SUDO, "/usr/bin/python3", AGENT_MAIN],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except FileNotFoundError as e:
        return {"triggered": False, "error": str(e)}

    time.sleep(FAST_FAIL_WINDOW_SECONDS)
    exit_code = proc.poll()
    if exit_code is not None and exit_code != 0:
        _, stderr = proc.communicate()
        error = stderr.strip() or f"sudo exited {exit_code}"
        return {"triggered": False, "error": error}

    return {"triggered": True}
