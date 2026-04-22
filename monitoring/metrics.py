"""System metrics collection."""

import psutil
from typing import Dict, Any


class SystemMetrics:
    """Collects system metrics."""

    @staticmethod
    def get_cpu_percent(interval: float = 1.0) -> float:
        """Get CPU usage percentage.

        Args:
            interval: Measurement interval in seconds

        Returns:
            CPU usage percentage
        """
        return psutil.cpu_percent(interval=interval)

    @staticmethod
    def get_memory_info() -> Dict[str, Any]:
        """Get memory information.

        Returns:
            Memory info dict
        """
        memory = psutil.virtual_memory()
        return {
            "total": memory.total,
            "available": memory.available,
            "percent": memory.percent,
            "used": memory.used,
        }

    @staticmethod
    def get_disk_info(path: str = "/") -> Dict[str, Any]:
        """Get disk information.

        Args:
            path: Disk path

        Returns:
            Disk info dict
        """
        disk = psutil.disk_usage(path)
        return {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
        }

    @staticmethod
    def get_network_info() -> Dict[str, Any]:
        """Get network information.

        Returns:
            Network info dict
        """
        net = psutil.net_io_counters()
        return {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
        }

    @staticmethod
    def get_process_info(pid: int) -> Dict[str, Any]:
        """Get process information.

        Args:
            pid: Process ID

        Returns:
            Process info dict or empty dict if not found
        """
        try:
            process = psutil.Process(pid)
            return {
                "pid": pid,
                "name": process.name(),
                "cpu_percent": process.cpu_percent(),
                "memory_percent": process.memory_percent(),
                "memory_info": dict(process.memory_info()._asdict()),
            }
        except psutil.NoSuchProcess:
            return {}
