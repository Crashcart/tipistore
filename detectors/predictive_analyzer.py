"""Predictive analysis to warn before lag occurs."""

from typing import Dict, List, Tuple, Any
from collections import deque
import statistics


class PredictiveAnalyzer:
    """Analyzes trends to predict lag before it occurs."""

    def __init__(self, history_window: int = 60, logger=None):
        """Initialize predictive analyzer.

        Args:
            history_window: Number of measurements to keep in history
            logger: Logger instance
        """
        self.logger = logger
        self.history_window = history_window

        # Keep historical data
        self.speed_history = deque(maxlen=history_window)
        self.peer_history = deque(maxlen=history_window)
        self.cpu_history = deque(maxlen=history_window)
        self.memory_history = deque(maxlen=history_window)

        # Thresholds
        self.speed_drop_threshold = 0.3  # Alert if speed drops 30% in trend
        self.peer_drop_threshold = 0.4  # Alert if peers drop 40%
        self.cpu_rise_threshold = 0.2  # Alert if CPU rises 20%

    def add_measurement(self, measurement: Dict[str, float]):
        """Add a measurement to history.

        Args:
            measurement: Dict with keys like 'speed', 'peers', 'cpu', 'memory'
        """
        self.speed_history.append(measurement.get("speed", 0))
        self.peer_history.append(measurement.get("peers", 0))
        self.cpu_history.append(measurement.get("cpu", 0))
        self.memory_history.append(measurement.get("memory", 0))

    def predict_lag(self) -> Tuple[float, List[str]]:
        """Predict if lag will occur based on trends.

        Returns:
            Tuple of (prediction_score: 0-100, warnings: list)
        """
        warnings = []
        prediction_score = 0.0

        if len(self.speed_history) < 10:
            # Need sufficient history
            return 0.0, ["Insufficient data for prediction"]

        # Analyze speed trend
        speed_warning, speed_score = self._analyze_speed_trend()
        if speed_warning:
            warnings.append(speed_warning)
            prediction_score += speed_score

        # Analyze peer trend
        peer_warning, peer_score = self._analyze_peer_trend()
        if peer_warning:
            warnings.append(peer_warning)
            prediction_score += peer_score

        # Analyze CPU trend
        cpu_warning, cpu_score = self._analyze_cpu_trend()
        if cpu_warning:
            warnings.append(cpu_warning)
            prediction_score += cpu_score

        # Analyze memory trend
        mem_warning, mem_score = self._analyze_memory_trend()
        if mem_warning:
            warnings.append(mem_warning)
            prediction_score += mem_score

        # Normalize score
        prediction_score = min(100.0, prediction_score)

        return prediction_score, warnings

    def _analyze_speed_trend(self) -> Tuple[str, float]:
        """Analyze download speed trend.

        Returns:
            Tuple of (warning: str or None, score: 0-25)
        """
        if len(self.speed_history) < 5:
            return None, 0.0

        # Split into recent and older windows
        recent = list(self.speed_history)[-5:]
        older = list(self.speed_history)[-10:-5] if len(self.speed_history) >= 10 else recent

        recent_avg = statistics.mean(recent)
        older_avg = statistics.mean(older)

        if older_avg == 0:
            return None, 0.0

        # Calculate drop percentage
        drop_percent = 1.0 - (recent_avg / older_avg)

        if drop_percent > self.speed_drop_threshold:
            return (
                f"Speed degrading: {drop_percent*100:.1f}% drop detected",
                min(25.0, drop_percent * 50),
            )

        return None, 0.0

    def _analyze_peer_trend(self) -> Tuple[str, float]:
        """Analyze peer count trend.

        Returns:
            Tuple of (warning: str or None, score: 0-20)
        """
        if len(self.peer_history) < 5:
            return None, 0.0

        recent = list(self.peer_history)[-5:]
        older = list(self.peer_history)[-10:-5] if len(self.peer_history) >= 10 else recent

        recent_avg = statistics.mean(recent)
        older_avg = statistics.mean(older)

        if older_avg == 0:
            return None, 0.0

        drop_percent = 1.0 - (recent_avg / older_avg)

        if drop_percent > self.peer_drop_threshold:
            return (
                f"Peer availability declining: {drop_percent*100:.1f}% drop",
                min(20.0, drop_percent * 40),
            )

        return None, 0.0

    def _analyze_cpu_trend(self) -> Tuple[str, float]:
        """Analyze CPU trend.

        Returns:
            Tuple of (warning: str or None, score: 0-20)
        """
        if len(self.cpu_history) < 5:
            return None, 0.0

        recent = list(self.cpu_history)[-5:]
        older = list(self.cpu_history)[-10:-5] if len(self.cpu_history) >= 10 else recent

        recent_avg = statistics.mean(recent)
        older_avg = statistics.mean(older)

        rise_percent = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0

        if rise_percent > self.cpu_rise_threshold:
            return (
                f"CPU usage rising: {rise_percent*100:.1f}% increase",
                min(20.0, rise_percent * 50),
            )

        return None, 0.0

    def _analyze_memory_trend(self) -> Tuple[str, float]:
        """Analyze memory trend.

        Returns:
            Tuple of (warning: str or None, score: 0-15)
        """
        if len(self.memory_history) < 5:
            return None, 0.0

        recent = list(self.memory_history)[-5:]

        avg_memory = statistics.mean(recent)
        if avg_memory > 85:
            return (
                f"Memory usage high: {avg_memory:.1f}%",
                min(15.0, (avg_memory - 80) * 3),
            )

        return None, 0.0

    def get_trend_report(self) -> Dict[str, Any]:
        """Get detailed trend report.

        Returns:
            Trend analysis report
        """
        report = {
            "prediction_score": 0.0,
            "warnings": [],
            "trends": {},
        }

        if len(self.speed_history) < 5:
            report["status"] = "Insufficient data"
            return report

        # Speed trend
        recent_speed = list(self.speed_history)[-5:]
        speed_trend = "stable"
        if recent_speed[-1] < statistics.mean(recent_speed[:-1]):
            speed_trend = "declining"
        else:
            speed_trend = "improving"

        report["trends"]["speed"] = {
            "current": recent_speed[-1],
            "average": statistics.mean(recent_speed),
            "trend": speed_trend,
        }

        # Peer trend
        recent_peers = list(self.peer_history)[-5:]
        report["trends"]["peers"] = {
            "current": recent_peers[-1],
            "average": statistics.mean(recent_peers),
        }

        # CPU trend
        recent_cpu = list(self.cpu_history)[-5:]
        report["trends"]["cpu"] = {
            "current": recent_cpu[-1],
            "average": statistics.mean(recent_cpu),
        }

        # Get prediction
        pred_score, warnings = self.predict_lag()
        report["prediction_score"] = pred_score
        report["warnings"] = warnings
        report["status"] = "normal" if pred_score < 30 else "warning" if pred_score < 60 else "critical"

        return report
