# RHDE — Release decision support

A local MVP for reviewing whether a deployment is associated with a service regression and whether rollback deserves investigation. It records deployments and metric buckets in SQLite, compares the ten minutes before and after a release, and presents an evidence summary and timeline.

**Recommendations are advisory. RHDE does not execute rollbacks, retries, or alerts, and correlation is not proof of cause.**

## Run

Python 3.10+ is required (validated with Python 3.12).

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

From another terminal, in the repository with the same virtual environment active:

```bash
python scripts/demo.py
```

The demo inserts four synthetic scenarios through the API and asserts their results:

| Scenario | Expected recommendation |
| --- | --- |
| Error rate rises from 0% to 20% after release | Consider rollback |
| Healthy release | No intervention suggested |
| Degradation already exists before release | Investigate existing incident |
| Only 20 requests in each window | Insufficient evidence |

Use the app's root page on port 8000 to select a deployment, inspect before/after metrics, and review the timeline and next checks. Refresh to include newly collected data. The API schema is served at `/docs`.

Demo runs use unique service names and do not overwrite existing data. Each run adds four deployments and 80 metric buckets. Demo data is synthetic; passing it establishes behavior, not operational accuracy or business value.

In the prepared cloud workspace, the existing interpreter is `/workspace/.venvs/rhde/bin/python`; use it in place of `python` if you do not create a local virtual environment.

## API and data contract

- `POST /deployments`: `service_id`, `version`, `previous_version`, `timestamp`. Returns a deployment ID and HTTP 201. Duplicate service/version/time records return 409.
- `POST /metrics`: `service_id`, `timestamp`, `latency_ms`, `error_count`, `request_count`, optional `interval_seconds` (default 60, range 1–600). Returns the original per-bucket health classification. Empty buckets return `Unknown`.
- `GET /deployments`: latest 100 recorded deployments.
- `GET /deployments/{id}/analysis`: evidence, recommendation, before/after summaries, timeline, and policy details. Unknown IDs return 404.
- `GET /health`: process readiness.
- `/` and `/incidents/{id}`: incident review page.

Timestamps must be timezone-aware ISO 8601 strings or Unix seconds; future timestamps are rejected. A metric timestamp is the **end** of its bucket. Submit interval counts, not cumulative counters. `latency_ms` must be the mean latency for requests in that bucket, not p95/p99. Counts must be nonnegative integers and errors cannot exceed requests. Buckets must not overlap for the same service: duplicate or overlapping submissions return 409. Aggregate replicas before ingestion. Gaps are preserved, not interpreted as zero errors.

Example event shapes (replace the dates with the actual observation times):

```json
{"service_id":"checkout","version":"v2","previous_version":"v1","timestamp":"2026-01-01T12:00:00Z"}
```

```json
{"service_id":"checkout","timestamp":"2026-01-01T12:01:00Z","interval_seconds":60,"latency_ms":150,"error_count":20,"request_count":100}
```

## Decision policy

Each comparison window is ten minutes. Analysis requires a completed post-release window, at least 100 requests and 80% bucket coverage in **each** window. Buckets crossing a window or deployment boundary are excluded from that window's aggregate. Nearby deployments in the comparison period make attribution ambiguous and return `Insufficient evidence`.

Error rates are total errors / total requests; latency is request-weighted mean latency.

- Error regression: post-release rate above 5%, at least +3 percentage points, and at least twice the baseline.
- Latency regression: post-release mean above 500 ms, at least +200 ms, and at least 1.5 times the baseline.
- A degraded baseline, or degradation in either of its final two nonempty buckets, leads to `Investigate existing incident`. This conservative rule can also flag a transient pre-release spike.
- A new material regression with critical post-release health (error rate above 10% or latency above 1000 ms) leads to `Consider rollback`; a smaller qualifying regression leads to `Investigate this deployment`.
- Degraded post-release health without a qualifying relative regression leads to `Investigate service health`.
- Otherwise, no intervention is suggested.

These are explicit demo heuristics, not statistically calibrated confidence estimates. The page shows checks for dependencies, traffic changes, release contents, migration compatibility, and engineer approval before any action.

## Persistence and tests

The default database is `.local/rhde.sqlite3` relative to the working directory. Set `RHDE_DB_PATH` to use another file. Data survives server restarts. Use a separate path for experiments; no cleanup job deletes records automatically.

```bash
python -m unittest discover -v
```

The suite uses temporary databases and starts an isolated HTTP server. It checks the four scenarios, repeatable demo ingestion, data validation, persistence, weighted aggregates, missing coverage, open observation windows, overlapping deployments, bucket boundaries, and API/UI asset responses. No company credentials or services are required.

## MVP boundaries

This is a single-user local demo with no authentication, production telemetry connector, incident notification, or automatic remediation. Keep it bound to loopback. It compares fixed windows; it does not infer root cause, model changing traffic composition, evaluate business impact, or determine whether schema changes make rollback safe. Historical analysis uses currently stored observations and is not a reconstruction of what was known at the time. The UI lists the most recent 100 deployments; older IDs remain accessible directly. Dependencies have version ranges, not a frozen lockfile.

The next validation step is to replay real, approved incident data and assess incorrect recommendations as well as useful ones. Older project documents describe the original stateless prototype; this README describes the release-analysis MVP.
