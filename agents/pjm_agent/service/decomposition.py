"""
Decomposition service facade — re-exports DecompositionOrchestrator for convenience.

The orchestrator implementation lives in ``agents.pjm_agent.core.decomposition_orchestrator``
and owns all decomposition workflow logic (decompose, approve, reject, retry, get).
PMAgent delegates to it via thin wrapper methods.
"""

from ..core.decomposition_orchestrator import DecompositionOrchestrator

__all__ = ["DecompositionOrchestrator"]
