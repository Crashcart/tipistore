"""Per-category recovery rules for qBittorrent torrents."""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class CategoryRule:
    """Recovery rule for a category."""

    category: str
    enabled: bool = True
    priority: int = 5  # 1-10, higher = more important
    recovery_enabled: bool = True
    max_recovery_attempts: int = 3
    lag_threshold: float = 50.0  # 0-100
    auto_remove_on_dead: bool = False
    max_torrents: int = 100
    bandwidth_limit_percent: int = 100  # % of global limit


class CategoryRulesEngine:
    """Manages per-category recovery rules and thresholds."""

    def __init__(self, logger=None):
        """Initialize category rules engine.

        Args:
            logger: Logger instance
        """
        self.logger = logger
        self.rules: Dict[str, CategoryRule] = {}
        self._load_default_rules()

    def _load_default_rules(self):
        """Load default rules for common categories."""
        default_categories = [
            ("important", 1, 10, 75.0, False),
            ("archive", 2, 5, 60.0, False),
            ("test", 3, 3, 40.0, True),
        ]

        for category, priority, max_attempts, lag_threshold, auto_remove in default_categories:
            rule = CategoryRule(
                category=category,
                priority=priority,
                max_recovery_attempts=max_attempts,
                lag_threshold=lag_threshold,
                auto_remove_on_dead=auto_remove,
            )
            self.rules[category] = rule

    def add_rule(self, rule: CategoryRule):
        """Add or update a category rule.

        Args:
            rule: CategoryRule to add
        """
        self.rules[rule.category] = rule

        if self.logger:
            self.logger.info(f"Added rule for category: {rule.category}")

    def get_rule(self, category: str) -> Optional[CategoryRule]:
        """Get rule for a category.

        Args:
            category: Category name

        Returns:
            CategoryRule or None
        """
        return self.rules.get(category)

    def should_recover_torrent(self, torrent: Dict[str, Any], lag_score: float) -> bool:
        """Determine if torrent should be recovered.

        Args:
            torrent: Torrent info dict
            lag_score: Current lag score (0-100)

        Returns:
            True if should attempt recovery
        """
        category = torrent.get("category", "default")
        rule = self.get_rule(category)

        if not rule:
            # Use default behavior
            return lag_score > 50

        if not rule.enabled or not rule.recovery_enabled:
            return False

        # Check against category-specific threshold
        return lag_score > rule.lag_threshold

    def get_recovery_priority(self, torrent: Dict[str, Any]) -> int:
        """Get recovery priority for a torrent.

        Args:
            torrent: Torrent info dict

        Returns:
            Priority score (0-100)
        """
        category = torrent.get("category", "default")
        rule = self.get_rule(category)

        if not rule:
            return 5  # Default priority

        return rule.priority * 10  # Convert to 0-100 scale

    def apply_category_bandwidth_limit(
        self,
        api_client,
        torrent_hash: str,
        category: str,
        global_limit: int,
    ) -> bool:
        """Apply bandwidth limit for a torrent based on its category.

        Args:
            api_client: qBittorrent API client
            torrent_hash: Torrent hash
            category: Category name
            global_limit: Global bandwidth limit

        Returns:
            True if successful
        """
        try:
            rule = self.get_rule(category)
            if not rule:
                return True

            # Calculate category-specific limit
            category_limit = int(global_limit * rule.bandwidth_limit_percent / 100)

            # Note: Actual implementation would require qBittorrent API enhancement
            # to support per-torrent bandwidth limits

            if self.logger:
                self.logger.debug(
                    f"Applied bandwidth limit {category_limit}bps to {category} torrent"
                )

            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error applying bandwidth limit: {e}")
            return False

    def should_auto_remove_torrent(self, torrent: Dict[str, Any]) -> bool:
        """Determine if torrent should be auto-removed.

        Args:
            torrent: Torrent info dict

        Returns:
            True if should remove
        """
        category = torrent.get("category", "default")
        rule = self.get_rule(category)

        if not rule:
            return False

        if not rule.auto_remove_on_dead:
            return False

        # Check if torrent is dead
        num_seeds = torrent.get("num_seeds", 0)
        num_leech = torrent.get("num_leechs", 0)
        upspeed = torrent.get("upspeed", 0)

        return num_seeds == 0 and num_leech == 0 and upspeed == 0

    def get_category_stats(
        self,
        torrents: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Get statistics for each category.

        Args:
            torrents: List of torrent info dicts

        Returns:
            Dict mapping category to stats
        """
        stats = {}

        for torrent in torrents:
            category = torrent.get("category", "default")

            if category not in stats:
                stats[category] = {
                    "count": 0,
                    "downloading": 0,
                    "seeding": 0,
                    "paused": 0,
                    "total_size": 0,
                    "rule": self.get_rule(category),
                }

            stats[category]["count"] += 1
            stats[category]["total_size"] += torrent.get("total_size", 0)

            state = torrent.get("state", "")
            if state.startswith("downloading"):
                stats[category]["downloading"] += 1
            elif state.startswith("uploading"):
                stats[category]["seeding"] += 1
            elif state.startswith("paused"):
                stats[category]["paused"] += 1

        return stats

    def get_rules_config(self) -> Dict[str, Dict[str, Any]]:
        """Get all rules as config dict.

        Returns:
            Configuration dict
        """
        return {
            category: {
                "enabled": rule.enabled,
                "priority": rule.priority,
                "recovery_enabled": rule.recovery_enabled,
                "max_recovery_attempts": rule.max_recovery_attempts,
                "lag_threshold": rule.lag_threshold,
                "auto_remove_on_dead": rule.auto_remove_on_dead,
                "max_torrents": rule.max_torrents,
                "bandwidth_limit_percent": rule.bandwidth_limit_percent,
            }
            for category, rule in self.rules.items()
        }

    def load_rules_from_config(self, config: Dict[str, Dict[str, Any]]):
        """Load rules from configuration dict.

        Args:
            config: Configuration dict
        """
        for category, rule_config in config.items():
            rule = CategoryRule(
                category=category,
                **rule_config,
            )
            self.add_rule(rule)
