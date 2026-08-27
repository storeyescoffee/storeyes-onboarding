# Pi Onboarding Console — multi-feature plan

> **Status: implemented.** All four features and the layout below are built. This
> doc is kept as the design rationale; see `README.md` for how to run it.
> Verified on a non-Pi host (routes, templates, graceful degradation when
> `nmcli`/`rpi-connect`/`vcgencmd` are absent). Still needs a real Pi to confirm
> the sudoers allowlist and the keyfile → `connection up` flow end to end.

## Goal

Grow the single-file camera app into a small **device onboarding console** that runs
on the Raspberry Pi and is opened from a browser on the same LAN. First screen is a
dashboard; each capability is its own page/section:

- **Camera** — live MJPEG stream + still capture (already built)
- **Wi‑Fi** — scan networks, connect / forget, show current connection & signal
- **Raspberry Pi Connect** — show status, start sign‑in (device code), enable/disable
- **System** (nice-to-have) — hostname, IP addresses, temperature, uptime, disk

Non-goals for now: auth/login, HTTPS, multi-user, remote (WAN) access, OTA updates.

---

## Target layout

```
storeyes-onboarding/
├── main.py                    # thin entrypoint: build app, include routers, uvicorn
├── app/
│   ├── __init__.py
│   ├── config.py              # all tunables (camera res/fps, port, paths)
│   ├── shell.py               # run() helper + sudo allowlist wrapper
│   ├── camera/
│   │   ├── __init__.py
│   │   ├── backends.py        # Picamera2Backend / UsbBackend / _JpegSink
│   │   ├── service.py         # make_camera(), save_snapshot(), mjpeg_generator()
│   │   └── router.py          # GET /camera, /camera/stream, POST /camera/capture
│   ├── wifi/
│   │   ├── __init__.py
│   │   ├── service.py         # nmcli wrappers -> dataclasses
│   │   └── router.py          # GET /wifi, /wifi/scan, /wifi/status; POST /wifi/connect, /wifi/forget
│   ├── connect/
│   │   ├── __init__.py
│   │   ├── service.py         # rpi-connect wrappers
│   │   └── router.py          # GET /connect, /connect/status; POST /connect/signin, /connect/on, /connect/off
│   └── system/
│       ├── __init__.py
│       ├── service.py
│       └── router.py          # GET /system, /system/info
├── templates/
│   ├── base.html              # shared shell: nav, styles block, {% block content %}
│   ├── dashboard.html         # "/" — cards linking to each feature + quick status
│   ├── camera.html
│   ├── wifi.html
│   ├── connect.html
│   └── system.html
├── static/
│   ├── app.css
│   └── app.js                 # small fetch() helpers, no framework
├── docs/
│   └── multi-feature-plan.md
└── deploy/
    ├── sudoers.d/pi-console   # command allowlist (installed to /etc/sudoers.d/)
    └── onboarding.service     # systemd --user unit
```

Rule of thumb: **`service.py` = logic + subprocess, no FastAPI. `router.py` = HTTP only, no
subprocess.** Keeps each feature testable without a running server.

---

## App composition

`main.py` becomes ~20 lines:

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.config import STATIC_DIR, CAPTURE_DIR
from app.camera.router import router as camera_router
from app.wifi.router import router as wifi_router
from app.connect.router import router as connect_router
from app.system.router import router as system_router
from app.dashboard import router as dashboard_router

app = FastAPI(title="Pi Onboarding Console")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/captures", StaticFiles(directory=CAPTURE_DIR), name="captures")
for r in (dashboard_router, camera_router, wifi_router, connect_router, system_router):
    app.include_router(r)
```

- **Templates**: one `Jinja2Templates` instance in `app/config.py`, imported by each router.
  Every page `{% extends "base.html" %}`. `base.html` holds the nav bar and the global CSS
  link so feature pages stay tiny.
- **Camera lifecycle**: the camera object is a process-wide singleton created lazily on first
  use (not at import) and torn down in a FastAPI `lifespan` handler, so `wifi`/`connect` work
  even on a box with no camera attached.
- **Long actions**: run the subprocess in a thread (`await anyio.to_thread.run_sync(...)`) so
  the event loop isn't blocked. `wifi connect` returns fast + page polls `/wifi/status`.
  `connect signin` holds the request open until `rpi-connect signin` exits (block-until-verified,
  see below) — give that route a long timeout.

---

## Privilege model — sudo allowlist

The app runs as the **current login user** (the `pi` user, or whoever starts it) — *not* a
dedicated `pi-console` account and *not* root. This keeps the `rpi-connect` user service and
its DBus/`XDG_RUNTIME_DIR` session working with no linger setup. State-changing *system* calls
(Wi‑Fi) still go through `sudo`; `rpi-connect` runs directly as the user.

Every state-changing system call goes through one helper:

```python
# app/shell.py
import subprocess, shlex

SUDO = ["sudo", "-n"]          # -n: never prompt; fail if no cached/NOPASSWD rule

def run(cmd: list[str], *, timeout=30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)

def sudo(cmd: list[str], **kw):
    return run([*SUDO, *cmd], **kw)
```

Read-only calls (`nmcli -t -f ... dev wifi`, `rpi-connect status`) run **without** sudo where
possible. Only mutations use `sudo(...)`.

`deploy/sudoers.d/pi-console` — exact commands only, `NOPASSWD`. Replace `pi` with the actual
login user at install time (`whoami`). Wi‑Fi only; `rpi-connect` is **not** here (runs as the
user directly):

```
# Wi-Fi (NetworkManager) — profiles are written by the app as keyfiles, then activated
pi ALL=(root) NOPASSWD: /usr/bin/nmcli connection reload
pi ALL=(root) NOPASSWD: /usr/bin/nmcli connection up *
pi ALL=(root) NOPASSWD: /usr/bin/nmcli connection down *
pi ALL=(root) NOPASSWD: /usr/bin/nmcli connection delete *
pi ALL=(root) NOPASSWD: /usr/bin/nmcli radio wifi *
pi ALL=(root) NOPASSWD: /usr/bin/tee /etc/NetworkManager/system-connections/*
```

Notes / decisions to lock down on the real Pi:
- **No `nmcli device wifi connect`** — password would be in argv. Instead the app *writes the
  connection profile itself* (see Wi‑Fi flow below) and only ever runs
  `nmcli connection up <label>` via sudo.
- The `tee` rule is how the unprivileged app drops the `0600 root:root` keyfile into
  `/etc/NetworkManager/system-connections/` (`nmcli con up` refuses a keyfile that isn't
  `root`-owned `0600`). Alternative: give the app group-write on that dir and skip `tee`.
- Validate/whitelist arguments in `service.py` before building the command (SSID length, no
  control chars, label is `[A-Za-z0-9_-]+`); pass args as a list (never `shell=True`).
- **Never log** the PSK; redact it from any `nmcli`/error output surfaced to the UI.

---

## Feature details

### Wi‑Fi  (`app/wifi/`)

| Endpoint | Method | Backend command |
|---|---|---|
| `/wifi` | GET | page |
| `/wifi/status` | GET | `nmcli -t -f NAME,DEVICE,TYPE,STATE connection show --active` + `nmcli -t -f IN-USE,SSID,SIGNAL,SECURITY dev wifi` |
| `/wifi/scan` | GET | `nmcli -t -f SSID,SIGNAL,SECURITY,IN-USE dev wifi list --rescan yes` |
| `/wifi/connect` | POST `{ssid, password?}` | write keyfile → `sudo nmcli connection reload` → `sudo nmcli connection up <label>` |
| `/wifi/forget` | POST `{ssid}` | `sudo nmcli connection delete id <label>` |

- Parse `nmcli -t` (terminal/colon-separated, `-e` escaping) into dataclasses — stable to parse.
- `status` response feeds both the Wi‑Fi page and the dashboard status card.

**Connect flow (keyfile, no secret in argv):**

1. `label = "pi-console-" + slug(ssid)` (deterministic, so re-connecting updates in place).
2. Render a NetworkManager keyfile:

   ```ini
   [connection]
   id=<label>
   type=wifi
   [wifi]
   mode=infrastructure
   ssid=<ssid>
   [wifi-security]
   key-mgmt=wpa-psk
   psk=<password>
   [ipv4]
   method=auto
   [ipv6]
   method=auto
   ```

   (open network → omit `[wifi-security]`.)
3. Write it `0600` to `/etc/NetworkManager/system-connections/<label>.nmconnection` via the
   `sudo tee` rule, then `sudo nmcli connection reload`.
4. `sudo nmcli connection up <label>` — validates the PSK by actually associating.
5. On failure, `sudo nmcli connection delete <label>` so a bad profile doesn't linger, and
   return the (PSK-redacted) error.

- Guard: connecting may drop the AP you're browsing from → you lose the page. Warn before
  submit; after step 4 return immediately with "attempting…" and have the page poll `status`
  (it may need to be reloaded from the new network).

### Raspberry Pi Connect  (`app/connect/`)

| Endpoint | Method | Backend command |
|---|---|---|
| `/connect` | GET | page |
| `/connect/status` | GET | `rpi-connect status` (parse Signed in / Screen sharing / Remote shell) |
| `/connect/signin` | POST | `rpi-connect signin` → parse the `https://connect.raspberrypi.com/verify/XXXX-XXXX` URL + code from stdout, then **hold the request open until the command exits** (verified or timed out) |
| `/connect/on` / `/connect/off` | POST | `rpi-connect on` / `off` |

- `rpi-connect signin` prints the verify URL/code, then blocks until the user completes
  verification in a browser. Chosen behavior: **block until verified.** Run it in a worker
  thread; the request returns the URL/code *and* the final result together. Downside: one
  long-held HTTP request (set a generous client + server timeout, e.g. 5 min). Iterate later
  toward: return code immediately → poll `/connect/status`.
- Implementation sketch: spawn `rpi-connect signin` with `Popen`, read stdout line-by-line
  until the verify URL appears, stash it where `/connect/status` can report it, then `wait()`.
- Runs as the current user — no sudo, no linger (user has an active session).
- Preconditions to show on the page: package installed (`which rpi-connect`), `rpi-connect
  doctor` output, current `rpi-connect status`.

### System  (`app/system/`)

Read-only. `hostname -I`, `vcgencmd measure_temp` (or `/sys/class/thermal/...`), `uptime -p`,
`df -h /`, model from `/proc/device-tree/model`. Pure display; no sudo.

### Camera  (`app/camera/`)

Straight move of today's code. Route prefix changes `/` → `/camera`, `/stream` →
`/camera/stream`, `/capture` → `/camera/capture`. Dashboard shows a small thumbnail linking in.

---

## Frontend

- Keep it **server-rendered + vanilla JS**. No build step, works offline on the Pi.
- `base.html`: top nav (Dashboard · Camera · Wi‑Fi · Connect · System), `<main>{% block content %}`.
- `static/app.js`: `getJSON(url)` / `postJSON(url, body)` helpers + a `poll(url, fn, ms)` helper
  for the async actions. Each page has a `<script>` block wiring its own buttons.
- Dashboard cards each fetch their feature's `/status` on load and render a one-line summary
  (e.g. "Wi‑Fi: MyNet (72%)", "Connect: signed in, screen sharing off").

---

## Migration steps

1. Create `app/` package; move camera code into `app/camera/{backends,service}.py` unchanged.
2. Add `app/config.py`; move the module-level constants + `Jinja2Templates` there.
3. Add `app/shell.py` (`run` / `sudo`).
4. Wrap camera routes in an `APIRouter(prefix="/camera")`; add `app/dashboard.py` for `/`.
5. Slim `main.py` to the composition snippet above; add `lifespan` for camera teardown.
6. Add `templates/base.html`; convert `index.html` → `camera.html` (`{% extends %}`), add
   `dashboard.html`.
7. Build Wi‑Fi feature (service + router + page); add `deploy/sudoers.d/pi-console` (substitute
   real user), test the keyfile → `connection up` flow.
8. Build Pi Connect feature (block-until-verified signin).
9. Add `system` feature.
10. Add `deploy/onboarding.service` — a `systemctl --user` unit
    (`WantedBy=default.target`) so it inherits the user session bus rpi-connect
    needs; `loginctl enable-linger` for boot start. Document install: sudoers,
    `pip install`, enable service.

Steps 1–6 are pure refactor (no behavior change) and can land first.

---

## Decisions (resolved)

- **Service user:** the current login user (e.g. `pi`). Not isolated, but no linger/DBus setup
  and `rpi-connect` works out of the box.
- **Network stack:** NetworkManager / `nmcli` (Bookworm default). Not supporting
  `dhcpcd`/`wpa_supplicant`.
- **Wi‑Fi secret handling:** app writes a `0600` NM keyfile, then `sudo nmcli connection up
  <label>`. No PSK in argv, ever.
- **`/connect/signin`:** blocks until `rpi-connect signin` exits (verified or timeout).
  Acceptable for v1; revisit toward return-code-then-poll if the long request is a problem.

## Still open

- Keyfile drop mechanism: `sudo tee` rule vs. group-write on
  `/etc/NetworkManager/system-connections/`. Pick during step 7 on the real Pi.
- `signin` request timeout value (client + uvicorn) — start at 5 min.
- systemd: `--user` unit vs. system unit with `User=pi` — decide in step 10.
