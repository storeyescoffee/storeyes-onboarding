# storeyes-onboarding

An **API-only** service that runs on a Raspberry Pi, reachable from the same
LAN. No web UI — the frontend is
[storeyes-fast-onboarding](https://github.com/storeyescoffee/storeyes-fast-onboarding),
a Tauri desktop app that talks to this API directly (CORS is wide open since
there's no auth here — same LAN-only trust model the old browser console had).
Features:

- **Camera** — live 15 FPS MJPEG stream + full-res still capture (no OpenCV)
- **Wi-Fi** — scan, connect, forget, show current connection (NetworkManager)
- **Raspberry Pi Connect** — status, sign-in, enable/disable
- **System** — read-only device info (hostname, IP, temperature, uptime, disk)

Independent of [storeyes-agent](https://github.com/storeyescoffee/storeyes-agent)
— that's a separate, unrelated service that happens to run on the same Pi.

Design notes: [docs/multi-feature-plan.md](docs/multi-feature-plan.md) (predates
the API-only switch, but the feature breakdown still applies).

## Layout

```
install.sh           one-shot installer (deps + sudoers + systemd user service)
main.py              entrypoint (builds the app, includes routers, CORS)
app/
  config.py          all tunables (camera res/fps, port, paths)
  shell.py           run() / sudo() subprocess helpers
  dashboard.py       "/" — health/status JSON only
  camera/  wifi/  connect/  system/
                     each: service.py (logic, no FastAPI) + router.py (HTTP only)
deploy/              sudoers allowlist + systemd user unit
```

## Install (Raspberry Pi OS Bookworm)

On the Pi, as the user the console should run as (**not** root):

```bash
git clone <this repo> ~/storeyes-onboarding && cd ~/storeyes-onboarding
./install.sh
```

That installs the apt dependencies (picking the camera packages from
`CAMERA_BACKEND` in `app/config.py`), the Wi-Fi sudoers allowlist scoped to your
account, and the systemd **user** service — then enables lingering and starts
it. It's idempotent, so re-run it after a `git pull`. Steps can be skipped with
`--skip-apt`, `--skip-sudoers`, `--skip-service` and `--no-connect`;
`./install.sh --help` lists them.

To remove it again:

```bash
./install.sh --uninstall
```

That stops and deletes the user service and the sudoers allowlist. The apt
packages are left alone, and so is lingering unless you add `--disable-linger`.
The same `--skip-*` flags apply, so `--uninstall --skip-sudoers` drops only the
service.

### By hand

```bash
# Deps, system-wide (Bookworm has them all in apt — no venv):
sudo apt install -y python3-fastapi python3-uvicorn python3-picamera2
# USB webcam instead: set CAMERA_BACKEND="usb" in app/config.py and
#   sudo apt install -y python3-imageio python3-simplejpeg
#
# Prefer a venv? python3 -m venv --system-site-packages .venv
#   (--system-site-packages so it can see python3-picamera2)

# Wi-Fi feature needs the sudoers allowlist (runs as your user, not root):
sudo cp deploy/sudoers.d/pi-console /etc/sudoers.d/pi-console
sudo sed -i "s/^pi /$(whoami) /" /etc/sudoers.d/pi-console
sudo chmod 440 /etc/sudoers.d/pi-console && sudo chown root:root /etc/sudoers.d/pi-console
sudo visudo -c

# Raspberry Pi Connect (optional):
sudo apt install -y rpi-connect
```

## Run

```bash
python3 main.py            # http://<pi-ip>:8000
```

Or as a systemd **user** service (keeps `rpi-connect`'s session bus) — this is
what `./install.sh` sets up; by hand it is:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/onboarding.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now onboarding
sudo loginctl enable-linger "$USER"      # run at boot / without being logged in
```

## Notes

- The app **never runs as root.** Wi-Fi changes go through the `sudo` allowlist
  in `deploy/sudoers.d/pi-console`; the Wi-Fi password is written into a
  `0600` NetworkManager keyfile, never passed on a command line.
- Changing Wi-Fi may drop the connection the client reached this API over —
  callers should expect that and poll `/wifi/status` afterward.
- `POST /connect/signin` is a long-lived request: it stays open until
  `rpi-connect signin` completes. Callers poll `/connect/signin/status`
  meanwhile to show the verification link.
