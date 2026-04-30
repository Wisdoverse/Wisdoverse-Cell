# VectorStorePlugin — 共享向量存储 RuntimePlugin 设计

> Language note: English is the primary documentation language. This legacy document may still contain Chinese implementation details; when editing it, put the English explanation first.

**Status**: Reviewed Draft
**Date**: 2026-03-20
**Author**: Claude + Human
**Issue**: TBD

## Review Notes

This revision rewrites the original draft to close the main design gaps found during review:

- **Lifecycle corrected for the current runtime**: `AgentRuntime.startup()` is fail-fast today, so `VectorStorePlugin` must catch dependency failures inside its own lifecycle hooks. Only invalid local config should still raise.
- **K8s readiness semantics clarified**: vector search is an optional capability by default. Milvus or embedder outages should report `degraded`, not `down`, so pods stay ready unless an agent explicitly marks vector search as required.
- **API made more complete and more type-safe**: replaced the loose `list[dict]` batch/search API with typed results and added missing operations agents commonly need: `search_by_id()`, `get_by_ids()`, `delete_many()`, and safe metadata equality filters.
- **Migration risk reduced**: rollout is now **requirement_manager first**. The existing `agents/requirement_manager/db/vector_store.py` remains as a compatibility facade so current imports, API routes, comparator logic, and tests do not all have to change at once.
- **Naming aligned with the codebase**: plugin ID stays kebab-case (`vector-store`); Python methods/args stay snake_case; collection names remain snake_case (`requirements`, `pm_tasks`).
- **Missing production concerns added**: bounded timeouts, retry policy, circuit breaker behavior, idempotent collection ensure, concurrent startup safety, metrics, PII-safe logging, and readiness detail expectations.
- **Runtime injection recommendation changed**: do not mutate `agent._runtime` as the primary access pattern. `create_agent_app()` already exposes `app.state.runtime`; requirement_manager should bind its compatibility facade from an `on_startup` hook.

## Problem

Milvus is currently only wired into `requirement_manager`, even though semantic search is a reusable infrastructure capability. The current agent-specific wrapper mixes three concerns:

- domain formatting (`format_requirement_for_embedding`)
- vector infrastructure (Milvus connection, collection ensure, embedding)
- lifecycle management (`initialize()` / `close()`)

That makes reuse awkward and creates drift between agents.

## Goals

- Extract Milvus + embedding access into a shared `RuntimePlugin`
- Let any agent declare collections in `create_agent_app(..., plugins=[...])`
- Preserve current `requirement_manager` behavior and graceful degradation
- Keep domain-specific text shaping in the agent layer, not in the shared plugin
- Keep the event loop non-blocking: all Milvus SDK and embedding work must stay off the async event loop

## Non-Goals

- Multi-embedder or per-collection model selection
- Automatic collection schema migration or destructive collection recreation
- Cross-agent shared collections in the first rollout
- Immediate adoption by every agent in the same PR
- Replacing `InfraHealthPlugin` Milvus checks

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Plugin placement | `shared/app/plugins/vector_store.py` | Shared runtime capability, no agent-specific imports |
| Plugin name | `vector-store` | Matches repo convention: IDs kebab-case |
| Access pattern | `app.state.runtime.get_plugin("vector-store")` | Already supported by factory state; avoids ambiguous raw vs wrapped agent mutation |
| Default criticality | `required=False` | Semantic search is additive for most agents; readiness should degrade, not flap |
| Domain formatting | Keep in agent wrappers | Shared plugin should not know requirement-specific prompt/text layout |
| Search return type | `list[VectorSearchResult]` | Reuse existing shared types from `shared.infra.vector_store` |
| Filter API | safe equality `metadata_filters`, not raw user-built filter strings | Avoid injection-prone string concatenation in agents |
| Retry model | short bounded retries for Milvus operations only | Helps transient failures without masking prolonged outages |
| Failure isolation | circuit breaker + best-effort no-op defaults | Prevent request storms when Milvus is down |
| Rollout | requirement_manager first, other agents later | Lowest migration risk; validate semantics before broad adoption |

## Architecture

```text
shared/app/plugins/vector_store.py          # New shared RuntimePlugin
  ├─ wraps shared/infra/milvus_store.py     # existing MilvusVectorStore
  ├─ uses shared/infra/embedder.py          # existing TextEmbedder / embedder singleton
  ├─ manages bounded startup + readiness state
  ├─ exposes generic text/vector CRUD/search APIs
  └─ publishes plugin health for /health/ready/detail

agents/requirement_manager/db/vector_store.py
  ├─ remains as compatibility facade
  ├─ owns requirement-specific text formatting and thresholds
  └─ delegates infra calls to VectorStorePlugin once bound
```

### Separation of Responsibilities

- **VectorStorePlugin** owns connection management, collection ensure, embedding orchestration, retries, circuit breaking, and generic vector CRUD/search.
- **Agent wrappers** own domain-specific text shaping, domain-specific thresholds, and response shaping for APIs.
- **InfraHealthPlugin** continues to answer "is Milvus reachable?"
- **VectorStorePlugin** answers "is vector capability currently usable by this agent?"

That distinction avoids duplicate health semantics:

- `infra-health.milvus`: infrastructure reachability probe
- `vector-store.client`: plugin capability status
- `vector-store.circuit_breaker`: whether requests are being short-circuited

## Runtime Lifecycle

### Lifecycle Contract

`VectorStorePlugin` should use `startup()` and `shutdown()`. It does **not** need `pre_agent_startup()` in the first rollout because `requirement_manager` will no longer initialize Milvus inside `agent.startup()`.

Startup sequence:

1. Validate local plugin config
2. Create or reuse a single long-lived `MilvusVectorStore`
3. Reuse the shared embedder singleton by default
4. Attempt Milvus connection with a bounded timeout
5. Ensure all declared collections exist
6. If Milvus/embedder init fails, mark plugin unavailable and continue process startup

Shutdown sequence:

1. Stop accepting new vector work
2. Best-effort close the Milvus client
3. Never block process termination on close failures

### Fail-Fast vs Graceful Degradation

The plugin must distinguish **programmer/config errors** from **dependency/runtime errors**.

Raise during startup:

- invalid collection names
- duplicate collection declarations
- non-positive dimensions
- unsupported plugin arguments

Do not raise during startup:

- Milvus unavailable / timeout
- embedder model load failure
- collection ensure failing because the dependency is down

Instead, set:

- `available = False`
- `_last_error = type(exc).__name__`
- health = `degraded` if `required=False`
- health = `down` if `required=True`

This matches cloud-native behavior better than crash-looping on a non-critical dependency.

### Concurrent Startup Safety

K8s may start multiple replicas at the same time. Collection creation must therefore be treated as **idempotent and race-safe**:

- if collection already exists, treat as success
- if two pods race to create the same collection, the loser must treat "already exists" as success
- if a collection exists with an incompatible dimension, mark the plugin unavailable and report a clear health detail; do **not** auto-drop or auto-recreate it

## Public API

### Collection Declaration

```python
from dataclasses import dataclass

from shared.infra.embedder import DEFAULT_DIMENSION


@dataclass(frozen=True)
class VectorCollection:
    description: str = ""
    dimension: int = DEFAULT_DIMENSION
```

Notes:

- Collection names are the dict keys and should be snake_case
- Phase 1 deliberately keeps the current Milvus defaults (`COSINE` + `IVF_FLAT`) to avoid widening the migration surface
- Alternate index/metric tuning can be added later without changing the plugin access pattern

### Batch Input Type

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class VectorUpsertItem:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
```

### VectorStorePlugin

```python
from collections.abc import Mapping
from typing import Any

from shared.app.runtime import HealthCheckResult, RuntimePlugin
from shared.infra.embedder import TextEmbedder
from shared.infra.vector_store import BaseVectorStore, VectorDocument, VectorSearchResult


class VectorStorePlugin(RuntimePlugin):
    name = "vector-store"

    def __init__(
        self,
        *,
        collections: Mapping[str, VectorCollection | str],
        required: bool = False,
        uri: str = "",
        token: str = "",
        store: BaseVectorStore | None = None,
        embedder: TextEmbedder | None = None,
        connect_timeout_seconds: int = 10,
        operation_timeout_seconds: int = 15,
        retry_attempts: int = 2,
    ): ...

    @property
    def available(self) -> bool: ...

    async def startup(self, runtime) -> None: ...
    async def shutdown(self, runtime) -> None: ...
    async def health_check(self) -> dict[str, HealthCheckResult]: ...

    async def search_text(
        self,
        collection: str,
        query: str,
        *,
        limit: int = 10,
        min_score: float | None = None,
        metadata_filters: dict[str, str | int | float | bool] | None = None,
        strict: bool = False,
    ) -> list[VectorSearchResult]: ...

    async def search_by_id(
        self,
        collection: str,
        doc_id: str,
        *,
        limit: int = 10,
        min_score: float | None = None,
        include_self: bool = False,
        strict: bool = False,
    ) -> list[VectorSearchResult]: ...

    async def upsert_text(
        self,
        collection: str,
        doc_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        *,
        strict: bool = False,
    ) -> bool: ...

    async def upsert_batch_text(
        self,
        collection: str,
        items: list[VectorUpsertItem],
        *,
        strict: bool = False,
    ) -> int: ...

    async def get_by_ids(
        self,
        collection: str,
        ids: list[str],
        *,
        strict: bool = False,
    ) -> list[VectorDocument]: ...

    async def delete(
        self,
        collection: str,
        doc_id: str,
        *,
        strict: bool = False,
    ) -> bool: ...

    async def delete_many(
        self,
        collection: str,
        doc_ids: list[str],
        *,
        strict: bool = False,
    ) -> int: ...

    async def count(
        self,
        collection: str,
        *,
        strict: bool = False,
    ) -> int: ...
```

### API Semantics

- `search_text()` is the main entry point for semantic search
- `search_by_id()` is required because "find similar to an existing record" is a common pattern and is already used by `requirement_manager`
- `get_by_ids()` is required because the current wrapper already relies on `BaseVectorStore.get_by_ids()`
- `delete_many()` avoids forcing every agent wrapper to adapt a list-based low-level delete API
- `strict=False` means graceful degradation:
  - search/read methods return empty lists
  - write/delete methods return `False` or `0`
  - count returns `0`
- `strict=True` re-raises after logging/metrics so future agents can opt into hard failure when appropriate

### Safe Metadata Filters

The shared plugin should not expose raw Milvus filter strings in its public API.

Phase 1 supports only equality-based metadata filters:

```python
metadata_filters={"category": "登录", "priority": "high"}
```

The plugin compiles that into a backend-safe filter expression internally. This removes the current burden from agents to sanitize quotes and backslashes themselves.

## Implementation Notes

### Async Safety

Both dependencies are synchronous today and must stay off the event loop:

- `MilvusVectorStore` already uses `asyncio.to_thread(...)`
- `TextEmbedder.embed()` and `embed_batch()` must also be called via `asyncio.to_thread(...)`

The plugin must never call either dependency directly on the event loop thread.

### Connection Model

Use one long-lived `MilvusVectorStore` per plugin instance and reuse the shared embedder singleton by default.

- Do not create a new Milvus client per request
- Do not create a new `SentenceTransformer` per request
- Do not start a perpetual reconnect background task

Recovery should be **lazy**:

- failed startup marks the plugin unavailable
- the next allowed operation may attempt reconnection after circuit-breaker recovery

That keeps the process quiet when the dependency is down and avoids hidden background churn.

## Error Handling and Resilience

### Retry Policy

Retry only for transient Milvus operation failures:

- max 2 retries after the initial attempt
- exponential backoff with jitter
- no retry for validation errors, empty text, or malformed metadata filters

Suggested policy:

```text
attempt 1: immediate
attempt 2: 100-250ms later
attempt 3: 300-750ms later
```

### Circuit Breaker

Use `shared.infra.circuit_breaker.CircuitBreaker` inside the plugin.

Recommended defaults:

- `failure_threshold=5`
- `recovery_timeout=60`
- breaker name = `"{runtime.agent_id}.vector-store"`

Behavior:

- when open, `strict=False` calls fail fast without touching Milvus
- `health_check()` reports breaker state as `degraded`
- the first probe after recovery timeout acts as the half-open test

### Logging Rules

Structured logs must include:

- `agent_id`
- `collection`
- `operation`
- `error_type`
- `attempt`

Do **not** log:

- raw query text
- raw documents
- full metadata payloads
- Milvus tokens or auth-bearing URIs

Short counts and IDs are acceptable.

### Health Contract

`health_check()` should return something equivalent to:

```python
{
    "client": HealthCheckResult("ok" | "degraded" | "down", detail),
    "collections": HealthCheckResult("ok" | "degraded" | "down", detail),
    "circuit_breaker": HealthCheckResult("ok" | "degraded", detail),
}
```

Rules:

- `client=ok` only when the plugin currently has a usable client
- `collections=ok` only when all declared collections were ensured or verified
- `circuit_breaker=degraded` when open or half-open
- if `required=False`, dependency outages return `degraded`
- if `required=True`, dependency outages return `down`

This ensures `/health/ready` returns HTTP 200 for optional vector degradation, but 503 for agents that explicitly depend on vector search to serve traffic.

## requirement_manager Migration

### Current Behavior To Preserve

The current wrapper provides behavior that external callers already depend on:

- global singleton import: `from ..db.vector_store import vector_store`
- domain-specific formatting via `RequirementEmbedder.format_requirement_for_embedding()`
- graceful no-op when vector search is unavailable
- `search()` returning requirement-shaped dicts
- `find_similar()` excluding the target document itself

Those semantics should remain intact in Phase 1.

### Migration Strategy

#### Phase 1: Shared plugin + compatibility facade

- Add `VectorStorePlugin`
- Add `AgentRuntime.get_plugin(name)`
- Keep `agents/requirement_manager/db/vector_store.py` as the public facade
- Change the facade to support `bind_plugin(plugin)` / `unbind_plugin()`
- When bound, facade methods delegate to `VectorStorePlugin`
- When unbound, the existing direct-Milvus fallback path still works for isolated tests and legacy paths

#### Phase 2: Wire requirement_manager through the factory

Register:

```python
VectorStorePlugin(
    collections={
        "requirements": VectorCollection(description="Requirement semantic index"),
    },
    required=False,
)
```

Use `main_factory.py` startup/shutdown hooks to bind and unbind the compatibility facade:

```python
async def bind_vector_store_plugin(runtime):
    plugin = runtime.get_plugin("vector-store")
    if plugin is not None:
        vector_store.bind_plugin(plugin)


async def unbind_vector_store_plugin(runtime):
    vector_store.unbind_plugin()
```

Do **not** make the facade depend directly on FastAPI request objects.

#### Phase 3: Remove direct lifecycle ownership from the agent

`RequirementManagerAgent.startup()` and `shutdown()` should stop calling:

- `self._vector_store.initialize()`
- `self._vector_store.close()`

The plugin owns infrastructure lifecycle after migration.

### Why This Migration Is Safer

This avoids a flag day across the agent:

- API routes can keep importing `vector_store`
- comparator logic can keep calling `vector_store.search(...)`
- repository cleanup can keep calling `delete_requirement(...)`
- existing tests can move incrementally

The only shared runtime addition needed is `get_plugin()`. No `agent._runtime` mutation is required for the first rollout.

## Example Usage

### Generic Agent

```python
from shared.app import create_agent_app
from shared.app.plugins.vector_store import VectorCollection, VectorStorePlugin

app = create_agent_app(
    agent,
    plugins=[
        VectorStorePlugin(
            collections={
                "pm_tasks": VectorCollection(description="PM task semantic index"),
            },
        ),
    ],
)
```

### requirement_manager Facade Delegation

```python
async def add_requirement(...):
    text = embedder.format_requirement_for_embedding(...)
    await self._plugin.upsert_text(
        collection="requirements",
        doc_id=requirement_id,
        text=text,
        metadata=doc_metadata,
    )
```

The plugin stays generic; the requirement wrapper keeps the domain-specific formatting.

## Observability

Add plugin-level Prometheus metrics using the existing repo pattern:

- `projectcell_vector_store_operations_total{collection,operation,status}`
- `projectcell_vector_store_operation_duration_seconds{collection,operation}`
- `projectcell_vector_store_available`
- `projectcell_vector_store_documents{collection}`
- `projectcell_vector_store_circuit_breaker_open_total`

Guidelines:

- do not include `agent_id` as a label because metrics are already exposed per agent process
- collection names are acceptable label values because they are static and low-cardinality
- increment `status="degraded"` on graceful fallbacks so outages are visible even when requests succeed

## Testing Strategy

| Layer | Coverage |
|------|----------|
| `shared/app/tests/test_vector_store_plugin.py` | startup degradation, strict mode, retries, circuit breaker, health states, metrics/logging safety |
| `shared/app/tests/test_runtime.py` | `get_plugin()` behavior |
| `shared/infra/tests/test_vector_store.py` | collection ensure race handling, count/get/search behavior, schema mismatch handling if added there |
| `agents/requirement_manager/tests/test_vector_store.py` | facade delegation, compatibility behavior, preserved search/find_similar semantics |
| `agents/requirement_manager/tests/test_agent.py` | agent no longer initializes/closes Milvus directly |
| e2e/integration | Milvus unavailable => ingest still works, semantic search degrades cleanly, readiness stays `degraded` not `not_ready` when plugin is optional |

Critical regression cases:

- search still returns `[]` when Milvus is unavailable
- ingest still succeeds when vector upsert fails
- `find_similar()` still excludes the seed requirement
- readiness becomes `degraded` rather than `503` for optional vector outages
- no sensitive data leaks in readiness detail or logs

## File Changes

| Operation | File | Purpose |
|----------|------|---------|
| **Add** | `shared/app/plugins/vector_store.py` | shared VectorStorePlugin |
| **Update** | `shared/app/plugins/__init__.py` | export VectorStorePlugin |
| **Update** | `shared/app/runtime.py` | add `get_plugin()` |
| **Add** | `shared/app/tests/test_vector_store_plugin.py` | plugin lifecycle and degradation tests |
| **Update** | `shared/app/tests/test_runtime.py` | runtime lookup tests |
| **Update** | `shared/infra/milvus_store.py` | race-safe collection ensure and any small support helpers needed by the plugin |
| **Update** | `agents/requirement_manager/app/main_factory.py` | register plugin and bind/unbind facade in startup hooks |
| **Update** | `agents/requirement_manager/db/vector_store.py` | compatibility facade + plugin delegation |
| **Update** | `agents/requirement_manager/service/agent.py` | remove direct vector lifecycle ownership |
| **Update** | `agents/requirement_manager/tests/test_vector_store.py` | facade delegation tests |
| **Update** | `agents/requirement_manager/tests/test_agent.py` | updated lifecycle expectations |

Explicitly **not** in the first PR:

- registering the plugin in `pjm_agent`, `chat_agent`, `analysis_agent`, or `evolution_agent`
- deleting the requirement_manager facade
- changing collection/index strategy from the current Milvus defaults

## Future Adoption Candidates

Once the shared plugin is proven in `requirement_manager`, other agents can adopt it declaratively:

- `pjm_agent`: `pm_tasks`
- `analysis_agent`: `analysis_reports`
- `chat_agent`: `chat_knowledge`
- `evolution_agent`: `evolution_suggestions`

Those should be separate follow-up changes so each agent can decide whether vector search is optional or required.

## Out of Scope

- Multiple embedding models
- Automatic collection reindexing or schema migration
- Shared collections across agents
- Raw Milvus filter expression exposure
- Broad multi-agent rollout in the initial change
