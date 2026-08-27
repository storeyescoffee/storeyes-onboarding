"""HTTP surface for the read-only System page."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from app import config
from app.system import service

router = APIRouter(prefix="/system", tags=["system"])


@router.get("", response_class=HTMLResponse)
def page(request: Request):
    return config.templates.TemplateResponse(request, "system.html")


@router.get("/info")
async def info():
    return await run_in_threadpool(service.info)
