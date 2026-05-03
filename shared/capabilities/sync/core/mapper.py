"""Shared data mapper for OpenProject and Feishu Bitable sync boundaries."""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional


@dataclass
class WorkPackageData:
    """Normalized work package data."""
    op_id: int
    title: str
    description: Optional[str] = None
    status: Optional[str] = None
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    progress: int = 0
    priority: Optional[str] = None
    project_id: Optional[int] = None
    parent_id: Optional[int] = None


@dataclass
class FeishuRecordData:
    """Normalized Feishu record data."""
    record_id: Optional[str] = None
    op_id: Optional[int] = None
    title: Optional[str] = None
    subtask_name: Optional[str] = None
    subtask_status: Optional[str] = None
    parent_op_id: Optional[int] = None


class DataMapper:
    """Map data between OpenProject and Feishu formats."""

    # 飞书任务表字段名
    FIELD_OP_ID = "关联 Feature ID (关键字段)"
    FIELD_TITLE = "任务(动宾短语)"
    FIELD_STATUS = "状态"
    FIELD_ASSIGNEE = "DRI (负责人)"
    FIELD_PRIORITY = "优先级"
    FIELD_DUE_DATE = "计划完成日期"
    FIELD_ACTUAL_FINISH = "实际完成时间"
    FIELD_PARENT_RECORD = "父记录"
    FIELD_CATEGORY = "所属大类"
    FIELD_BLOCKER = "阻塞原因"
    FIELD_SUBTASK_NAME = "subtask_name"
    FIELD_SUBTASK_STATUS = "subtask_status"
    FIELD_PARENT_OP_ID = "parent_op_id"

    @classmethod
    def op_to_work_package_data(cls, wp: dict[str, Any]) -> WorkPackageData:
        links = wp.get("_links", {})

        project_href = links.get("project", {}).get("href", "")
        project_id = None
        if project_href:
            try:
                project_id = int(project_href.split("/")[-1])
            except (ValueError, IndexError):
                pass

        parent_href = links.get("parent", {}).get("href", "")
        parent_id = None
        if parent_href:
            try:
                parent_id = int(parent_href.split("/")[-1])
            except (ValueError, IndexError):
                pass

        status = links.get("status", {}).get("title", "")

        assignee = links.get("assignee", {}).get("title", "")
        due_date = wp.get("dueDate", "")
        priority = links.get("priority", {}).get("title", "")

        return WorkPackageData(
            op_id=wp.get("id"),
            title=wp.get("subject", ""),
            description=wp.get("description", {}).get("raw", "") if wp.get("description") else None,
            status=status,
            assignee=assignee or None,
            due_date=due_date or None,
            progress=wp.get("percentageDone", 0),
            priority=priority or None,
            project_id=project_id,
            parent_id=parent_id,
        )

    @staticmethod
    def _date_to_timestamp_ms(date_str: str) -> int | None:
        try:
            d = date.fromisoformat(date_str)
            return int(datetime(d.year, d.month, d.day).timestamp() * 1000)
        except (ValueError, TypeError):
            return None

    @classmethod
    def work_package_to_feishu_fields(
        cls, wp_data: WorkPackageData, member_map: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {
            cls.FIELD_OP_ID: wp_data.op_id,
            cls.FIELD_TITLE: wp_data.title,
        }
        if wp_data.status:
            fields[cls.FIELD_STATUS] = wp_data.status
        if wp_data.assignee:
            if member_map:
                record_id = member_map.get(wp_data.assignee)
                if record_id:
                    fields[cls.FIELD_ASSIGNEE] = [record_id]
            else:
                fields[cls.FIELD_ASSIGNEE] = wp_data.assignee
        if wp_data.due_date:
            fields[cls.FIELD_DUE_DATE] = wp_data.due_date
        if wp_data.priority:
            fields[cls.FIELD_PRIORITY] = wp_data.priority
        fields["完成百分比"] = wp_data.progress
        return fields

    @classmethod
    def build_member_map(cls, member_records: list[dict]) -> dict[str, str]:
        name_to_record: dict[str, str] = {}
        for record in member_records:
            record_id = record.get("record_id", "")
            fields = record.get("fields", {})
            for value in fields.values():
                if isinstance(value, str) and value and record_id:
                    name_to_record[value] = record_id
                    break
        return name_to_record

    @classmethod
    def feishu_to_record_data(cls, record: dict[str, Any]) -> FeishuRecordData:
        fields = record.get("fields", {})

        op_id = fields.get(cls.FIELD_OP_ID)
        if isinstance(op_id, float):
            op_id = int(op_id)

        parent_op_id = fields.get(cls.FIELD_PARENT_OP_ID)
        if isinstance(parent_op_id, float):
            parent_op_id = int(parent_op_id)

        return FeishuRecordData(
            record_id=record.get("record_id"),
            op_id=op_id,
            title=fields.get(cls.FIELD_TITLE),
            subtask_name=fields.get(cls.FIELD_SUBTASK_NAME),
            subtask_status=fields.get(cls.FIELD_SUBTASK_STATUS),
            parent_op_id=parent_op_id,
        )


data_mapper = DataMapper()
