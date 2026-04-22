"""Docker container integration and management."""

from typing import Dict, List, Any, Optional
import subprocess
import json


class DockerContainerManager:
    """Manages qBittorrent agent in Docker containers."""

    def __init__(self, logger=None):
        """Initialize Docker manager.

        Args:
            logger: Logger instance
        """
        self.logger = logger
        self.containers: Dict[str, Dict[str, Any]] = {}

    def check_docker_available(self) -> bool:
        """Check if Docker is available.

        Returns:
            True if Docker is installed and running
        """
        try:
            subprocess.run(
                ["docker", "version"],
                capture_output=True,
                timeout=5,
            )
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Docker not available: {e}")
            return False

    def build_agent_image(
        self,
        dockerfile_path: str,
        image_name: str = "qbittorrent-agent",
        tag: str = "latest",
    ) -> bool:
        """Build Docker image for agent.

        Args:
            dockerfile_path: Path to Dockerfile
            image_name: Name for the image
            tag: Image tag

        Returns:
            True if build successful
        """
        try:
            full_image_name = f"{image_name}:{tag}"

            result = subprocess.run(
                ["docker", "build", "-t", full_image_name, "-f", dockerfile_path, "."],
                capture_output=True,
                timeout=600,
            )

            if result.returncode == 0:
                if self.logger:
                    self.logger.info(f"Built Docker image: {full_image_name}")
                return True
            else:
                if self.logger:
                    self.logger.error(f"Docker build failed: {result.stderr.decode()}")
                return False

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error building Docker image: {e}")
            return False

    def run_agent_container(
        self,
        image_name: str,
        container_name: str,
        qbt_host: str = "localhost",
        qbt_port: int = 8080,
        agent_port: int = 8081,
        environment_vars: Dict[str, str] = None,
    ) -> bool:
        """Run agent in Docker container.

        Args:
            image_name: Docker image to run
            container_name: Name for container
            qbt_host: qBittorrent host
            qbt_port: qBittorrent port
            agent_port: Agent metrics port
            environment_vars: Optional environment variables

        Returns:
            True if container started
        """
        try:
            cmd = [
                "docker",
                "run",
                "-d",
                "--name",
                container_name,
                "--network",
                "host",
                "-e",
                f"QBT_HOST={qbt_host}",
                "-e",
                f"QBT_PORT={qbt_port}",
                "-e",
                f"AGENT_PORT={agent_port}",
            ]

            if environment_vars:
                for key, value in environment_vars.items():
                    cmd.extend(["-e", f"{key}={value}"])

            cmd.append(image_name)

            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=30,
            )

            if result.returncode == 0:
                container_id = result.stdout.decode().strip()
                self.containers[container_name] = {
                    "id": container_id,
                    "image": image_name,
                    "status": "running",
                }

                if self.logger:
                    self.logger.info(f"Started container: {container_name} ({container_id})")

                return True
            else:
                if self.logger:
                    self.logger.error(f"Container start failed: {result.stderr.decode()}")
                return False

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error starting container: {e}")
            return False

    def stop_container(self, container_name: str) -> bool:
        """Stop a running container.

        Args:
            container_name: Container to stop

        Returns:
            True if stopped
        """
        try:
            result = subprocess.run(
                ["docker", "stop", container_name],
                capture_output=True,
                timeout=30,
            )

            if result.returncode == 0:
                if container_name in self.containers:
                    self.containers[container_name]["status"] = "stopped"

                if self.logger:
                    self.logger.info(f"Stopped container: {container_name}")

                return True
            else:
                if self.logger:
                    self.logger.error(f"Failed to stop container: {result.stderr.decode()}")
                return False

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error stopping container: {e}")
            return False

    def get_container_logs(self, container_name: str, lines: int = 100) -> str:
        """Get logs from container.

        Args:
            container_name: Container name
            lines: Number of log lines

        Returns:
            Container logs
        """
        try:
            result = subprocess.run(
                ["docker", "logs", "--tail", str(lines), container_name],
                capture_output=True,
                timeout=10,
            )

            if result.returncode == 0:
                return result.stdout.decode()
            else:
                return f"Error getting logs: {result.stderr.decode()}"

        except Exception as e:
            return f"Error: {e}"

    def get_container_stats(self, container_name: str) -> Optional[Dict[str, Any]]:
        """Get resource stats for container.

        Args:
            container_name: Container name

        Returns:
            Stats dict or None
        """
        try:
            result = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "json", container_name],
                capture_output=True,
                timeout=10,
            )

            if result.returncode == 0:
                stats = json.loads(result.stdout.decode())
                return stats
            else:
                return None

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error getting stats: {e}")
            return None

    def compose_deployment(self, config: Dict[str, Any]) -> str:
        """Generate docker-compose.yml for deployment.

        Args:
            config: Deployment configuration

        Returns:
            YAML content
        """
        compose = f"""version: '3.8'

services:
  qbittorrent-agent:
    image: {config.get('image', 'qbittorrent-agent:latest')}
    container_name: {config.get('container_name', 'qbittorrent-agent')}
    network_mode: host
    environment:
      - QBT_HOST={config.get('qbt_host', 'localhost')}
      - QBT_PORT={config.get('qbt_port', 8080)}
      - AGENT_PORT={config.get('agent_port', 8081)}
      - LOG_LEVEL={config.get('log_level', 'INFO')}
      - SENSITIVITY={config.get('sensitivity', 'balanced')}
    volumes:
      - /var/lib/qbittorrent-agent:/var/lib/qbittorrent-agent
      - /etc/qbittorrent:/etc/qbittorrent:ro
    restart_policy:
      condition: on-failure
      delay: 10s
      max_attempts: 3
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8081/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
"""

        if config.get('enable_metrics', False):
            compose += """
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
    ports:
      - "9090:9090"
    depends_on:
      - qbittorrent-agent
"""

        return compose

    def get_deployment_status(self) -> Dict[str, Any]:
        """Get status of deployed containers.

        Returns:
            Status report
        """
        return {
            "docker_available": self.check_docker_available(),
            "containers": self.containers,
            "total_containers": len(self.containers),
        }
