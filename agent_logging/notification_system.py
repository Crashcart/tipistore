"""Notification system for alerts and important events."""

from typing import Dict, List, Any, Optional
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
import subprocess
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


class NotificationLevel(Enum):
    """Notification severity levels."""

    DEBUG = 0
    INFO = 1
    WARNING = 2
    CRITICAL = 3


@dataclass
class Notification:
    """Single notification event."""

    level: NotificationLevel
    title: str
    message: str
    timestamp: datetime = None
    tags: List[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.tags is None:
            self.tags = []


class EmailNotifier:
    """Send notifications via email."""

    def __init__(self, smtp_server: str, smtp_port: int, sender: str, password: str, logger=None):
        """Initialize email notifier.

        Args:
            smtp_server: SMTP server address
            smtp_port: SMTP port
            sender: Sender email address
            password: SMTP password
            logger: Logger instance
        """
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.sender = sender
        self.password = password
        self.logger = logger

    def send(self, notification: Notification, recipients: List[str]) -> bool:
        """Send notification via email.

        Args:
            notification: Notification to send
            recipients: List of recipient emails

        Returns:
            True if successful
        """
        try:
            msg = MIMEMultipart()
            msg["From"] = self.sender
            msg["To"] = ", ".join(recipients)
            msg["Subject"] = f"[{notification.level.name}] {notification.title}"

            body = f"{notification.message}\n\nTime: {notification.timestamp}\nTags: {', '.join(notification.tags)}"
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender, self.password)
                server.send_message(msg)

            if self.logger:
                self.logger.info(f"Email sent to {len(recipients)} recipients")

            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Email notification failed: {e}")
            return False


class WebhookNotifier:
    """Send notifications via webhook."""

    def __init__(self, webhook_url: str, logger=None):
        """Initialize webhook notifier.

        Args:
            webhook_url: Webhook URL
            logger: Logger instance
        """
        self.webhook_url = webhook_url
        self.logger = logger

    def send(self, notification: Notification) -> bool:
        """Send notification via webhook.

        Args:
            notification: Notification to send

        Returns:
            True if successful
        """
        try:
            import requests

            payload = {
                "level": notification.level.name,
                "title": notification.title,
                "message": notification.message,
                "timestamp": notification.timestamp.isoformat(),
                "tags": notification.tags,
            }

            response = requests.post(self.webhook_url, json=payload, timeout=5)
            success = response.status_code == 200

            if self.logger:
                if success:
                    self.logger.info(f"Webhook notification sent")
                else:
                    self.logger.error(f"Webhook returned {response.status_code}")

            return success

        except Exception as e:
            if self.logger:
                self.logger.error(f"Webhook notification failed: {e}")
            return False


class SyslogNotifier:
    """Send notifications via syslog."""

    def __init__(self, facility: str = "local0", logger=None):
        """Initialize syslog notifier.

        Args:
            facility: Syslog facility
            logger: Logger instance
        """
        self.facility = facility
        self.logger = logger

    def send(self, notification: Notification) -> bool:
        """Send notification via syslog.

        Args:
            notification: Notification to send

        Returns:
            True if successful
        """
        try:
            priority_map = {
                NotificationLevel.DEBUG: "debug",
                NotificationLevel.INFO: "info",
                NotificationLevel.WARNING: "warning",
                NotificationLevel.CRITICAL: "crit",
            }

            priority = priority_map.get(notification.level, "info")
            message = f"{notification.title}: {notification.message}"

            # Use logger-ng or fallback to command
            subprocess.run(
                ["logger", "-p", f"{self.facility}.{priority}", message],
                timeout=5,
                capture_output=True,
            )

            if self.logger:
                self.logger.info(f"Syslog notification sent")

            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Syslog notification failed: {e}")
            return False


class NotificationSystem:
    """Central notification system managing multiple channels."""

    def __init__(self, logger=None):
        """Initialize notification system.

        Args:
            logger: Logger instance
        """
        self.logger = logger
        self.notifiers: Dict[str, Any] = {}
        self.notification_history: List[Notification] = []
        self.enabled_levels = [NotificationLevel.WARNING, NotificationLevel.CRITICAL]
        self.max_history = 1000

    def register_email_notifier(
        self,
        name: str,
        smtp_server: str,
        smtp_port: int,
        sender: str,
        password: str,
    ):
        """Register email notifier.

        Args:
            name: Notifier name
            smtp_server: SMTP server
            smtp_port: SMTP port
            sender: Sender email
            password: SMTP password
        """
        self.notifiers[f"email_{name}"] = {
            "type": "email",
            "notifier": EmailNotifier(smtp_server, smtp_port, sender, password, self.logger),
            "config": {"sender": sender},
        }

    def register_webhook_notifier(self, name: str, webhook_url: str):
        """Register webhook notifier.

        Args:
            name: Notifier name
            webhook_url: Webhook URL
        """
        self.notifiers[f"webhook_{name}"] = {
            "type": "webhook",
            "notifier": WebhookNotifier(webhook_url, self.logger),
            "config": {"url": webhook_url},
        }

    def register_syslog_notifier(self, name: str = "default", facility: str = "local0"):
        """Register syslog notifier.

        Args:
            name: Notifier name
            facility: Syslog facility
        """
        self.notifiers[f"syslog_{name}"] = {
            "type": "syslog",
            "notifier": SyslogNotifier(facility, self.logger),
            "config": {"facility": facility},
        }

    def send_notification(
        self,
        level: NotificationLevel,
        title: str,
        message: str,
        tags: List[str] = None,
        recipients: List[str] = None,
    ) -> bool:
        """Send notification through all registered channels.

        Args:
            level: Notification level
            title: Notification title
            message: Notification message
            tags: Optional tags
            recipients: Optional recipient list (for email)

        Returns:
            True if at least one notifier succeeded
        """
        # Check if should send based on level
        if level not in self.enabled_levels:
            return False

        notification = Notification(
            level=level,
            title=title,
            message=message,
            tags=tags or [],
        )

        # Store in history
        self.notification_history.append(notification)
        if len(self.notification_history) > self.max_history:
            self.notification_history.pop(0)

        # Send through all notifiers
        success_count = 0

        for notifier_key, notifier_config in self.notifiers.items():
            try:
                notifier = notifier_config["notifier"]

                if notifier_config["type"] == "email" and recipients:
                    if notifier.send(notification, recipients):
                        success_count += 1
                elif notifier_config["type"] in ["webhook", "syslog"]:
                    if notifier.send(notification):
                        success_count += 1

            except Exception as e:
                if self.logger:
                    self.logger.error(f"Error sending via {notifier_key}: {e}")

        return success_count > 0

    def set_enabled_levels(self, levels: List[NotificationLevel]):
        """Set which notification levels should be sent.

        Args:
            levels: List of NotificationLevel to enable
        """
        self.enabled_levels = levels

    def get_notification_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get notification history.

        Args:
            limit: Maximum number of entries

        Returns:
            List of notification dicts
        """
        return [
            {
                "level": n.level.name,
                "title": n.title,
                "message": n.message,
                "timestamp": n.timestamp.isoformat(),
                "tags": n.tags,
            }
            for n in self.notification_history[-limit:]
        ]
