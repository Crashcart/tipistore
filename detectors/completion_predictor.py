"""Torrent completion time prediction and ETA calculations."""

from typing import Dict, List, Any, Optional, Tuple
from collections import deque
import statistics


class TorrentCompletionPredictor:
    """Predicts torrent completion times using historical speed data."""

    def __init__(self, history_window: int = 60, logger=None):
        """Initialize completion predictor.

        Args:
            history_window: Number of speed measurements to track
            logger: Logger instance
        """
        self.logger = logger
        self.history_window = history_window

        # Per-torrent speed history
        self.torrent_speed_history: Dict[str, deque] = {}
        self.torrent_size_history: Dict[str, deque] = {}

    def record_torrent_speed(self, torrent_hash: str, speed_kbps: float, total_size: int):
        """Record torrent speed measurement.

        Args:
            torrent_hash: Torrent hash
            speed_kbps: Current download speed in KiB/s
            total_size: Total torrent size in bytes
        """
        if torrent_hash not in self.torrent_speed_history:
            self.torrent_speed_history[torrent_hash] = deque(maxlen=self.history_window)
            self.torrent_size_history[torrent_hash] = deque(maxlen=self.history_window)

        self.torrent_speed_history[torrent_hash].append(speed_kbps)
        self.torrent_size_history[torrent_hash].append(total_size)

    def estimate_completion_time(
        self,
        torrent: Dict[str, Any],
    ) -> Tuple[Optional[int], str]:
        """Estimate time to completion for a torrent.

        Args:
            torrent: Torrent info dict with 'hash', 'size', 'downloaded', 'dl_speed'

        Returns:
            Tuple of (eta_seconds: int or None, confidence: str)
        """
        torrent_hash = torrent.get("hash")
        total_size = torrent.get("total_size", 0)
        downloaded = torrent.get("downloaded", 0)
        current_speed = torrent.get("dl_speed", 0)

        if total_size <= 0 or downloaded >= total_size:
            return None, "complete"

        remaining = total_size - downloaded

        # Check speed history for average speed
        if torrent_hash in self.torrent_speed_history:
            history = list(self.torrent_speed_history[torrent_hash])
            if history:
                # Filter out zero speeds
                non_zero_speeds = [s for s in history if s > 0]

                if non_zero_speeds:
                    avg_speed = statistics.mean(non_zero_speeds)

                    # Use weighted average: 70% recent speed, 30% historical average
                    if current_speed > 0:
                        estimated_speed = current_speed * 0.7 + avg_speed * 0.3
                    else:
                        estimated_speed = avg_speed

                    confidence = "high" if len(non_zero_speeds) >= 10 else "medium"
                else:
                    # No historical speed data
                    if current_speed <= 0:
                        return None, "stalled"
                    estimated_speed = current_speed
                    confidence = "low"
            else:
                # No history at all
                if current_speed <= 0:
                    return None, "stalled"
                estimated_speed = current_speed
                confidence = "low"
        else:
            # No history for this torrent
            if current_speed <= 0:
                return None, "stalled"
            estimated_speed = current_speed
            confidence = "low"

        if estimated_speed <= 0:
            return None, "stalled"

        # Convert remaining bytes to KiB, then calculate time
        remaining_kib = remaining / 1024
        eta_seconds = int(remaining_kib / estimated_speed)

        return eta_seconds, confidence

    def predict_batch_completion(
        self,
        torrents: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Predict completion times for multiple torrents.

        Args:
            torrents: List of torrent info dicts

        Returns:
            Predictions dict
        """
        predictions = {}
        total_eta = 0
        reliable_count = 0

        for torrent in torrents:
            torrent_hash = torrent.get("hash")
            eta, confidence = self.estimate_completion_time(torrent)

            predictions[torrent_hash] = {
                "eta_seconds": eta,
                "eta_formatted": self._format_eta(eta) if eta else "Unknown",
                "confidence": confidence,
                "name": torrent.get("name", "Unknown"),
            }

            if eta and confidence in ["high", "medium"]:
                total_eta += eta
                reliable_count += 1

        # Estimate total time to completion
        avg_eta = total_eta / reliable_count if reliable_count > 0 else None

        return {
            "predictions": predictions,
            "total_estimated_eta_seconds": total_eta,
            "average_eta_seconds": avg_eta,
            "average_eta_formatted": self._format_eta(int(avg_eta)) if avg_eta else "Unknown",
            "reliable_predictions": reliable_count,
        }

    def identify_slow_torrents(
        self,
        torrents: List[Dict[str, Any]],
        speed_threshold_kbps: float = 10,
    ) -> List[Dict[str, Any]]:
        """Identify torrents with slow download speeds.

        Args:
            torrents: List of torrent info dicts
            speed_threshold_kbps: Speed below which is considered slow

        Returns:
            List of slow torrent info
        """
        slow_torrents = []

        for torrent in torrents:
            if torrent.get("state", "").startswith("downloading"):
                speed = torrent.get("dl_speed", 0) / 1024  # Convert to KiB/s
                eta, confidence = self.estimate_completion_time(torrent)

                if speed < speed_threshold_kbps:
                    slow_torrents.append(
                        {
                            "hash": torrent.get("hash"),
                            "name": torrent.get("name"),
                            "speed_kbps": speed,
                            "eta_seconds": eta,
                            "eta_formatted": self._format_eta(eta) if eta else "Unknown",
                        }
                    )

        return slow_torrents

    def estimate_queue_completion(
        self,
        torrents: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Estimate when entire queue will be complete.

        Args:
            torrents: List of torrent info dicts

        Returns:
            Queue completion estimate
        """
        predictions = self.predict_batch_completion(torrents)

        downloading = [
            t
            for t in torrents
            if t.get("state", "").startswith("downloading")
        ]

        return {
            "total_torrents": len(torrents),
            "downloading": len(downloading),
            "queue_eta_seconds": predictions.get("total_estimated_eta_seconds"),
            "queue_eta_formatted": self._format_eta(
                predictions.get("total_estimated_eta_seconds")
            )
            if predictions.get("total_estimated_eta_seconds")
            else "Unknown",
            "estimated_completion_timestamp": None,  # Would be current time + eta
        }

    def _format_eta(self, seconds: Optional[int]) -> str:
        """Format ETA in human-readable format.

        Args:
            seconds: Seconds until completion

        Returns:
            Formatted string
        """
        if seconds is None or seconds < 0:
            return "Unknown"

        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes}m"
        elif seconds < 86400:
            hours = seconds // 3600
            return f"{hours}h"
        else:
            days = seconds // 86400
            return f"{days}d"

    def get_prediction_report(self) -> Dict[str, Any]:
        """Get prediction system report.

        Returns:
            System status report
        """
        return {
            "tracked_torrents": len(self.torrent_speed_history),
            "history_window_size": self.history_window,
            "torrents_with_history": {
                hash: len(history)
                for hash, history in self.torrent_speed_history.items()
                if len(history) > 0
            },
        }
