"""Backup and restore recovery state and configuration snapshots."""

from typing import Dict, List, Any, Optional
from datetime import datetime
import json
import os


class StateSnapshot:
    """Single point-in-time recovery state snapshot."""

    def __init__(
        self,
        timestamp: datetime,
        lag_score: float,
        applied_limits: Dict[str, Any],
        system_metrics: Dict[str, Any],
        recovery_attempts: List[str],
        torrent_states: Dict[str, Any],
    ):
        """Initialize state snapshot.

        Args:
            timestamp: When snapshot was taken
            lag_score: Current lag score (0-100)
            applied_limits: Current connection/bandwidth limits
            system_metrics: CPU, memory, disk stats
            recovery_attempts: List of attempted fixes
            torrent_states: State of all torrents
        """
        self.timestamp = timestamp
        self.lag_score = lag_score
        self.applied_limits = applied_limits
        self.system_metrics = system_metrics
        self.recovery_attempts = recovery_attempts
        self.torrent_states = torrent_states

    def to_dict(self) -> Dict[str, Any]:
        """Convert snapshot to dict for serialization.

        Returns:
            Dictionary representation
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "lag_score": self.lag_score,
            "applied_limits": self.applied_limits,
            "system_metrics": self.system_metrics,
            "recovery_attempts": self.recovery_attempts,
            "torrent_states": self.torrent_states,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StateSnapshot":
        """Create snapshot from dict.

        Args:
            data: Dictionary representation

        Returns:
            StateSnapshot instance
        """
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            lag_score=data["lag_score"],
            applied_limits=data["applied_limits"],
            system_metrics=data["system_metrics"],
            recovery_attempts=data["recovery_attempts"],
            torrent_states=data["torrent_states"],
        )


class BackupRestoreManager:
    """Manages backup and restore of recovery state."""

    def __init__(self, backup_dir: str = "/var/lib/qbittorrent-agent/backups", logger=None):
        """Initialize backup manager.

        Args:
            backup_dir: Directory to store backups
            logger: Logger instance
        """
        self.logger = logger
        self.backup_dir = backup_dir
        self.snapshots: List[StateSnapshot] = []
        self.max_snapshots = 50

        # Create backup directory if needed
        os.makedirs(backup_dir, exist_ok=True)

    def create_snapshot(
        self,
        lag_score: float,
        applied_limits: Dict[str, Any],
        system_metrics: Dict[str, Any],
        recovery_attempts: List[str],
        torrent_states: Dict[str, Any],
    ) -> StateSnapshot:
        """Create a state snapshot.

        Args:
            lag_score: Current lag score
            applied_limits: Applied connection/bandwidth limits
            system_metrics: Current system metrics
            recovery_attempts: Attempted recovery strategies
            torrent_states: Current torrent states

        Returns:
            Created StateSnapshot
        """
        snapshot = StateSnapshot(
            timestamp=datetime.utcnow(),
            lag_score=lag_score,
            applied_limits=applied_limits,
            system_metrics=system_metrics,
            recovery_attempts=recovery_attempts,
            torrent_states=torrent_states,
        )

        self.snapshots.append(snapshot)

        # Keep only most recent snapshots
        if len(self.snapshots) > self.max_snapshots:
            self.snapshots.pop(0)

        if self.logger:
            self.logger.info(
                f"Created state snapshot: lag_score={lag_score:.1f}, "
                f"recovery_attempts={len(recovery_attempts)}"
            )

        return snapshot

    def save_snapshot_to_file(self, snapshot: StateSnapshot, name: str = None) -> str:
        """Save snapshot to file.

        Args:
            snapshot: Snapshot to save
            name: Optional custom name (defaults to timestamp)

        Returns:
            Path to saved file
        """
        if name is None:
            name = snapshot.timestamp.strftime("%Y%m%d_%H%M%S")

        filepath = os.path.join(self.backup_dir, f"{name}.json")

        with open(filepath, "w") as f:
            json.dump(snapshot.to_dict(), f, indent=2)

        if self.logger:
            self.logger.info(f"Saved snapshot to {filepath}")

        return filepath

    def load_snapshot_from_file(self, filepath: str) -> Optional[StateSnapshot]:
        """Load snapshot from file.

        Args:
            filepath: Path to snapshot file

        Returns:
            StateSnapshot or None if load failed
        """
        try:
            with open(filepath, "r") as f:
                data = json.load(f)

            snapshot = StateSnapshot.from_dict(data)

            if self.logger:
                self.logger.info(f"Loaded snapshot from {filepath}")

            return snapshot

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error loading snapshot: {e}")
            return None

    def list_snapshots(self) -> List[Dict[str, Any]]:
        """List all available snapshots.

        Returns:
            List of snapshot info dicts
        """
        snapshots_info = []

        try:
            for filename in sorted(os.listdir(self.backup_dir)):
                if filename.endswith(".json"):
                    filepath = os.path.join(self.backup_dir, filename)
                    snapshot = self.load_snapshot_from_file(filepath)

                    if snapshot:
                        snapshots_info.append(
                            {
                                "filename": filename,
                                "timestamp": snapshot.timestamp.isoformat(),
                                "lag_score": snapshot.lag_score,
                                "recovery_attempts": len(snapshot.recovery_attempts),
                            }
                        )

            return snapshots_info

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error listing snapshots: {e}")
            return []

    def get_latest_snapshot(self) -> Optional[StateSnapshot]:
        """Get most recent snapshot from memory.

        Returns:
            Latest StateSnapshot or None
        """
        if self.snapshots:
            return self.snapshots[-1]
        return None

    def compare_snapshots(
        self, snapshot1: StateSnapshot, snapshot2: StateSnapshot
    ) -> Dict[str, Any]:
        """Compare two snapshots to show changes.

        Args:
            snapshot1: First snapshot
            snapshot2: Second snapshot

        Returns:
            Comparison report
        """
        return {
            "time_delta_seconds": (snapshot2.timestamp - snapshot1.timestamp).total_seconds(),
            "lag_score_change": snapshot2.lag_score - snapshot1.lag_score,
            "recovery_attempts_added": len(set(snapshot2.recovery_attempts) - set(snapshot1.recovery_attempts)),
            "limit_changes": {
                key: snapshot2.applied_limits.get(key) - snapshot1.applied_limits.get(key, 0)
                for key in snapshot2.applied_limits
                if key in snapshot1.applied_limits
            },
        }

    def export_rules_config(self, rules_engine) -> str:
        """Export category rules configuration.

        Args:
            rules_engine: CategoryRulesEngine instance

        Returns:
            Path to exported config file
        """
        filepath = os.path.join(self.backup_dir, f"rules_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json")

        config = rules_engine.get_rules_config()

        with open(filepath, "w") as f:
            json.dump(config, f, indent=2)

        if self.logger:
            self.logger.info(f"Exported rules config to {filepath}")

        return filepath

    def import_rules_config(self, filepath: str, rules_engine) -> bool:
        """Import category rules configuration.

        Args:
            filepath: Path to config file
            rules_engine: CategoryRulesEngine instance

        Returns:
            True if successful
        """
        try:
            with open(filepath, "r") as f:
                config = json.load(f)

            rules_engine.load_rules_from_config(config)

            if self.logger:
                self.logger.info(f"Imported rules config from {filepath}")

            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error importing rules config: {e}")
            return False

    def get_backup_report(self) -> Dict[str, Any]:
        """Get comprehensive backup status report.

        Returns:
            Report dict
        """
        snapshots_list = self.list_snapshots()
        latest = self.get_latest_snapshot()

        return {
            "backup_directory": self.backup_dir,
            "total_snapshots": len(snapshots_list),
            "max_snapshots_retained": self.max_snapshots,
            "snapshots": snapshots_list,
            "latest_snapshot": {
                "timestamp": latest.timestamp.isoformat(),
                "lag_score": latest.lag_score,
            } if latest else None,
            "disk_usage_info": {
                "backup_dir_exists": os.path.exists(self.backup_dir),
                "writable": os.access(self.backup_dir, os.W_OK),
            },
        }
