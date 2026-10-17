"""Seed four isolated synthetic scenarios through the public API; safe to rerun."""
import argparse
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import requests

SCENARIOS = [
    ('release-regression', 0, 20, 100, 'Consider rollback'),
    ('healthy-release', 0, 0, 100, 'No intervention suggested'),
    ('existing-incident', 20, 20, 100, 'Investigate existing incident'),
    ('low-traffic', 0, 1, 2, 'Insufficient evidence'),
]


def run(base_url):
    run_id = uuid4().hex[:8]
    release = (datetime.now(timezone.utc) - timedelta(minutes=20)).replace(microsecond=0)
    with requests.Session() as session:
        for name, before_errors, after_errors, count, expected in SCENARIOS:
            service = f'demo-{name}-{run_id}'
            response = session.post(base_url + '/deployments', json={
                'service_id': service, 'version': 'v2', 'previous_version': 'v1',
                'timestamp': release.isoformat(),
            }, timeout=10)
            response.raise_for_status()
            deployment_id = response.json()['id']
            for minute in range(-9, 11):
                errors = before_errors if minute <= 0 else after_errors
                response = session.post(base_url + '/metrics', json={
                    'service_id': service,
                    'timestamp': (release + timedelta(minutes=minute)).isoformat(),
                    'interval_seconds': 60, 'request_count': count,
                    'error_count': errors, 'latency_ms': 150,
                }, timeout=10)
                response.raise_for_status()
            response = session.get(f'{base_url}/deployments/{deployment_id}/analysis', timeout=10)
            response.raise_for_status()
            result = response.json()
            if result['decision'] != expected:
                raise RuntimeError(f"{name}: expected {expected}, got {result['decision']}")
            print(f"PASS {name}: {result['decision']} (deployment {deployment_id})")
    print('All four scenarios passed. Open the app and select a demo deployment.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    run(args.base_url.rstrip('/'))
