"""Prometheus metrics exporter for qBittorrent agent."""

from typing import Dict, Any
import json
from datetime import datetime


class PrometheusExporter:
    """Exports metrics in Prometheus format for monitoring."""

    def __init__(self, logger=None):
        """Initialize Prometheus exporter.

        Args:
            logger: Logger instance
        """
        self.logger = logger
        self.metrics = {}

    def record_metric(self, name: str, value: float, labels: Dict[str, str] = None):
        """Record a metric value.

        Args:
            name: Metric name
            value: Metric value
            labels: Optional label dict
        """
        self.metrics[name] = {
            "value": value,
            "labels": labels or {},
            "timestamp": datetime.utcnow().isoformat(),
        }

    def export_prometheus_format(self) -> str:
        """Export metrics in Prometheus text format.

        Returns:
            Prometheus-formatted metric string
        """
        lines = []

        for metric_name, data in self.metrics.items():
            value = data["value"]
            labels = data["labels"]

            # Format labels
            if labels:
                label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
                line = f"{metric_name}{{{label_str}}} {value}"
            else:
                line = f"{metric_name} {value}"

            lines.append(line)

        return "\n".join(lines) + "\n"

    def export_json_format(self) -> str:
        """Export metrics in JSON format.

        Returns:
            JSON-formatted metrics
        """
        return json.dumps(self.metrics, indent=2, default=str)

    def get_qbittorrent_metrics(self, api_client, lag_detector, system_metrics) -> Dict[str, Any]:
        """Collect qBittorrent metrics from various sources.

        Args:
            api_client: qBittorrent API client
            lag_detector: Lag detector instance
            system_metrics: System metrics instance

        Returns:
            Dict of collected metrics
        """
        metrics = {}

        try:
            # Get server state
            stats = api_client.get_server_state()
            if stats:
                metrics["qbittorrent_download_speed"] = stats.get("dl_info_speed", 0)
                metrics["qbittorrent_upload_speed"] = stats.get("up_info_speed", 0)
                metrics["qbittorrent_peers_connected"] = stats.get("peers", 0)
                metrics["qbittorrent_dht_nodes"] = stats.get("dht_nodes", 0)
                metrics["qbittorrent_torrents_downloading"] = stats.get("nb_dl", 0)
                metrics["qbittorrent_torrents_seeding"] = stats.get("nb_up", 0)

            # Get lag score
            lag_score, _ = lag_detector.detect_lag()
            metrics["qbittorrent_lag_score"] = lag_score

            # Get system metrics
            cpu_percent = system_metrics.get_cpu_percent()
            memory_info = system_metrics.get_memory_info()

            metrics["system_cpu_percent"] = cpu_percent
            metrics["system_memory_percent"] = memory_info["percent"]
            metrics["system_memory_available_mb"] = memory_info["available"] / 1024 / 1024

            # Get preferences
            prefs = api_client.get_preferences()
            if prefs:
                metrics["qbittorrent_dl_limit_bps"] = prefs.get("dl_limit", 0)
                metrics["qbittorrent_ul_limit_bps"] = prefs.get("up_limit", 0)

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error collecting Prometheus metrics: {e}")

        return metrics

    def export_with_metrics(
        self,
        api_client,
        lag_detector,
        system_metrics,
        format_type: str = "prometheus",
    ) -> str:
        """Export metrics with current data.

        Args:
            api_client: qBittorrent API client
            lag_detector: Lag detector instance
            system_metrics: System metrics instance
            format_type: 'prometheus' or 'json'

        Returns:
            Formatted metrics string
        """
        # Collect metrics
        metrics = self.get_qbittorrent_metrics(api_client, lag_detector, system_metrics)

        # Record metrics
        for name, value in metrics.items():
            self.record_metric(name, value)

        # Export in requested format
        if format_type == "json":
            return self.export_json_format()
        else:
            return self.export_prometheus_format()

    @staticmethod
    def get_grafana_dashboard_json() -> Dict[str, Any]:
        """Get sample Grafana dashboard JSON for importing.

        Returns:
            Grafana dashboard dict
        """
        return {
            "dashboard": {
                "title": "qBittorrent Agent Monitoring",
                "tags": ["qbittorrent", "torrent", "monitoring"],
                "timezone": "UTC",
                "panels": [
                    {
                        "title": "Lag Score",
                        "targets": [{"expr": "qbittorrent_lag_score"}],
                        "type": "graph",
                    },
                    {
                        "title": "Download Speed",
                        "targets": [{"expr": "qbittorrent_download_speed"}],
                        "type": "graph",
                    },
                    {
                        "title": "Upload Speed",
                        "targets": [{"expr": "qbittorrent_upload_speed"}],
                        "type": "graph",
                    },
                    {
                        "title": "Connected Peers",
                        "targets": [{"expr": "qbittorrent_peers_connected"}],
                        "type": "graph",
                    },
                    {
                        "title": "System CPU %",
                        "targets": [{"expr": "system_cpu_percent"}],
                        "type": "graph",
                    },
                    {
                        "title": "System Memory %",
                        "targets": [{"expr": "system_memory_percent"}],
                        "type": "graph",
                    },
                ],
            }
        }
