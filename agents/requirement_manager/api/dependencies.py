"""Requirement Manager API dependency wiring."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.agent_prompt_config import resolve_agent_system_prompt
from shared.infra.llm_gateway import llm_gateway

from ..core.admin_circuit_breaker import CircuitBreakerAdminUseCase
from ..core.analyzer import RequirementAnalyzer
from ..core.comparator import RequirementComparator
from ..core.conflict_check import RequirementConflictCheckUseCase
from ..core.export_use_cases import ExportUseCase
from ..core.feedback_use_cases import RequirementFeedbackUseCase
from ..core.generator import DocumentGenerator
from ..core.ingest_use_cases import IngestUseCase
from ..core.llm_usage_queries import LLMUsageQueryService
from ..core.message_queries import MessageQueryService
from ..core.requirement_analysis import RequirementAnalysisUseCase
from ..core.requirement_context_queries import RequirementContextQueryService
from ..core.requirement_mutations import RequirementMutationUseCase
from ..core.requirement_queries import RequirementQueryService
from ..db.database import get_db
from ..db.repository import (
    LLMUsageRepository,
    MeetingRepository,
    MessageRepository,
    QuestionRepository,
    RequirementRepository,
)
from ..db.vector_store import vector_store
from ..service import get_agent

_requirement_comparator = RequirementComparator(
    vector_search=vector_store,
    llm=llm_gateway,
    system_prompt_resolver=resolve_agent_system_prompt,
)
_document_generator = DocumentGenerator(
    llm=llm_gateway,
    system_prompt_resolver=resolve_agent_system_prompt,
)
_requirement_analyzer = RequirementAnalyzer(
    llm=llm_gateway,
    system_prompt_resolver=resolve_agent_system_prompt,
)


def get_llm_usage_query_service(
    db: AsyncSession = Depends(get_db),
) -> LLMUsageQueryService:
    return LLMUsageQueryService(LLMUsageRepository(db))


def get_circuit_breaker_admin_use_case() -> CircuitBreakerAdminUseCase:
    return CircuitBreakerAdminUseCase(gateway=llm_gateway)


def get_message_query_service(
    db: AsyncSession = Depends(get_db),
) -> MessageQueryService:
    return MessageQueryService(MessageRepository(db))


def get_requirement_context_query_service(
    db: AsyncSession = Depends(get_db),
) -> RequirementContextQueryService:
    return RequirementContextQueryService(
        requirement_repository=RequirementRepository(db),
        message_repository=MessageRepository(db),
    )


def get_requirement_query_service(
    db: AsyncSession = Depends(get_db),
) -> RequirementQueryService:
    return RequirementQueryService(
        requirement_repository=RequirementRepository(db),
        meeting_repository=MeetingRepository(db),
        vector_stats=vector_store,
    )


def get_export_use_case(
    db: AsyncSession = Depends(get_db),
) -> ExportUseCase:
    return ExportUseCase(
        requirement_repository=RequirementRepository(db),
        question_repository=QuestionRepository(db),
        generator=_document_generator,
    )


def get_requirement_analysis_use_case(
    db: AsyncSession = Depends(get_db),
) -> RequirementAnalysisUseCase:
    return RequirementAnalysisUseCase(
        requirement_repository=RequirementRepository(db),
        analyzer=_requirement_analyzer,
    )


def get_ingest_use_case(
    db: AsyncSession = Depends(get_db),
) -> IngestUseCase:
    return IngestUseCase(
        meeting_repository=MeetingRepository(db),
        agent=get_agent(),
        session=db,
    )


def get_requirement_feedback_use_case(
    db: AsyncSession = Depends(get_db),
) -> RequirementFeedbackUseCase:
    return RequirementFeedbackUseCase(
        agent=get_agent(),
        session=db,
    )


def get_requirement_mutation_use_case(
    db: AsyncSession = Depends(get_db),
) -> RequirementMutationUseCase:
    return RequirementMutationUseCase(
        agent=get_agent(),
        session=db,
    )


def get_requirement_conflict_check_use_case() -> RequirementConflictCheckUseCase:
    return RequirementConflictCheckUseCase(comparator=_requirement_comparator)
