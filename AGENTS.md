# Repository instructions

Wisdoverse Cell is a self-hosted control plane for AI-native company operations.
Use the [product roadmap](docs/overview/roadmap.md) for delivery priorities.
Read the linked rules before work in their scope.

## Work

1. Before you edit files, inspect the working tree.
2. Before you edit files, create a branch from `main`.
3. Plan the required design, logic, events, tests, and documentation changes.
4. Give simple tasks with clear acceptance criteria to Luna (`gpt-6-luna`) when available.
5. Before you accept delegated work, review its results.
6. Verify each changed behavior with the applicable checks.
7. Report the result, evidence, remaining risk, and unverified checks.
8. Use `[Analysis]`, `[Risk:H/M/L]`, and `[Fixes]` in the final audit.

## Boundaries

- Keep `intern-archive` read-only. Never merge it into `main`.
- Recover archive changes only through reviewed patches or cherry-picks.
- Submit changes through a pull request. Never commit directly to `main`.
- Apply DDD with explicit bounded contexts, domain invariants, and data ownership.
- Keep microservices independently deployable. Follow the cloud-native requirements in the [architecture principles](docs/architecture/architecture-principles.md).
- Use Clean Architecture inside each runtime.
- Connect runtimes through versioned HTTP contracts or events.
- Access external platforms through ports and adapters.
- Follow strict Feature-Sliced Design in the frontend.
- Preserve the [stable identifiers](docs/architecture/architecture-principles.md#stable-identifiers).
- Keep required human approval for finance, legal, customer, and technical actions.
- Keep secrets, personal data, and private infrastructure details out of public artifacts.
- Never log secrets or personal data.

## Write

- Use English for repository text, with the [documented exceptions](docs/guides/agent-writing.md#scope).
- Reply in the user's language.
- Limit instruction sentences to 20 words. Give one action per instruction sentence.
- Limit description sentences to 25 words.
- Use direct commands and consistent terms.
- Apply the [writing rules](docs/guides/agent-writing.md) to new or changed English text.

## Read by task

| Task | Required reference |
|------|--------------------|
| Architecture or runtime boundaries | [Principles](docs/architecture/architecture-principles.md), [review checklist](docs/architecture/architecture-review-checklist.md) |
| Code | [Code standards](CONTRIBUTING.md#code-standards), [runtime guide](docs/guides/agent-development.md) |
| HTTP or event contracts | [API rules](docs/architecture/api-guidelines.md), [event rules](docs/architecture/event-guidelines.md) |
| Frontend | [Frontend guide](frontend/README.md), [architecture](docs/overview/architecture.md) |
| Setup or commands | [Onboarding](docs/overview/onboarding.md), [Makefile](Makefile) |
| Verification | [Test strategy](docs/architecture/testing-strategy.md), [documentation checks](docs/architecture/migration-plan.md#stage-0--architecture-docs-and-standards) |
| Review or pull request | [Contribution process](CONTRIBUTING.md#pull-request-process), [review roles](docs/CONTRIBUTING.md#5-ai-agent-collaboration) |

Keep this file within 75 lines and 500 words.
Put detailed rules in the relevant guide.
Keep tool-specific instruction files linked to this file.
