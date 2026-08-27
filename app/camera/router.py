"""HTTP surface for the camera feature. Routes only — logic lives in service.py."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from app import config
from app.camera import service

router = APIRouter(prefix="/camera", tags=["camera"])


@router.get("", response_class=HTMLResponse)
def page(request: Request):
    return config.templates.TemplateResponse(
        request, "camera.html", {"fps": config.FPS}
    )


@router.get("/status")
def status():
    return {
        "backend": config.CAMERA_BACKEND,
        "initialized": service.camera_initialized(),
        "stream_resolution": [config.STREAM_W, config.STREAM_H],
        "still_resolution": [config.STILL_W, config.STILL_H],
        "fps": config.FPS,
    }


@router.get("/stream")
def stream():
    return StreamingResponse(
        service.mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.post("/capture")
def capture():
    try:
        name = service.save_snapshot()
        return {"ok": True, "url": f"/captures/{name}", "name": name}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
