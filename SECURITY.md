# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| main    | Yes       |
| feat/*  | Development only |
| intern-archive | No - historical internal archive only |

## Reporting Vulnerabilities

Report suspected vulnerabilities privately. Do not open a public issue, public
pull request, or public discussion thread for a vulnerability under embargo.

### Preferred channel

Use GitHub private vulnerability reporting:
<https://github.com/Wisdoverse/Wisdoverse-Cell/security/advisories/new>.

### Backup channel

Email **dev@wisdoverse.com** if GitHub private reporting is unavailable to
you. Encrypt sensitive material with the maintainer team's published PGP key
when one is in use.

### What to include

- A description of the issue and the affected component or endpoint.
- Reproduction steps or a proof-of-concept that demonstrates the impact.
- Affected versions, commits, or deployment modes.
- An impact assessment: confidentiality, integrity, availability, and any
  affected data classes.
- Suggested remediation, if known.

### Response timeline

| Stage | Target |
|-------|--------|
| First reply from the maintainer team | Within 48 hours of report |
| Triage decision (accept, reject, request more info) | Within 5 business days |
| Remediation plan with target fix window | Within 10 business days for accepted high or critical reports |
| Coordinated disclosure | After a fix is available, with reporter agreement on timing |

A standard embargo period of up to 90 days applies from the date the report is
acknowledged. The maintainer team may request an extension when remediation
requires upstream coordination, and the reporter may agree or decline.

### Scope

In scope:

- Code in the `main` branch of this repository.
- Dependencies pinned by `requirements.txt`, `requirements-lock.txt`, and
  `Cargo.lock` when the issue is exploitable through Wisdoverse Cell's own
  attack surface.
- Container images published from this repository.

Out of scope:

- Issues that require physical access, an already-compromised host, or
  privileged credentials that the legitimate operator already controls.
- Reports based solely on missing best-practice headers or banner-grab output
  without a demonstrated exploit path.
- Denial-of-service through volumetric traffic without a logic-layer
  amplification component.
- Vulnerabilities in third-party services (Feishu, WeCom, OpenProject, GitLab,
  LiteLLM providers) that do not pivot through Wisdoverse Cell.

### Credit and disclosure

Reporters who follow private disclosure receive credit in the published
GitHub Security Advisory unless they prefer to remain anonymous. The
maintainer team does not currently operate a paid bug bounty.

## Security Architecture

### Authentication & Authorization
- **External**: Feishu/WeCom webhook signature verification; Feishu signature
  verification fails closed if `FEISHU_ENCRYPT_KEY` is missing while signature
  verification is enabled.
- **Internal**: `X-Internal-Key` header between services (HMAC comparison)
- **Database**: Per-agent PostgreSQL users with table-level GRANT
- **Redis**: Password authentication + per-agent db isolation

### Data Protection
- **PII Handling**: open_id hashed in logs, never in LLM prompts
- **Data Residency**: route model traffic through an approved LiteLLM proxy
- **DSAR**: Data Subject Access Request API. See the DSAR section below.
- **Transport**: External TLS should terminate at the reverse proxy or platform
  ingress. Internal Compose gRPC traffic runs on the private backend network by
  default; use mTLS or a service mesh before carrying internal traffic over an
  untrusted network.
- **Encryption**: Database encryption at rest should be enforced by the
  production PostgreSQL platform.

### LLM Security
- **Prompt Injection**: XML delimiter isolation for user input
- **Tool Permissions**: send_feishu_message restricted to self (non-admin)
- **Budget Control**: Redis-based daily cost metering with auto-downgrade
- **Circuit Breaker**: Prevents cascade failures on API outage

### Infrastructure
- **Containers**: Non-root user, read-only filesystem where possible
- **Secrets**: Environment variables (Docker Secrets in production)
- **Network**: Backend network is internal-only
- **Monitoring**: 51 Prometheus alert rules including security alerts

## DSAR (Data Subject Access Requests)

The DSAR API supports data subject rights workflows for GDPR and PIPL
compliance.

### Supported Operations

| Operation | Endpoint | Description |
|------|------|------|
| Data export | `POST /api/dsar/export` | Export all user data as JSON |
| Data deletion | `POST /api/dsar/delete?confirm=true` | Delete or anonymize user data |
| Deletion preview | `POST /api/dsar/delete` | Dry-run preview of affected records |

### Data Scope

DSAR requests cover these data sources:

- **Chat Agent**: chat history and user preferences
- **PJM Agent**: task assignment records and approval records
- **Sync Module**: user-linked data in synchronization logs
- **Requirements capability**: user context captured during requirement extraction

### Processing Flow

1. Each agent mounts its own `shared.api.dsar_router`.
2. Each agent exports or deletes data it owns through its local `DSARService`
   and `DSARHandler`.
3. Deletion defaults to dry-run mode. Write operations require
   `confirm=true`.
4. Operators aggregate per-agent results and respond to the requester within
   30 days.

### Data Retention

| Data Type | Retention | Notes |
|----------|----------|------|
| Chat history | 90 days | Archived automatically after expiry |
| Audit logs | 365 days | Legal and compliance retention |
| LLM call logs | 30 days | Metadata only, no prompt content |
| Event queues | 24 hours | Redis Streams TTL |

## LLM Cross-Border Data Compliance

### Proxy Enforcement

```bash
# .env configuration: route LLM traffic through the approved LiteLLM proxy.
LITELLM_API_BASE=https://llm-proxy.example.com/v1
```

- `LLMGateway` sends provider requests through `LITELLM_API_BASE` when it is
  configured.
- Production deployments should set `LITELLM_API_BASE` to the approved regional
  proxy instead of routing directly to provider APIs.
- The proxy is responsible for logging, data masking, and regional controls.

### LLM Prompt Security

- **No PII in prompts**: `open_id`, phone numbers, email addresses, and similar
  identifiers must not enter LLM prompts.
- **XML delimiter isolation**: user input is wrapped in `<user_input>` tags to
  reduce prompt-injection risk.
- **AI content labeling**: agent-generated content is labeled as
  "AI generated, for reference only".
- **Output filtering**: system prompts and internal information must not be
  exposed in responses.

## Dependency Management

- Python: `requirements.txt` with `scripts/lock-deps.sh` for reproducible builds
- Rust: `Cargo.lock` for dependency integrity and reproducible gateway builds
- Regular dependency updates via CI scanning
