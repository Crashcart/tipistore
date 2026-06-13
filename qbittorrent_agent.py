#!/usr/bin/env python3
"""qBittorrent Intelligent Recovery Agent.

Monitors qbittorrent-nox for crashes, storage problems, and lag, and applies
recovery automatically while preserving the user's configuration. Settings live
in an auto-generated config file next to qBittorrent.conf and are remembered
across runs; CLI flags override and persist.
"""

import argparse
import signal
import sys
import time
from pathlib import Path

from agent_logging.agent_logger import setup_logger
from qbt_api.agent_config import AgentConfig
from qbt_api.api_client import QBittorrentAPIClient
from qbt_api.config_manager import ConfigManager
from detectors.lag_detector import LagDetector
from detectors.predictive_analyzer import PredictiveAnalyzer
from detectors.torrent_health import TorrentHealthAnalyzer
from recovery.recovery_engine import RecoveryEngine
from recovery.backup_restore import BackupRestoreManager
from monitoring.metrics import SystemMetrics
from monitoring.process_watchdog import ProcessWatchdog
from monitoring.storage_monitor import StorageMonitor
from monitoring.status_server import AgentState, StatusServer
from monitoring.history_store import HistoryStore
from monitoring.maintenance import MaintenanceController
from monitoring.port_manager import PortManager, parse_range
from monitoring.health_checks import HealthChecks


# argparse dest -> (config section, key). Flags default to None so that
# "not provided" falls back to the saved file / built-in default.
ARG_MAP = {
    "interval": ("agent", "interval"),
    "sensitivity": ("agent", "sensitivity"),
    "log_level": ("agent", "log_level"),
    "log_file": ("agent", "log_file"),
    "dry_run": ("agent", "dry_run"),
    "maintenance": ("agent", "maintenance"),
    "state_db": ("agent", "state_db"),
    "qbt_host": ("qbittorrent", "host"),
    "qbt_port": ("qbittorrent", "port"),
    "qbt_username": ("qbittorrent", "username"),
    "qbt_password": ("qbittorrent", "password"),
    "service_name": ("qbittorrent", "service_name"),
    "qbt_log": ("qbittorrent", "qbt_log"),
    "api_timeout": ("qbittorrent", "api_timeout"),
    "api_retries": ("qbittorrent", "api_retries"),
    "maintenance_window": ("schedule", "maintenance_window"),
    "no_watchdog": ("recovery", "no_watchdog"),
    "max_restarts": ("recovery", "max_restarts"),
    "restart_cooldown": ("recovery", "restart_cooldown"),
    "drain_timeout": ("recovery", "drain_timeout"),
    "auto_pause_dead": ("recovery", "auto_pause_dead"),
    "no_disk_guard": ("storage", "no_disk_guard"),
    "watch_mount": ("storage", "watch_mount"),
    "min_free_gb": ("storage", "min_free_gb"),
    "min_free_percent": ("storage", "min_free_percent"),
    "wait_for_mount": ("storage", "wait_for_mount"),
    "mount_wait_timeout": ("storage", "mount_wait_timeout"),
    "random_port": ("ports", "random_port"),
    "random_port_mode": ("ports", "random_port_mode"),
    "random_port_range": ("ports", "random_port_range"),
    "random_port_interval": ("ports", "random_port_interval"),
    "no_random_outgoing_ports": ("ports", "random_outgoing_ports"),  # inverted below
    "status_port": ("status", "status_port"),
    "status_bind": ("status", "status_bind"),
    "notify_level": ("notifications", "notify_level"),
    "notify_webhook": ("notifications", "notify_webhook"),
    "notify_syslog": ("notifications", "notify_syslog"),
    "notify_email_smtp": ("notifications", "notify_email_smtp"),
    "notify_email_port": ("notifications", "notify_email_port"),
    "notify_email_from": ("notifications", "notify_email_from"),
    "notify_email_password": ("notifications", "notify_email_password"),
    "notify_email_to": ("notifications", "notify_email_to"),
}


class QBittorrentAgent:
    """Main agent: builds components from config and runs the monitor loop."""

    def __init__(self, cfg: AgentConfig, logger):
        self.cfg = cfg
        self.logger = logger
        self.running = True
        self.dry_run = cfg.get("agent", "dry_run")

        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        self.state = AgentState()
        self.system_metrics = SystemMetrics()

        # API client
        self.api = QBittorrentAPIClient(
            host=cfg.get("qbittorrent", "host"),
            port=cfg.get("qbittorrent", "port"),
            username=cfg.get("qbittorrent", "username"),
            password=cfg.get("qbittorrent", "password"),
            timeout=cfg.get("qbittorrent", "api_timeout"),
            retries=cfg.get("qbittorrent", "api_retries"),
            logger=logger,
        )

        # qBittorrent config file
        self.qbt_config_path = cfg.get("_runtime", "qbt_config_path")
        self.config_manager = ConfigManager(self.qbt_config_path)

        # Notifications
        self.notifier = self._build_notifier()

        # Detection
        self.lag_detector = LagDetector(
            self.api, self.config_manager,
            sensitivity=cfg.get("agent", "sensitivity"),
            qbt_log=cfg.get("qbittorrent", "qbt_log"),
            logger=logger,
        )
        self.predictor = PredictiveAnalyzer(logger=logger)
        self.health_analyzer = TorrentHealthAnalyzer(logger=logger)
        self.health_checks = HealthChecks(logger=logger)

        # Recovery
        self.recovery = RecoveryEngine(
            self.api, self.config_manager,
            system_metrics=self.system_metrics,
            service_name=cfg.get("qbittorrent", "service_name"),
            drain_timeout=cfg.get("recovery", "drain_timeout"),
            dry_run=self.dry_run,
            notifier=self.notifier,
            logger=logger,
        )

        # Reliability
        self.watchdog = None
        if not cfg.get("recovery", "no_watchdog"):
            self.watchdog = ProcessWatchdog(
                service_name=cfg.get("qbittorrent", "service_name"),
                max_restarts=cfg.get("recovery", "max_restarts"),
                restart_cooldown=cfg.get("recovery", "restart_cooldown"),
                unresponsive_cycles=cfg.get("recovery", "unresponsive_cycles"),
                logger=logger,
            )

        self.storage = None
        if not cfg.get("storage", "no_disk_guard"):
            self.storage = StorageMonitor(
                watch_paths=cfg.get("storage", "watch_mount"),
                min_free_gb=cfg.get("storage", "min_free_gb"),
                min_free_percent=cfg.get("storage", "min_free_percent"),
                logger=logger,
            )

        # Maintenance (scheduled throttled hours / manual)
        self.maintenance = MaintenanceController(
            windows_spec=cfg.get("schedule", "maintenance_window"),
            manual=cfg.get("agent", "maintenance"),
            pause_torrents=cfg.get("schedule", "pause_during_maintenance"),
            logger=logger,
        )

        # Ports
        self.port_manager = None
        if cfg.get("ports", "random_port"):
            self.port_manager = PortManager(
                port_range=parse_range(cfg.get("ports", "random_port_range")),
                randomize_outgoing=cfg.get("ports", "random_outgoing_ports"),
                verify=cfg.get("ports", "verify_port"),
                webui_port=cfg.get("qbittorrent", "port"),
                logger=logger,
            )

        # History + backups
        self.history = None
        state_db = cfg.get("agent", "state_db")
        if state_db and state_db.lower() != "none":
            self.history = HistoryStore(state_db, logger=logger)
        self.backups = BackupRestoreManager(logger=logger)

        # Status server
        self.status_server = None
        port = cfg.get("status", "status_port")
        if port:
            self.status_server = StatusServer(
                self.state, bind=cfg.get("status", "status_bind"), port=port, logger=logger
            )

    # ------------------------------------------------------------------ #
    def _build_notifier(self):
        from agent_logging.notification_system import NotificationSystem, NotificationLevel

        ns = NotificationSystem(logger=self.logger)
        cfg = self.cfg
        registered = False

        webhook = cfg.get("notifications", "notify_webhook")
        if webhook:
            ns.register_webhook_notifier("default", webhook)
            registered = True
        syslog = cfg.get("notifications", "notify_syslog")
        if syslog:
            ns.register_syslog_notifier("default", syslog)
            registered = True
        smtp = cfg.get("notifications", "notify_email_smtp")
        if smtp:
            ns.register_email_notifier(
                "default", smtp, cfg.get("notifications", "notify_email_port"),
                cfg.get("notifications", "notify_email_from"),
                cfg.get("notifications", "notify_email_password"),
            )
            self._email_recipients = cfg.get("notifications", "notify_email_to")
            registered = True

        level_name = cfg.get("notifications", "notify_level")
        order = ["DEBUG", "INFO", "WARNING", "CRITICAL"]
        if level_name in order:
            enabled = [getattr(NotificationLevel, n) for n in order[order.index(level_name):]]
            ns.set_enabled_levels(enabled)

        return ns if registered else None

    def _handle_shutdown(self, signum, frame):
        self.logger.info("Shutdown signal received")
        self.running = False

    # ------------------------------------------------------------------ #
    def run(self):
        cfg = self.cfg
        self.logger.info(
            f"qBittorrent Agent started (interval={cfg.get('agent','interval')}s, "
            f"sensitivity={cfg.get('agent','sensitivity')}"
            f"{', DRY RUN' if self.dry_run else ''})"
        )
        if self.status_server:
            self.status_server.start()

        # Wait-for-mount gate (5m)
        if self.storage and cfg.get("storage", "wait_for_mount"):
            self.storage.wait_for_mounts(
                dry_run=self.dry_run, timeout=cfg.get("storage", "mount_wait_timeout")
            )

        # Startup port randomization (5a)
        if self.port_manager and cfg.get("ports", "random_port_mode") in ("startup", "once", "interval"):
            self._apply_port_change()

        interval = cfg.get("agent", "interval")
        try:
            while self.running:
                try:
                    self._cycle()
                except Exception as e:
                    self.logger.error(f"Error in monitor cycle: {e}", exc_info=True)
                self._sleep(interval)
        finally:
            if self.status_server:
                self.status_server.stop()
            if self.history:
                self.history.close()
            self.logger.info("qBittorrent Agent stopped")

    def _sleep(self, seconds):
        # Sleep in small slices so shutdown is responsive.
        end = time.time() + seconds
        while self.running and time.time() < end:
            time.sleep(min(1.0, end - time.time()))

    def _cycle(self):
        cfg = self.cfg

        # 1. Maintenance (scheduled throttled hours / manual)
        maint = self.maintenance.update(
            self.api, storage_paused=self.storage.storage_paused if self.storage else False,
            dry_run=self.dry_run,
        )
        if maint["transition"] == "entered":
            self._event("maintenance", "entered")
        elif maint["transition"] == "exited":
            self._event("maintenance", "exited")

        # 2. Watchdog (crash detection) — runs even during maintenance.
        if self.watchdog:
            verdict = self.watchdog.evaluate(self.api)
            self.state.update(qbt_running=verdict["running"], qbt_responsive=verdict["responsive"])
            if verdict["needs_restart"]:
                self._handle_restart(verdict["reason"])
                return  # give qBittorrent time to come up before next cycle

        # 3. If in maintenance, downloads are paused; skip lag work.
        if maint["active"]:
            self.state.update(maintenance=True)
            self._record_sample(lag_score=0.0)
            return
        self.state.update(maintenance=False)

        # 4. Storage safety gate.
        if self.storage:
            result = self.storage.enforce(self.api, dry_run=self.dry_run)
            self.state.update(storage_paused=result["paused"], disk_issues=result["issues"])
            if result["action"] == "paused":
                detail = "; ".join(f"{i['path']}:{i['problem']}" for i in result["issues"])
                self._event("storage", f"paused: {detail}")
                self._notify("CRITICAL", "Storage problem", detail)
            elif result["action"] == "resumed":
                self._event("storage", "recovered")
                self._notify("WARNING", "Storage recovered", "resumed torrents")
            if result["paused"]:
                self._record_sample(lag_score=0.0)
                return

        # 5. Interval-based port rotation.
        if self.port_manager and cfg.get("ports", "random_port_mode") == "interval":
            self._apply_port_change(interval=cfg.get("ports", "random_port_interval"))

        # 6. Detect lag + feed predictor + health.
        stats = self.api.get_server_state() or {}
        cpu = self.system_metrics.get_cpu_percent()
        mem = self.system_metrics.get_memory_info()["percent"]

        lag_score, desc = self.lag_detector.detect_lag()
        self.predictor.add_measurement({
            "speed": stats.get("dl_info_speed", 0),
            "peers": stats.get("total_peer_connections", 0),
            "cpu": cpu, "memory": mem,
        })
        pred_score, _pred_warn = self.predictor.predict_lag()

        torrents = self.api.get_torrents()
        health = self.health_analyzer.get_health_summary(torrents)
        dead = health.get("unrecoverable", 0)

        # 5h/5i: tracker + hash-fail signals.
        hf = self.health_checks.check_hash_fails(stats)
        if hf["suspect"]:
            self._notify("WARNING", "Possible corruption", f"{hf['wasted_delta']//(1024*1024)} MiB wasted this cycle")
            self._event("hash_fail", f"wasted_delta={hf['wasted_delta']}")

        # Optional: pause confirmed-dead torrents.
        if cfg.get("recovery", "auto_pause_dead") and not self.dry_run:
            for h in self.health_analyzer.get_unrecoverable_torrents(torrents):
                self.api.pause_torrent(h)

        # 7. Recovery if lagged.
        if lag_score > 0:
            self.logger.warning(f"Lag {lag_score:.0f}/100 - {desc}")
            if lag_score > 30:
                self.backups.backup_file(self.qbt_config_path)  # 5f
                self.recovery.execute_recovery(lag_score)
                self.state.recovery_count += 1
                self._event("recovery", f"lag={lag_score:.0f}: {desc}")
                self._snapshot(lag_score)

        # 8. Publish state + record sample.
        self.state.update(
            lag_score=lag_score, predicted_score=pred_score, issues=desc.split("; "),
            dl_speed=stats.get("dl_info_speed", 0), up_speed=stats.get("up_info_speed", 0),
            peers=stats.get("total_peer_connections", 0), dht=stats.get("dht_nodes", 0),
            cpu=cpu, mem=mem, dead_torrents=dead,
        )
        self._record_sample(lag_score=lag_score, cpu=cpu, mem=mem, stats=stats)

    # ------------------------------------------------------------------ #
    def _handle_restart(self, reason):
        if not self.watchdog.can_restart():
            self.logger.error(
                f"qBittorrent down ({reason}) but restart cap reached "
                f"({self.watchdog.restarts_in_window()}); manual intervention needed"
            )
            self._notify("CRITICAL", "qBittorrent down — manual intervention",
                         f"{reason}; restart cap reached")
            self._event("restart_blocked", reason)
            return
        self.backups.backup_file(self.qbt_config_path)  # 5f
        self.recovery.restart(reason=reason)
        self.watchdog.record_restart()
        self.state.restarts += 1
        self._event("restart", reason)

    def _apply_port_change(self, interval=0):
        result = self.port_manager.apply(self.api, interval=interval, dry_run=self.dry_run)
        if result.get("changed") and result.get("listen_port"):
            self.state.update(listen_port=result["listen_port"])
            self._event("port", f"listen={result['listen_port']} outgoing={result.get('outgoing')}")

    def _record_sample(self, lag_score=0.0, cpu=0.0, mem=0.0, stats=None):
        if not self.history:
            return
        stats = stats or {}
        self.history.record_sample(
            lag_score=lag_score, dl_speed=stats.get("dl_info_speed", 0),
            up_speed=stats.get("up_info_speed", 0),
            peers=stats.get("total_peer_connections", 0), dht=stats.get("dht_nodes", 0),
            cpu=cpu, mem=mem,
        )

    def _snapshot(self, lag_score):
        try:
            self.backups.create_snapshot(
                lag_score=lag_score, applied_limits={}, system_metrics={},
                recovery_attempts=self.recovery.get_recovery_plan(lag_score), torrent_states={},
            )
        except Exception as e:
            self.logger.debug(f"Snapshot failed: {e}")

    def _event(self, event_type, detail):
        self.state.update(last_event=f"{event_type}: {detail}")
        if self.history:
            self.history.record_event(event_type, detail)

    def _notify(self, level, title, message):
        if not self.notifier:
            return
        from agent_logging.notification_system import NotificationLevel
        recipients = getattr(self, "_email_recipients", None)
        try:
            self.notifier.send_notification(
                getattr(NotificationLevel, level, NotificationLevel.WARNING),
                title, message, recipients=recipients,
            )
        except Exception as e:
            self.logger.debug(f"Notify failed: {e}")


def build_parser():
    p = argparse.ArgumentParser(
        description="qBittorrent Intelligent Recovery Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run with --configure for an interactive text-GUI configuration screen.",
    )
    # All value flags default to None so they only override when provided.
    p.add_argument("--qbt-config", default=str(Path.home() / ".config/qBittorrent/qBittorrent.conf"),
                   help="Path to qBittorrent.conf (default: ~/.config/qBittorrent/qBittorrent.conf)")
    p.add_argument("--config", default=None, help="Agent config path (default: next to qBittorrent.conf)")
    p.add_argument("--configure", action="store_true", help="Open the text-GUI config screen and exit")
    p.add_argument("--no-save-config", action="store_true", help="Do not persist CLI values to the config file")
    p.add_argument("--no-save-secrets", action="store_true", help="Do not write secrets (passwords) to disk")

    p.add_argument("--interval", type=int, default=None)
    p.add_argument("--sensitivity", choices=["aggressive", "balanced", "conservative"], default=None)
    p.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default=None)
    p.add_argument("--log-file", default=None)
    p.add_argument("--dry-run", action="store_true", default=None, help="Log actions without making changes")
    p.add_argument("--maintenance", action="store_true", default=None, help="Start in maintenance mode")
    p.add_argument("--state-db", default=None, help="SQLite history DB ('none' disables)")

    p.add_argument("--qbt-host", default=None)
    p.add_argument("--qbt-port", type=int, default=None)
    p.add_argument("--qbt-username", default=None)
    p.add_argument("--qbt-password", default=None)
    p.add_argument("--service-name", default=None)
    p.add_argument("--qbt-log", default=None)
    p.add_argument("--api-timeout", type=int, default=None)
    p.add_argument("--api-retries", type=int, default=None)

    p.add_argument("--maintenance-window", default=None, help="Throttled hours, e.g. '22:00-06:00'")

    p.add_argument("--no-watchdog", action="store_true", default=None)
    p.add_argument("--max-restarts", type=int, default=None)
    p.add_argument("--restart-cooldown", type=int, default=None)
    p.add_argument("--drain-timeout", type=int, default=None)
    p.add_argument("--auto-pause-dead", action="store_true", default=None)

    p.add_argument("--no-disk-guard", action="store_true", default=None)
    p.add_argument("--watch-mount", action="append", default=None, help="Mount to guard (repeatable)")
    p.add_argument("--min-free-gb", type=float, default=None)
    p.add_argument("--min-free-percent", type=float, default=None)
    p.add_argument("--wait-for-mount", action="store_true", default=None)
    p.add_argument("--mount-wait-timeout", type=int, default=None)

    p.add_argument("--random-port", action="store_true", default=None)
    p.add_argument("--random-port-mode", choices=["startup", "interval", "once", "on-throttle"], default=None)
    p.add_argument("--random-port-range", default=None, help="LOW-HIGH")
    p.add_argument("--random-port-interval", type=int, default=None)
    p.add_argument("--no-random-outgoing-ports", action="store_true", default=None)

    p.add_argument("--status-port", type=int, default=None, help="0 disables")
    p.add_argument("--status-bind", default=None)

    p.add_argument("--notify-level", choices=["DEBUG", "INFO", "WARNING", "CRITICAL"], default=None)
    p.add_argument("--notify-webhook", default=None)
    p.add_argument("--notify-syslog", default=None, help="Syslog facility, e.g. local0")
    p.add_argument("--notify-email-smtp", default=None)
    p.add_argument("--notify-email-port", type=int, default=None)
    p.add_argument("--notify-email-from", default=None)
    p.add_argument("--notify-email-password", default=None)
    p.add_argument("--notify-email-to", default=None, help="Comma-separated recipients")
    return p


def overrides_from_args(args) -> dict:
    """Build a (section,key)->value override map from parsed args (non-None only)."""
    out = {}
    for dest, (section, key) in ARG_MAP.items():
        value = getattr(args, dest, None)
        if value is None:
            continue
        if dest == "no_random_outgoing_ports":
            value = not value  # flag disables; config stores the positive sense
        out[(section, key)] = value
    return out


def main():
    args = build_parser().parse_args()

    qbt_config = str(Path(args.qbt_config).expanduser())
    agent_config_path = AgentConfig.resolve_path(qbt_config, args.config)

    cfg = AgentConfig(agent_config_path)
    cfg.apply_overrides(overrides_from_args(args))
    # Stash the qBittorrent config path for components (runtime-only).
    cfg.values.setdefault("_runtime", {})["qbt_config_path"] = qbt_config

    logger = setup_logger(cfg.get("agent", "log_level"), cfg.get("agent", "log_file"))
    cfg.logger = logger
    if cfg._loaded_from_file:
        cfg._warn_if_world_readable()

    # Text-GUI configuration screen.
    if args.configure:
        from tui.config_tui import run_config_tui
        run_config_tui(cfg, api_client_factory=lambda: QBittorrentAPIClient(
            host=cfg.get("qbittorrent", "host"), port=cfg.get("qbittorrent", "port"),
            username=cfg.get("qbittorrent", "username"), password=cfg.get("qbittorrent", "password"),
            timeout=cfg.get("qbittorrent", "api_timeout"), retries=1, logger=logger))
        cfg.save(include_secrets=not args.no_save_secrets)
        return

    # Persist resolved config (so CLI-set values are remembered).
    cfg.ensure_exists(include_secrets=not args.no_save_secrets)
    if not args.no_save_config:
        cfg.save(include_secrets=not args.no_save_secrets)

    if not Path(qbt_config).exists():
        logger.warning(f"qBittorrent config not found at {qbt_config}; "
                       f"config-based checks limited. Use --qbt-config to set it.")

    agent = QBittorrentAgent(cfg, logger)
    agent.run()


if __name__ == "__main__":
    main()
