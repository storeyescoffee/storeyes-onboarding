"""JPEG-native camera backends. No OpenCV.

- Picamera2Backend: hardware MJPEG encoder on the lores stream, full-res still
  from the main stream.
- UsbBackend: imageio (ffmpeg) grab + simplejpeg encode in a background thread.

Heavy imports (picamera2, imageio) happen inside __init__ so a box without a
camera can still run the Wi-Fi / Connect / System features.
"""

from __future__ import annotations

import io
import threading
import time

from app import config


class _JpegSink(io.BufferedIOBase):
    """FileOutput-compatible sink that keeps only the most recent JPEG frame.
    Must subclass io.BufferedIOBase — picamera2's FileOutput enforces it."""

    def __init__(self):
        super().__init__()
        self.frame: bytes | None = None
        self.cond = threading.Condition()

    def writable(self) -> bool:
        return True

    def write(self, buf) -> int:
        data = bytes(buf)
        with self.cond:
            self.frame = data
            self.cond.notify_all()
        return len(data)

    def flush(self) -> None:  # noqa: D401 - part of the IO contract
        pass


class Picamera2Backend:
    def __init__(self):
        from picamera2 import Picamera2
        from picamera2.encoders import MJPEGEncoder
        from picamera2.outputs import FileOutput

        self._picam = Picamera2()
        cfg = self._picam.create_video_configuration(
            main={"size": (config.STILL_W, config.STILL_H)},
            lores={"size": (config.STREAM_W, config.STREAM_H)},
            display="lores",
            controls={"FrameRate": config.FPS},
        )
        self._picam.configure(cfg)

        self._sink = _JpegSink()
        encoder = MJPEGEncoder()
        encoder.frame_rate = config.FPS
        self._picam.start_recording(
            encoder, FileOutput(self._sink), name="lores"
        )
        time.sleep(1)  # let the encoder produce the first frame

    def get_frame(self) -> bytes | None:
        with self._sink.cond:
            if self._sink.frame is None:
                self._sink.cond.wait(timeout=2)
            return self._sink.frame

    def snapshot_bytes(self) -> bytes:
        buf = io.BytesIO()
        self._picam.capture_file(buf, name="main", format="jpeg")
        return buf.getvalue()

    def close(self) -> None:
        try:
            self._picam.stop_recording()
        finally:
            self._picam.close()


class UsbBackend:
    def __init__(self):
        import imageio.v3 as iio
        import simplejpeg

        self._simplejpeg = simplejpeg
        self._reader = iio.imiter(config.USB_DEVICE, plugin="pyav", fps=config.FPS)
        self._lock = threading.Lock()
        self._frame: bytes | None = None
        self._stop = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

        for _ in range(50):  # wait up to ~5s for the first frame
            if self._frame is not None:
                break
            time.sleep(0.1)

    def _loop(self) -> None:
        for rgb in self._reader:  # rgb: HxWx3 uint8
            if self._stop.is_set():
                break
            jpg = self._simplejpeg.encode_jpeg(
                rgb, quality=config.JPEG_QUALITY, colorspace="RGB"
            )
            with self._lock:
                self._frame = jpg

    def get_frame(self) -> bytes | None:
        with self._lock:
            return self._frame

    def snapshot_bytes(self) -> bytes | None:
        return self.get_frame()

    def close(self) -> None:
        self._stop.set()
