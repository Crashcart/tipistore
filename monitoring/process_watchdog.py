"""Process crash watchdog for qbittorrent-nox.

Detects when qBittorrent has actually died (process gone) or stopped responding
on its Web API, and coordinates restarts with backoff and a restart cap.
"""

import time
from typing import Optional

import psutil


class ProcessWatchdog:
    """Monitors the qbittorrent-nox process and API responsiveness."""

    def __init__(
        self,
        service_name: str = "qbittorrent-nox",
        process_name: str = "qbittorrent-nox",
        max_restarts: int = 3,
        restart_cooldown: int = 300,
        unresponsive_cycles: int = 2,
        logger=None,
    ):
        """Initialize the watchdog.

        Args:
            service_name: systemd unit name (used by the restart action).
            process_name: process name to match via psutil.
            max_restarts: max restarts allowed within ``restart_cooldown``.
            restart_cooldown: rolling window (seconds) for counting restarts.
            unresponsive_cycles: consecutive unresponsive checks before acting.
            logger: optional logger.
        """
        self.service_name = service_name
        self.process_name = process_name
        self.max_restarts = max_restarts
        self.restart_cooldown = restart_cooldown
        self.unresponsive_cycles = unresponsive_cycles
        self.logger = logger

        self._unresponsive_count = 0
        self._restart_times: list = []

    def find_pid(self) -> Optional[int]:
        """Return the PID of qbittorrent-nox if running, else None."""
        for proc in psutil.process_iter(["name"]):
            try:
                name = proc.info.get("name") or ""
                if self.process_name in name:
                    return proc.pid
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def is_running(self) -> bool:
        """Return True if the qBittorrent process exists."""
        return self.find_pid() is not None

    def evaluate(self, api_client) -> dict:
        """Assess process/API health and whether a restart is warranted.

        Args:
            api_client: QBittorrentAPIClient instance.

        Returns:
            Dict with keys: running, responsive, healthy, needs_restart, reason.
        """
        running = self.is_running()
        responsive = api_client.is_reachable() if running else False

        if running and responsive:
            self._unresponsive_count = 0
            return {
                "running": True,
                "responsive": True,
                "healthy": True,
                "needs_restart": False,
                "reason": "ok",
            }

        # Process gone -> immediate restart candidate.
        if not running:
            return {
                "running": False,
                "responsive": False,
                "healthy": False,
                "needs_restart": True,
                "reason": "process not running",
            }

        # Running but API unresponsive -> require sustained failures.
        self._unresponsive_count += 1
        needs_restart = self._unresponsive_count >= self.unresponsive_cycles
        return {
            "running": True,
            "responsive": False,
            "healthy": False,
            "needs_restart": needs_restart,
            "reason": (
                f"API unresponsive for {self._unresponsive_count} cycle(s)"
                if needs_restart
                else f"API unresponsive ({self._unresponsive_count}/{self.unresponsive_cycles})"
            ),
        }

    def can_restart(self) -> bool:
        """Return True if a restart is allowed under the rolling cap."""
        self._prune_restart_history()
        return len(self._restart_times) < self.max_restarts

    def record_restart(self):
        """Record that a restart was performed (for cap accounting)."""
        self._restart_times.append(time.time())
        self._prune_restart_history()
        self._unresponsive_count = 0

    def restarts_in_window(self) -> int:
        """Number of restarts within the current cooldown window."""
        self._prune_restart_history()
        return len(self._restart_times)

    def _prune_restart_history(self):
        cutoff = time.time() - self.restart_cooldown
        self._restart_times = [t for t in self._restart_times if t >= cutoff]
