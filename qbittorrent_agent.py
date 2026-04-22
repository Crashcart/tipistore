#!/usr/bin/env python3
"""
qBittorrent Intelligent Recovery Agent

Monitors qBittorrent-nox for lag/degradation and automatically applies
recovery strategies while preserving user configurations.
"""

import argparse
import sys
import time
import signal
import logging
from pathlib import Path

from detectors.lag_detector import LagDetector
from recovery.recovery_engine import RecoveryEngine
from qbt_api.api_client import QBittorrentAPIClient
from qbt_api.config_manager import ConfigManager
from logging.agent_logger import setup_logger


class QBittorrentAgent:
    """Main agent class for monitoring and recovering qBittorrent."""

    def __init__(self, args):
        """Initialize the agent with configuration."""
        self.args = args
        self.logger = setup_logger(args.log_level, args.log_file)
        self.running = True

        # Set up signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        # Initialize components
        try:
            self.api_client = QBittorrentAPIClient(
                host="127.0.0.1",
                port=args.qbt_port,
                username=args.qbt_username,
                password=args.qbt_password,
            )
            self.logger.info(f"Connected to qBittorrent on port {args.qbt_port}")
        except Exception as e:
            self.logger.error(f"Failed to connect to qBittorrent: {e}")
            sys.exit(1)

        try:
            self.config_manager = ConfigManager(args.qbt_config_path)
            self.logger.info(f"Loaded qBittorrent config from {args.qbt_config_path}")
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            sys.exit(1)

        self.lag_detector = LagDetector(
            api_client=self.api_client,
            config_manager=self.config_manager,
            sensitivity=args.sensitivity,
            logger=self.logger,
        )

        self.recovery_engine = RecoveryEngine(
            api_client=self.api_client,
            config_manager=self.config_manager,
            logger=self.logger,
        )

    def _handle_shutdown(self, signum, frame):
        """Handle graceful shutdown."""
        self.logger.info("Shutdown signal received")
        self.running = False

    def run(self):
        """Main monitoring loop."""
        self.logger.info("qBittorrent Agent started")
        self.logger.info(
            f"Monitoring interval: {self.args.interval}s, "
            f"Sensitivity: {self.args.sensitivity}"
        )

        try:
            while self.running:
                try:
                    # Detect lag
                    lag_score, lag_details = self.lag_detector.detect_lag()

                    if lag_score > 0:
                        self.logger.warning(
                            f"Lag detected (score: {lag_score:.1f}/100) - {lag_details}"
                        )

                        # Attempt recovery
                        if self.args.dry_run:
                            self.logger.info("[DRY RUN] Would execute recovery strategies")
                            self.logger.info(
                                f"Recovery plan: {self.recovery_engine.get_recovery_plan(lag_score)}"
                            )
                        else:
                            self.recovery_engine.execute_recovery(lag_score)
                    else:
                        self.logger.debug("qBittorrent health normal")

                except Exception as e:
                    self.logger.error(f"Error in monitoring loop: {e}", exc_info=True)

                # Wait for next check
                time.sleep(self.args.interval)

        except KeyboardInterrupt:
            self.logger.info("Interrupted by user")
        finally:
            self.logger.info("qBittorrent Agent stopped")

    @staticmethod
    def create_argument_parser():
        """Create and return argument parser."""
        parser = argparse.ArgumentParser(
            description="qBittorrent Intelligent Recovery Agent",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Basic monitoring with default settings
  %(prog)s --qbt-config ~/.config/qBittorrent/qBittorrent.conf

  # Custom port and sensitivity
  %(prog)s --qbt-config ~/.config/qBittorrent/qBittorrent.conf \\
           --qbt-port 8080 --sensitivity balanced

  # Dry run to see what would happen
  %(prog)s --qbt-config ~/.config/qBittorrent/qBittorrent.conf --dry-run

  # Verbose logging
  %(prog)s --qbt-config ~/.config/qBittorrent/qBittorrent.conf \\
           --log-level DEBUG
            """,
        )

        # qBittorrent API settings
        parser.add_argument(
            "--qbt-config",
            type=str,
            required=True,
            help="Path to qBittorrent config file",
        )
        parser.add_argument(
            "--qbt-port",
            type=int,
            default=8080,
            help="qBittorrent Web API port (default: 8080)",
        )
        parser.add_argument(
            "--qbt-username",
            type=str,
            default="",
            help="qBittorrent Web API username",
        )
        parser.add_argument(
            "--qbt-password",
            type=str,
            default="",
            help="qBittorrent Web API password",
        )

        # Agent settings
        parser.add_argument(
            "--interval",
            type=int,
            default=60,
            help="Monitoring interval in seconds (default: 60)",
        )
        parser.add_argument(
            "--sensitivity",
            type=str,
            choices=["aggressive", "balanced", "conservative"],
            default="balanced",
            help="Lag detection sensitivity: aggressive=sensitive, balanced=medium (default), conservative=tolerant",
        )

        # Logging
        parser.add_argument(
            "--log-level",
            type=str,
            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
            default="INFO",
            help="Logging level (default: INFO)",
        )
        parser.add_argument(
            "--log-file",
            type=str,
            default="/var/log/qbittorrent-agent.log",
            help="Log file path",
        )

        # Operation modes
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--daemon",
            action="store_true",
            help="Run as background daemon",
        )

        return parser


def main():
    """Main entry point."""
    parser = QBittorrentAgent.create_argument_parser()
    args = parser.parse_args()

    # Validate config path exists
    config_path = Path(args.qbt_config)
    if not config_path.exists():
        print(f"Error: qBittorrent config not found: {args.qbt_config}", file=sys.stderr)
        sys.exit(1)

    # Create and run agent
    agent = QBittorrentAgent(args)
    agent.run()


if __name__ == "__main__":
    main()
