"""Explainable release analysis. Association is never treated as proof of cause."""

from datetime import datetime, timezone

from .classification import classify_health
from .storage import analysis_records, iso_time

WINDOW_SECONDS = 600
MIN_REQUESTS = 100
MIN_COVERAGE = 0.8


def summarize(rows, start, end):
    buckets = [row for row in rows
               if row["timestamp"] - row["interval_seconds"] >= start
               and row["timestamp"] <= end]
    requests = sum(row["request_count"] for row in buckets)
    errors = sum(row["error_count"] for row in buckets)
    latency = (sum(row["latency_ms"] * row["request_count"] for row in buckets) / requests
               if requests else None)
    rate = errors / requests if requests else None
    return {
        "start": iso_time(start), "end": iso_time(end),
        "buckets": len(buckets), "request_count": requests, "error_count": errors,
        "error_rate": rate, "latency_ms": latency,
        "coverage": sum(row["interval_seconds"] for row in buckets) / WINDOW_SECONDS,
        "health": classify_health({"latency_ms": latency, "error_rate": rate}) if requests else "Unknown",
    }


def analyze(deployment, now=None):
    now = now or datetime.now(timezone.utc)
    release = datetime.fromisoformat(deployment["timestamp"]).timestamp()
    start, end = release - WINDOW_SECONDS, release + WINDOW_SECONDS
    rows, nearby = analysis_records(deployment, start, end)
    rows = [row for row in rows if row["timestamp"] <= now.timestamp()]
    before = summarize(rows, start, release)
    after = summarize(rows, release, end)
    reasons = []
    if now.timestamp() < end:
        reasons.append("The 10-minute post-deployment observation window is still open.")
    for label, window in [("Before", before), ("After", after)]:
        if window["coverage"] < MIN_COVERAGE:
            reasons.append(f"{label}: less than 80% of the 10-minute window has complete metric buckets.")
        if window["request_count"] < MIN_REQUESTS:
            reasons.append(f"{label}: fewer than 100 requests were observed.")
    if nearby:
        reasons.append("Another deployment overlaps the comparison period; this release cannot be isolated.")

    decision = "Insufficient evidence"
    evidence = []
    checks = ["Check dependency incidents and traffic changes before attributing a regression to this release."]
    if not reasons:
        error_delta = after["error_rate"] - before["error_rate"]
        latency_delta = after["latency_ms"] - before["latency_ms"]
        evidence = [
            f"Error rate: {before['error_rate']:.1%} → {after['error_rate']:.1%} ({error_delta * 100:+.1f} percentage points).",
            f"Mean latency: {before['latency_ms']:.0f} → {after['latency_ms']:.0f} ms ({latency_delta:+.0f} ms).",
        ]
        error_regression = (after["error_rate"] > 0.05 and error_delta >= 0.03
                            and after["error_rate"] >= 2 * before["error_rate"])
        latency_regression = (after["latency_ms"] > 500 and latency_delta >= 200
                              and after["latency_ms"] >= 1.5 * before["latency_ms"])
        baseline_rows = [row for row in rows
                         if row["timestamp"] - row["interval_seconds"] >= start
                         and row["timestamp"] <= release and row["request_count"] > 0]
        last_two = baseline_rows[-2:]
        prior_degradation = before["health"] != "Healthy" or (
            any(
                classify_health({"latency_ms": row["latency_ms"],
                                 "error_rate": row["error_count"] / row["request_count"]}) != "Healthy"
                for row in last_two
            )
        )
        if prior_degradation:
            decision = "Investigate existing incident"
            reasons.append("Degradation was present before the deployment. Timing does not support this release as the initial cause.")
            if error_regression or latency_regression:
                reasons.append("Metrics worsened further after release; the deployment could still have contributed.")
        elif error_regression or latency_regression:
            decision = "Consider rollback" if after["health"] == "Critical" else "Investigate this deployment"
            reasons.append("A material regression follows the deployment relative to the observed baseline.")
            checks.extend([
                "Inspect the release diff and logs for a mechanism consistent with the regression.",
                "Confirm the previous version is healthy and compatible with current data, migrations, and dependencies.",
                "Have the incident owner approve any rollback and monitor recovery afterward.",
            ])
        elif after["health"] != "Healthy":
            decision = "Investigate service health"
            reasons.append("Post-deployment health is degraded, but the relative change does not meet the release-regression rule.")
        else:
            decision = "No intervention suggested"
            reasons.append("No material degradation was observed in the comparison windows.")
    else:
        checks.insert(0, "Collect complete, non-overlapping metric buckets and isolate a single deployment before reassessing.")

    return {
        "deployment": deployment, "decision": decision, "reasons": reasons,
        "evidence": evidence, "checks": checks, "before": before, "after": after,
        "nearby_deployments": nearby,
        "timeline": [{"timestamp": iso_time(row["timestamp"]),
                      "interval_seconds": row["interval_seconds"],
                      "latency_ms": row["latency_ms"] if row["request_count"] else None,
                      "error_rate": row["error_count"] / row["request_count"] if row["request_count"] else None,
                      "request_count": row["request_count"]} for row in rows],
        "policy": {"window_seconds": WINDOW_SECONDS, "min_requests": MIN_REQUESTS,
                   "min_coverage": MIN_COVERAGE,
                   "error_regression": "Above 5%, at least +3 percentage points and 2× baseline",
                   "latency_regression": "Above 500 ms, at least +200 ms and 1.5× baseline"},
        "limitations": [
            "Timing and metric correlation do not prove the deployment caused the incident.",
            "This is a deterministic heuristic, not a calibrated probability or a guarantee that rollback is safe.",
            "Latency is a request-weighted mean, not a percentile. Historical analysis uses currently stored data.",
            "No action is executed. Recommendations require engineering review.",
        ],
    }
