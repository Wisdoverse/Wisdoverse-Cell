# Requirements Integrations

This directory contains integration wiring owned by the requirements
capability. Code here may coordinate requirements-specific workflow behavior,
but shared platform primitives must stay under `shared/integrations`.

## Boundary Rules

- Use shared platform clients or ports for external systems.
- Keep requirement extraction, confirmation, and PRD workflow decisions inside
  the requirement manager agent.
- Do not expose these modules as shared Feishu primitives.
- Do not import another deployed agent's internal code; use typed clients or
  EventBus events.

## Packages

| Package | Responsibility |
|---------|----------------|
| `feishu/` | Requirements-owned Feishu bot, card, event, message recording, and session wiring. |
