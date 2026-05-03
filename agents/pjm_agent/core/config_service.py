"""PJM 配置服务 - 从飞书多维表格读取配置"""

from shared.config import settings
from shared.core import BitableTablePort
from shared.utils.logger import get_logger

logger = get_logger("pjm_agent.config")


class PMConfigService:
    def __init__(self, bitable: BitableTablePort):
        self._bitable = bitable
        self._members: list[dict] = []
        self._projects: list[dict] = []
        self._rules: dict[str, str] = {}

    @property
    def members(self) -> list[dict]:
        return self._members

    @property
    def projects(self) -> list[dict]:
        return self._projects

    @property
    def rules(self) -> dict[str, str]:
        return self._rules

    def get_rule(self, name: str, default: str = "") -> str:
        return self._rules.get(name, default)

    async def refresh(self) -> None:
        """从飞书表刷新所有配置（原子更新）"""
        app_token = settings.feishu_pm_app_token
        if not app_token:
            logger.warning("pm_config_no_token")
            return

        errors = []
        new_members = self._members  # keep old on failure
        new_projects = self._projects
        new_rules = self._rules

        if settings.feishu_pm_member_table_id:
            try:
                records = await self._bitable.list_all_records(
                    app_token=app_token, table_id=settings.feishu_pm_member_table_id
                )
                new_members = [r.get("fields", {}) for r in records]
                logger.info("pm_config_members_loaded", count=len(new_members))
            except Exception as e:
                errors.append(f"members: {e}")
                logger.error("pm_config_members_failed", error=str(e))

        if settings.feishu_pm_project_table_id:
            try:
                records = await self._bitable.list_all_records(
                    app_token=app_token, table_id=settings.feishu_pm_project_table_id
                )
                new_projects = [r.get("fields", {}) for r in records]
                logger.info("pm_config_projects_loaded", count=len(new_projects))
            except Exception as e:
                errors.append(f"projects: {e}")
                logger.error("pm_config_projects_failed", error=str(e))

        if settings.feishu_pm_rules_table_id:
            try:
                records = await self._bitable.list_all_records(
                    app_token=app_token, table_id=settings.feishu_pm_rules_table_id
                )
                rules = {}
                for r in records:
                    fields = r.get("fields", {})
                    name = fields.get("规则名称", "")
                    value = fields.get("规则值", "")
                    if name:
                        rules[name] = value
                new_rules = rules
                logger.info("pm_config_rules_loaded", count=len(new_rules))
            except Exception as e:
                errors.append(f"rules: {e}")
                logger.error("pm_config_rules_failed", error=str(e))

        self._members = new_members
        self._projects = new_projects
        self._rules = new_rules

        if errors:
            failed_sections = [e.split(":")[0] for e in errors]
            all_sections = {"members", "projects", "rules"}
            fresh_sections = all_sections - set(failed_sections)
            logger.error(
                "pm_config_refresh_partial",
                errors=errors,
                stale=sorted(failed_sections),
                fresh=sorted(fresh_sections),
            )
