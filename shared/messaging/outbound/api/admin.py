"""Admin endpoints for channel gateway."""
from fastapi import APIRouter, Depends

from shared.api import raise_outbound_adapter_not_found
from shared.messaging.outbound.core.registry import AdapterRegistry
from shared.middleware.internal_auth import verify_internal_key

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(verify_internal_key)],
)


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
        raise_outbound_adapter_not_found()

    return {
        "channel_id": adapter.channel_id,
        "channel_name": adapter.channel_name,
        "status": adapter.status.value,
        "capabilities": [c.value for c in adapter.capabilities],
    }
