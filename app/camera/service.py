"""Camera lifecycle + frame helpers, independent of FastAPI.

The camera is a lazily-created process-wide singleton: nothing touches the
hardware until the first stream/capture request, and `shutdown_camera()` (called
from the app lifespan) releases it.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime

from app import config
from app.camera.backends import Picamera2Backend, UsbBackend

_camera = None
_lock = threading.Lock()


def _make_camera():
    if config.CAMERA_BACKEND == "picamera2":
        return Picamera2Backend()
    if config.CAMERA_BACKEND == "usb":
        return UsbBackend()
    raise ValueError(f"Unknown CAMERA_BACKEND: {config.CAMERA_BACKEND!r}")


def get_camera():
    global _camera
    with _lock:
        if _camera is None:
            _camera = _make_camera()
        return _camera


def camera_initialized() -> bool:
    return _camera is not None


def shutdown_camera() -> None:
    global _camera
    with _lock:
        if _camera is not None:
            close = getattr(_camera, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
            _camera = None


def save_snapshot() -> str:
    frame = get_camera().snapshot_bytes()
    if frame is None:
        raise RuntimeError("No frame available yet")
    filename = f"capture_{datetime.now():%Y%m%d_%H%M%S}.jpg"
    (config.CAPTURE_DIR / filename).write_bytes(frame)
    return filename


def mjpeg_generator():
    cam = get_camera()
    last = None
    while True:
        frame = cam.get_frame()
        if frame is not None and frame is not last:
            last = frame
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n"
                + frame + b"\r\n"
            )
        time.sleep(config.FRAME_INTERVAL)
