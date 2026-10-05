# Writing rules for coding assistants

Apply these rules when you write or change English repository text.
The rules use ASD-STE100 Issue 9 as their language reference.
Full ASD-STE100 conformance also requires a vocabulary and grammar review against the official standard.

## Scope

Use English for documentation, comments, API descriptions, model prompts, agent seed prompts, commits, pull requests, and runbooks.
Keep non-English text only in these cases:

- Locale files.
- External platform field names.
- Quoted user or source content.
- Test fixtures that check multilingual behavior.
- Product copy during a documented localization migration.

Use the user's language in chat.
For non-English replies, preserve clear terms and short statements.
English word limits do not define limits for other languages.
Keep code, identifiers, external contracts, and exact quotations unchanged during a language edit.

## Sentence rules

1. Limit each instruction sentence to 20 words.
2. Put one action in each instruction sentence.
3. Use the imperative for instructions.
4. Put a required condition before its action.
5. Limit each description sentence to 25 words.
6. Use one topic per paragraph, with at most six sentences.
7. Use active voice. In descriptions, use passive voice only when the actor is unknown.
8. Use simple verb forms. Avoid progressive and perfect tenses.
9. Expand contractions.
10. Keep noun groups within three words. Define a short term when a technical name needs more words.
11. Keep articles where they clarify the noun.
12. Keep instructions out of informational notes.

## Word choice

Use dictionary-approved general words with their specified meanings and parts of speech.
Use established technical nouns and verbs for software concepts.
Use one term for each concept throughout a document.
Avoid idioms, metaphors, and synonyms used only for variety.
Check unfamiliar terms against the official dictionary or the [project glossary](../overview/glossary.md).
Do not mark vocabulary as STE-approved without that check.

Use these terms when you describe this project:

| Term | Meaning |
|------|---------|
| Coding assistant | A tool that changes this repository. |
| `AgentRole` | A durable company role in the Control Plane. |
| Runtime | A service with its own deployment boundary. |
| `AgentRun` | A durable record of an agent execution. |
| Port | An interface that the owning context defines. |
| Adapter | An implementation that connects a port to an external system. |
| Domain event | A record of a domain change within one context. |
| Integration event | A versioned message that crosses a runtime boundary. |

Preserve API field names, event names, paths, and [runtime identifiers](../architecture/architecture-principles.md#stable-identifiers).
For example, keep `AgentRun` distinct from the runtime that performs the work.

## Repository examples

| Avoid | Use |
|-------|-----|
| It should probably be retried after approval. | After the operator approves the work item, retry the failed run. |
| Update the route and add tests and refresh the API docs. | Update the route. Add contract tests. Update the API reference. |
| The adapter was fixed. | The HTTP adapter now rejects a response without an artifact reference. |
| Tests are green. | The adapter tests passed: 12 passed, 0 failed. |

The test count above is illustrative.
Use measured results in actual reports.
Keep uncertainty visible when evidence is incomplete.
Do not replace a contract's `MUST`, `SHOULD`, or `MAY` with a different obligation during a language edit.

## Review procedure

1. Identify the reader, task, and required result.
2. Check each instruction for its condition, action, and object.
3. Check sentence limits after you remove Markdown markup.
4. Keep complete commands and identifiers together when you count words.
5. Check terms against the glossary and the official dictionary.
6. Check that the edit preserves permissions, contracts, and acceptance gates.
7. Check links, privacy, and the final diff.

For delegated work, follow the [model selection and review rules](../CONTRIBUTING.md#5-ai-agent-collaboration).

## Sources

- [ASD-STE100 Issue 9](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf): sections 1–6 cover vocabulary, grammar, instructions, and descriptions.
- [Official STE FAQ](https://www.asd-ste100.org/STE_faq.html): dictionary use, technical terms, and applications outside maintenance manuals.
- [Karpathy's post](https://x.com/karpathy/status/2105819303471976479): user-supplied reference for this change.

Sources reviewed on 2026-10-05.
The X page did not return its body during this review.
The language rules above use the official STE material.
