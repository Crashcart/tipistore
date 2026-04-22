"""Lag detection analysis for qBittorrent."""

import time
from typing import Tuple, Dict, Any
from collections import deque

from monitoring.metrics import SystemMetrics


class LagDetector:
    """Detects qBittorrent lag through multi-factor analysis."""

    def __init__(self, api_client, config_manager, sensitivity="balanced", logger=None):
        """Initialize lag detector.

        Args:
            api_client: QBittorrent API client
            config_manager: Configuration manager
            sensitivity: Detection sensitivity ('aggressive', 'balanced', 'conservative')
            logger: Logger instance
        """
        self.api_client = api_client
        self.config_manager = config_manager
        self.sensitivity = sensitivity
        self.logger = logger

        # Thresholds based on sensitivity
        self.thresholds = self._get_thresholds(sensitivity)

        # Historical data for trend analysis (5-minute rolling window)
        self.metrics_history = deque(maxlen=30)  # 30 samples at 10s intervals
        self.system_metrics = SystemMetrics()

    def _get_thresholds(self, sensitivity: str) -> Dict[str, float]:
        """Get lag thresholds based on sensitivity level.

        Args:
            sensitivity: 'aggressive', 'balanced', or 'conservative'

        Returns:
            Dict of threshold values
        """
        thresholds = {
            "aggressive": {
                "speed_drop_percent": 10,  # Alert at 10% drop
                "cpu_threshold": 60,  # %
                "memory_threshold": 70,  # %
                "peer_drop_percent": 30,  # Alert when peer count drops 30%
                "dht_drop_percent": 40,  # Alert when DHT nodes drop 40%
                "connection_count_min": 50,
            },
            "balanced": {
                "speed_drop_percent": 20,  # Alert at 20% drop
                "cpu_threshold": 70,  # %
                "memory_threshold": 80,  # %
                "peer_drop_percent": 40,  # Alert when peer count drops 40%
                "dht_drop_percent": 50,  # Alert when DHT nodes drop 50%
                "connection_count_min": 30,
            },
            "conservative": {
                "speed_drop_percent": 35,  # Alert at 35% drop
                "cpu_threshold": 85,  # %
                "memory_threshold": 90,  # %
                "peer_drop_percent": 60,  # Alert when peer count drops 60%
                "dht_drop_percent": 70,  # Alert when DHT nodes drop 70%
                "connection_count_min": 10,
            },
        }
        return thresholds.get(sensitivity, thresholds["balanced"])

    def detect_lag(self) -> Tuple[float, str]:
        """Detect lag in qBittorrent.

        Returns:
            Tuple of (lag_score: 0-100, description: str)
        """
        try:
            lag_score = 0.0
            issues = []

            # 1. Performance metrics
            perf_score, perf_issues = self._check_performance()
            lag_score += perf_score
            issues.extend(perf_issues)

            # 2. System health
            health_score, health_issues = self._check_system_health()
            lag_score += health_score
            issues.extend(health_issues)

            # 3. Configuration validation
            config_score, config_issues = self._check_configuration()
            lag_score += config_score
            issues.extend(config_issues)

            # 4. Log analysis
            log_score, log_issues = self._analyze_logs()
            lag_score += log_score
            issues.extend(log_issues)

            # 5. Trend analysis
            trend_score, trend_issues = self._analyze_trends()
            lag_score += trend_score
            issues.extend(trend_issues)

            # Normalize to 0-100
            lag_score = min(100.0, lag_score)

            description = "; ".join(issues[:3]) if issues else "All systems normal"

            return lag_score, description

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error detecting lag: {e}")
            return 0.0, "Detection error"

    def _check_performance(self) -> Tuple[float, list]:
        """Check performance metrics (speed, peers, DHT).

        Returns:
            Tuple of (score: 0-30, issues: list)
        """
        score = 0.0
        issues = []

        try:
            stats = self.api_client.get_server_state()
            if not stats:
                return 0.0, []

            # Check download/upload speed
            baseline_speed = 1024 * 1024  # 1 MB/s baseline
            current_speed = (stats.get("dl_info_speed", 0) + stats.get("up_info_speed", 0)) / 2

            if current_speed < baseline_speed * (1 - self.thresholds["speed_drop_percent"] / 100):
                speed_drop = 100 - (current_speed / baseline_speed * 100)
                score += min(15, speed_drop / 5)
                issues.append(f"Speed drop: {speed_drop:.0f}%")

            # Check peer count
            peer_count = stats.get("peers", 0)
            if peer_count < self.thresholds["connection_count_min"]:
                score += 10
                issues.append(f"Low peer count: {peer_count}")

            # Check DHT nodes
            dht_nodes = stats.get("dht_nodes", 0)
            baseline_dht = 100  # Reasonable DHT node count
            if dht_nodes < baseline_dht * (1 - self.thresholds["dht_drop_percent"] / 100):
                dht_drop = 100 - (dht_nodes / baseline_dht * 100)
                score += min(5, dht_drop / 10)
                issues.append(f"DHT degradation: {dht_drop:.0f}%")

        except Exception as e:
            if self.logger:
                self.logger.debug(f"Performance check error: {e}")

        return score, issues

    def _check_system_health(self) -> Tuple[float, list]:
        """Check system health (CPU, memory, disk I/O).

        Returns:
            Tuple of (score: 0-25, issues: list)
        """
        score = 0.0
        issues = []

        try:
            cpu_percent = self.system_metrics.get_cpu_percent()
            memory_info = self.system_metrics.get_memory_info()

            # CPU check
            if cpu_percent > self.thresholds["cpu_threshold"]:
                cpu_excess = cpu_percent - self.thresholds["cpu_threshold"]
                score += min(10, cpu_excess / 2)
                issues.append(f"High CPU: {cpu_percent:.0f}%")

            # Memory check
            if memory_info["percent"] > self.thresholds["memory_threshold"]:
                mem_excess = memory_info["percent"] - self.thresholds["memory_threshold"]
                score += min(15, mem_excess / 1)
                issues.append(f"High memory: {memory_info['percent']:.0f}%")

        except Exception as e:
            if self.logger:
                self.logger.debug(f"System health check error: {e}")

        return score, issues

    def _check_configuration(self) -> Tuple[float, list]:
        """Check qBittorrent configuration validity.

        Returns:
            Tuple of (score: 0-15, issues: list)
        """
        score = 0.0
        issues = []

        try:
            config = self.config_manager.get_config()

            # Check for common issues
            if config.get("network", {}).get("port", 0) <= 0:
                score += 5
                issues.append("Invalid listening port")

            if config.get("network", {}).get("upnp", False) is False:
                # UPnP disabled might cause connectivity issues
                pass  # Not an error, just informational

        except Exception as e:
            if self.logger:
                self.logger.debug(f"Configuration check error: {e}")

        return score, issues

    def _analyze_logs(self) -> Tuple[float, list]:
        """Analyze qBittorrent logs for errors.

        Returns:
            Tuple of (score: 0-20, issues: list)
        """
        score = 0.0
        issues = []

        try:
            # This would parse qBittorrent logs
            # For now, placeholder implementation
            pass

        except Exception as e:
            if self.logger:
                self.logger.debug(f"Log analysis error: {e}")

        return score, issues

    def _analyze_trends(self) -> Tuple[float, list]:
        """Analyze performance trends (5-minute rolling window).

        Returns:
            Tuple of (score: 0-10, issues: list)
        """
        score = 0.0
        issues = []

        try:
            # Get current metrics
            stats = self.api_client.get_server_state()
            if not stats:
                return 0.0, []

            # Store in history
            current_metric = {"timestamp": time.time(), "speed": stats.get("dl_info_speed", 0)}
            self.metrics_history.append(current_metric)

            # Analyze if we have enough history
            if len(self.metrics_history) > 5:
                recent = [m["speed"] for m in list(self.metrics_history)[-5:]]
                older = [m["speed"] for m in list(self.metrics_history)[-10:-5]]

                if older:
                    recent_avg = sum(recent) / len(recent)
                    older_avg = sum(older) / len(older)

                    if older_avg > 0:
                        trend_drop = 100 - (recent_avg / older_avg * 100)
                        if trend_drop > 20:
                            score += min(10, trend_drop / 5)
                            issues.append(f"Speed degrading: {trend_drop:.0f}% drop")

        except Exception as e:
            if self.logger:
                self.logger.debug(f"Trend analysis error: {e}")

        return score, issues
