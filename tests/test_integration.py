"""Integration tests for the qBittorrent agent.

Covers configuration, API resilience, reliability (watchdog/storage),
scheduling/maintenance, ports, detection, recovery, and the status server.
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from qbt_api.agent_config import AgentConfig
from qbt_api.api_client import QBittorrentAPIClient
from detectors.lag_detector import LagDetector
from detectors.torrent_health import TorrentHealthAnalyzer
from detectors.predictive_analyzer import PredictiveAnalyzer
from recovery.recovery_engine import RecoveryEngine
from monitoring.process_watchdog import ProcessWatchdog
from monitoring.storage_monitor import StorageMonitor
from monitoring.history_store import HistoryStore
from monitoring.scheduler import parse_windows, is_within_windows
from monitoring.maintenance import MaintenanceController
from monitoring.port_manager import PortManager, parse_range
from monitoring.health_checks import HealthChecks
from monitoring.status_server import AgentState


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #
class FakeResponse:
    def __init__(self, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data if json_data is not None else {}

    def json(self):
        return self._json


class FakeSession:
    """Scripted session: yields queued responses for request()."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def request(self, method, url, **kw):
        self.calls.append((method, url))
        return self.script.pop(0)

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)


class FakeAPI:
    """Minimal qBittorrent API stand-in for component tests."""

    def __init__(self):
        self.calls = []
        self.prefs = {"dht": True, "listen_port": 6881, "random_port": True}

    def is_reachable(self):
        return True

    def get_server_state(self):
        return {"dl_info_speed": 2_000_000, "up_info_speed": 500_000,
                "total_peer_connections": 40, "dht_nodes": 250, "total_wasted_session": 0}

    def get_torrents(self, *a, **k):
        return [{"hash": "h1", "name": "t", "state": "downloading", "num_seeds": 5,
                 "num_leechs": 2, "upspeed": 1000, "progress": 0.5, "ratio": 0.2}]

    def get_trackers(self, h):
        return []

    def get_preferences(self):
        return dict(self.prefs)

    def set_preferences(self, p):
        self.prefs.update(p)
        self.calls.append(("set", p))
        return True

    def pause_torrent(self, h="all"):
        self.calls.append(("pause", h))
        return True

    def resume_torrent(self, h="all"):
        self.calls.append(("resume", h))
        return True

    def reannounce_all(self):
        self.calls.append(("reannounce",))
        return True


class FakeConfigManager:
    def reload(self):
        pass

    def get_network_config(self):
        return {"port": 6881}


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
class TestAgentConfig(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "sub", "qbittorrent-agent.conf")

    def test_generate_and_defaults(self):
        cfg = AgentConfig(self.path)
        cfg.ensure_exists()
        self.assertTrue(os.path.exists(self.path))
        self.assertEqual(cfg.get("status", "status_port"), 8081)

    def test_cli_overrides_only_non_none_and_persists(self):
        cfg = AgentConfig(self.path)
        cfg.apply_overrides({("status", "status_port"): 9000, ("agent", "interval"): None})
        self.assertEqual(cfg.get("status", "status_port"), 9000)
        self.assertEqual(cfg.get("agent", "interval"), 60)  # untouched default
        cfg.save()
        reloaded = AgentConfig(self.path)
        self.assertEqual(reloaded.get("status", "status_port"), 9000)  # remembered

    def test_list_round_trip(self):
        cfg = AgentConfig(self.path)
        cfg.set("storage", "watch_mount", "/mnt/a,/mnt/b")
        self.assertEqual(cfg.get("storage", "watch_mount"), ["/mnt/a", "/mnt/b"])


# --------------------------------------------------------------------------- #
# API resilience
# --------------------------------------------------------------------------- #
class TestApiResilience(unittest.TestCase):
    def test_reauth_on_403_then_success(self):
        client = QBittorrentAPIClient(username="u", password="p", retries=2)
        # First request 403 -> re-auth (200 Ok.) -> retry returns 200 with json.
        client.session = FakeSession([
            FakeResponse(403),
            FakeResponse(200, text="Ok."),               # re-auth
            FakeResponse(200, json_data={"a": 1}),         # retried call
        ])
        prefs = client.get_preferences()
        self.assertEqual(prefs, {"a": 1})

    def test_returns_none_after_retries(self):
        client = QBittorrentAPIClient(retries=2)
        client.session = FakeSession([FakeResponse(500), FakeResponse(500)])
        self.assertIsNone(client.get_preferences())


# --------------------------------------------------------------------------- #
# Reliability
# --------------------------------------------------------------------------- #
class TestWatchdog(unittest.TestCase):
    def test_restart_when_process_gone(self):
        wd = ProcessWatchdog(process_name="definitely-not-running-xyz", max_restarts=2)
        verdict = wd.evaluate(FakeAPI())
        self.assertTrue(verdict["needs_restart"])
        self.assertFalse(verdict["running"])

    def test_restart_cap(self):
        wd = ProcessWatchdog(max_restarts=2)
        self.assertTrue(wd.can_restart())
        wd.record_restart()
        wd.record_restart()
        self.assertFalse(wd.can_restart())


class TestStorage(unittest.TestCase):
    def test_missing_path_flagged(self):
        sm = StorageMonitor(watch_paths=["/nonexistent/xyz"])
        issues = sm.check(paths=["/nonexistent/xyz"])
        self.assertEqual(issues[0]["problem"], "missing")

    def test_enforce_pause_resume_latch(self):
        sm = StorageMonitor(min_free_gb=0, min_free_percent=0)
        api = FakeAPI()
        # Inject a failing path, enforce -> pause.
        with patch.object(sm, "check", return_value=[{"path": "/x", "problem": "missing", "detail": ""}]):
            r = sm.enforce(api)
            self.assertEqual(r["action"], "paused")
            self.assertTrue(sm.storage_paused)
        # Now healthy -> resume.
        with patch.object(sm, "check", return_value=[]):
            r = sm.enforce(api)
            self.assertEqual(r["action"], "resumed")
            self.assertFalse(sm.storage_paused)


# --------------------------------------------------------------------------- #
# History
# --------------------------------------------------------------------------- #
class TestHistoryStore(unittest.TestCase):
    def test_round_trip(self):
        db = os.path.join(tempfile.mkdtemp(), "sub", "state.db")
        h = HistoryStore(db)
        h.record_sample(lag_score=42.0, peers=5)
        h.record_event("recovery", "did a thing")
        self.assertEqual(h.recent_samples()[0]["lag_score"], 42.0)
        self.assertEqual(h.recent_events()[0]["type"], "recovery")
        h.close()


# --------------------------------------------------------------------------- #
# Scheduling + maintenance
# --------------------------------------------------------------------------- #
class TestScheduler(unittest.TestCase):
    def test_cross_midnight_window(self):
        w = parse_windows("22:00-06:00")
        self.assertTrue(is_within_windows(w, datetime(2026, 6, 13, 23, 0)))
        self.assertTrue(is_within_windows(w, datetime(2026, 6, 13, 5, 0)))
        self.assertFalse(is_within_windows(w, datetime(2026, 6, 13, 12, 0)))

    def test_maintenance_pause_resume(self):
        api = FakeAPI()
        mc = MaintenanceController(windows_spec="22:00-06:00")
        mc.update(api, now=datetime(2026, 6, 13, 23, 0))   # enter -> pause
        self.assertTrue(mc.maintenance_paused)
        self.assertIn(("pause", "all"), api.calls)
        mc.update(api, now=datetime(2026, 6, 13, 7, 0))    # exit -> resume
        self.assertFalse(mc.maintenance_paused)
        self.assertIn(("resume", "all"), api.calls)

    def test_maintenance_defers_to_storage(self):
        api = FakeAPI()
        mc = MaintenanceController(windows_spec="22:00-06:00")
        mc.update(api, now=datetime(2026, 6, 13, 23, 0))
        mc.update(api, storage_paused=True, now=datetime(2026, 6, 13, 7, 0))
        self.assertNotIn(("resume", "all"), api.calls)


# --------------------------------------------------------------------------- #
# Ports
# --------------------------------------------------------------------------- #
class TestPortManager(unittest.TestCase):
    def test_apply_and_verify(self):
        api = FakeAPI()
        pm = PortManager(port_range=(40000, 41000), webui_port=8080)
        r = pm.apply(api, now=1000.0)
        self.assertTrue(r["changed"])
        self.assertTrue(40000 <= r["listen_port"] <= 41000)
        self.assertNotEqual(r["listen_port"], 8080)
        self.assertFalse(api.prefs["random_port"])

    def test_interval_guard(self):
        api = FakeAPI()
        pm = PortManager(port_range=(40000, 41000))
        pm.apply(api, now=1000.0)
        self.assertFalse(pm.apply(api, interval=3600, now=1010.0)["changed"])

    def test_dry_run_no_mutation(self):
        api = FakeAPI()
        PortManager(port_range=(40000, 41000)).apply(api, dry_run=True, now=1.0)
        self.assertTrue(api.prefs["random_port"])  # unchanged

    def test_parse_range(self):
        self.assertEqual(parse_range("10000-20000"), (10000, 20000))
        self.assertEqual(parse_range("bad"), (49152, 65535))


# --------------------------------------------------------------------------- #
# Health checks
# --------------------------------------------------------------------------- #
class TestHealthChecks(unittest.TestCase):
    def test_hash_fail_detection(self):
        hc = HealthChecks()
        self.assertFalse(hc.check_hash_fails({"total_wasted_session": 0})["suspect"])
        self.assertTrue(hc.check_hash_fails({"total_wasted_session": 50 * 1024 * 1024})["suspect"])

    def test_webui_security(self):
        warns = HealthChecks.check_webui_security(
            {"bypass_local_auth": True, "web_ui_username": "admin", "web_ui_address": "0.0.0.0"}
        )
        self.assertGreaterEqual(len(warns), 3)


# --------------------------------------------------------------------------- #
# Detection + recovery
# --------------------------------------------------------------------------- #
class TestDetection(unittest.TestCase):
    def test_log_analysis_incremental(self):
        logp = os.path.join(tempfile.mkdtemp(), "q.log")
        with open(logp, "w") as f:
            f.write("ok\n[ERROR] I/O error on disk\nTimed out\nI/O error again\n")
        ld = LagDetector(FakeAPI(), FakeConfigManager(), qbt_log=logp)
        score, issues = ld._analyze_logs()
        self.assertGreater(score, 0)
        self.assertEqual(ld._analyze_logs()[0], 0.0)  # no new lines

    def test_detect_lag_runs(self):
        ld = LagDetector(FakeAPI(), FakeConfigManager())
        score, desc = ld.detect_lag()
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)

    def test_predictive_degradation(self):
        pa = PredictiveAnalyzer(history_window=20)
        # Clear regime change: steady high speed, then a sharp drop (>30%).
        for i in range(20):
            speed = 1000 if i < 15 else 300
            pa.add_measurement({"speed": speed, "peers": 50, "cpu": 40, "memory": 60})
        score, warnings = pa.predict_lag()
        self.assertGreater(score, 0)


class TestRecovery(unittest.TestCase):
    def test_plan_escalation(self):
        eng = RecoveryEngine(FakeAPI(), FakeConfigManager(), dry_run=True)
        self.assertEqual(eng.get_recovery_plan(45), ["connection_cleanup", "dht_refresh"])
        self.assertIn("restart_process", eng.get_recovery_plan(90))

    def test_dry_run_no_mutation(self):
        api = FakeAPI()
        eng = RecoveryEngine(api, FakeConfigManager(), dry_run=True)
        eng.execute_recovery(90)
        self.assertEqual(api.calls, [])

    def test_real_connection_cleanup(self):
        api = FakeAPI()
        eng = RecoveryEngine(api, FakeConfigManager(), dry_run=False)
        eng._connection_cleanup()
        self.assertIn(("reannounce",), api.calls)


class TestTorrentHealth(unittest.TestCase):
    def test_summary(self):
        analyzer = TorrentHealthAnalyzer()
        summary = analyzer.get_health_summary([
            {"hash": "a", "name": "good", "state": "uploading", "num_seeds": 50,
             "num_leechs": 5, "upspeed": 100000, "progress": 1.0, "ratio": 2.0},
            {"hash": "b", "name": "dead", "state": "stalledDL", "num_seeds": 0,
             "num_leechs": 0, "upspeed": 0, "progress": 0.1, "ratio": 0.0},
        ])
        self.assertEqual(summary["total_torrents"], 2)
        self.assertIn("average_health_score", summary)


class TestAgentState(unittest.TestCase):
    def test_snapshot_serializable(self):
        st = AgentState()
        st.update(lag_score=10.0, peers=5)
        snap = st.snapshot()
        self.assertEqual(snap["lag_score"], 10.0)
        self.assertIn("uptime_seconds", snap)


if __name__ == "__main__":
    unittest.main()
