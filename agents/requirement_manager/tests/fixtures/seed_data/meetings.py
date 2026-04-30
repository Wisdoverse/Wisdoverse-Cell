"""
Meeting Data Factory

Provides reusable meeting content for testing with various scenarios:
- Simple single-requirement meetings
- Complex multi-requirement meetings
- Edge cases (empty content, unicode, very long content)
- Different sources (upload, feishu, wechat)
"""
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Optional


@dataclass
class MeetingData:
    """Meeting test data structure"""
    content: str
    source: str
    title: Optional[str] = None
    meeting_date: Optional[datetime] = None
    participants: list[str] = field(default_factory=list)
    context: Optional[str] = None
    source_id: Optional[str] = None

    # Expected outcomes for assertions
    expected_requirements_min: int = 0
    expected_requirements_max: int = 10
    expected_questions_min: int = 0
    tags: list[str] = field(default_factory=list)


class MeetingFactory:
    """Factory for generating meeting test data"""

    @staticmethod
    def simple_product_meeting() -> MeetingData:
        """Single clear requirement - smoke test baseline"""
        return MeetingData(
            content="""
            2026年1月21日产品讨论会

            参会人员：张总、产品经理

            结论：必须支持离线录音功能，这是客户的核心诉求。
            设备在无网络时也能正常录音，联网后自动同步。
            """,
            source="upload",
            title="产品讨论会",
            meeting_date=datetime.now(UTC),
            participants=["张总", "产品经理"],
            expected_requirements_min=1,
            expected_requirements_max=2,
            tags=["simple", "smoke_test"],
        )

    @staticmethod
    def complex_requirements_meeting() -> MeetingData:
        """Multiple requirements with priorities and questions"""
        return MeetingData(
            content="""
            2026年1月21日需求评审会

            参会人员：张总、李经理、王工、赵设计

            讨论内容：

            1. 离线录音功能（P0 - 必须）
               - 设备在无网络环境下能本地存储录音
               - 联网后自动上传到云端
               - 张总强调这是客户的核心诉求

            2. 多音频格式支持（P1 - 重要）
               - 必须支持 MP3、WAV 格式
               - M4A 格式待评估

            3. 说话人识别（P2 - 期望）
               - 自动识别录音中的不同说话人
               - 可以放到后续版本

            4. 实时转写功能（P2 - 待评估）
               - 技术可行性待确认
               - 需要评估成本

            待确认问题：
            - 离线存储的容量上限是多少？需要和硬件团队确认
            - 是否需要加密存储？安全合规要求待确认
            """,
            source="upload",
            title="需求评审会",
            meeting_date=datetime.now(UTC),
            participants=["张总", "李经理", "王工", "赵设计"],
            expected_requirements_min=3,
            expected_requirements_max=5,
            expected_questions_min=1,
            tags=["complex", "multi_requirement", "with_questions"],
        )

    @staticmethod
    def empty_content_meeting() -> MeetingData:
        """No actionable requirements - edge case"""
        return MeetingData(
            content="今天天气不错，大家聊了聊近况。下周再开会讨论具体事项。",
            source="upload",
            title="闲聊",
            expected_requirements_min=0,
            expected_requirements_max=0,
            tags=["edge_case", "empty"],
        )

    @staticmethod
    def feishu_webhook_meeting(meeting_id: str = "feishu_001") -> MeetingData:
        """Feishu source meeting"""
        return MeetingData(
            content="""
            飞书会议纪要：录音分析项目需求评审

            会议时间：2026-01-21 14:00-15:00
            参会人员：张三、李四、王五

            决议：
            1. 确认离线录音为核心需求，必须在 v1.0 实现
            2. 第一版本支持 MP3、WAV 格式
            3. 说话人识别功能延后到 v1.1

            行动项：
            - 张三负责技术方案，下周三前完成
            - 李四负责 UI 设计，下周五前完成
            """,
            source="feishu",
            source_id=meeting_id,
            title="飞书会议纪要",
            participants=["张三", "李四", "王五"],
            expected_requirements_min=1,
            expected_requirements_max=3,
            tags=["feishu", "integration"],
        )

    @staticmethod
    def wecom_meeting(meeting_id: str = "wecom_001") -> MeetingData:
        """WeCom (WeChat Work) source meeting"""
        return MeetingData(
            content="""
            企业微信群聊记录整理

            @所有人 今天确认以下需求：
            1. 用户认证必须支持企业微信扫码登录
            2. 消息通知要同步到企业微信

            张总: 这两个功能必须在本月上线
            """,
            source="wecom",
            source_id=meeting_id,
            title="企业微信需求确认",
            expected_requirements_min=1,
            expected_requirements_max=3,
            tags=["wecom", "integration"],
        )

    @staticmethod
    def unicode_and_special_chars() -> MeetingData:
        """Unicode and special characters - edge case"""
        return MeetingData(
            content="""
            国际化需求讨论

            需求说明：
            1. 多语言支持：中文、English、日本語、한국어
            2. 特殊字符处理：用户输入需要转义 <>&"' 等字符
            3. Emoji 支持：用户昵称和评论可包含表情符号

            测试用例：
            - 中文名：张三
            - English: John Doe
            - 日本語：田中太郎
            - Emoji: User 🎉
            """,
            source="upload",
            title="国际化需求",
            expected_requirements_min=2,
            expected_requirements_max=4,
            tags=["edge_case", "unicode", "i18n"],
        )

    @staticmethod
    def very_long_meeting(requirement_count: int = 50) -> MeetingData:
        """Very long content - stress test"""
        base_content = "2026年1月需求汇总会议\n\n讨论了以下需求点：\n\n"
        requirements = "\n".join([
            f"{i+1}. 需求点 {i+1}：这是第 {i+1} 个需求的详细描述，"
            f"涉及到功能模块 {i % 5 + 1}，优先级为 {'P0' if i < 10 else 'P1' if i < 30 else 'P2'}"
            for i in range(requirement_count)
        ])
        return MeetingData(
            content=base_content + requirements,
            source="upload",
            title="大型需求汇总",
            expected_requirements_min=10,
            expected_requirements_max=requirement_count,
            tags=["edge_case", "stress_test", "long_content"],
        )

    @staticmethod
    def conflicting_requirements() -> MeetingData:
        """Conflicting requirements - for conflict detection testing"""
        return MeetingData(
            content="""
            需求讨论 - 存在分歧

            张总：系统必须支持 1000 并发用户，这是客户的硬性要求
            李经理：预算有限，先支持 100 并发就行，后续再扩展
            王工：从技术角度看，500 并发是合理的折中方案

            最终结论：待老板拍板确认具体并发数要求

            另外讨论了：
            - 数据存储方案：MySQL vs PostgreSQL，未定
            - 缓存方案：Redis vs Memcached，未定
            """,
            source="upload",
            title="需求分歧讨论",
            expected_requirements_min=1,
            expected_requirements_max=3,
            expected_questions_min=1,
            tags=["conflict", "ambiguous"],
        )


# Pre-defined scenario groups for different test types
SMOKE_TEST_MEETINGS = [
    MeetingFactory.simple_product_meeting,
]

FULL_E2E_MEETINGS = [
    MeetingFactory.simple_product_meeting,
    MeetingFactory.complex_requirements_meeting,
    MeetingFactory.empty_content_meeting,
    MeetingFactory.feishu_webhook_meeting,
]

EDGE_CASE_MEETINGS = [
    MeetingFactory.empty_content_meeting,
    MeetingFactory.unicode_and_special_chars,
    MeetingFactory.very_long_meeting,
    MeetingFactory.conflicting_requirements,
]

INTEGRATION_MEETINGS = [
    MeetingFactory.feishu_webhook_meeting,
    MeetingFactory.wecom_meeting,
]
