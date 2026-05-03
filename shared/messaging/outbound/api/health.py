"""Health check endpoints."""
from fastapi import APIRouter, Depends

from shared.messaging.outbound.core.registry import AdapterRegistry
from shared.middleware.internal_auth import verify_internal_key

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@router.get("/health/adapters", dependencies=[Depends(verify_internal_key)])
async def adapter_health():
    """Get status of all adapters."""
    adapters = AdapterRegistry.default().list_all()
    return {
        "adapters": [
            {
                "channel_id": a.channel_id,
                "channel_name": a.channel_name,
                "status": a.status.value,
            }
            for a in adapters
        ]
    }
