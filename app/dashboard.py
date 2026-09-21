"""Root health/status endpoint. No web UI here — the frontend is
storeyes-fast-onboarding; this service is API-only. See each feature's own
router (camera, wifi, connect, system, agent) for the actual endpoints.
"""

from fastapi import APIRouter

router = APIRouter(tags=["dashboard"])


@router.get("/")
def root():
    return {"service": "storeyes-onboarding", "status": "ok"}
