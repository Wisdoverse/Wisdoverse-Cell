# Support

This document describes how to get help with Wisdoverse Cell, what response to
expect, and which channel matches your situation.

## Quick Reference

| Situation | Channel | Response target |
|-----------|---------|-----------------|
| Reproducible defect | [GitHub issue: bug report](https://github.com/Wisdoverse/Wisdoverse-Cell/issues/new?template=bug_report.yml) | Triaged within 5 business days |
| Focused product or engineering improvement | [GitHub issue: feature request](https://github.com/Wisdoverse/Wisdoverse-Cell/issues/new?template=feature_request.yml) | Triaged within 5 business days |
| Open-ended question or design discussion | [GitHub Discussions](https://github.com/Wisdoverse/Wisdoverse-Cell/discussions) | Best-effort; community-driven |
| Suspected security vulnerability | Private process in [SECURITY.md](./SECURITY.md) | First reply within 48 hours |
| Conduct concern | dev@wisdoverse.com (see [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md)) | Reviewed by uninvolved maintainers |
| Commercial use, hosting, or licensing inquiry | dev@wisdoverse.com | Within 5 business days |

## Filing a Good Bug Report

Bug reports should let a maintainer reproduce the failure without follow-up.
Include:

- Wisdoverse Cell commit hash or release tag.
- Deployment mode: Docker Compose, local Python, or other.
- Operating system, Python version, Rust version, and Node.js version where
  relevant.
- Minimal reproduction: configuration, commands, and observed output.
- Expected behavior, with a reference to the spec or documentation when
  applicable.
- Logs with secrets, tokens, and personal data redacted.

The bug-report issue template enforces these fields. Reports that are missing
required fields are returned for revision rather than triaged.

## Asking Questions

Open-ended questions belong in
[GitHub Discussions](https://github.com/Wisdoverse/Wisdoverse-Cell/discussions),
not issues. Search existing discussions before posting. When asking a question:

- Link to the source files, ADRs, or specification sections under discussion.
- State what you have already tried.
- Describe the operational or product outcome you are trying to achieve, not
  only the immediate technical step.

The project does not provide synchronous support channels (Slack, Discord,
direct messages, or email) for general questions.

## Documentation

Self-service documentation should answer most questions before opening an
issue:

- [README](./README.md) for service goals, runtime options, and onboarding.
- [SPEC.md](./SPEC.md) for the implementation contract and normative
  requirements.
- [docs/INDEX.md](./docs/INDEX.md) as the documentation map.
- [docs/guides/operations.md](./docs/guides/operations.md) for deployment,
  runtime switches, and troubleshooting.
- [docs/guides/incident-response.md](./docs/guides/incident-response.md) for
  on-call playbooks and severity definitions.

## Supported Versions

Only the `main` branch receives active support and fixes. Tagged releases are
supported for the period stated in [SECURITY.md](./SECURITY.md). The
`intern-archive` branch is a read-only historical archive and receives no
support.

## Commercial Use

Wisdoverse Cell is source-available under the
[Wisdoverse Cell Business Source License 1.1](./LICENSE)
(`LicenseRef-Wisdoverse-Cell-BSL-1.1`). Production use, SaaS or hosted
services, managed services, resale, sublicensing, and competing products
require a separate commercial license. Direct commercial inquiries to
**dev@wisdoverse.com**.
