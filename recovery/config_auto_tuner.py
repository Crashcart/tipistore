"""Automatic configuration tuning based on system specs."""

from typing import Dict, List, Any, Optional
import multiprocessing
import psutil


class ConfigAutoTuner:
    """Analyzes system specs and suggests optimal qBittorrent settings."""

    def __init__(self, logger=None):
        """Initialize config auto tuner.

        Args:
            logger: Logger instance
        """
        self.logger = logger
        self.system_specs = self._get_system_specs()

    def _get_system_specs(self) -> Dict[str, Any]:
        """Get system specifications.

        Returns:
            Dict with system specs
        """
        cpu_count = multiprocessing.cpu_count()
        memory = psutil.virtual_memory()
        disk_partitions = psutil.disk_partitions()

        return {
            "cpu_cores": cpu_count,
            "memory_total_gb": memory.total / (1024**3),
            "memory_available_gb": memory.available / (1024**3),
            "disk_partitions": len(disk_partitions),
        }

    def get_system_specs(self) -> Dict[str, Any]:
        """Get current system specifications.

        Returns:
            System specs dict
        """
        return self.system_specs

    def suggest_connection_limits(self) -> Dict[str, int]:
        """Suggest connection limits based on memory.

        Returns:
            Dict with 'global_limit' and 'peer_limit'
        """
        memory_gb = self.system_specs["memory_total_gb"]

        # Heuristic: 1 connection ≈ 1-2MB memory
        # Reserve 50% for OS and other processes
        usable_memory_gb = memory_gb * 0.5

        # Conservative: 1MB per connection
        global_limit = int(usable_memory_gb * 1024)
        global_limit = min(max(global_limit, 100), 3000)

        # Per-torrent limit is typically 20-30% of global
        peer_limit = max(100, int(global_limit * 0.25))
        peer_limit = min(peer_limit, 600)

        if self.logger:
            self.logger.debug(
                f"Suggested limits: global={global_limit}, per-torrent={peer_limit}"
            )

        return {"global_limit": global_limit, "peer_limit": peer_limit}

    def suggest_bandwidth_limits(self) -> Dict[str, int]:
        """Suggest bandwidth limits based on system specs.

        Returns:
            Dict with 'upload_limit' and 'download_limit' in KiB/s
        """
        cpu_cores = self.system_specs["cpu_cores"]

        # Use available cores as proxy for bandwidth capacity
        # ~50 MiB/s per core is reasonable for typical hardware
        # But cap at reasonable limits
        estimated_download_kbps = cpu_cores * 50 * 1024
        estimated_upload_kbps = cpu_cores * 10 * 1024

        # Suggest slightly conservative to avoid saturation
        download_limit = int(estimated_download_kbps * 0.8)
        upload_limit = int(estimated_upload_kbps * 0.8)

        if self.logger:
            self.logger.debug(
                f"Suggested bandwidth: down={download_limit} KiB/s, up={upload_limit} KiB/s"
            )

        return {"download_limit": download_limit, "upload_limit": upload_limit}

    def suggest_cache_settings(self) -> Dict[str, int]:
        """Suggest cache settings based on memory.

        Returns:
            Dict with cache size recommendations
        """
        memory_gb = self.system_specs["memory_total_gb"]

        # Allocate 5-10% of RAM for disk cache
        cache_mb = int((memory_gb * 0.07) * 1024)
        cache_mb = max(64, min(cache_mb, 2048))

        if self.logger:
            self.logger.debug(f"Suggested cache size: {cache_mb} MiB")

        return {"disk_cache_mb": cache_mb}

    def suggest_active_torrents(self) -> Dict[str, int]:
        """Suggest max active torrents based on CPU cores.

        Returns:
            Dict with 'max_active_torrents'
        """
        cpu_cores = self.system_specs["cpu_cores"]

        # Heuristic: ~10 torrents per CPU core
        max_active = cpu_cores * 10
        max_active = min(max_active, 200)

        if self.logger:
            self.logger.debug(f"Suggested active torrents: {max_active}")

        return {"max_active_torrents": max_active}

    def suggest_piece_size(self) -> Dict[str, int]:
        """Suggest piece size based on disk I/O capacity.

        Returns:
            Dict with 'piece_size_bytes'
        """
        # Larger piece size (16-32MB) for faster disk I/O
        # Smaller piece size (4-8MB) for slower disk I/O
        cpu_cores = self.system_specs["cpu_cores"]

        if cpu_cores >= 8:
            piece_size_mb = 32
        elif cpu_cores >= 4:
            piece_size_mb = 16
        else:
            piece_size_mb = 8

        if self.logger:
            self.logger.debug(f"Suggested piece size: {piece_size_mb} MiB")

        return {"piece_size_mb": piece_size_mb}

    def get_tuning_recommendations(self) -> Dict[str, Any]:
        """Get all tuning recommendations.

        Returns:
            Comprehensive tuning recommendations
        """
        return {
            "system_specs": self.system_specs,
            "connection_limits": self.suggest_connection_limits(),
            "bandwidth_limits": self.suggest_bandwidth_limits(),
            "cache_settings": self.suggest_cache_settings(),
            "active_torrents": self.suggest_active_torrents(),
            "piece_size": self.suggest_piece_size(),
            "rationale": {
                "connection_limits": "Based on available memory (50% usable)",
                "bandwidth_limits": f"Based on CPU cores ({self.system_specs['cpu_cores']} cores)",
                "cache_settings": "5-10% of total RAM",
                "active_torrents": "~10 per CPU core",
                "piece_size": "Larger for more cores, smaller for resource-constrained systems",
            },
        }

    def compare_with_current(
        self, current_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compare current config with recommendations.

        Args:
            current_config: Current qBittorrent config dict

        Returns:
            Comparison report
        """
        recommendations = self.get_tuning_recommendations()
        comparison = {
            "recommendations": recommendations,
            "differences": {},
        }

        # Compare connection limits
        current_global = current_config.get("connections_limit", 0)
        suggested_global = recommendations["connection_limits"]["global_limit"]
        if current_global != suggested_global:
            comparison["differences"]["connection_limit"] = {
                "current": current_global,
                "suggested": suggested_global,
                "delta": suggested_global - current_global,
            }

        # Compare peer limits
        current_peer = current_config.get("max_connec_per_torrent", 0)
        suggested_peer = recommendations["connection_limits"]["peer_limit"]
        if current_peer != suggested_peer:
            comparison["differences"]["peer_limit"] = {
                "current": current_peer,
                "suggested": suggested_peer,
                "delta": suggested_peer - current_peer,
            }

        if self.logger:
            self.logger.info(f"Configuration comparison: {len(comparison['differences'])} differences found")

        return comparison
