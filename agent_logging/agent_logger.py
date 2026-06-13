"""Agent logging configuration."""

import logging
import logging.handlers
from pathlib import Path


def setup_logger(log_level: str = "INFO", log_file: str = "/var/log/qbittorrent-agent.log") -> logging.Logger:
    """Set up logger for the agent.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Path to log file

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("qbittorrent_agent")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Create formatters
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    try:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not create file handler: {e}")

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
