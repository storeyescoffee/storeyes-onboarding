#!/usr/bin/env python3
"""storeyes-onboarding — entrypoint.

An API-only service that runs on a Raspberry Pi: camera (live MJPEG + still),
Wi-Fi management, Raspberry Pi Connect setup, read-only system info, and
triggering storeyes-agent on demand. No web UI here — the frontend is
storeyes-fast-onboarding (a Tauri desktop app), which talks to this API
directly over the LAN.

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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import config
from app.agent.router import router as agent_router
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


app = FastAPI(title="storeyes-onboarding", lifespan=lifespan)

# No auth on this API — it's a LAN-only device endpoint, same trust model as
# the old single-origin web console. The frontend now runs from a different
# origin entirely (a Tauri app), so it needs this to read JSON responses.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/captures", StaticFiles(directory=str(config.CAPTURE_DIR)), name="captures")

for _router in (
    dashboard_router,
    camera_router,
    wifi_router,
    connect_router,
    system_router,
    agent_router,
):
    app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT)
