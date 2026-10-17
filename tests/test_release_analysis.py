from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from src.analysis import analyze
from src.models import DeploymentData, MetricData
from src import storage

RELEASE = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)


class ReleaseAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.environment = patch.dict(os.environ, {'RHDE_DB_PATH': str(Path(self.directory.name) / 'test.sqlite3')})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        storage.init_db()
        self.deployment = self.deploy()

    def deploy(self, service='checkout', timestamp=RELEASE, version='v2'):
        return storage.add_deployment(DeploymentData(service_id=service, timestamp=timestamp,
                                                     version=version, previous_version='v1'))

    def metric(self, minute, *, errors=0, requests=100, latency=150, service='checkout', interval=60):
        data = MetricData(service_id=service, timestamp=RELEASE + timedelta(minutes=minute),
                          latency_ms=latency, error_count=errors, request_count=requests,
                          interval_seconds=interval)
        storage.add_metric(data)
        return data

    def seed(self, before_errors=0, after_errors=20, requests=100, after_latency=150):
        for minute in range(-9, 11):
            self.metric(minute, errors=before_errors if minute <= 0 else after_errors,
                        requests=requests, latency=150 if minute <= 0 else after_latency)

    def test_critical_error_regression_suggests_reviewed_rollback(self):
        self.seed()
        result = analyze(self.deployment)
        self.assertEqual(result['decision'], 'Consider rollback')
        self.assertEqual(result['before']['error_rate'], 0)
        self.assertEqual(result['after']['error_rate'], .2)
        self.assertEqual(result['before']['coverage'], 1)
        self.assertEqual(result['after']['request_count'], 1000)
        self.assertTrue(any('approve' in check for check in result['checks']))

    def test_healthy_release(self):
        self.seed(after_errors=0)
        self.assertEqual(analyze(self.deployment)['decision'], 'No intervention suggested')

    def test_preexisting_incident_is_not_blamed_on_release(self):
        self.seed(before_errors=20)
        self.assertEqual(analyze(self.deployment)['decision'], 'Investigate existing incident')

    def test_recent_baseline_degradation_is_not_hidden_by_average(self):
        for minute in range(-9, 11):
            self.metric(minute, errors=20 if minute >= -1 else 0)
        result = analyze(self.deployment)
        self.assertLess(result['before']['error_rate'], .05)
        self.assertEqual(result['decision'], 'Investigate existing incident')

    def test_low_traffic(self):
        self.seed(after_errors=1, requests=2)
        self.assertEqual(analyze(self.deployment)['decision'], 'Insufficient evidence')

    def test_degradation_in_last_pre_release_bucket_blocks_attribution(self):
        for minute in range(-9, 11):
            self.metric(minute, errors=20 if minute >= 0 else 0)
        result = analyze(self.deployment)
        self.assertEqual(result['before']['health'], 'Healthy')
        self.assertEqual(result['decision'], 'Investigate existing incident')

    def test_missing_metrics(self):
        result = analyze(self.deployment)
        self.assertEqual(result['decision'], 'Insufficient evidence')
        self.assertIsNone(result['before']['error_rate'])

    def test_high_volume_does_not_compensate_for_missing_coverage(self):
        self.metric(0, requests=10000)
        self.metric(1, requests=10000, errors=2000)
        self.assertEqual(analyze(self.deployment)['decision'], 'Insufficient evidence')

    def test_window_must_finish(self):
        self.seed()
        result = analyze(self.deployment, now=RELEASE + timedelta(minutes=9))
        self.assertEqual(result['decision'], 'Insufficient evidence')
        self.assertEqual(result['after']['request_count'], 900)

    def test_overlapping_deployment_prevents_attribution(self):
        self.seed()
        self.deploy(timestamp=RELEASE + timedelta(minutes=2), version='v3')
        self.assertEqual(analyze(self.deployment)['decision'], 'Insufficient evidence')

    def test_other_services_do_not_contaminate_analysis(self):
        self.seed(after_errors=0)
        self.deploy(service='other')
        self.metric(1, errors=100, service='other')
        self.assertEqual(analyze(self.deployment)['decision'], 'No intervention suggested')

    def test_latency_regression_without_errors(self):
        self.seed(after_errors=0, after_latency=1200)
        self.assertEqual(analyze(self.deployment)['decision'], 'Consider rollback')

    def test_warning_regression_does_not_recommend_rollback(self):
        self.seed(after_errors=8)
        self.assertEqual(analyze(self.deployment)['decision'], 'Investigate this deployment')

    def test_means_and_rates_are_weighted_by_request_counts(self):
        for minute in range(-9, 11):
            self.metric(minute, requests=100 if minute != 10 else 1000,
                        errors=0 if minute != 10 else 500,
                        latency=100 if minute != 10 else 1000)
        result = analyze(self.deployment)
        self.assertAlmostEqual(result['after']['error_rate'], 500 / 1900)
        self.assertAlmostEqual(result['after']['latency_ms'], 1090000 / 1900)

    def test_cross_release_bucket_is_excluded_from_both_windows(self):
        self.metric(.5, interval=60)
        result = analyze(self.deployment)
        self.assertEqual(result['before']['buckets'], 0)
        self.assertEqual(result['after']['buckets'], 0)

    def test_duplicate_and_overlapping_buckets_are_rejected(self):
        self.metric(0)
        with self.assertRaises(ValueError):
            self.metric(0)
        with self.assertRaises(ValueError):
            self.metric(.5)
        self.metric(1)  # Adjacent intervals are valid.

    def test_duplicate_deployment_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.deploy()

    def test_database_reinitialization_preserves_records(self):
        self.seed()
        storage.init_db()
        self.assertEqual(storage.get_deployment(self.deployment['id']), self.deployment)
        self.assertEqual(analyze(self.deployment)['decision'], 'Consider rollback')

    def test_invalid_metrics_are_rejected(self):
        base = dict(service_id='checkout', timestamp=RELEASE, latency_ms=10,
                    request_count=100, error_count=0)
        for change in [dict(request_count=-1), dict(error_count=-1),
                       dict(error_count=101), dict(request_count=0, error_count=1),
                       dict(latency_ms=float('nan')), dict(latency_ms=float('inf')),
                       dict(latency_ms=-1), dict(service_id=' '),
                       dict(timestamp='bad date'), dict(timestamp='2025-01-01T00:00:00'),
                       dict(timestamp=datetime.now(timezone.utc) + timedelta(days=1)),
                       dict(request_count=1.5), dict(request_count=True), dict(interval_seconds=0)]:
            with self.subTest(change=change), self.assertRaises(ValidationError):
                MetricData(**(base | change))

    def test_unix_timestamp_compatibility(self):
        metric = MetricData(service_id='checkout', timestamp=str(RELEASE.timestamp()),
                            latency_ms=100, request_count=10, error_count=0)
        self.assertEqual(metric.timestamp, RELEASE)

    def test_empty_buckets_provide_no_latency_evidence(self):
        self.seed(after_errors=0, requests=0)
        result = analyze(self.deployment)
        self.assertEqual(result['decision'], 'Insufficient evidence')
        self.assertIsNone(result['after']['latency_ms'])
        self.assertEqual(result['after']['health'], 'Unknown')


if __name__ == '__main__':
    unittest.main()
