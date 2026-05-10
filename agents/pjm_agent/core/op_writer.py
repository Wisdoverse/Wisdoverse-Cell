"""Write WBS decomposition results to OpenProject as child work packages."""

from shared.core import OpenProjectWorkPackagePort
from shared.utils.logger import get_logger

logger = get_logger("pjm_agent.op_writer")

# OpenProject work package type IDs configured for this deployment.
TYPE_USER_STORY = 272
TYPE_TASK = 267


class OPWriterService:
    def __init__(self, op_client: OpenProjectWorkPackagePort):
        self._op = op_client

    async def write_wbs(
        self,
        parent_wp_id: int,
        project_id: int,
        wbs_result: dict,
        assignee_id: int | None = None,
    ) -> dict:
        stories_created = 0
        tasks_created = 0
        errors = []

        for subtask in wbs_result.get("subtasks", []):
            try:
                us_data = {
                    "subject": subtask["subject"],
                    "_links": {
                        "parent": {"href": f"/api/v3/work_packages/{parent_wp_id}"},
                        "type": {"href": f"/api/v3/types/{TYPE_USER_STORY}"},
                    },
                }
                days = subtask.get("estimated_days", 1)
                us_data["estimatedTime"] = f"PT{days * 8}H"

                if assignee_id:
                    us_data["_links"]["assignee"] = {"href": f"/api/v3/users/{assignee_id}"}

                us_wp = await self._op.create_work_package(project_id, us_data)
                us_wp_id = us_wp["id"]
                stories_created += 1
                logger.info("us_created", wp_id=us_wp_id, subject=subtask["subject"])

                for child in subtask.get("children", []):
                    try:
                        task_data = {
                            "subject": child["subject"],
                            "_links": {
                                "parent": {"href": f"/api/v3/work_packages/{us_wp_id}"},
                                "type": {"href": f"/api/v3/types/{TYPE_TASK}"},
                            },
                        }
                        hours = child.get("estimated_hours", 4)
                        task_data["estimatedTime"] = f"PT{hours}H"

                        task_wp = await self._op.create_work_package(project_id, task_data)
                        tasks_created += 1
                        logger.info("task_created", wp_id=task_wp["id"], subject=child["subject"])
                    except Exception as e:
                        logger.error("task_create_failed", error=str(e), subject=child["subject"])
                        errors.append(f"Task '{child['subject']}': {e}")

            except Exception as e:
                logger.error("us_create_failed", error=str(e), subject=subtask["subject"])
                errors.append(f"US '{subtask['subject']}': {e}")

        return {
            "stories_created": stories_created,
            "tasks_created": tasks_created,
            "errors": errors,
        }

    async def write_task_subtasks(
        self,
        parent_wp_id: int,
        project_id: int,
        subtasks: list[dict],
        assignee_id: int | None = None,
    ) -> dict:
        tasks_created = 0
        errors = []

        for task in subtasks:
            try:
                task_data = {
                    "subject": task["subject"],
                    "_links": {
                        "parent": {"href": f"/api/v3/work_packages/{parent_wp_id}"},
                        "type": {"href": f"/api/v3/types/{TYPE_TASK}"},
                    },
                }
                hours = task.get("estimated_hours", 4)
                task_data["estimatedTime"] = f"PT{hours}H"

                if assignee_id:
                    task_data["_links"]["assignee"] = {"href": f"/api/v3/users/{assignee_id}"}

                wp = await self._op.create_work_package(project_id, task_data)
                tasks_created += 1
                logger.info("subtask_created", wp_id=wp["id"], subject=task["subject"])
            except Exception as e:
                logger.error("subtask_create_failed", error=str(e), subject=task["subject"])
                errors.append(f"Task '{task['subject']}': {e}")

        return {"tasks_created": tasks_created, "errors": errors}
