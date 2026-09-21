"""HTTP surface for Raspberry Pi Connect.

POST /connect/signin is intentionally long-lived: it holds the request open
until `rpi-connect signin` finishes. The page polls GET /connect/signin/status
meanwhile to show the verification link.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.connect import service

router = APIRouter(prefix="/connect", tags=["connect"])


@router.get("/status")
async def status():
    return await run_in_threadpool(service.status)


@router.get("/signin/status")
async def signin_status():
    return await run_in_threadpool(service.signin_progress)


@router.post("/signin")
async def signin():
    try:
        return await run_in_threadpool(service.signin)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=409)


@router.post("/on")
async def on():
    try:
        await run_in_threadpool(service.enable)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/off")
async def off():
    try:
        await run_in_threadpool(service.disable)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
