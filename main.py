#!/usr/bin/env python3
"""Pi Onboarding Console — entrypoint.

A small web console that runs on a Raspberry Pi and is opened from a browser on
the same LAN. Features: camera (live MJPEG + still), Wi-Fi management, Raspberry
Pi Connect setup, read-only system info.

See docs/multi-feature-plan.md for the design.

Install:
    python3 -m venv .venv && . .venv/bin/activate
    pip install -r requirements.txt
    sudo apt install -y python3-picamera2          # Pi Camera backend
    # Wi-Fi feature needs the sudoers allowlist:
    #   see deploy/sudoers.d/pi-console

Run:
    python3 main.py            # http://<pi-ip>:8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import config
from app.camera import service as camera_service
from app.camera.router import router as camera_router
from app.connect.router import router as connect_router
from app.dashboard import router as dashboard_router
from app.system.router import router as system_router
from app.wifi.router import router as wifi_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    camera_service.shutdown_camera()


app = FastAPI(title="Pi Onboarding Console", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")
app.mount("/captures", StaticFiles(directory=str(config.CAPTURE_DIR)), name="captures")

for _router in (
    dashboard_router,
    camera_router,
    wifi_router,
    connect_router,
    system_router,
):
    app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT)
