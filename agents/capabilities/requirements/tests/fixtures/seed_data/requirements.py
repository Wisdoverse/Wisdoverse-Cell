"""
Requirement Data Factory

Provides reusable requirement data for testing lifecycle operations:
- Pending requirements
- Confirmed requirements
- Rejected requirements
- Various priorities and categories
"""
import uuid
from dataclasses import dataclass, field
from typing import Optional


def _generate_id(prefix: str) -> str:
    """Generate a test ID (simplified version for testing)"""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class RequirementData:
    """Requirement test data structure"""
    title: str
    description: str
    category: str
    priority: str
    status: str = "PENDING"
    source_quote: Optional[str] = None
    source_meeting_ids: list[str] = field(default_factory=list)
    id: Optional[str] = None
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.id is None:
            self.id = _generate_id("req")

    def to_dict(self) -> dict:
        """Convert to dictionary for API requests"""
        from dataclasses import asdict
        result = asdict(self)
        # Remove internal fields not needed for API
        result.pop("source_meeting_ids", None)
        result.pop("tags", None)
        return result


class RequirementFactory:
    """Factory for generating requirement test data"""

    @staticmethod
    def offline_recording(status: str = "PENDING") -> RequirementData:
        """High priority functional requirement - core feature"""
        return RequirementData(
            title="离线录音功能",
            description="设备在无网络环境下能本地存储录音，联网后自动上传到云端",
            category="功能",
            priority="HIGH",
            status=status,
            source_quote="必须支持离线录音功能，设备在无网络时也能工作",
            tags=["core", "functional"],
        )

    @staticmethod
    def multi_format_support(status: str = "PENDING") -> RequirementData:
        """Medium priority functional requirement"""
        return RequirementData(
            title="多音频格式支持",
            description="录音文件需要支持 MP3、WAV、M4A 三种格式的播放和转换",
            category="功能",
            priority="MEDIUM",
            status=status,
            source_quote="录音文件需要支持 MP3 和 WAV 格式",
            tags=["functional"],
        )

    @staticmethod
    def speaker_recognition(status: str = "PENDING") -> RequirementData:
        """Medium priority AI requirement"""
        return RequirementData(
            title="说话人识别",
            description="使用 AI 自动识别录音中的不同说话人并标记时间戳",
            category="AI功能",
            priority="MEDIUM",
            status=status,
            source_quote="希望能自动识别说话人",
            tags=["ai", "feature"],
        )

    @staticmethod
    def security_encryption(status: str = "PENDING") -> RequirementData:
        """High priority security requirement"""
        return RequirementData(
            title="数据加密存储",
            description="所有录音文件和用户数据必须使用 AES-256 加密存储",
            category="安全",
            priority="HIGH",
            status=status,
            source_quote="数据安全是客户的核心关注点",
            tags=["security", "compliance"],
        )

    @staticmethod
    def realtime_transcription(status: str = "PENDING") -> RequirementData:
        """Low priority AI requirement"""
        return RequirementData(
            title="实时转写",
            description="录音过程中实时将语音转换为文字",
            category="AI功能",
            priority="LOW",
            status=status,
            tags=["ai", "future"],
        )

    @staticmethod
    def user_authentication(status: str = "PENDING") -> RequirementData:
        """High priority security requirement"""
        return RequirementData(
            title="用户认证",
            description="支持多种登录方式：手机号、邮箱、企业微信扫码",
            category="安全",
            priority="HIGH",
            status=status,
            tags=["security", "auth"],
        )

    @staticmethod
    def performance_requirement(status: str = "PENDING") -> RequirementData:
        """Non-functional performance requirement"""
        return RequirementData(
            title="系统性能要求",
            description="系统需支持 500 并发用户，API 响应时间 < 200ms",
            category="性能",
            priority="HIGH",
            status=status,
            tags=["non_functional", "performance"],
        )

    @staticmethod
    def similar_to_offline_recording(status: str = "PENDING") -> RequirementData:
        """Similar requirement for conflict detection testing"""
        return RequirementData(
            title="本地录音存储",
            description="支持在本地设备存储录音文件，无需网络连接",
            category="功能",
            priority="HIGH",
            status=status,
            tags=["conflict_test"],
        )

    @staticmethod
    def batch(count: int, status: str = "PENDING") -> list[RequirementData]:
        """Generate multiple requirements for bulk testing"""
        factories = [
            RequirementFactory.offline_recording,
            RequirementFactory.multi_format_support,
            RequirementFactory.speaker_recognition,
            RequirementFactory.security_encryption,
            RequirementFactory.realtime_transcription,
            RequirementFactory.user_authentication,
            RequirementFactory.performance_requirement,
        ]
        return [factories[i % len(factories)](status) for i in range(count)]

    @staticmethod
    def with_all_statuses() -> dict[str, RequirementData]:
        """One requirement in each status for lifecycle testing"""
        return {
            "pending": RequirementFactory.offline_recording("PENDING"),
            "confirmed": RequirementFactory.multi_format_support("CONFIRMED"),
            "rejected": RequirementFactory.speaker_recognition("REJECTED"),
        }


# Pre-defined requirement sets for different test scenarios
LIFECYCLE_TEST_REQUIREMENTS = {
    "to_confirm": RequirementFactory.offline_recording("PENDING"),
    "to_reject": RequirementFactory.speaker_recognition("PENDING"),
    "already_confirmed": RequirementFactory.multi_format_support("CONFIRMED"),
}

CONFLICT_DETECTION_REQUIREMENTS = [
    RequirementFactory.offline_recording("CONFIRMED"),
    RequirementFactory.similar_to_offline_recording("PENDING"),
]

SEARCH_TEST_REQUIREMENTS = [
    RequirementFactory.offline_recording(),
    RequirementFactory.multi_format_support(),
    RequirementFactory.speaker_recognition(),
    RequirementFactory.security_encryption(),
    RequirementFactory.realtime_transcription(),
]
