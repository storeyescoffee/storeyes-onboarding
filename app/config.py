"""Central configuration. Import `config` anywhere; never hard-code paths."""

import getpass
from pathlib import Path

from fastapi.templating import Jinja2Templates

# --- Paths ------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
CAPTURE_DIR = BASE_DIR / "captures"
CAPTURE_DIR.mkdir(exist_ok=True)

# OS account the app runs as. All docs/sudoers refer to this user.
SERVICE_USER = getpass.getuser()

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# --- Camera ---------------------------------------------------------------
CAMERA_BACKEND = "picamera2"       # "picamera2" (Pi Camera) or "usb" (UVC webcam)
USB_DEVICE = "<video0>"            # imageio device id, only for the "usb" backend

STREAM_W, STREAM_H = 1280, 720     # what the browser sees (lores)
STILL_W, STILL_H = 1920, 1080      # what /camera/capture saves (main)
FPS = 15
FRAME_INTERVAL = 1.0 / FPS
JPEG_QUALITY = 80

# --- Server -------------------------------------------------------------
HOST = "0.0.0.0"
PORT = 8000
