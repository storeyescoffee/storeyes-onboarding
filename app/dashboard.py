"""Landing page ("/"). Feature status is filled in client-side from each
feature's own `/status` endpoint."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app import config

router = APIRouter(tags=["dashboard"])


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return config.templates.TemplateResponse(request, "dashboard.html")
