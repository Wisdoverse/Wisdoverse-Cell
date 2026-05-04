# QA Agent

Automated acceptance verification for AI-generated code. Wisdoverse Cell's 7th agent.

## Events

| Event | Direction | Description |
|-------|-----------|-------------|
| `code.committed` | Subscribe | Triggers acceptance on new code |
| `qa.run-requested` | Subscribe | Manual/PJM Agent triggered run |
| `qa.acceptance-completed` | Publish | Always — full report |
| `qa.gate-failed` | Publish | Only on L0 FAIL |

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/qa/run` | POST | Trigger acceptance run |
| `/api/v1/qa/runs` | GET | List run history |
| `/api/v1/qa/runs/{id}` | GET | Run detail |
| `/api/v1/qa/stats` | GET | Aggregated stats |
| `/health` | GET | Liveness |
| `/health/ready` | GET | Readiness |
| `/metrics` | GET | Prometheus |

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `GITLAB_API_URL` | - | GitLab API base URL |
| `GITLAB_PROJECT_ID` | - | GitLab project ID |
| `GITLAB_QA_TOKEN` | - | Bot token for MR comments |
| `QA_RUNNER_TIMEOUT_SECONDS` | 120 | Runner subprocess timeout |
| `QA_FEISHU_WEBHOOK_URL` | - | QA-specific Feishu webhook |
| `QA_HIGH_SEVERITY_CHECKS` | - | Comma-separated L1 checks that trigger Feishu |

## Development

```bash
# Run locally
make qa-dev  # uvicorn --reload on port 8014

# Run tests
pytest agents/qa_agent/tests/ -v

# Self-acceptance
python .acceptance/runner.py --target agents/qa_agent --level all
```

## Architecture

```
code.committed → QAAgent.handle_event()
                      ↓
              AcceptanceRunnerService (subprocess: .acceptance/runner.py)
                      ↓
              QAReportStore (persist to PostgreSQL)
                      ↓
              QANotifier (EventBus + Feishu + GitLab MR)
```

Port: 8014 | Redis DB: 5
