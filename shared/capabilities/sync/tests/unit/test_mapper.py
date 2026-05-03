"""
Unit Tests - DataMapper

Tests OpenProject <-> Feishu data format conversion.
"""

from shared.capabilities.sync.core.mapper import DataMapper, FeishuRecordData, WorkPackageData


class TestOpToWorkPackageData:
    def test_op_to_work_package_data_full(self):
        """Convert a complete OpenProject work package JSON payload."""
        wp = {
            "id": 42,
            "subject": "完成用户认证模块",
            "description": {"raw": "实现 OAuth2 流程"},
            "percentageDone": 75,
            "dueDate": "2026-03-15",
            "_links": {
                "project": {"href": "/api/v3/projects/7"},
                "parent": {"href": "/api/v3/work_packages/10"},
                "status": {"title": "In Progress"},
                "assignee": {"title": "张三"},
            },
        }

        result = DataMapper.op_to_work_package_data(wp)

        assert isinstance(result, WorkPackageData)
        assert result.op_id == 42
        assert result.title == "完成用户认证模块"
        assert result.description == "实现 OAuth2 流程"
        assert result.status == "In Progress"
        assert result.assignee == "张三"
        assert result.due_date == "2026-03-15"
        assert result.progress == 75
        assert result.project_id == 7
        assert result.parent_id == 10

    def test_op_to_work_package_data_minimal(self):
        """Convert a minimal OpenProject work package and apply defaults."""
        wp = {
            "id": 1,
            "subject": "最小任务",
            "_links": {},
        }

        result = DataMapper.op_to_work_package_data(wp)

        assert result.op_id == 1
        assert result.title == "最小任务"
        assert result.description is None
        assert result.status == ""
        assert result.assignee is None
        assert result.due_date is None
        assert result.progress == 0
        assert result.project_id is None
        assert result.parent_id is None

    def test_op_to_work_package_data_invalid_project_href(self):
        """Return project_id=None when the project href has no numeric ID."""
        wp = {
            "id": 5,
            "subject": "测试",
            "_links": {
                "project": {"href": "/api/v3/projects/not-a-number"},
                "parent": {"href": "/api/v3/work_packages/abc"},
            },
        }

        result = DataMapper.op_to_work_package_data(wp)

        assert result.op_id == 5
        assert result.project_id is None
        assert result.parent_id is None


class TestWorkPackageToFeishuFields:
    def test_work_package_to_feishu_fields_full(self):
        """Convert a complete WorkPackageData model to Feishu fields."""
        wp_data = WorkPackageData(
            op_id=42,
            title="完成设计文档",
            status="In Progress",
            assignee="李四",
            due_date="2026-04-01",
            progress=50,
        )

        result = DataMapper.work_package_to_feishu_fields(wp_data)

        assert result[DataMapper.FIELD_OP_ID] == 42
        assert result[DataMapper.FIELD_TITLE] == "完成设计文档"
        assert result[DataMapper.FIELD_STATUS] == "In Progress"
        assert result[DataMapper.FIELD_ASSIGNEE] == "李四"
        assert result[DataMapper.FIELD_DUE_DATE] == "2026-04-01"
        assert result["完成百分比"] == 50

    def test_work_package_to_feishu_fields_minimal(self):
        """Include only required fields when optional WorkPackageData fields are absent."""
        wp_data = WorkPackageData(
            op_id=1,
            title="最小任务",
        )

        result = DataMapper.work_package_to_feishu_fields(wp_data)

        assert result[DataMapper.FIELD_OP_ID] == 1
        assert result[DataMapper.FIELD_TITLE] == "最小任务"
        # Optional fields should be omitted when absent.
        assert DataMapper.FIELD_STATUS not in result
        assert DataMapper.FIELD_ASSIGNEE not in result
        assert DataMapper.FIELD_DUE_DATE not in result
        # progress defaults to 0 and is still included.
        assert result["完成百分比"] == 0


class TestFeishuToRecordData:
    def test_feishu_to_record_data(self):
        """Convert a Feishu record with float IDs to FeishuRecordData."""
        record = {
            "record_id": "rec_abc_123",
            "fields": {
                DataMapper.FIELD_OP_ID: 42.0,
                DataMapper.FIELD_TITLE: "设计文档",
                DataMapper.FIELD_SUBTASK_NAME: "子任务1",
                DataMapper.FIELD_SUBTASK_STATUS: "完成",
                DataMapper.FIELD_PARENT_OP_ID: 10.0,
            },
        }

        result = DataMapper.feishu_to_record_data(record)

        assert isinstance(result, FeishuRecordData)
        assert result.record_id == "rec_abc_123"
        assert result.op_id == 42
        assert isinstance(result.op_id, int)
        assert result.title == "设计文档"
        assert result.subtask_name == "子任务1"
        assert result.subtask_status == "完成"
        assert result.parent_op_id == 10
        assert isinstance(result.parent_op_id, int)

    def test_feishu_to_record_data_empty(self):
        """Return FeishuRecordData with None fields for an empty fields dict."""
        record = {
            "record_id": "rec_empty",
            "fields": {},
        }

        result = DataMapper.feishu_to_record_data(record)

        assert result.record_id == "rec_empty"
        assert result.op_id is None
        assert result.title is None
        assert result.subtask_name is None
        assert result.subtask_status is None
        assert result.parent_op_id is None
