"""HTTP surface for Wi-Fi management."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app import config
from app.wifi import service

router = APIRouter(prefix="/wifi", tags=["wifi"])


class ConnectBody(BaseModel):
    ssid: str
    password: str | None = None


class SsidBody(BaseModel):
    ssid: str


@router.get("", response_class=HTMLResponse)
def page(request: Request):
    return config.templates.TemplateResponse(request, "wifi.html")


@router.get("/status")
async def status():
    try:
        return await run_in_threadpool(service.status)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/scan")
async def scan(rescan: bool = False):
    try:
        networks = await run_in_threadpool(service.scan, rescan)
        saved = await run_in_threadpool(service.saved)
        return {"networks": networks, "saved": saved}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/connect")
async def connect(body: ConnectBody):
    try:
        result = await run_in_threadpool(service.connect, body.ssid, body.password)
        return {"ok": True, **result}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@router.post("/forget")
async def forget(body: SsidBody):
    try:
        result = await run_in_threadpool(service.forget, body.ssid)
        return {"ok": True, **result}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
