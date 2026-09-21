"""HTTP surface for triggering storeyes-agent on demand."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.agent import service

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/run")
async def run():
    result = await run_in_threadpool(service.trigger)
    if not result["triggered"]:
        return JSONResponse(result, status_code=502)
    return result
