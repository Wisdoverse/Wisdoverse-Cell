from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String, Text

from .base import Base


class ReportLog(Base):
    """分析报告日志"""
    __tablename__ = "analysis_agent_report_logs"
    __table_args__ = (
        CheckConstraint("report_type IN ('daily', 'weekly', 'milestone')", name="ck_report_type"),
        CheckConstraint("status IN ('generated', 'pushed', 'failed')", name="ck_report_status"),
    )

    id = Column(Integer, primary_key=True)
    report_type = Column(String(20), nullable=False)  # daily, weekly, milestone
    report_date = Column(DateTime(timezone=True), nullable=False)
    content = Column(Text)
    status = Column(String(20), default="generated")  # generated, pushed, failed
    pushed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
