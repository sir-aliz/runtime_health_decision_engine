"""Local SQLite persistence; no telemetry leaves this process."""

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from uuid import uuid4


def db_path():
    return Path(os.environ.get("RHDE_DB_PATH", ".local/rhde.sqlite3"))


@contextmanager
def connection():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    with connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS deployments (
                id TEXT PRIMARY KEY,
                service_id TEXT NOT NULL,
                version TEXT NOT NULL,
                previous_version TEXT NOT NULL,
                timestamp REAL NOT NULL,
                UNIQUE(service_id, version, timestamp)
            );
            CREATE INDEX IF NOT EXISTS deployments_service_time
                ON deployments(service_id, timestamp);
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY,
                service_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                interval_seconds INTEGER NOT NULL,
                latency_ms REAL NOT NULL,
                error_count INTEGER NOT NULL,
                request_count INTEGER NOT NULL,
                UNIQUE(service_id, timestamp)
            );
            CREATE INDEX IF NOT EXISTS metrics_service_time
                ON metrics(service_id, timestamp);
        """)


def iso_time(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def public_deployment(row):
    data = dict(row)
    data["timestamp"] = iso_time(data["timestamp"])
    return data


def add_deployment(data):
    deployment_id = str(uuid4())
    with connection() as conn:
        conn.execute(
            "INSERT INTO deployments VALUES (?, ?, ?, ?, ?)",
            (deployment_id, data.service_id, data.version,
             data.previous_version, data.timestamp.timestamp()),
        )
    return get_deployment(deployment_id)


def get_deployment(deployment_id):
    with connection() as conn:
        row = conn.execute("SELECT * FROM deployments WHERE id = ?", (deployment_id,)).fetchone()
    return public_deployment(row) if row else None


def list_deployments():
    with connection() as conn:
        rows = conn.execute("SELECT * FROM deployments ORDER BY timestamp DESC, id LIMIT 100").fetchall()
    return [public_deployment(row) for row in rows]


def add_metric(data):
    end = data.timestamp.timestamp()
    start = end - data.interval_seconds
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        overlap = conn.execute(
            """SELECT 1 FROM metrics WHERE service_id = ?
               AND timestamp > ? AND timestamp - interval_seconds < ? LIMIT 1""",
            (data.service_id, start, end),
        ).fetchone()
        if overlap:
            raise ValueError("Metric bucket overlaps an existing bucket for this service")
        conn.execute(
            """INSERT INTO metrics
               (service_id, timestamp, interval_seconds, latency_ms, error_count, request_count)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (data.service_id, end, data.interval_seconds, data.latency_ms,
             data.error_count, data.request_count),
        )


def analysis_records(deployment, start, end):
    with connection() as conn:
        metrics = conn.execute(
            """SELECT * FROM metrics WHERE service_id = ? AND timestamp > ?
               AND timestamp - interval_seconds < ? ORDER BY timestamp""",
            (deployment["service_id"], start, end),
        ).fetchall()
        nearby = conn.execute(
            """SELECT * FROM deployments WHERE service_id = ? AND id != ?
               AND timestamp >= ? AND timestamp < ? ORDER BY timestamp""",
            (deployment["service_id"], deployment["id"], start, end),
        ).fetchall()
    return [dict(row) for row in metrics], [public_deployment(row) for row in nearby]
