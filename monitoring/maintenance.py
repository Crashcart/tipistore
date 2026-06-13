"""Maintenance mode controller.

Maintenance can be triggered manually (--maintenance) or automatically during
scheduled throttled hours (a maintenance window). While active, active torrents
are paused; when maintenance ends, they are resumed automatically — unless the
storage guard is currently holding them paused for a disk/mount problem.
"""

from datetime import datetime
from typing import Optional

from monitoring.scheduler import parse_windows, is_within_windows


class MaintenanceController:
    """Coordinates scheduled/manual maintenance and pauses/resumes torrents."""

    def __init__(
        self,
        windows_spec=None,
        manual: bool = False,
        pause_torrents: bool = True,
        logger=None,
    ):
        """Initialize the controller.

        Args:
            windows_spec: Maintenance window spec, e.g. "22:00-06:00".
            manual: Start in manual maintenance mode (always active).
            pause_torrents: Pause torrents while maintenance is active.
            logger: Optional logger.
        """
        self.windows = parse_windows(windows_spec)
        self.manual = manual
        self.pause_torrents = pause_torrents
        self.logger = logger

        # Latch: True while torrents are paused *by this controller*.
        self.maintenance_paused = False
        self._active = False

    def is_active(self, now: Optional[datetime] = None) -> bool:
        """Return True if maintenance should be active right now."""
        if self.manual:
            return True
        return is_within_windows(self.windows, now)

    def update(self, api_client, storage_paused: bool = False, dry_run: bool = False,
               now: Optional[datetime] = None) -> dict:
        """Apply maintenance transitions (pause on entry, resume on exit).

        Args:
            api_client: QBittorrentAPIClient.
            storage_paused: True if the storage guard currently holds a pause;
                if so, we do not resume on maintenance exit.
            dry_run: Log intended actions without making changes.
            now: Override the current time (for testing).

        Returns:
            Dict: {active, transition}.
        """
        active = self.is_active(now)
        transition = "none"

        if active and not self._active:
            transition = "entered"
            if self.logger:
                self.logger.info("Entering maintenance mode")
            if self.pause_torrents and not self.maintenance_paused:
                if self.logger:
                    self.logger.info("Pausing torrents for maintenance")
                if not dry_run:
                    api_client.pause_torrent("all")
                self.maintenance_paused = True

        elif not active and self._active:
            transition = "exited"
            if self.logger:
                self.logger.info("Maintenance window ended")
            if self.maintenance_paused:
                if storage_paused:
                    # Storage guard owns the pause now; don't override it.
                    if self.logger:
                        self.logger.warning(
                            "Maintenance ended but storage problem active; "
                            "leaving torrents paused"
                        )
                else:
                    if self.logger:
                        self.logger.info("Resuming torrents after maintenance")
                    if not dry_run:
                        api_client.resume_torrent("all")
                self.maintenance_paused = False

        self._active = active
        return {"active": active, "transition": transition}
