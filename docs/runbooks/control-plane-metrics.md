# Control Plane metrics and alerts

The Control Plane has a company-scoped, read-only Prometheus endpoint at
`GET /api/v1/control-plane/operating-metrics/prometheus`. It requires both
`X-Internal-Key` and `X-Control-Plane-Operator-Token`; the operator principal
must have `control-plane:read` access for the selected company. The endpoint
exports aggregate metrics. Do not add company, user, run, approval, or other
record identifiers as metric labels.

Scraping is opt-in. The existing Prometheus configuration and default
observability deployment do not enable this job. The example at
[`docs/examples/control-plane-prometheus-scrape.yml`](../examples/control-plane-prometheus-scrape.yml)
is a single job to merge into a separately managed Prometheus configuration.
Its target assumes the Prometheus and API containers share a Docker network;
change it if your deployment uses another reachable address. The example uses
the canonical `cmp_wisdoverse_cell` company ID; set `company_id` to a company
the configured operator token is allowed to read.

## Configure credentials and enable the job

Provision the internal key and an operator token with `control-plane:read` for
the intended company through your secret manager. Mount them read-only in the
Prometheus container at the two paths shown in the example. Keep the files
outside source control, restrict their host and container permissions, and do
not put credential values in Prometheus YAML, command-line arguments, or
logs. Ensure the API is reachable only over the intended private network; use
TLS when traffic crosses a trust boundary.

Prometheus v2.55.1 supports `http_headers` entries with `files` values, as
documented in its [versioned configuration reference](https://github.com/prometheus/prometheus/blob/v2.55.1/docs/configuration/configuration.md).
Before enabling the job, validate the merged configuration with `promtool`
from that same image. The configuration has not been validated or deployed in
this environment.

For a configuration mounted at `/etc/prometheus/prometheus.yml`, validate
configuration and rules inside the running Prometheus container:

```sh
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
docker compose exec prometheus promtool check rules /etc/prometheus/rules/control-plane-alerts.yml
```

After validation, apply the separately managed configuration using your normal
Prometheus deployment process. Confirm the job is `UP` at the Prometheus
Targets page or `GET /api/v1/targets`. Check `scrape_samples_scraped` and query
the exported families, including `control_plane_pending_approval_oldest_age_seconds`,
`control_plane_unresolved_execution_leases`,
`control_plane_pending_outbox_oldest_age_seconds`,
`control_plane_adapter_errors_total`,
`control_plane_work_queue_delay_p95_seconds`,
`control_plane_run_success_rate`, and
`control_plane_full_cost_usd_per_accepted_outcome`.

If the target is down, inspect only sanitized scrape errors and verify network
reachability, mounted file paths, file readability, and the company grant.
Authentication failures should be handled as credential/configuration issues;
never copy request headers or secret contents into tickets or logs.

## Validate alert rules

The rules in
[`docker/prometheus/rules/control-plane-alerts.yml`](../../docker/prometheus/rules/control-plane-alerts.yml)
define `ControlPlanePendingApprovalsOld`,
`ControlPlaneExecutionRecoveryBacklog`, `ControlPlaneOutboxBacklogOld`,
`ControlPlaneAdapterErrors`, `ControlPlaneWorkQueueDelayHigh`,
`ControlPlaneRunSuccessRateLow`, and `ControlPlaneAcceptedOutcomeCostHigh`.
They cover a pending approval older than 24 hours, unresolved execution
leases, old outbox delivery, adapter errors, high queue delay, low run success,
and high accepted-outcome cost. Review and approve their thresholds and
notification routing before enabling alerts in an environment.

Check rule syntax with the command above. In Prometheus, inspect
`ALERTS{alertname=~"ControlPlane.*"}` and each alert expression to confirm the
rules are loaded and have data. A healthy zero or absent signal can be normal;
do not create operational incidents merely to force an alert to fire. Use a
separate, non-production rule test fixture with `promtool test rules` when
testing firing behavior. This documentation and the checked-in rule file do
not establish that scraping or alert delivery has been deployed or exercised
in staging or production.
