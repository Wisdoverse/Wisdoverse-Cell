"""Read-only HTTP verification against the independently owned Control Plane."""

import httpx

from ..core.domain.delivery_handoff import DeliveryHandoffCommand


class HttpDeliveryContextVerifier:
    def __init__(
        self,
        base_url: str,
        *,
        authorization: str,
        internal_key: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("delivery_context_endpoint_required")
        self._base_url = base_url.rstrip("/")
        self._authorization = authorization
        self._internal_key = internal_key
        self._transport = transport

    async def verify(self, command: DeliveryHandoffCommand) -> None:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=10,
                follow_redirects=False,
                transport=self._transport,
                headers={
                    "X-Control-Plane-Operator-Token": self._authorization,
                    "X-Internal-Key": self._internal_key,
                },
            ) as client:
                goal = await client.get(f"/api/v1/control-plane/goals/{command.goal_id}")
                work = await client.get(f"/api/v1/control-plane/work-items/{command.work_item_id}")
                goal.raise_for_status()
                work.raise_for_status()
                try:
                    goal_data, work_data = goal.json(), work.json()
                except ValueError as exc:
                    raise ValueError("delivery_context_unavailable") from exc
            if (
                goal_data.get("company_id") != command.company_id
                or work_data.get("company_id") != command.company_id
                or work_data.get("goal_id") != command.goal_id
                or work_data.get("status") in {"done", "completed", "cancelled"}
            ):
                raise ValueError("delivery_context_mismatch")
        except (httpx.HTTPError, TypeError, AttributeError) as exc:
            raise ValueError("delivery_context_unavailable") from exc
