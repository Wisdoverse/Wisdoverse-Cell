"""AnalysisAgent FastAPI 入口"""

from fastapi import Depends

from shared.app import create_agent_app
from shared.app.plugins.infra_health import InfraHealthPlugin
from shared.middleware.internal_auth import verify_internal_key

from ..api.analysis import router as analysis_router
from ..service.agent import agent as _raw_agent

app = create_agent_app(
    _raw_agent,
    title="Analysis Agent",
    description="分析报告 Agent（日报/周报/里程碑/质量评估）",
    routers=[(analysis_router, [Depends(verify_internal_key)])],
    plugins=[InfraHealthPlugin()],
)
