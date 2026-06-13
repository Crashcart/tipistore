"""Disk / mount safety for qBittorrent save paths.

Detects full disks, missing/unmounted paths, and read-only mounts, and acts as
a hard safety gate: pause torrents before they error, resume when storage
recovers.
"""

import os
from typing import Any, Dict, List, Optional

from monitoring.metrics import SystemMetrics


class StorageMonitor:
    """Guards qBittorrent storage paths and pauses torrents on failure."""

    def __init__(
        self,
        watch_paths: Optional[List[str]] = None,
        min_free_gb: float = 5.0,
        min_free_percent: float = 2.0,
        require_mountpoint: bool = False,
        logger=None,
    ):
        """Initialize the storage monitor.

        Args:
            watch_paths: Explicit paths to guard (from --watch-mount).
            min_free_gb: Pause threshold for free space, in GB.
            min_free_percent: Pause threshold for free space, in percent.
            require_mountpoint: If True, a watched path must be an actual
                mountpoint (use for NAS mounts that should never be a bare dir).
            logger: Optional logger.
        """
        self.watch_paths = list(watch_paths or [])
        self.min_free_gb = min_free_gb
        self.min_free_percent = min_free_percent
        self.require_mountpoint = require_mountpoint
        self.logger = logger
        self.metrics = SystemMetrics()

        # Latch: True while torrents are paused due to a storage problem.
        self.storage_paused = False

    def discover_paths(self, api_client) -> List[str]:
        """Combine explicit watch paths with qBittorrent's configured paths.

        Args:
            api_client: QBittorrentAPIClient to read save_path/temp_path from.

        Returns:
            De-duplicated list of paths to check.
        """
        paths = list(self.watch_paths)
        prefs = api_client.get_preferences() if api_client else None
        if prefs:
            save_path = prefs.get("save_path")
            if save_path:
                paths.append(save_path)
            temp_path = prefs.get("temp_path")
            if temp_path and prefs.get("temp_path_enabled", False):
                paths.append(temp_path)
        # De-duplicate, preserve order.
        seen = set()
        result = []
        for p in paths:
            if p and p not in seen:
                seen.add(p)
                result.append(p)
        return result

    def check(self, api_client=None, paths: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Check all watched paths and return a list of problems.

        Args:
            api_client: Used to discover qBittorrent paths if ``paths`` is None.
            paths: Explicit list of paths to check.

        Returns:
            List of issue dicts: {path, problem, detail}.
        """
        if paths is None:
            paths = self.discover_paths(api_client) if api_client else self.watch_paths

        issues: List[Dict[str, Any]] = []

        for path in paths:
            if not os.path.exists(path):
                issues.append({"path": path, "problem": "missing", "detail": "path does not exist"})
                continue

            if self.require_mountpoint and not os.path.ismount(path):
                issues.append(
                    {"path": path, "problem": "not_mounted", "detail": "expected a mountpoint"}
                )
                continue

            if not os.access(path, os.W_OK):
                issues.append({"path": path, "problem": "read_only", "detail": "not writable"})
                continue

            try:
                disk = self.metrics.get_disk_info(path)
            except OSError as e:
                issues.append({"path": path, "problem": "unreadable", "detail": str(e)})
                continue

            free_gb = disk["free"] / (1024**3)
            free_percent = 100.0 - disk["percent"]

            if free_gb < self.min_free_gb or free_percent < self.min_free_percent:
                issues.append(
                    {
                        "path": path,
                        "problem": "low_space",
                        "detail": f"{free_gb:.1f} GB / {free_percent:.1f}% free",
                    }
                )

        return issues

    def enforce(self, api_client, dry_run: bool = False) -> Dict[str, Any]:
        """Pause torrents on storage failure; resume when recovered.

        Args:
            api_client: QBittorrentAPIClient.
            dry_run: If True, log intended actions without making changes.

        Returns:
            Dict: {issues, action, paused}.
        """
        issues = self.check(api_client)
        action = "none"

        if issues:
            if not self.storage_paused:
                detail = "; ".join(f"{i['path']}: {i['problem']}" for i in issues)
                if self.logger:
                    self.logger.warning(f"Storage problem detected, pausing torrents: {detail}")
                if not dry_run:
                    api_client.pause_torrent("all")
                self.storage_paused = True
                action = "paused"
        else:
            if self.storage_paused:
                if self.logger:
                    self.logger.info("Storage recovered, resuming torrents")
                if not dry_run:
                    api_client.resume_torrent("all")
                self.storage_paused = False
                action = "resumed"

        return {"issues": issues, "action": action, "paused": self.storage_paused}

    def wait_for_mounts(self, dry_run: bool = False, timeout: int = 120, poll: float = 2.0) -> bool:
        """Block until all watched paths are mounted and writable (5m).

        Args:
            dry_run: If True, do not actually sleep-wait; report current state.
            timeout: Max seconds to wait.
            poll: Seconds between checks.

        Returns:
            True if all paths became available within the timeout.
        """
        import time

        if not self.watch_paths:
            return True

        deadline = time.time() + timeout
        while True:
            issues = self.check(paths=self.watch_paths)
            if not issues:
                if self.logger:
                    self.logger.info("All watched mounts are available")
                return True

            if dry_run or time.time() >= deadline:
                if self.logger:
                    detail = "; ".join(f"{i['path']}: {i['problem']}" for i in issues)
                    self.logger.warning(f"Mounts not ready (timeout/dry-run): {detail}")
                return False

            time.sleep(poll)
