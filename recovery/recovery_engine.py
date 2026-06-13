"""Recovery engine: executes real recovery strategies in escalating order."""

import time
import subprocess
from typing import List, Optional

from recovery.connection_optimizer import ConnectionOptimizer
from recovery.bandwidth_optimizer import BandwidthOptimizer


class RecoveryEngine:
    """Executes recovery strategies from least to most invasive."""

    def __init__(
        self,
        api_client,
        config_manager,
        system_metrics=None,
        service_name: str = "qbittorrent-nox",
        drain_timeout: int = 15,
        dry_run: bool = False,
        notifier=None,
        logger=None,
    ):
        """Initialize the recovery engine.

        Args:
            api_client: QBittorrentAPIClient.
            config_manager: ConfigManager.
            system_metrics: SystemMetrics instance (for dynamic limits).
            service_name: systemd unit name for restarts.
            drain_timeout: Seconds to pause/drain torrents before a restart (5g).
            dry_run: Log intended actions without making changes.
            notifier: Optional NotificationSystem.
            logger: Optional logger.
        """
        self.api_client = api_client
        self.config_manager = config_manager
        self.system_metrics = system_metrics
        self.service_name = service_name
        self.drain_timeout = drain_timeout
        self.dry_run = dry_run
        self.notifier = notifier
        self.logger = logger

        self.connection_optimizer = ConnectionOptimizer(logger=logger)

        self.strategies = {
            "connection_cleanup": (self._connection_cleanup, 30),
            "dht_refresh": (self._dht_refresh, 40),
            "reload_config": (self._reload_config, 50),
            "dynamic_limits": (self._dynamic_limits, 60),
            "torrent_refresh": (self._torrent_refresh, 75),
            "restart_process": (self._restart_process, 85),
        }

    # ------------------------------------------------------------------ #
    # Planning + orchestration
    # ------------------------------------------------------------------ #
    def get_recovery_plan(self, lag_score: float) -> List[str]:
        """Return the ordered strategies whose threshold the score exceeds."""
        return [
            name
            for name, (_func, threshold) in self.strategies.items()
            if lag_score > threshold
        ]

    def execute_recovery(self, lag_score: float) -> bool:
        """Execute the recovery plan for the given lag score."""
        plan = self.get_recovery_plan(lag_score)
        if not plan:
            if self.logger:
                self.logger.info("No recovery needed")
            return True

        if self.logger:
            self.logger.info(
                f"{'[DRY RUN] ' if self.dry_run else ''}Recovery plan "
                f"(lag {lag_score:.0f}): {', '.join(plan)}"
            )
        self._notify("WARNING", "qBittorrent recovery", f"lag {lag_score:.0f}: {', '.join(plan)}")

        for name in plan:
            func, _ = self.strategies[name]
            if self.logger:
                self.logger.info(f"Strategy: {name}")
            try:
                func()
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Strategy {name} failed: {e}")
                continue
            time.sleep(2)
        return True

    # ------------------------------------------------------------------ #
    # Strategies (all respect dry_run)
    # ------------------------------------------------------------------ #
    def _connection_cleanup(self) -> bool:
        """Force a tracker re-announce to refresh peers/connections."""
        if self.dry_run:
            self.logger and self.logger.info("[DRY RUN] would reannounce all torrents")
            return True
        return self.api_client.reannounce_all()

    def _dht_refresh(self) -> bool:
        """Re-bootstrap DHT by toggling it off then back on."""
        prefs = self.api_client.get_preferences() or {}
        if not prefs.get("dht", True):
            self.logger and self.logger.info("DHT disabled in config; skipping refresh")
            return True
        if self.dry_run:
            self.logger and self.logger.info("[DRY RUN] would toggle DHT off/on")
            return True
        self.api_client.set_preferences({"dht": False})
        time.sleep(3)
        return self.api_client.set_preferences({"dht": True})

    def _reload_config(self) -> bool:
        """Reload the qBittorrent config from disk into the agent's view."""
        self.config_manager.reload()
        return True

    def _dynamic_limits(self) -> bool:
        """Adjust connection and bandwidth limits to current system capacity."""
        if self.system_metrics is None:
            return True

        suggestion = self.connection_optimizer.suggest_connection_limits(
            self.api_client, self.system_metrics
        )
        rec_limit = suggestion.get("recommended_limit")
        rec_peer = suggestion.get("recommended_peer_limit")

        if self.dry_run:
            self.logger and self.logger.info(
                f"[DRY RUN] would set connection limits {rec_limit}/{rec_peer} "
                f"and re-tune bandwidth"
            )
            return True

        if rec_limit and rec_peer:
            self.connection_optimizer.apply_connection_limits(self.api_client, rec_limit, rec_peer)

        bandwidth = BandwidthOptimizer(self.api_client, self.system_metrics, self.logger)
        bandwidth.optimize_bandwidth()
        return True

    def _torrent_refresh(self) -> bool:
        """Pause then resume all torrents to reset internal per-torrent state."""
        if self.dry_run:
            self.logger and self.logger.info("[DRY RUN] would pause/resume all torrents")
            return True
        self.api_client.pause_torrent("all")
        time.sleep(min(10, self.drain_timeout))
        return self.api_client.resume_torrent("all")

    def _restart_process(self) -> bool:
        """Last resort: gracefully drain torrents, then restart the service."""
        return self.restart(reason="recovery escalation")

    # ------------------------------------------------------------------ #
    # Restart (also called directly by the watchdog)
    # ------------------------------------------------------------------ #
    def restart(self, reason: str = "") -> bool:
        """Gracefully drain torrents and restart qbittorrent-nox.

        Args:
            reason: Human-readable reason (logged + notified).

        Returns:
            True if the restart command succeeded (or dry-run).
        """
        msg = f"Restarting {self.service_name}" + (f" ({reason})" if reason else "")
        if self.logger:
            self.logger.warning(("[DRY RUN] " if self.dry_run else "") + msg)
        self._notify("CRITICAL", "qBittorrent restart", msg)

        if self.dry_run:
            self.logger and self.logger.info(
                f"[DRY RUN] would drain {self.drain_timeout}s then 'systemctl restart {self.service_name}'"
            )
            return True

        # Graceful drain: pause torrents and let active pieces flush (5g).
        try:
            if self.api_client.is_reachable():
                self.api_client.pause_torrent("all")
                time.sleep(self.drain_timeout)
        except Exception as e:
            self.logger and self.logger.debug(f"Drain skipped: {e}")

        try:
            result = subprocess.run(
                ["systemctl", "restart", self.service_name],
                capture_output=True,
                timeout=60,
            )
            if result.returncode == 0:
                self.logger and self.logger.info(f"{self.service_name} restarted")
                return True
            self.logger and self.logger.error(
                f"Restart failed: {result.stderr.decode(errors='replace').strip()}"
            )
            return False
        except Exception as e:
            self.logger and self.logger.error(f"Restart error: {e}")
            return False

    def _notify(self, level: str, title: str, message: str):
        if not self.notifier:
            return
        try:
            from agent_logging.notification_system import NotificationLevel

            self.notifier.send_notification(
                getattr(NotificationLevel, level, NotificationLevel.WARNING),
                title,
                message,
                tags=["recovery"],
            )
        except Exception as e:
            self.logger and self.logger.debug(f"Notify failed: {e}")
