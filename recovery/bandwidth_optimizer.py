"""Bandwidth optimization and smart throttling."""

from typing import Dict, Any, Optional
from collections import deque


class BandwidthOptimizer:
    """Optimizes bandwidth limits based on system capacity and usage."""

    def __init__(self, api_client, system_metrics, logger=None):
        """Initialize bandwidth optimizer.

        Args:
            api_client: qBittorrent API client
            system_metrics: SystemMetrics instance
            logger: Logger instance
        """
        self.api_client = api_client
        self.system_metrics = system_metrics
        self.logger = logger

        # Bandwidth history (keep last 100 measurements)
        self.bandwidth_history = deque(maxlen=100)

        # Thresholds
        self.cpu_threshold = 75  # %
        self.memory_threshold = 85  # %
        self.network_saturation_threshold = 80  # % of interface capacity

    def optimize_bandwidth(self) -> Dict[str, Any]:
        """Optimize bandwidth limits based on current system state.

        Returns:
            Dict with optimization results
        """
        try:
            # Get current system state
            cpu_percent = self.system_metrics.get_cpu_percent()
            memory_info = self.system_metrics.get_memory_info()
            current_prefs = self.api_client.get_preferences()

            if not current_prefs:
                return {"success": False, "reason": "Could not get preferences"}

            # Get current bandwidth settings
            current_dl_limit = current_prefs.get("dl_limit", 0)  # bytes/s
            current_ul_limit = current_prefs.get("up_limit", 0)  # bytes/s

            # Calculate recommended limits
            recommendations = self._calculate_optimal_limits(
                cpu_percent,
                memory_info,
                current_dl_limit,
                current_ul_limit,
            )

            # Apply recommendations if significant improvement
            applied = False
            if recommendations["should_apply"]:
                self._apply_limits(
                    recommendations["recommended_dl_limit"],
                    recommendations["recommended_ul_limit"],
                )
                applied = True

                if self.logger:
                    self.logger.info(
                        f"Bandwidth adjusted: DL={recommendations['recommended_dl_limit']}/s, "
                        f"UL={recommendations['recommended_ul_limit']}/s"
                    )

            return {
                "success": True,
                "current_dl_limit": current_dl_limit,
                "current_ul_limit": current_ul_limit,
                "recommended_dl_limit": recommendations["recommended_dl_limit"],
                "recommended_ul_limit": recommendations["recommended_ul_limit"],
                "cpu_percent": cpu_percent,
                "memory_percent": memory_info["percent"],
                "applied": applied,
                "reason": recommendations["reason"],
            }

        except Exception as e:
            if self.logger:
                self.logger.error(f"Bandwidth optimization error: {e}")
            return {"success": False, "reason": str(e)}

    def _calculate_optimal_limits(
        self,
        cpu_percent: float,
        memory_info: Dict[str, Any],
        current_dl: int,
        current_ul: int,
    ) -> Dict[str, Any]:
        """Calculate optimal bandwidth limits.

        Args:
            cpu_percent: Current CPU usage %
            memory_info: Memory info dict
            current_dl: Current download limit (bytes/s)
            current_ul: Current upload limit (bytes/s)

        Returns:
            Recommendations dict
        """
        # Start with current limits
        recommended_dl = current_dl
        recommended_ul = current_ul

        reason = "Current limits appropriate"
        should_apply = False

        # If CPU is high, reduce bandwidth
        if cpu_percent > self.cpu_threshold:
            reduction_factor = 0.8  # Reduce to 80%
            recommended_dl = int(current_dl * reduction_factor) if current_dl > 0 else 0
            recommended_ul = int(current_ul * reduction_factor) if current_ul > 0 else 0
            reason = f"CPU high ({cpu_percent:.1f}%), reducing bandwidth"
            should_apply = True

        # If memory is high, reduce bandwidth
        elif memory_info["percent"] > self.memory_threshold:
            reduction_factor = 0.7  # Reduce to 70%
            recommended_dl = int(current_dl * reduction_factor) if current_dl > 0 else 0
            recommended_ul = int(current_ul * reduction_factor) if current_ul > 0 else 0
            reason = f"Memory high ({memory_info['percent']:.1f}%), reducing bandwidth"
            should_apply = True

        # If both are low, try to increase bandwidth
        elif cpu_percent < 40 and memory_info["percent"] < 60:
            increase_factor = 1.1  # Increase to 110%
            recommended_dl = int(current_dl * increase_factor) if current_dl > 0 else current_dl
            recommended_ul = int(current_ul * increase_factor) if current_ul > 0 else current_ul
            reason = "System headroom available, slightly increasing bandwidth"
            should_apply = recommended_dl > current_dl or recommended_ul > current_ul

        return {
            "recommended_dl_limit": recommended_dl,
            "recommended_ul_limit": recommended_ul,
            "should_apply": should_apply,
            "reason": reason,
        }

    def _apply_limits(self, dl_limit: int, ul_limit: int) -> bool:
        """Apply bandwidth limits to qBittorrent.

        Args:
            dl_limit: Download limit in bytes/s
            ul_limit: Upload limit in bytes/s

        Returns:
            True if successful
        """
        try:
            prefs = {
                "dl_limit": dl_limit,
                "up_limit": ul_limit,
            }
            return self.api_client.set_preferences(prefs)
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to apply bandwidth limits: {e}")
            return False

    def get_bandwidth_efficiency(self) -> Dict[str, Any]:
        """Calculate bandwidth efficiency metrics.

        Returns:
            Efficiency metrics dict
        """
        try:
            prefs = self.api_client.get_preferences()
            stats = self.api_client.get_server_state()

            if not (prefs and stats):
                return {}

            dl_limit = prefs.get("dl_limit", 0)
            ul_limit = prefs.get("up_limit", 0)
            actual_dl = stats.get("dl_info_speed", 0)
            actual_ul = stats.get("up_info_speed", 0)

            # Calculate efficiency
            dl_efficiency = (actual_dl / dl_limit * 100) if dl_limit > 0 else 0
            ul_efficiency = (actual_ul / ul_limit * 100) if ul_limit > 0 else 0

            return {
                "dl_limit": dl_limit,
                "ul_limit": ul_limit,
                "actual_dl": actual_dl,
                "actual_ul": actual_ul,
                "dl_efficiency_percent": min(100, dl_efficiency),
                "ul_efficiency_percent": min(100, ul_efficiency),
                "is_throttled": dl_efficiency > 95 or ul_efficiency > 95,
            }

        except Exception as e:
            if self.logger:
                self.logger.debug(f"Could not calculate efficiency: {e}")
            return {}

    def suggest_optimal_limits(self) -> Dict[str, Any]:
        """Suggest optimal bandwidth limits based on historical data.

        Returns:
            Suggestion dict
        """
        if not self.bandwidth_history:
            return {"suggestion": "Insufficient data", "reason": "No history yet"}

        # Analyze history
        avg_cpu = sum(h["cpu"] for h in self.bandwidth_history) / len(self.bandwidth_history)
        avg_dl = sum(h["dl_actual"] for h in self.bandwidth_history) / len(self.bandwidth_history)

        # Calculate recommended limit (add 10% buffer to average)
        recommended = int(avg_dl * 1.1)

        return {
            "recommended_limit": recommended,
            "average_actual": avg_dl,
            "average_cpu": avg_cpu,
            "reason": "Based on historical usage patterns",
        }
