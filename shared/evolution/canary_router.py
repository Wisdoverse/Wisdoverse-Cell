"""
Canary Router — deterministic traffic splitting for mini-canary experiments.

Routes a percentage of traffic to a candidate skill version while the rest
uses the control version. Routing is deterministic based on trace_id so that
the same trace always receives the same skill version across retries.
"""

import hashlib

from shared.utils.logger import get_logger

logger = get_logger("evolution.canary")


class CanaryRouter:
    """Deterministic traffic splitting for mini-canary experiments.

    Routes a percentage of traffic to a candidate skill version while
    the rest uses the control version. Routing is deterministic based
    on trace_id (same trace always gets same version).
    """

    def __init__(self, *, db_manager=None, repo=None) -> None:
        self._db_manager = db_manager
        self._repo = repo  # legacy: tests inject mock repo

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _bucket(trace_id: str) -> int:
        """Return a deterministic bucket [0, 100) for the given trace_id."""
        return int(hashlib.md5(trace_id.encode()).hexdigest()[:8], 16) % 100

    def _make_repo(self, session):
        if self._repo is not None:
            return self._repo
        from shared.evolution.db.repository import EvolutionRepository
        return EvolutionRepository(session)

    # ── Public API ────────────────────────────────────────────────────────────

    async def resolve_skill_version(
        self, agent_id: str, skill_id: str, trace_id: str,
    ) -> int:
        """Return the skill version to use for this trace.

        If no experiment is running, returns the active skill's version.
        If an experiment is running, uses MD5 hash of trace_id for
        deterministic bucket assignment.

        Args:
            agent_id: The agent that owns the skill.
            skill_id: Skill being resolved.
            trace_id: Unique identifier of the current execution trace.

        Returns:
            Integer skill version to use.
        """
        if self._repo is not None:
            return await self._resolve_with_repo(
                self._repo, agent_id, skill_id, trace_id,
            )
        async with self._db_manager.session() as session:
            repo = self._make_repo(session)
            return await self._resolve_with_repo(
                repo, agent_id, skill_id, trace_id,
            )

    async def _resolve_with_repo(self, repo, agent_id, skill_id, trace_id):
        experiment = await repo.get_active_experiment(agent_id, skill_id)

        if experiment is None:
            active = await repo.get_active_skill(skill_id)
            version = active.version if active else 1
            logger.debug(
                "no_experiment skill=%s version=%d trace=%s",
                skill_id,
                version,
                trace_id,
            )
            return version

        bucket = self._bucket(trace_id)
        if bucket < experiment.traffic_pct:
            chosen = experiment.candidate_version
            arm = "candidate"
        else:
            chosen = experiment.control_version
            arm = "control"

        logger.debug(
            "experiment=%s skill=%s trace=%s bucket=%d traffic_pct=%d arm=%s version=%d",
            experiment.experiment_id,
            skill_id,
            trace_id,
            bucket,
            experiment.traffic_pct,
            arm,
            chosen,
        )
        return chosen

    async def record_result(
        self, agent_id: str, skill_id: str, trace_id: str, score: float
    ) -> None:
        """Record an experiment result for the appropriate arm.

        Args:
            agent_id: The agent that owns the skill.
            skill_id: Skill being evaluated.
            trace_id: Unique identifier of the execution trace.
            score: Outcome score (e.g. 0.0–1.0) for this execution.
        """
        if self._repo is not None:
            return await self._record_with_repo(
                self._repo, agent_id, skill_id, trace_id, score,
            )
        async with self._db_manager.session() as session:
            repo = self._make_repo(session)
            return await self._record_with_repo(
                repo, agent_id, skill_id, trace_id, score,
            )

    async def _record_with_repo(
        self, repo, agent_id, skill_id, trace_id, score,
    ):
        experiment = await repo.get_active_experiment(agent_id, skill_id)
        if experiment is None:
            return

        bucket = self._bucket(trace_id)
        is_candidate = bucket < experiment.traffic_pct

        logger.debug(
            "record_result experiment=%s trace=%s is_candidate=%s score=%.4f",
            experiment.experiment_id,
            trace_id,
            is_candidate,
            score,
        )

        await repo.add_experiment_result(
            experiment.experiment_id, is_candidate=is_candidate, score=score,
        )

    async def check_experiment(
        self, agent_id: str, skill_id: str, *, min_samples: int | None = None
    ) -> str:
        """Evaluate experiment and decide: promote, rollback, or continue.

        Returns:
            "promote" — candidate >= control, conclude and promote
            "rollback" — candidate significantly worse (>10% drop), conclude and rollback
            "continue" — not enough data yet
            "no_experiment" — no active experiment
        """
        if self._repo is not None:
            return await self._check_with_repo(
                self._repo, agent_id, skill_id, min_samples,
            )
        async with self._db_manager.session() as session:
            repo = self._make_repo(session)
            return await self._check_with_repo(
                repo, agent_id, skill_id, min_samples,
            )

    async def _check_with_repo(self, repo, agent_id, skill_id, min_samples):
        experiment = await repo.get_active_experiment(agent_id, skill_id)
        if experiment is None:
            return "no_experiment"

        control = experiment.control_results or []
        candidate = experiment.candidate_results or []

        # Honor the experiment's own min_samples config; caller override takes precedence
        effective_min = min_samples if min_samples is not None else getattr(experiment, "min_samples", 10)

        if len(control) < effective_min or len(candidate) < effective_min:
            return "continue"

        control_mean = sum(control) / len(control)
        candidate_mean = sum(candidate) / len(candidate)

        if candidate_mean >= control_mean:
            await repo.conclude_experiment(
                experiment.experiment_id, status="promoted",
            )
            logger.info(
                "experiment_promoted",
                experiment_id=experiment.experiment_id,
                control_mean=round(control_mean, 4),
                candidate_mean=round(candidate_mean, 4),
            )
            return "promote"

        degradation = (control_mean - candidate_mean) / max(control_mean, 0.01)
        if degradation > 0.10:
            await repo.conclude_experiment(
                experiment.experiment_id, status="rolled_back",
            )
            logger.info(
                "experiment_rolled_back",
                experiment_id=experiment.experiment_id,
                control_mean=round(control_mean, 4),
                candidate_mean=round(candidate_mean, 4),
            )
            return "rollback"

        return "continue"
