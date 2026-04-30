"""Admin endpoints for channel gateway."""
from fastapi import APIRouter, HTTPException

from shared.messaging.outbound.core.registry import AdapterRegistry

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/adapters")
async def list_adapters():
    """List all registered adapters."""
    adapters = AdapterRegistry.default().list_all()
    return {
        "adapters": [
            {
                "channel_id": a.channel_id,
                "channel_name": a.channel_name,
                "status": a.status.value,
                "capabilities": [c.value for c in a.capabilities],
            }
            for a in adapters
        ]
    }


@router.get("/adapters/{channel_id}")
async def get_adapter(channel_id: str):
    """Get adapter details."""
    adapter = AdapterRegistry.default().get(channel_id)
    if not adapter:
        raise HTTPException(status_code=404, detail="Adapter not found")

    return {
        "channel_id": adapter.channel_id,
        "channel_name": adapter.channel_name,
        "status": adapter.status.value,
        "capabilities": [c.value for c in adapter.capabilities],
    }
