# ADR-0001: Migrate EventBus from Redis LIST to Redis Streams

## Status
Accepted (2026-03-07)

## Context
The EventBus used Redis LIST (LPUSH/BRPOP) with manual fan-out via Redis SET tracking consumer groups. This had several limitations:
- No built-in acknowledgment — failed consumers lose messages
- No replay capability — messages consumed once are gone
- Manual fan-out logic — complex and error-prone
- No dead letter queue — poisoned messages block consumers
- No observability — no way to check pending/lag

## Decision
Migrate to Redis Streams (XADD/XREADGROUP) which provides:
- **Native consumer groups** with acknowledgment (XACK)
- **Message persistence** — messages stay in stream until trimmed
- **Replay** — consumers can re-read from any position
- **Pending entries** — acts as dead letter queue for failed processing
- **Observability** — XINFO/XPENDING for monitoring lag and health
- **Approximate trimming** — MAXLEN ~10000 for bounded memory

## Consequences

### Positive
- Messages survive consumer restarts (re-delivered from pending)
- Multiple consumer groups work without manual fan-out code
- Built-in monitoring via get_pending_count()
- Simpler publish() — single XADD replaces LPUSH + smembers loop

### Negative
- Requires Redis 5.0+ (we use Redis 8, so no issue)
- Slightly different error semantics (must XACK after processing)
- Stream trimming is approximate (~MAXLEN), not exact

### Neutral
- EventBusProtocol interface unchanged — drop-in replacement
- NATS backend still available as alternative
