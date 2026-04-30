import asyncio

from shared.infra.event_bus import event_bus
from shared.integrations.openproject.client import get_op_client
from shared.schemas.event import Event, EventTypes


async def main():
    client = get_op_client()
    wps = await client.get_work_packages(project_id=72)

    # Build parent_ids set to find leaf tasks
    parent_ids = set()
    for wp in wps:
        parent_href = wp.get("_links", {}).get("parent", {}).get("href", "")
        if parent_href:
            try:
                parent_ids.add(int(parent_href.split("/")[-1]))
            except (ValueError, IndexError):
                pass

    await event_bus.connect()

    count = 0
    for wp in wps:
        wp_type = wp.get("_links", {}).get("type", {}).get("title", "")
        if wp_type == "Task" and wp["id"] not in parent_ids:
            assignee_title = wp.get("_links", {}).get("assignee", {}).get("title", "")
            assignee_href = wp.get("_links", {}).get("assignee", {}).get("href", "")
            assignee_id = int(assignee_href.split("/")[-1]) if assignee_href else None
            desc_raw = wp.get("description", {})
            description = desc_raw.get("raw", "") if isinstance(desc_raw, dict) else ""
            project_name = wp.get("_links", {}).get("project", {}).get("title", "")

            evt = Event.create(
                event_type=EventTypes.SYNC_TASK_NEEDS_DECOMPOSE,
                source_agent="batch-task-check",
                payload={
                    "wp_id": wp["id"],
                    "subject": wp["subject"],
                    "description": description,
                    "wp_type": "Task",
                    "project_id": 72,
                    "project_name": project_name,
                    "assignee": assignee_title,
                    "assignee_id": assignee_id,
                },
            )
            await event_bus.publish(evt)
            count += 1
            print("Published: WP#" + str(wp["id"]) + " " + wp["subject"])

    await event_bus.disconnect()
    print("\nTotal: " + str(count) + " task check events published")

asyncio.run(main())
