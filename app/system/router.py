"""HTTP surface for the read-only System info."""

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from app.system import service

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/info")
async def info():
    return await run_in_threadpool(service.info)
