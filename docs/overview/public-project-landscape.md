# Public Project Landscape

Reviewed: 2026-10-01

Purpose: inform the [Product Roadmap](./roadmap.md) against Wisdoverse Cell's
[service goals](../../SPEC.md#2-goals-and-non-goals). This is a selected survey
of eight public repositories, not an exhaustive market ranking.

## Evidence and Limits

The sources below are upstream READMEs pinned to the commits reviewed. They
establish what each project documents or claims; no competing product was
installed, benchmarked, or audited. Examples, SDK capabilities and commercial
offerings are distinguished from a self-hosted company control plane. A
feature absent from a README is not evidence that its implementation lacks it.
Stars, demos and agent counts are not delivery or reliability evidence.

Wisdoverse Cell's implementation comparison uses main at `c387877`
(2026-10-01), its source and existing tests. Its deployment and complete
operator-flow acceptance remain pending. Research links contain public
repository references; no contacts, account configuration or operational
data are reproduced here.

## Closest and Adjacent Projects

| Project / source | Relationship | Documented pattern | Implication for Wisdoverse Cell |
|------------------|--------------|--------------------|--------------------------------|
| Paperclip [R1](#source-snapshots) | Closest product comparison: agents managed as an organization | Goals, org chart, task ownership, adapters, heartbeats, scoped budgets, approvals, persistent context, evaluations and portable company templates | Treat company objects as the existing foundation. Prioritize a verified operating loop, execution ownership and outcome evidence before expanding the feature list. |
| MetaGPT [R2](#source-snapshots) | Role-based software-company framework | Product manager, architect, project manager and engineer roles connected through explicit SOPs | Give Requirement Manager → PJM → Dev → QA handoffs typed artifacts and acceptance criteria. Role names alone do not establish successful delivery. |
| ChatDev [R3](#source-snapshots) | Software-team origin; current 2.0 is a configurable multi-agent platform | The README distinguishes legacy 1.0's virtual software company from 2.0's workflow authoring, intermediate artifacts and human feedback | Start with repeatable, versioned business playbooks. A general visual workflow editor remains outside the current service goals. |
| ClawTeam [R4](#source-snapshots) | CLI-agent team coordination | Task allocation/dependencies, agent inboxes, isolated worktrees, monitoring and TOML team templates; research and engineering demos | Specify claim/lease, dependencies and artifact handoffs for workers. The demos do not establish company governance or production parity. |
| CrewAI [R5](#source-snapshots) | Agent/workflow framework | Crews for role collaboration, Flows for event-driven control, structured output, human input and checkpointing | Keep autonomous reasoning behind explicit business transitions and policy gates. The README presents the Crew Control Plane as a separate product (with free access) and AMP as its commercial suite; neither establishes parity in the open-source framework. |
| LangGraph [R6](#source-snapshots) | Long-running agent execution framework | Durable execution, interrupts and persistent memory; LangSmith is presented separately for debugging, evaluation and deployment | Define resume/replay and approval semantics on the existing runtime. Checkpoints alone do not prevent duplicate external effects; reuse still needs idempotency at the affected operation. |
| OpenHands / Agent Canvas [R7](#source-snapshots) | Self-hosted developer control center | The reviewed README describes Agent Canvas, ACP-compatible agents, local/remote backends, automations and Docker conversation isolation | Certify one real executor boundary with workspace isolation, cancellation and evidence. Separate executor protocols from company policy and tool permissions. |
| Temporal [R8](#source-snapshots) | Durable execution infrastructure | Workflows resilient to intermittent failures and retries | Use restart, retry and recovery acceptance tests. Introducing another execution engine requires an observed gap and a separate design decision. |

## Decisions Derived from the Survey

| Observation | Local evidence or gap | Roadmap decision |
|-------------|-----------------------|------------------|
| Paperclip already documents the goals/org/tasks/budgets/governance category | Cell already has the corresponding [product objects](./product-model.md#core-objects), command APIs and operator surfaces | M0 proves a complete business outcome; adding more records or role names is not its exit criterion. |
| MetaGPT/ChatDev connect roles through explicit workflow outputs | Requirement Manager, PJM, Dev and QA exist, but complete task-flow acceptance is still pending | M0 records a goal-linked artifact, QA verdict, required decision and work-item closure together. |
| Paperclip documents task ownership and persistent context; ClawTeam documents task status, inbox coordination and isolated worktrees | [Heartbeat scheduler](../../shared/control_plane/scheduler.py) checks due roles; this is not a distributed lease. Deduplication exists in selected paths, not as a proven global command guarantee. | M1 requires atomic claiming, bounded leases, reconciliation and observable duplicate-effect tests. |
| Paperclip/Agent Canvas bring external executors into an operating surface | [Adapter registry](../../shared/control_plane/adapter_registry.py) registers `builtin`, `http`, `process`, `codex_local` and `claude_local`; local aliases share the process implementation. `builtin` only records a wakeup. | M0 uses a real supported execution path. M2 certifies existing HTTP/local paths before adding another executor or protocol. |
| Evaluation and recovery are important operating capabilities | [Proposal ledger](../../shared/control_plane/domain/evolution_proposal.py) has rollout states; [Evaluator](../../shared/evolution/evaluator.py), [CanaryRouter](../../shared/evolution/canary_router.py), [EvolutionGuard](../../shared/evolution/evolution_guard.py) and [ShadowRunner](../../shared/evolution/collaboration/shadow_runner.py) exist as components | M3 connects proposal → evaluation → approved experiment → rollback. A ledger transition or component test does not prove this integrated flow. |
| Several projects document reusable team/workflow templates | Company export/import with secret scrubbing is currently planned; PRD export is a different capability | M4 adds a versioned company-template round trip after governance and stable contracts. A small synthetic onboarding fixture may ship in M0. |
| Durable execution frameworks make failure recovery an explicit contract | Outbox/replay and migration playbooks exist; rollout observation remains unaccepted | R0 preserves migration, staging, replay and rollback gates while M0–M3 progress in the bundled topology. |

These are product and engineering recommendations for Cell. They are not
claims that Cell outperforms the surveyed projects or commitments to adopt
their libraries. Existing HTTP/EventBus boundaries, the single write-owner
rules and the default modular deployment remain binding.

## Source Snapshots

Every source was read on 2026-10-01. The links freeze the inspected README;
upstream main/master can change after that date.

| ID | Public repository | Reviewed README |
|----|-------------------|-----------------|
| R1 | [paperclipai/paperclip](https://github.com/paperclipai/paperclip) | [467125f — product pillars, execution and governance](https://github.com/paperclipai/paperclip/blob/467125fafb47a8520856504fecc48d6e32055db1/README.md) |
| R2 | [FoundationAgents/MetaGPT](https://github.com/FoundationAgents/MetaGPT) | [11cdf46 — roles and SOPs](https://github.com/FoundationAgents/MetaGPT/blob/11cdf466d042aece04fc6cfd13b28e1a70341b1f/README.md) |
| R3 | [OpenBMB/ChatDev](https://github.com/OpenBMB/ChatDev) | [4fb2db0 — 2.0 platform and legacy 1.0 distinction](https://github.com/OpenBMB/ChatDev/blob/4fb2db0ea90375ce1059f44fe03ffbd191a7a169/README.md) |
| R4 | [HKUDS/ClawTeam](https://github.com/HKUDS/ClawTeam) | [0119833 — coordination, worktrees and templates](https://github.com/HKUDS/ClawTeam/blob/01198332ef9270c32c5460b8a178f964fc0df451/README.md) |
| R5 | [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | [fbcf2de — Crews/Flows and commercial AMP distinction](https://github.com/crewAIInc/crewAI/blob/fbcf2de39d3f8252500b74a0751b92c5774c751b/README.md) |
| R6 | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | [4be610c — durable execution, interrupts and memory](https://github.com/langchain-ai/langgraph/blob/4be610c6bc7c042038f671d6def9f523ca385a69/README.md) |
| R7 | [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) | [a8c0558 — Agent Canvas and executor backends](https://github.com/OpenHands/OpenHands/blob/a8c05584ec6bb063a0857460b9cbff48e136919f/README.md) |
| R8 | [temporalio/temporal](https://github.com/temporalio/temporal) | [fc43726 — durable execution and retries](https://github.com/temporalio/temporal/blob/fc4372605ce23f333b7e1a43eef303ff002c2ef1/README.md) |

## Refresh Policy

Revisit a source when a proposed adapter, workflow or governance change uses
it as evidence. Record the new revision, affected claim and resulting local
decision. Update the roadmap only when Cell's goals, implementation or
acceptance evidence justify a change; upstream popularity alone does not.
