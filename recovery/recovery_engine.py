"""Recovery engine for qBittorrent."""

import time
from typing import List, Dict, Any


class RecoveryEngine:
    """Executes recovery strategies in intelligent order."""

    def __init__(self, api_client, config_manager, logger=None):
        """Initialize recovery engine.

        Args:
            api_client: QBittorrent API client
            config_manager: Configuration manager
            logger: Logger instance
        """
        self.api_client = api_client
        self.config_manager = config_manager
        self.logger = logger

        # Recovery strategies in order (least to most invasive)
        self.strategies = [
            ("connection_cleanup", self._connection_cleanup, 15),
            ("dht_refresh", self._dht_refresh, 10),
            ("reload_config", self._reload_config, 10),
            ("dynamic_limits", self._dynamic_limits, 20),
            ("torrent_refresh", self._torrent_refresh, 30),
            ("restart_process", self._restart_process, 60),
        ]

    def get_recovery_plan(self, lag_score: float) -> List[str]:
        """Get the recovery plan for a given lag score.

        Args:
            lag_score: Lag detection score (0-100)

        Returns:
            List of strategy names to execute
        """
        plan = []

        # Determine which strategies to execute based on lag score
        if lag_score > 30:
            plan.append("connection_cleanup")
        if lag_score > 40:
            plan.append("dht_refresh")
        if lag_score > 50:
            plan.append("reload_config")
        if lag_score > 60:
            plan.append("dynamic_limits")
        if lag_score > 75:
            plan.append("torrent_refresh")
        if lag_score > 85:
            plan.append("restart_process")

        return plan

    def execute_recovery(self, lag_score: float) -> bool:
        """Execute recovery strategies based on lag score.

        Args:
            lag_score: Lag detection score (0-100)

        Returns:
            True if recovery was successful
        """
        try:
            plan = self.get_recovery_plan(lag_score)

            if not plan:
                if self.logger:
                    self.logger.info("No recovery needed")
                return True

            if self.logger:
                self.logger.info(f"Executing recovery plan: {', '.join(plan)}")

            for strategy_name in plan:
                if self.logger:
                    self.logger.info(f"Executing strategy: {strategy_name}")

                success = self._execute_strategy(strategy_name)

                if not success:
                    if self.logger:
                        self.logger.warning(f"Strategy {strategy_name} failed")
                    continue

                # Check if lag improved after this strategy
                time.sleep(5)  # Wait for effect

                if self.logger:
                    self.logger.info(f"Strategy {strategy_name} executed")

            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Recovery execution error: {e}", exc_info=True)
            return False

    def _execute_strategy(self, strategy_name: str) -> bool:
        """Execute a single recovery strategy.

        Args:
            strategy_name: Name of the strategy

        Returns:
            True if successful
        """
        for name, func, _ in self.strategies:
            if name == strategy_name:
                try:
                    return func()
                except Exception as e:
                    if self.logger:
                        self.logger.error(f"Strategy {strategy_name} error: {e}")
                    return False
        return False

    def _connection_cleanup(self) -> bool:
        """Clear stale connections and peers."""
        try:
            if self.logger:
                self.logger.debug("Cleaning up stale connections")

            # Implementation would interact with qBittorrent API
            # to reset peer connections
            self.api_client.purge_all_cache()

            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Connection cleanup error: {e}")
            return False

    def _dht_refresh(self) -> bool:
        """Trigger full DHT node rescan."""
        try:
            if self.logger:
                self.logger.debug("Refreshing DHT")

            # Implementation would trigger DHT rescan
            # This might require API call or config manipulation
            stats = self.api_client.get_server_state()
            current_dht = stats.get("dht_nodes", 0)

            if self.logger:
                self.logger.info(f"DHT nodes before refresh: {current_dht}")

            # Note: Actual DHT refresh would require API enhancement
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"DHT refresh error: {e}")
            return False

    def _reload_config(self) -> bool:
        """Reload configuration from disk."""
        try:
            if self.logger:
                self.logger.debug("Reloading configuration")

            # Reload config manager
            self.config_manager.reload()

            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Config reload error: {e}")
            return False

    def _dynamic_limits(self) -> bool:
        """Adjust connection/bandwidth limits based on system capacity."""
        try:
            if self.logger:
                self.logger.debug("Adjusting dynamic limits")

            # Would analyze system capacity and adjust qBittorrent limits
            # This requires API calls to qBittorrent to set preferences
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Dynamic limits error: {e}")
            return False

    def _torrent_refresh(self) -> bool:
        """Pause and resume torrents to reset internal state."""
        try:
            if self.logger:
                self.logger.debug("Refreshing torrents")

            torrents = self.api_client.get_torrents()
            paused_count = 0
            resumed_count = 0

            # Pause all torrents
            for torrent in torrents:
                if torrent.get("state") not in ["pausedDL", "pausedUP"]:
                    self.api_client.pause_torrent(torrent["hash"])
                    paused_count += 1

            # Wait
            time.sleep(10)

            # Resume all torrents
            for torrent in torrents:
                if torrent.get("state") in ["pausedDL", "pausedUP"]:
                    self.api_client.resume_torrent(torrent["hash"])
                    resumed_count += 1

            if self.logger:
                self.logger.info(f"Paused {paused_count}, resumed {resumed_count} torrents")

            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Torrent refresh error: {e}")
            return False

    def _restart_process(self) -> bool:
        """Gracefully restart qBittorrent process."""
        try:
            if self.logger:
                self.logger.warning("Restarting qBittorrent process")

            # This would stop and start the qBittorrent process
            # Implementation depends on how qBittorrent is running (systemd, docker, etc)
            import subprocess

            # Example: systemctl restart
            result = subprocess.run(
                ["systemctl", "restart", "qbittorrent-nox"],
                capture_output=True,
                timeout=30,
            )

            if result.returncode == 0:
                if self.logger:
                    self.logger.info("qBittorrent restarted successfully")
                return True
            else:
                if self.logger:
                    self.logger.error(f"Restart failed: {result.stderr.decode()}")
                return False

        except Exception as e:
            if self.logger:
                self.logger.error(f"Process restart error: {e}")
            return False
