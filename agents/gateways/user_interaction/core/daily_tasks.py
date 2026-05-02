"""Daily task dispatch (9:00) and progress collection (17:30)."""
import json
from datetime import datetime, timedelta, timezone

from shared.config import settings
from shared.infra.llm_gateway import llm_gateway
from shared.integrations.feishu.bitable import bitable_service
from shared.integrations.feishu.client import get_feishu_client
from shared.utils.logger import get_logger

from ..db.database import db_manager
from ..db.repository import DailyProgressRepository

logger = get_logger("chat_agent.daily_tasks")

_SHANGHAI_TZ = timezone(timedelta(hours=8))
_ACTIVE_STATUSES = {"待办", "进行中", "阻塞(Blocked)"}


async def _get_members() -> list[dict]:
    """Fetch all members from the member table. Returns list of {open_id, name, record_id}."""
    result = await bitable_service.list_records(
        app_token=settings.feishu_bitable_app_token,
        table_id=settings.feishu_bitable_member_table_id,
        page_size=100,
    )
    members = []
    for record in result.get("items", []):
        fields = record.get("fields", {})
        person_fields = [
            v for v in fields.values()
            if isinstance(v, list) and v
            and isinstance(v[0], dict)
            and str(v[0].get("id", "")).startswith("ou_")
        ]
        if not person_fields:
            continue
        open_id = person_fields[0][0]["id"]
        name = person_fields[0][0].get("name", "")
        if not name:
            for v in fields.values():
                if isinstance(v, str) and v and not v.startswith("ou_") and not v.startswith("rec"):
                    name = v
                    break
        if open_id:
            members.append({"open_id": open_id, "name": name, "record_id": record["record_id"]})
    return members


async def _get_user_tasks(member_record_id: str) -> list[dict]:
    """Get active tasks for a user from Bitable main table.

    DRI field is a linked-record pointing to the member table via record_ids.
    """
    result = await bitable_service.list_records(
        app_token=settings.feishu_bitable_app_token,
        table_id=settings.feishu_bitable_table_id,
        page_size=50,
    )
    tasks = []
    for record in result.get("items", []):
        fields = record.get("fields", {})
        status = fields.get("状态", "")
        if status not in _ACTIVE_STATUSES:
            continue
        dri = fields.get("DRI (负责人)", [])
        if isinstance(dri, list):
            dri_record_ids = []
            for entry in dri:
                if isinstance(entry, dict):
                    dri_record_ids.extend(entry.get("record_ids", []))
            if member_record_id not in dri_record_ids:
                continue
        else:
            continue
        title = fields.get("任务(动宾短语)", "")
        priority = fields.get("优先级", "Normal")
        tasks.append({
            "record_id": record["record_id"],
            "title": title,
            "priority": priority,
            "status": status,
            "due_date": fields.get("计划完成日期", ""),
        })
    return tasks


# Bitable 状态 → DailyProgress 初始状态映射
_STATUS_MAP = {
    "待办": "pending",
    "进行中": "in_progress",
    "阻塞(Blocked)": "blocked",
}


async def _generate_dispatch_message(name: str, tasks: list[dict]) -> str:
    """Call Claude via LLMGateway to generate a personalized morning dispatch."""
    task_lines = []
    for t in tasks:
        due = t.get("due_date", "")
        task_lines.append(
            f"- {t['title']} | 状态: {t['status']}"
            f" | 优先级: {t['priority']}"
            f" | 截止: {due or '未设定'}"
        )
    task_block = "\n".join(task_lines)

    today_str = datetime.now(_SHANGHAI_TZ).strftime("%Y-%m-%d %A")

    prompt = f"""你是一个顶级项目管理经理。今天是 {today_str}。
以下是 {name} 当前的活跃任务：

{task_block}

请为 {name} 生成一条简洁的晨间工作消息（纯文本，不超过300字）：
1. 先总览：几个进行中、几个阻塞、几个待办
2. 对阻塞任务：追问具体阻塞原因，需要什么支持
3. 对进行中任务：询问预计完成时间
4. 对待办任务：建议今天优先处理哪些（结合优先级）
5. 语气专业温暖，像一个关心团队的PM

直接输出消息内容，不要加任何前缀说明。"""

    return await llm_gateway.complete(
        prompt=prompt,
        agent_id="chat-agent",
        task_type="daily_dispatch",
        max_tokens=500,
    )


async def dispatch_morning_tasks():
    """9:00 AM - Send each employee their active tasks with AI-generated analysis."""
    logger.info("morning_dispatch_start")
    try:
        members = await _get_members()
        client = get_feishu_client()
        today = datetime.now(_SHANGHAI_TZ).date()
        dispatched = 0

        for member in members:
            open_id = member["open_id"]
            name = member["name"]
            tasks = await _get_user_tasks(member["record_id"])
            if not tasks:
                continue

            try:
                text = await _generate_dispatch_message(name, tasks)
            except Exception as e:
                logger.warning("claude_dispatch_fallback", user=name, error=str(e))
                lines = [f"早上好 {name}！你当前有 {len(tasks)} 个活跃任务：\n"]
                for i, t in enumerate(tasks, 1):
                    lines.append(f"{i}. [{t['status']}] {t['title']} [{t['priority']}]")
                lines.append("\n加油，祝今天高效顺利 🚀")
                text = "\n".join(lines)

            try:
                content = json.dumps({"text": text}, ensure_ascii=False)
                await client.send_message(
                    receive_id=open_id, receive_id_type="open_id",
                    msg_type="text", content=content,
                )
                dispatched += 1
            except Exception as e:
                logger.error("dispatch_send_failed", user=name, error=str(e))
                continue

            async with db_manager.session() as session:
                repo = DailyProgressRepository(session)
                await repo.create_batch([
                    {
                        "user_id": open_id,
                        "user_name": name,
                        "date": today,
                        "task_record_id": t["record_id"],
                        "task_title": t["title"],
                        "status": _STATUS_MAP.get(t["status"], "pending"),
                    }
                    for t in tasks
                ])

        logger.info("morning_dispatch_done", dispatched=dispatched, total_members=len(members))
    except Exception as e:
        logger.error("morning_dispatch_failed", error=str(e))


async def collect_evening_progress():
    """5:30 PM - Ask each employee to report progress."""
    logger.info("evening_collect_start")
    try:
        today = datetime.now(_SHANGHAI_TZ).date()
        client = get_feishu_client()
        asked = 0

        async with db_manager.session() as session:
            repo = DailyProgressRepository(session)
            from sqlalchemy import select

            from ..models.daily_progress import DailyProgress
            stmt = select(DailyProgress.user_id, DailyProgress.user_name).where(
                DailyProgress.date == today
            ).distinct()
            result = await session.execute(stmt)
            users = result.all()

        for user_id, user_name in users:
            async with db_manager.session() as session:
                repo = DailyProgressRepository(session)
                progress_list = await repo.get_pending(user_id, today)

            if not progress_list:
                continue

            lines = [f"{user_name}，下班前更新一下今天的进展吧：\n"]
            for i, p in enumerate(progress_list, 1):
                status_mark = "✅" if p.status == "completed" else "⬜"
                lines.append(f"{i}. {status_mark} {p.task_title}")
            lines.append('\n直接回复就行，比如"1完成了，2在调接口预计明天完，3阻塞等后端"')
            text = "\n".join(lines)

            try:
                content = json.dumps({"text": text}, ensure_ascii=False)
                await client.send_message(
                    receive_id=user_id, receive_id_type="open_id",
                    msg_type="text", content=content,
                )
                asked += 1
            except Exception as e:
                logger.error("collect_send_failed", user=user_name, error=str(e))

        logger.info("evening_collect_done", asked=asked)
    except Exception as e:
        logger.error("evening_collect_failed", error=str(e))
