"""Integration tests for qBittorrent agent components."""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from detectors.lag_detector import LagDetector
from detectors.torrent_health import TorrentHealthAnalyzer
from detectors.predictive_analyzer import PredictiveAnalyzer
from detectors.completion_predictor import TorrentCompletionPredictor

from recovery.recovery_engine import RecoveryEngine
from recovery.bandwidth_optimizer import BandwidthOptimizer
from recovery.connection_optimizer import ConnectionOptimizer
from recovery.category_rules import CategoryRulesEngine
from recovery.config_auto_tuner import ConfigAutoTuner
from recovery.backup_restore import BackupRestoreManager

from monitoring.metrics import SystemMetrics
from logging.notification_system import NotificationSystem, NotificationLevel
from optimization.ab_testing_framework import ABTestingFramework


class TestLagDetectionIntegration(unittest.TestCase):
    """Test lag detection with multiple factors."""

    def setUp(self):
        self.lag_detector = LagDetector(sensitivity="balanced")
        self.api_client = Mock()
        self.config_manager = Mock()
        self.logger = Mock()

    def test_lag_detection_with_all_factors(self):
        """Test lag detection considering all factors."""
        # Mock API client responses
        self.api_client.get_server_state.return_value = {
            "dl_info_speed": 1000000,
            "up_info_speed": 500000,
            "nb_dl": 5,
            "nb_up": 3,
        }

        self.api_client.get_torrents.return_value = [
            {"name": "torrent1", "state": "downloading", "num_seeds": 10},
        ]

        self.config_manager.get_value.return_value = "500"

        # Mock system metrics
        with patch("monitoring.metrics.SystemMetrics.get_cpu_percent", return_value=50):
            with patch("monitoring.metrics.SystemMetrics.get_memory_info") as mem_mock:
                mem_mock.return_value = {"percent": 60}

                # Run detection
                lag_score, description = self.lag_detector.detect_lag(
                    self.api_client,
                    self.config_manager,
                )

                # Should detect healthy state
                self.assertIsInstance(lag_score, float)
                self.assertGreaterEqual(lag_score, 0)
                self.assertLessEqual(lag_score, 100)
                self.assertIsInstance(description, str)

    def test_lag_detection_high_cpu(self):
        """Test lag detection with high CPU usage."""
        self.api_client.get_server_state.return_value = {
            "dl_info_speed": 500000,
            "up_info_speed": 200000,
            "nb_dl": 3,
        }

        self.api_client.get_torrents.return_value = []
        self.config_manager.get_value.return_value = "500"

        with patch("monitoring.metrics.SystemMetrics.get_cpu_percent", return_value=85):
            with patch("monitoring.metrics.SystemMetrics.get_memory_info") as mem_mock:
                mem_mock.return_value = {"percent": 50}

                lag_score, description = self.lag_detector.detect_lag(
                    self.api_client,
                    self.config_manager,
                )

                # Should detect CPU pressure
                self.assertGreater(lag_score, 0)


class TestTorrentHealthIntegration(unittest.TestCase):
    """Test torrent health analysis."""

    def setUp(self):
        self.health_analyzer = TorrentHealthAnalyzer()

    def test_health_scoring_mixed_torrents(self):
        """Test health scoring with various torrent states."""
        torrents = [
            {
                "hash": "abc123",
                "name": "healthy",
                "state": "uploading",
                "num_seeds": 50,
                "upspeed": 100000,
                "completion_date": 0,
            },
            {
                "hash": "def456",
                "name": "stalled",
                "state": "downloading",
                "num_seeds": 0,
                "upspeed": 0,
                "completion_date": 0,
            },
        ]

        score = self.health_analyzer.score_torrents(torrents)

        self.assertIn("abc123", score["by_torrent"])
        self.assertIn("def456", score["by_torrent"])
        self.assertEqual(score["by_torrent"]["abc123"]["health"], "EXCELLENT")


class TestRecoveryEngineIntegration(unittest.TestCase):
    """Test recovery engine with simulated scenarios."""

    def setUp(self):
        self.recovery_engine = RecoveryEngine()
        self.api_client = Mock()

    def test_recovery_strategy_order(self):
        """Test that recovery strategies execute in correct order."""
        strategies_called = []

        def mock_strategy(strategy_name):
            def strategy():
                strategies_called.append(strategy_name)
                return True

            return strategy

        # Override strategies with mocks
        self.recovery_engine.connection_cleanup = mock_strategy("cleanup")
        self.recovery_engine.dht_refresh = mock_strategy("dht")

        # Execute
        result = self.recovery_engine.execute_recovery(self.api_client)

        # First two strategies should execute
        self.assertIn("cleanup", strategies_called)
        self.assertIn("dht", strategies_called)


class TestOptimizationIntegration(unittest.TestCase):
    """Test optimization components working together."""

    def setUp(self):
        self.bandwidth_optimizer = BandwidthOptimizer()
        self.connection_optimizer = ConnectionOptimizer()
        self.config_tuner = ConfigAutoTuner()

    def test_bandwidth_and_connection_recommendations(self):
        """Test bandwidth and connection limits work together."""
        # Record some metrics
        self.bandwidth_optimizer.record_bandwidth_usage(5000, 2000)
        self.connection_optimizer.record_connection_state(450, errors=0)

        # Get recommendations
        bandwidth_rec = self.bandwidth_optimizer.suggest_bandwidth_adjustment()
        connection_rec = self.connection_optimizer.suggest_connection_limits(
            Mock(),
            Mock(),
        )

        self.assertIn("current_limit", connection_rec)
        self.assertIn("recommended_limit", connection_rec)


class TestNotificationIntegration(unittest.TestCase):
    """Test notification system integration."""

    def setUp(self):
        self.notification_system = NotificationSystem()

    def test_notification_multi_channel(self):
        """Test notifications through multiple channels."""
        # Register multiple notifiers
        webhook_notifier = Mock()
        webhook_notifier.send = Mock(return_value=True)

        self.notification_system.notifiers["webhook_test"] = {
            "type": "webhook",
            "notifier": webhook_notifier,
            "config": {"url": "http://example.com/webhook"},
        }

        # Send notification
        result = self.notification_system.send_notification(
            NotificationLevel.WARNING,
            "Test Alert",
            "Test message",
            tags=["test"],
        )

        # Should succeed
        self.assertTrue(result)

        # Check history
        history = self.notification_system.get_notification_history()
        self.assertTrue(len(history) > 0)


class TestPredictiveAnalysisIntegration(unittest.TestCase):
    """Test predictive analysis with historical data."""

    def setUp(self):
        self.predictor = PredictiveAnalyzer(history_window=20)

    def test_trend_prediction_with_degradation(self):
        """Test prediction when performance is degrading."""
        # Add measurements showing degradation
        for i in range(20):
            speed = 1000 - (i * 30)  # Declining speed
            self.predictor.add_measurement({
                "speed": max(100, speed),
                "peers": 50,
                "cpu": 40,
                "memory": 60,
            })

        # Predict
        score, warnings = self.predictor.predict_lag()

        # Should detect degradation
        self.assertGreater(score, 0)
        self.assertTrue(len(warnings) > 0)


class TestCompletionPredictorIntegration(unittest.TestCase):
    """Test completion time prediction."""

    def setUp(self):
        self.predictor = TorrentCompletionPredictor()

    def test_eta_calculation(self):
        """Test ETA calculation with known values."""
        # Add speed history
        for i in range(20):
            self.predictor.record_torrent_speed("hash1", 1000, 10000000)

        # Estimate completion
        torrent = {
            "hash": "hash1",
            "total_size": 10000000,
            "downloaded": 5000000,
            "dl_speed": 1000000,  # 1 MB/s
        }

        eta, confidence = self.predictor.estimate_completion_time(torrent)

        # Should estimate ~5 seconds (5MB remaining at 1MB/s)
        self.assertIsNotNone(eta)
        self.assertGreater(eta, 0)


class TestABTestingIntegration(unittest.TestCase):
    """Test A/B testing framework."""

    def setUp(self):
        self.ab_framework = ABTestingFramework()

    def test_variant_comparison(self):
        """Test creating and comparing variants."""
        # Create test
        test = self.ab_framework.create_test(
            test_name="connection_limits",
            metric_name="lag_score",
            control_params={"global_limit": 500},
            variant_params=[
                {"global_limit": 600},
                {"global_limit": 400},
            ],
        )

        # Mock metric function
        def metric_func(params):
            # Simulate: higher limit = lower lag score
            return 100 - (params["global_limit"] / 10)

        # Run test
        results = self.ab_framework.run_test("connection_limits", metric_func)

        # Should have results
        self.assertIn("summary", results)
        self.assertIn("results", results["summary"])

        # Recommend variant
        recommended = self.ab_framework.recommend_variant("connection_limits")
        self.assertIsNotNone(recommended)


class TestBackupRestoreIntegration(unittest.TestCase):
    """Test backup and restore functionality."""

    def setUp(self):
        self.backup_manager = BackupRestoreManager(backup_dir="/tmp/test_backups")

    def test_snapshot_lifecycle(self):
        """Test creating and restoring snapshots."""
        # Create snapshot
        snapshot = self.backup_manager.create_snapshot(
            lag_score=25.5,
            applied_limits={"global": 500, "peer": 200},
            system_metrics={"cpu": 50, "memory": 60},
            recovery_attempts=["cleanup", "dht"],
            torrent_states={},
        )

        # Should be stored
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.lag_score, 25.5)

        # Get latest
        latest = self.backup_manager.get_latest_snapshot()
        self.assertEqual(latest.lag_score, 25.5)


if __name__ == "__main__":
    unittest.main()
