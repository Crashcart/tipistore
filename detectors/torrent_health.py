"""Torrent health analyzer for qBittorrent."""

from typing import Dict, List, Tuple, Any
from dataclasses import dataclass
from enum import Enum


class TorrentHealth(Enum):
    """Torrent health classification."""

    EXCELLENT = 5  # High seeds, active, healthy
    GOOD = 4  # Good seeds, normal activity
    FAIR = 3  # Moderate seeds, some activity
    POOR = 2  # Few seeds, little activity
    DEAD = 1  # No seeds, stuck, unrecoverable


@dataclass
class TorrentHealthScore:
    """Torrent health score result."""

    torrent_hash: str
    torrent_name: str
    health_level: TorrentHealth
    health_score: float  # 0-100
    issues: List[str]
    recovery_priority: int  # 0-100 (higher = more recovery attempts)
    is_recoverable: bool


class TorrentHealthAnalyzer:
    """Analyzes torrent health and identifies problematic torrents."""

    def __init__(self, logger=None):
        """Initialize health analyzer.

        Args:
            logger: Logger instance
        """
        self.logger = logger

        # Thresholds for health assessment
        self.min_seeders = 1  # Minimum seeders for healthy torrent
        self.min_upload_speed = 1024  # 1 KB/s minimum upload
        self.stalled_threshold = 3600  # 1 hour with no activity = stalled
        self.dead_threshold = 86400  # 24 hours with no activity = dead
        self.min_ratio_threshold = 0.1  # Minimum ratio for active torrents

    def analyze_torrent(self, torrent: Dict[str, Any]) -> TorrentHealthScore:
        """Analyze health of a single torrent.

        Args:
            torrent: Torrent info dict from qBittorrent API

        Returns:
            TorrentHealthScore object
        """
        issues = []
        health_score = 100.0
        recovery_priority = 0

        torrent_hash = torrent.get("hash", "unknown")
        torrent_name = torrent.get("name", "Unknown")

        # 1. Check seeders
        num_seeds = torrent.get("num_seeds", 0)
        if num_seeds == 0:
            issues.append("No seeders available")
            health_score -= 40
            recovery_priority += 10
        elif num_seeds < 3:
            issues.append(f"Very few seeders: {num_seeds}")
            health_score -= 15
            recovery_priority += 5

        # 2. Check upload activity
        upspeed = torrent.get("upspeed", 0)
        if upspeed == 0 and torrent.get("state", "") not in ["pausedUP", "pausedDL"]:
            issues.append("No upload activity")
            health_score -= 20
            recovery_priority += 5

        # 3. Check completion status
        progress = torrent.get("progress", 0)
        if progress < 1.0 and upspeed == 0:
            issues.append(f"Incomplete download with no upload: {progress*100:.1f}%")
            health_score -= 25
            recovery_priority += 5

        # 4. Check for stalled torrents
        if self._is_stalled(torrent):
            issues.append("Torrent is stalled (no activity)")
            health_score -= 30
            recovery_priority += 15

        # 5. Check for dead torrents
        if self._is_dead(torrent):
            issues.append("Torrent appears dead (no activity for 24h+)")
            health_score -= 50
            recovery_priority -= 50  # Don't bother recovering

        # 6. Check ratio for complete torrents
        if progress >= 1.0:
            ratio = torrent.get("ratio", 0)
            if ratio < self.min_ratio_threshold and upspeed > 0:
                issues.append(f"Low ratio: {ratio:.2f}")
                health_score -= 10

        # 7. Check peers (leechers)
        num_leech = torrent.get("num_leechs", 0)
        if num_leech == 0 and progress < 1.0:
            issues.append("No leechers (complete, can't upload)")
            health_score -= 15

        # Normalize health score
        health_score = max(0, min(100, health_score))

        # Determine health level
        health_level = self._score_to_level(health_score)

        # Determine if recoverable
        is_recoverable = health_score >= 30 and recovery_priority >= -30

        return TorrentHealthScore(
            torrent_hash=torrent_hash,
            torrent_name=torrent_name,
            health_level=health_level,
            health_score=health_score,
            issues=issues,
            recovery_priority=recovery_priority,
            is_recoverable=is_recoverable,
        )

    def analyze_all_torrents(self, torrents: List[Dict[str, Any]]) -> Dict[str, TorrentHealthScore]:
        """Analyze all torrents.

        Args:
            torrents: List of torrent info dicts from qBittorrent API

        Returns:
            Dict mapping torrent hash to TorrentHealthScore
        """
        results = {}
        for torrent in torrents:
            try:
                score = self.analyze_torrent(torrent)
                results[score.torrent_hash] = score
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Error analyzing torrent {torrent.get('name')}: {e}")

        return results

    def get_health_summary(self, torrents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get summary of overall torrent health.

        Args:
            torrents: List of torrent info dicts

        Returns:
            Summary dict with statistics
        """
        scores = self.analyze_all_torrents(torrents)

        healthy = sum(1 for s in scores.values() if s.health_level.value >= 3)
        unhealthy = sum(1 for s in scores.values() if s.health_level.value < 3)
        unrecoverable = sum(1 for s in scores.values() if not s.is_recoverable)

        avg_health = sum(s.health_score for s in scores.values()) / len(scores) if scores else 0

        return {
            "total_torrents": len(torrents),
            "healthy": healthy,
            "unhealthy": unhealthy,
            "unrecoverable": unrecoverable,
            "average_health_score": avg_health,
            "problematic_torrents": [
                {
                    "name": s.torrent_name,
                    "hash": s.torrent_hash,
                    "health_level": s.health_level.name,
                    "score": s.health_score,
                    "issues": s.issues,
                    "recoverable": s.is_recoverable,
                }
                for s in sorted(scores.values(), key=lambda x: x.health_score)[:10]
            ],
        }

    def get_unrecoverable_torrents(self, torrents: List[Dict[str, Any]]) -> List[str]:
        """Get list of torrent hashes that should be removed/paused.

        Args:
            torrents: List of torrent info dicts

        Returns:
            List of torrent hashes to remove
        """
        scores = self.analyze_all_torrents(torrents)
        return [h for h, s in scores.items() if not s.is_recoverable and s.health_score < 20]

    @staticmethod
    def _score_to_level(score: float) -> TorrentHealth:
        """Convert score to health level.

        Args:
            score: Health score (0-100)

        Returns:
            TorrentHealth enum
        """
        if score >= 80:
            return TorrentHealth.EXCELLENT
        elif score >= 60:
            return TorrentHealth.GOOD
        elif score >= 40:
            return TorrentHealth.FAIR
        elif score >= 20:
            return TorrentHealth.POOR
        else:
            return TorrentHealth.DEAD

    @staticmethod
    def _is_stalled(torrent: Dict[str, Any]) -> bool:
        """Check if torrent is stalled.

        Args:
            torrent: Torrent info dict

        Returns:
            True if stalled
        """
        state = torrent.get("state", "")
        upspeed = torrent.get("upspeed", 0)
        dlspeed = torrent.get("dlspeed", 0)

        # Stalled if downloading/uploading but no speed
        if state in ["downloading", "uploading", "metaDL"] and upspeed == 0 and dlspeed == 0:
            return True

        # Stalled if stuck at same progress for long time (would need timestamp tracking)
        return False

    @staticmethod
    def _is_dead(torrent: Dict[str, Any]) -> bool:
        """Check if torrent is dead.

        Args:
            torrent: Torrent info dict

        Returns:
            True if dead
        """
        num_seeds = torrent.get("num_seeds", 0)
        num_leech = torrent.get("num_leechs", 0)
        upspeed = torrent.get("upspeed", 0)

        # Dead if no seeds, no leechers, and not uploading
        if num_seeds == 0 and num_leech == 0 and upspeed == 0:
            return True

        return False
