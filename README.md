# Pi Onboarding Console

A small web console that runs on a Raspberry Pi and is opened from a browser on
the same LAN. Features:

- **Camera** — live 15 FPS MJPEG stream + full-res still capture (no OpenCV)
- **Wi-Fi** — scan, connect, forget, show current connection (NetworkManager)
- **Raspberry Pi Connect** — status, sign-in, enable/disable
- **System** — read-only device info (hostname, IP, temperature, uptime, disk)

Design notes: [docs/multi-feature-plan.md](docs/multi-feature-plan.md).

## Layout

```
main.py              entrypoint (builds the app, includes routers)
app/
  config.py          all tunables (camera res/fps, port, paths)
  shell.py           run() / sudo() subprocess helpers
  dashboard.py       "/"
  camera/  wifi/  connect/  system/
                     each: service.py (logic, no FastAPI) + router.py (HTTP only)
templates/           base.html + one page per feature (Jinja2)
static/              app.css, app.js
deploy/              sudoers allowlist + systemd user unit
```

## Install (Raspberry Pi OS Bookworm)

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# Pi Camera backend:
sudo apt install -y python3-picamera2
# USB webcam instead: set CAMERA_BACKEND="usb" in app/config.py and
#   pip install "imageio[ffmpeg]" simplejpeg

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

Or as a systemd **user** service (keeps `rpi-connect`'s session bus):

```bash
mkdir -p ~/.config/systemd/user
cp deploy/pi-console.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now pi-console
sudo loginctl enable-linger "$USER"      # run without being logged in
```

## Notes

- The app **never runs as root.** Wi-Fi changes go through the `sudo` allowlist
  in `deploy/sudoers.d/pi-console`; the Wi-Fi password is written into a
  `0600` NetworkManager keyfile, never passed on a command line.
- Changing Wi-Fi may drop the network you're browsing from — the page warns and
  then polls for the new status.
- `POST /connect/signin` is a long-lived request: it stays open until
  `rpi-connect signin` completes. The page polls `/connect/signin/status` to
  show the verification link while you wait.
