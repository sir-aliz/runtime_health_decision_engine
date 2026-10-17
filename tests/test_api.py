"""Exercise a real HTTP server and an isolated SQLite database."""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from uuid import uuid4

import requests


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.log = open(Path(cls.directory.name) / 'server.log', 'w+')
        cls.addClassCleanup(cls.log.close)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        cls.url = f'http://127.0.0.1:{port}'
        cls.process = subprocess.Popen(
            [sys.executable, '-m', 'uvicorn', 'src.main:app', '--host', '127.0.0.1', '--port', str(port)],
            cwd=Path(__file__).resolve().parents[1],
            env=os.environ | {'RHDE_DB_PATH': str(Path(cls.directory.name) / 'api.sqlite3'),
                              'PYTHONDONTWRITEBYTECODE': '1'},
            stdout=cls.log, stderr=subprocess.STDOUT,
        )
        cls.addClassCleanup(cls.stop_server)
        for _ in range(100):
            try:
                response = requests.get(cls.url + '/health', timeout=.5)
                if response.status_code == 200:
                    return
            except requests.RequestException:
                pass
            if cls.process.poll() is not None:
                break
            time.sleep(.05)
        cls.log.seek(0)
        raise RuntimeError('Test server did not start: ' + cls.log.read())

    @classmethod
    def stop_server(cls):
        cls.process.terminate()
        try:
            cls.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.process.kill()
            cls.process.wait(timeout=5)

    def test_demo_runs_all_four_scenarios_and_can_repeat(self):
        from scripts.demo import run
        run(self.url)
        run(self.url)
        response = requests.get(self.url + '/deployments', timeout=5)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()), 8)

    def test_validation_and_conflict_responses(self):
        payload = dict(service_id='validation-' + uuid4().hex,
                       timestamp=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
                       latency_ms=100, request_count=100, error_count=0)
        self.assertEqual(requests.post(self.url + '/metrics', json={}, timeout=5).status_code, 422)
        self.assertEqual(requests.post(self.url + '/metrics', json=payload | {'error_count': 101}, timeout=5).status_code, 422)
        self.assertEqual(requests.post(self.url + '/metrics', json=payload, timeout=5).status_code, 200)
        self.assertEqual(requests.post(self.url + '/metrics', json=payload, timeout=5).status_code, 409)
        self.assertEqual(requests.get(self.url + '/deployments/missing/analysis', timeout=5).status_code, 404)

    def test_zero_requests_are_unknown(self):
        response = requests.post(self.url + '/metrics', json={
            'service_id': 'empty-' + uuid4().hex, 'timestamp': '2025-01-01T00:00:00Z',
            'latency_ms': 0, 'request_count': 0, 'error_count': 0,
        }, timeout=5)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['health_state'], 'Unknown')

    def test_page_and_assets_are_served(self):
        for path, content in [('/', 'Release review'), ('/incidents/example', 'Release review'),
                              ('/static/app.js', 'function render'), ('/static/style.css', ':root')]:
            with self.subTest(path=path):
                response = requests.get(self.url + path, timeout=5)
                self.assertEqual(response.status_code, 200)
                self.assertIn(content, response.text)


if __name__ == '__main__':
    unittest.main()
