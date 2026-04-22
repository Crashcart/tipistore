"""Connection pool optimization for qBittorrent."""

from typing import Dict, List, Any, Optional
from collections import deque


class ConnectionOptimizer:
    """Optimizes connection limits based on system state and peer availability."""

    def __init__(self, logger=None):
        """Initialize connection optimizer.

        Args:
            logger: Logger instance
        """
        self.logger = logger

        # Thresholds
        self.base_connection_limit = 500  # Default global limit
        self.base_peer_limit = 200  # Default per-torrent limit
        self.min_connection_limit = 50  # Minimum safe limit
        self.max_connection_limit = 2000  # Maximum safe limit

        # History tracking
        self.connection_history = deque(maxlen=60)
        self.error_history = deque(maxlen=60)

    def record_connection_state(self, connected_peers: int, errors: int = 0):
        """Record current connection state.

        Args:
            connected_peers: Number of connected peers
            errors: Number of connection errors this period
        """
        self.connection_history.append(connected_peers)
        if errors > 0:
            self.error_history.append(errors)

    def analyze_connection_health(self) -> Dict[str, Any]:
        """Analyze overall connection pool health.

        Returns:
            Health analysis dict
        """
        if not self.connection_history:
            return {
                "status": "unknown",
                "reason": "No data yet",
            }

        current_peers = self.connection_history[-1]
        recent_peers = list(self.connection_history)[-10:] if len(self.connection_history) >= 10 else list(self.connection_history)
        avg_peers = sum(recent_peers) / len(recent_peers)

        # Check error rate
        error_count = sum(self.error_history) if self.error_history else 0
        error_rate = error_count / len(self.error_history) if self.error_history else 0

        health = {
            "current_peers": current_peers,
            "average_peers": avg_peers,
            "error_rate": error_rate,
        }

        if error_rate > 0.1:
            health["status"] = "unhealthy"
            health["reason"] = f"High error rate: {error_rate:.1%}"
        elif current_peers == 0:
            health["status"] = "critical"
            health["reason"] = "No connected peers"
        elif current_peers < avg_peers * 0.5:
            health["status"] = "degraded"
            health["reason"] = "Peer count significantly below average"
        else:
            health["status"] = "healthy"
            health["reason"] = "Connection pool functioning normally"

        return health

    def suggest_connection_limits(self, api_client, system_metrics) -> Dict[str, Any]:
        """Suggest optimal connection limits based on analysis.

        Args:
            api_client: qBittorrent API client
            system_metrics: SystemMetrics instance

        Returns:
            Suggestion dict with recommended limits
        """
        try:
            # Get current preferences
            prefs = api_client.get_preferences()
            if not prefs:
                return {"suggestion": None, "reason": "Could not get preferences"}

            current_limit = prefs.get("connections_limit", self.base_connection_limit)
            current_peer_limit = prefs.get("max_connec_per_torrent", self.base_peer_limit)

            # Analyze system resources
            cpu_percent = system_metrics.get_cpu_percent()
            memory_info = system_metrics.get_memory_info()

            # Analyze connection health
            health = self.analyze_connection_health()

            # Calculate recommendation
            recommendation = self._calculate_optimal_limits(
                current_limit,
                current_peer_limit,
                cpu_percent,
                memory_info,
                health,
            )

            return {
                "current_limit": current_limit,
                "current_peer_limit": current_peer_limit,
                "recommended_limit": recommendation["limit"],
                "recommended_peer_limit": recommendation["peer_limit"],
                "reason": recommendation["reason"],
                "change_percent": (recommendation["limit"] - current_limit) / current_limit * 100,
            }

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error suggesting limits: {e}")
            return {"suggestion": None, "reason": str(e)}

    def _calculate_optimal_limits(
        self,
        current_limit: int,
        current_peer_limit: int,
        cpu_percent: float,
        memory_info: Dict[str, Any],
        health: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Calculate optimal connection limits.

        Args:
            current_limit: Current global limit
            current_peer_limit: Current per-torrent limit
            cpu_percent: CPU usage %
            memory_info: Memory info dict
            health: Connection health analysis

        Returns:
            Recommendation dict
        """
        new_limit = current_limit
        new_peer_limit = current_peer_limit
        reason = "Current limits appropriate"

        # If errors are high, reduce limits
        if health["error_rate"] > 0.1:
            reduction = 0.8
            new_limit = max(self.min_connection_limit, int(current_limit * reduction))
            new_peer_limit = max(50, int(current_peer_limit * reduction))
            reason = f"High error rate ({health['error_rate']:.1%}), reducing limits"

        # If CPU is high, reduce limits
        elif cpu_percent > 75:
            reduction = 0.85
            new_limit = max(self.min_connection_limit, int(current_limit * reduction))
            new_peer_limit = max(50, int(current_peer_limit * reduction))
            reason = f"High CPU usage ({cpu_percent:.1f}%), reducing limits"

        # If memory is high, reduce limits
        elif memory_info["percent"] > 85:
            reduction = 0.75
            new_limit = max(self.min_connection_limit, int(current_limit * reduction))
            new_peer_limit = max(50, int(current_peer_limit * reduction))
            reason = f"High memory usage ({memory_info['percent']:.1f}%), reducing limits"

        # If peer count is consistently high and system healthy, increase limits
        elif (
            health["status"] == "healthy"
            and health["current_peers"] > health["average_peers"] * 0.9
            and cpu_percent < 50
            and memory_info["percent"] < 70
        ):
            increase = 1.1
            new_limit = min(self.max_connection_limit, int(current_limit * increase))
            new_peer_limit = min(500, int(current_peer_limit * increase))
            reason = "System healthy with good peer availability, increasing limits"

        return {
            "limit": new_limit,
            "peer_limit": new_peer_limit,
            "reason": reason,
        }

    def apply_connection_limits(self, api_client, limit: int, peer_limit: int) -> bool:
        """Apply connection limits to qBittorrent.

        Args:
            api_client: qBittorrent API client
            limit: Global connection limit
            peer_limit: Per-torrent peer limit

        Returns:
            True if successful
        """
        try:
            prefs = {
                "connections_limit": limit,
                "max_connec_per_torrent": peer_limit,
            }
            result = api_client.set_preferences(prefs)

            if result and self.logger:
                self.logger.info(f"Applied connection limits: global={limit}, per-torrent={peer_limit}")

            return result

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error applying limits: {e}")
            return False

    def get_optimization_report(self) -> Dict[str, Any]:
        """Get comprehensive optimization report.

        Returns:
            Report dict
        """
        health = self.analyze_connection_health()

        return {
            "health": health,
            "history_samples": len(self.connection_history),
            "error_history_samples": len(self.error_history),
            "recommendation": "Increase limits" if health["status"] == "healthy" else "Reduce limits" if health["status"] == "degraded" else "Investigate",
        }
