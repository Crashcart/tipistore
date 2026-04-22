# Implementation Guide: Advanced Monitoring Features

This guide provides concrete code examples and implementation patterns for each proposed feature.

---

## Feature 1: Torrent Health Analysis

### Implementation Skeleton

```python
# monitoring/torrent_analyzer.py

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import time

class TorrentHealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STALLED = "stalled"
    CORRUPTED = "corrupted"
    UNKNOWN = "unknown"

@dataclass
class TorrentHealthReport:
    hash: str
    name: str
    status: TorrentHealthStatus
    health_score: float  # 0-100
    issues: List[str]
    recommendations: List[str]
    last_check: float

class TorrentHealthAnalyzer:
    def __init__(self, api_client, logger=None):
        self.api_client = api_client
        self.logger = logger
        self.torrent_cache = {}  # Cache health reports
        self.cache_ttl = 60  # seconds
    
    def analyze_torrent(self, torrent_hash: str) -> TorrentHealthReport:
        """Analyze single torrent health."""
        cached = self.torrent_cache.get(torrent_hash)
        if cached and (time.time() - cached['timestamp']) < self.cache_ttl:
            return cached['report']
        
        # Fetch torrent details
        torrents = self.api_client.get_torrents(filters={'hashes': torrent_hash})
        if not torrents:
            return TorrentHealthReport(
                hash=torrent_hash, name="Unknown", status=TorrentHealthStatus.UNKNOWN,
                health_score=0, issues=["Torrent not found"], 
                recommendations=[], last_check=time.time()
            )
        
        torrent = torrents[0]
        health_score = 100.0
        issues = []
        recommendations = []
        
        # Check 1: Stalled (no peers)
        total_peers = torrent.get('num_seeds', 0) + torrent.get('num_leechs', 0)
        if total_peers == 0:
            health_score -= 40
            issues.append("No peers available in swarm")
            recommendations.append("Re-announce to trackers or add backup trackers")
            
            # Check if stalled for long time
            last_seen = torrent.get('seen_complete', 0)
            if last_seen > 0:
                hours_stalled = (time.time() - last_seen) / 3600
                if hours_stalled > 24:
                    issues.append(f"Stalled for {hours_stalled:.1f} hours")
        
        # Check 2: Low availability
        availability = torrent.get('availability', 0)
        if availability < 20:
            health_score -= 30
            issues.append(f"Low availability: {availability:.1f}%")
            recommendations.append("Torrent has few complete copies in swarm")
        
        # Check 3: No progress
        if torrent.get('progress', 0) == 0 and torrent.get('added_on', 0) > 0:
            time_since_added = (time.time() - torrent['added_on']) / 3600
            if time_since_added > 1:  # 1 hour
                health_score -= 20
                issues.append(f"0% progress after {time_since_added:.1f} hours")
                recommendations.append("Torrent may be corrupted or have no available pieces")
        
        # Check 4: Seed/leech ratio (all seeds, no leechers = bad for you)
        num_seeds = torrent.get('num_seeds', 0)
        num_leechs = torrent.get('num_leechs', 0)
        if num_seeds > 0 and num_leechs == 0:
            health_score -= 15
            issues.append("Only seeds in swarm, no leechers")
            recommendations.append("May experience slow downloads from seeds only")
        
        # Check 5: Very slow piece download
        if torrent.get('progress', 0) > 0:
            est_speed = torrent.get('dl_speed', 0)
            if est_speed < 10 * 1024:  # < 10 KB/s
                health_score -= 10
                issues.append(f"Slow download speed: {est_speed / 1024:.1f} KB/s")
        
        # Determine overall status
        if health_score >= 80:
            status = TorrentHealthStatus.HEALTHY
        elif health_score >= 50:
            status = TorrentHealthStatus.DEGRADED
        elif health_score >= 20:
            status = TorrentHealthStatus.STALLED
        else:
            status = TorrentHealthStatus.CORRUPTED
        
        report = TorrentHealthReport(
            hash=torrent_hash,
            name=torrent.get('name', 'Unknown'),
            status=status,
            health_score=max(0, health_score),
            issues=issues,
            recommendations=recommendations,
            last_check=time.time()
        )
        
        # Cache report
        self.torrent_cache[torrent_hash] = {
            'report': report,
            'timestamp': time.time()
        }
        
        return report
    
    def analyze_all_torrents(self) -> Dict[str, TorrentHealthReport]:
        """Analyze all active torrents."""
        torrents = self.api_client.get_torrents()
        reports = {}
        
        for torrent in torrents:
            hash = torrent['hash']
            reports[hash] = self.analyze_torrent(hash)
        
        return reports
    
    def get_worst_torrents(self, limit: int = 5) -> List[TorrentHealthReport]:
        """Get N worst torrents by health score."""
        reports = self.analyze_all_torrents()
        sorted_reports = sorted(
            reports.values(),
            key=lambda r: r.health_score
        )
        return sorted_reports[:limit]
```

### Integration with Lag Detector

```python
# detectors/lag_detector.py (modified)

from monitoring.torrent_analyzer import TorrentHealthAnalyzer, TorrentHealthStatus

class LagDetector:
    def __init__(self, api_client, config_manager, sensitivity="balanced", logger=None):
        # ... existing code ...
        self.torrent_analyzer = TorrentHealthAnalyzer(api_client, logger)
    
    def _check_torrent_health(self) -> Tuple[float, list]:
        """Check health of all torrents (new factor)."""
        score = 0.0
        issues = []
        
        reports = self.torrent_analyzer.analyze_all_torrents()
        
        stalled_count = sum(1 for r in reports.values() 
                           if r.status == TorrentHealthStatus.STALLED)
        corrupted_count = sum(1 for r in reports.values() 
                             if r.status == TorrentHealthStatus.CORRUPTED)
        
        if stalled_count > 0:
            score += min(10, stalled_count * 2)
            issues.append(f"{stalled_count} torrents stalled")
        
        if corrupted_count > 0:
            score += min(20, corrupted_count * 5)
            issues.append(f"{corrupted_count} torrents may be corrupted")
        
        return score, issues
    
    def detect_lag(self) -> Tuple[float, str]:
        """Modified detect_lag including torrent health."""
        try:
            lag_score = 0.0
            issues = []
            
            # ... existing checks ...
            
            # NEW: Torrent health
            health_score, health_issues = self._check_torrent_health()
            lag_score += health_score
            issues.extend(health_issues)
            
            # ... rest of method ...
```

---

## Feature 2: Peer Analysis

### Implementation Skeleton

```python
# monitoring/peer_analyzer.py

from dataclasses import dataclass
from typing import List, Dict
from enum import Enum

class PeerClassification(Enum):
    DEAD = "dead"
    SLOW = "slow"
    NORMAL = "normal"
    FAST = "fast"
    SEED = "seed"

@dataclass
class PeerAnalysis:
    peer_ip: str
    peer_port: int
    client: str
    classification: PeerClassification
    speed: float  # bytes/sec
    progress: float  # 0-1
    quality_score: float  # 0-100
    flags: List[str]  # e.g., ["suspicious", "timeout"]

class SwarmHealthReport:
    def __init__(self, torrent_hash: str):
        self.torrent_hash = torrent_hash
        self.peer_analyses: List[PeerAnalysis] = []
        self.swarm_health_score: float = 100.0
        self.issues: List[str] = []
        self.recommendations: List[str] = []
    
    def add_analysis(self, analysis: PeerAnalysis):
        self.peer_analyses.append(analysis)
    
    def quality_summary(self) -> Dict[str, int]:
        """Count peers by classification."""
        summary = {
            "dead": 0, "slow": 0, "normal": 0, "fast": 0, "seed": 0
        }
        for analysis in self.peer_analyses:
            summary[analysis.classification.value] += 1
        return summary

class SwarmHealthAnalyzer:
    def __init__(self, api_client, logger=None):
        self.api_client = api_client
        self.logger = logger
        self.DEAD_THRESHOLD = 1 * 1024  # 1 KB/s
        self.SLOW_THRESHOLD = 100 * 1024  # 100 KB/s
        self.FAST_THRESHOLD = 1 * 1024 * 1024  # 1 MB/s
    
    def analyze_swarm(self, torrent_hash: str) -> SwarmHealthReport:
        """Analyze swarm health by peer classification."""
        report = SwarmHealthReport(torrent_hash)
        
        # Get peer list from API
        try:
            # Note: This endpoint may not be available in all qBT versions
            peers = self.api_client.get_torrent_peers(torrent_hash)
        except Exception as e:
            if self.logger:
                self.logger.debug(f"Could not get peers for {torrent_hash}: {e}")
            return report
        
        if not peers:
            report.issues.append("No peer data available")
            report.swarm_health_score = 50
            return report
        
        # Analyze each peer
        total_speed = 0
        seed_count = 0
        timeout_count = 0
        
        for peer in peers:
            analysis = self._classify_peer(peer)
            report.add_analysis(analysis)
            
            total_speed += analysis.speed
            if analysis.classification == PeerClassification.SEED:
                seed_count += 1
            if "timeout" in analysis.flags:
                timeout_count += 1
        
        # Calculate swarm health score
        summary = report.quality_summary()
        dead_percent = summary['dead'] / len(peers) * 100 if peers else 0
        slow_percent = summary['slow'] / len(peers) * 100 if peers else 0
        
        report.swarm_health_score = 100.0
        
        if dead_percent > 50:
            report.swarm_health_score -= 40
            report.issues.append(f"{dead_percent:.0f}% peers are dead")
        
        if slow_percent > 70:
            report.swarm_health_score -= 30
            report.issues.append(f"{slow_percent:.0f}% peers are slow")
        
        if seed_count == 0:
            report.swarm_health_score -= 20
            report.issues.append("No seeds in swarm")
        
        if timeout_count > len(peers) * 0.3:
            report.swarm_health_score -= 25
            report.issues.append(f"{timeout_count} peers timing out")
            report.recommendations.append("Connection issues detected, may need DHT refresh")
        
        return report
    
    def _classify_peer(self, peer: Dict) -> PeerAnalysis:
        """Classify single peer."""
        speed = peer.get('dl_speed', 0) + peer.get('up_speed', 0)
        progress = peer.get('progress', 0) / 100.0  # Convert percent to fraction
        
        # Determine classification
        if speed < self.DEAD_THRESHOLD:
            classification = PeerClassification.DEAD
            quality_score = 10
        elif speed < self.SLOW_THRESHOLD:
            classification = PeerClassification.SLOW
            quality_score = 40
        elif speed < self.FAST_THRESHOLD:
            classification = PeerClassification.NORMAL
            quality_score = 70
        else:
            classification = PeerClassification.FAST
            quality_score = 90
        
        # Check if seed
        if progress >= 0.99:
            classification = PeerClassification.SEED
            quality_score = max(quality_score, 80)
        
        # Detect flags
        flags = []
        if "flags" in peer and "X" in peer.get("flags", ""):
            flags.append("timeout")
        if progress == 0 and classification != PeerClassification.SEED:
            flags.append("leecher_no_progress")
        
        return PeerAnalysis(
            peer_ip=peer.get('ip', 'unknown'),
            peer_port=peer.get('port', 0),
            client=peer.get('client', 'unknown'),
            classification=classification,
            speed=speed,
            progress=progress,
            quality_score=quality_score,
            flags=flags
        )
```

---

## Feature 3: Bandwidth Intelligence

### Implementation Skeleton

```python
# monitoring/bandwidth_analyzer.py

from collections import deque
from dataclasses import dataclass
import time

@dataclass
class BandwidthSnapshot:
    timestamp: float
    dl_speed: float  # bytes/sec
    ul_speed: float  # bytes/sec
    dl_limit: float  # bytes/sec
    ul_limit: float  # bytes/sec
    active_torrents: int

class BandwidthIntelligence:
    def __init__(self, api_client, logger=None, history_size: int = 60):
        self.api_client = api_client
        self.logger = logger
        self.history = deque(maxlen=history_size)  # 60 samples = 1 hour at 60s intervals
    
    def collect_snapshot(self):
        """Collect current bandwidth snapshot."""
        try:
            stats = self.api_client.get_server_state()
            prefs = self.api_client.get_preferences()
            torrents = self.api_client.get_torrents()
            
            snapshot = BandwidthSnapshot(
                timestamp=time.time(),
                dl_speed=stats.get('dl_info_speed', 0),
                ul_speed=stats.get('up_info_speed', 0),
                dl_limit=prefs.get('dl_limit', 0),
                ul_limit=prefs.get('up_limit', 0),
                active_torrents=len([t for t in torrents 
                                    if t.get('state', '').startswith('downloading')])
            )
            self.history.append(snapshot)
            return snapshot
        except Exception as e:
            if self.logger:
                self.logger.error(f"Could not collect bandwidth snapshot: {e}")
            return None
    
    def detect_throttling(self) -> tuple[bool, str]:
        """Detect if bandwidth is being throttled."""
        if len(self.history) < 10:
            return False, "Not enough history"
        
        recent = list(self.history)[-10:]
        
        # Pattern 1: Speed caps at specific value repeatedly
        speeds = [s.dl_speed for s in recent if s.dl_speed > 0]
        if speeds and len(set([round(s, -4) for s in speeds])) == 1:
            # All speeds round to same value (e.g., 1MB/s)
            return True, "Speed capped at consistent value (likely throttled)"
        
        # Pattern 2: Speed drops suddenly when active_torrents increases
        for i in range(1, len(recent)):
            if (recent[i].active_torrents > recent[i-1].active_torrents and
                recent[i].dl_speed < recent[i-1].dl_speed * 0.7):
                return True, "Speed drops when new torrent added (bandwidth contention)"
        
        return False, ""
    
    def detect_limit_mismatch(self) -> tuple[bool, str]:
        """Detect if upload limit is hurting download speed."""
        if len(self.history) < 5:
            return False, ""
        
        recent = list(self.history)[-5:]
        avg_ul_speed = sum(s.ul_speed for s in recent) / len(recent)
        avg_dl_speed = sum(s.dl_speed for s in recent) / len(recent)
        
        # Check if upload is near limit
        snapshot = recent[-1]
        if snapshot.ul_limit > 0:
            ul_utilization = avg_ul_speed / snapshot.ul_limit
            if ul_utilization > 0.8:  # Upload at 80%+ of limit
                # This often throttles download via TCP congestion
                return True, f"Upload near limit ({ul_utilization:.0%}), may throttle download"
        
        return False, ""
    
    def predict_capacity(self) -> float:
        """Predict available bandwidth for new torrents."""
        if len(self.history) < 5:
            return 0
        
        recent = list(self.history)[-5:]
        snapshot = recent[-1]
        
        # If no download limit, estimate from current usage + headroom
        if snapshot.dl_limit == 0:
            avg_dl = sum(s.dl_speed for s in recent) / len(recent)
            # Assume we can go 2x average or 10MB/s, whichever is lower
            return min(avg_dl * 2, 10 * 1024 * 1024)
        
        # If limit set, use headroom
        utilization = snapshot.dl_speed / snapshot.dl_limit if snapshot.dl_limit > 0 else 1.0
        available = snapshot.dl_limit * (1.0 - utilization) * 0.8  # Leave 20% safety margin
        return max(0, available)
    
    def recommend_limit_adjustment(self) -> Optional[Dict]:
        """Recommend new bandwidth limits."""
        if len(self.history) < 10:
            return None
        
        recent = list(self.history)[-10:]
        avg_dl = sum(s.dl_speed for s in recent) / len(recent)
        avg_ul = sum(s.ul_speed for s in recent) / len(recent)
        max_dl = max(s.dl_speed for s in recent)
        max_ul = max(s.ul_speed for s in recent)
        
        # If we're consistently using < 50% of limit, we can increase it
        snapshot = recent[-1]
        if snapshot.dl_limit > 0:
            utilization = avg_dl / snapshot.dl_limit
            if utilization < 0.5 and snapshot.active_torrents > 0:
                new_limit = int(snapshot.dl_limit * 1.5)
                return {
                    'type': 'increase_dl_limit',
                    'current': snapshot.dl_limit,
                    'recommended': new_limit,
                    'reason': f'Only {utilization:.0%} utilized'
                }
        
        # Check upload/download ratio
        if avg_dl > 0 and avg_ul / avg_dl > 0.5:  # Upload is 50%+ of download
            return {
                'type': 'reduce_ul_limit',
                'current': snapshot.ul_limit,
                'recommended': int(avg_dl * 0.3),
                'reason': 'Upload may be throttling download'
            }
        
        return None
```

---

## Feature 4: Predictive Recovery

### Implementation Skeleton

```python
# detectors/predictive_detector.py

from collections import deque
from dataclasses import dataclass
from typing import Optional
import time

class DegradationLevel(Enum):
    NORMAL = "normal"
    YELLOW = "yellow"      # Trending down, take action soon
    ORANGE = "orange"      # Significant degradation, take action now
    RED = "red"            # Critical, take action immediately

@dataclass
class DegradationAlert:
    level: DegradationLevel
    metric: str  # "speed", "peer_count", "hash_failures", etc.
    current_value: float
    trend: str  # "stable", "declining", "increasing"
    trend_rate: float  # units per minute
    eta_critical: Optional[float]  # seconds until critical if trend continues
    recommendation: str

class PredictiveDetector:
    def __init__(self, logger=None):
        self.logger = logger
        self.speed_history = deque(maxlen=30)  # 5 mins at 10s intervals
        self.peer_history = deque(maxlen=30)
        self.hash_failure_history = deque(maxlen=30)
    
    def record_metrics(self, speed: float, peer_count: int, hash_failures: int):
        """Record metrics for trending."""
        self.speed_history.append((time.time(), speed))
        self.peer_history.append((time.time(), peer_count))
        self.hash_failure_history.append((time.time(), hash_failures))
    
    def detect_degradation(self) -> Optional[DegradationAlert]:
        """Detect if system is degrading."""
        
        # Check speed trend
        alert = self._check_speed_trend()
        if alert:
            return alert
        
        # Check peer count trend
        alert = self._check_peer_trend()
        if alert:
            return alert
        
        # Check hash failure trend
        alert = self._check_hash_failure_trend()
        if alert:
            return alert
        
        return None
    
    def _check_speed_trend(self) -> Optional[DegradationAlert]:
        """Check if download speed is trending down."""
        if len(self.speed_history) < 10:
            return None
        
        recent = list(self.speed_history)[-10:]
        older = list(self.speed_history)[-20:-10]
        
        if not older:
            return None
        
        recent_avg = sum(s for _, s in recent) / len(recent)
        older_avg = sum(s for _, s in older) / len(older)
        
        if older_avg == 0:
            return None
        
        decline_percent = (1 - recent_avg / older_avg) * 100
        
        if decline_percent > 50:  # Speed dropped >50%
            # Calculate trend rate
            time_span = (recent[-1][0] - recent[0][0]) / 60  # minutes
            trend_rate = (recent_avg - older_avg) / time_span  # KB/s per minute
            
            # Estimate when we hit critical (100 KB/s minimum)
            critical_threshold = 100 * 1024  # 100 KB/s
            if trend_rate < 0:
                eta_critical = (recent_avg - critical_threshold) / abs(trend_rate) * 60
            else:
                eta_critical = None
            
            level = DegradationLevel.ORANGE if decline_percent > 70 else DegradationLevel.YELLOW
            
            return DegradationAlert(
                level=level,
                metric="download_speed",
                current_value=recent_avg / 1024 / 1024,  # MB/s
                trend="declining",
                trend_rate=trend_rate,
                eta_critical=eta_critical,
                recommendation="Check peer health, consider pausing non-essential torrents"
            )
        
        return None
    
    def _check_peer_trend(self) -> Optional[DegradationAlert]:
        """Check if peer count is declining."""
        if len(self.peer_history) < 15:
            return None
        
        recent = list(self.peer_history)[-10:]
        older = list(self.peer_history)[-20:-10]
        
        recent_avg = sum(p for _, p in recent) / len(recent)
        older_avg = sum(p for _, p in older) / len(older)
        
        decline_percent = (1 - recent_avg / older_avg) * 100 if older_avg > 0 else 0
        
        if decline_percent > 40 and recent_avg < 20:  # 40% decline AND < 20 peers
            time_span = (recent[-1][0] - recent[0][0]) / 60  # minutes
            trend_rate = (recent_avg - older_avg) / time_span  # peers per minute
            
            eta_critical = recent_avg / abs(trend_rate) * 60 if trend_rate < 0 else None
            
            return DegradationAlert(
                level=DegradationLevel.RED if recent_avg < 5 else DegradationLevel.ORANGE,
                metric="peer_count",
                current_value=recent_avg,
                trend="declining",
                trend_rate=trend_rate,
                eta_critical=eta_critical,
                recommendation="Trigger DHT refresh and peer discovery"
            )
        
        return None
    
    def _check_hash_failure_trend(self) -> Optional[DegradationAlert]:
        """Check if hash failures are increasing (corruption)."""
        if len(self.hash_failure_history) < 10:
            return None
        
        recent = list(self.hash_failure_history)[-10:]
        failures = [f for _, f in recent if f > 0]
        
        if len(failures) > 5:  # Multiple failures detected
            return DegradationAlert(
                level=DegradationLevel.RED,
                metric="hash_failures",
                current_value=failures[-1] if failures else 0,
                trend="increasing",
                trend_rate=len(failures) / 10,
                eta_critical=None,
                recommendation="Possible disk corruption, recheck torrent or move to different disk"
            )
        
        return None
```

---

## Feature 5: Auto-Cleanup Manager

### Implementation Skeleton

```python
# recovery/cleanup_manager.py

from enum import Enum
from dataclasses import dataclass
from typing import List
import time

class CleanupAction(Enum):
    PAUSE = "pause"
    REMOVE_METADATA = "remove_metadata"
    REMOVE_WITH_FILES = "remove_with_files"

@dataclass
class ProblematicTorrent:
    hash: str
    name: str
    reason: str
    age_hours: float
    severity: str  # "low", "medium", "high"
    recommended_action: CleanupAction

class AutoCleanupManager:
    def __init__(self, api_client, logger=None):
        self.api_client = api_client
        self.logger = logger
        self.cleanup_history = deque(maxlen=1000)  # Track removals for 7 days
    
    def identify_problematic_torrents(self, 
                                     no_peers_threshold_hours: int = 1,
                                     stuck_threshold_hours: int = 24,
                                     ) -> List[ProblematicTorrent]:
        """Identify torrents that should be cleaned up."""
        torrents = self.api_client.get_torrents()
        problems = []
        
        for torrent in torrents:
            problem = self._analyze_torrent(
                torrent, 
                no_peers_threshold_hours,
                stuck_threshold_hours
            )
            if problem:
                problems.append(problem)
        
        return problems
    
    def _analyze_torrent(self, torrent: dict, 
                        no_peers_h: int, stuck_h: int) -> Optional[ProblematicTorrent]:
        """Analyze single torrent for issues."""
        now = time.time()
        added_time = torrent.get('added_on', now)
        age_hours = (now - added_time) / 3600
        
        hash = torrent['hash']
        name = torrent['name']
        
        # Issue 1: No peers + stalled for N hours
        peers = torrent.get('num_seeds', 0) + torrent.get('num_leechs', 0)
        if peers == 0 and age_hours > no_peers_h:
            seen_complete = torrent.get('seen_complete', 0)
            if seen_complete == 0:
                # Never seen a complete copy
                return ProblematicTorrent(
                    hash=hash, name=name,
                    reason="No peers and never seen complete",
                    age_hours=age_hours,
                    severity="high",
                    recommended_action=CleanupAction.PAUSE
                )
        
        # Issue 2: 0% progress for N hours
        if torrent.get('progress', 0) == 0 and age_hours > stuck_h:
            return ProblematicTorrent(
                hash=hash, name=name,
                reason="0% progress after 24 hours",
                age_hours=age_hours,
                severity="high",
                recommended_action=CleanupAction.PAUSE
            )
        
        # Issue 3: Corrupted (high hash failure rate)
        # TODO: Requires integration with piece analyzer
        
        # Issue 4: Duplicate (same infohash already exists)
        # TODO: Requires bloom filter or dedup check
        
        return None
    
    def cleanup_torrent(self, torrent_hash: str, action: CleanupAction) -> bool:
        """Execute cleanup action on torrent."""
        try:
            if action == CleanupAction.PAUSE:
                self.api_client.pause_torrent(torrent_hash)
                self.logger.info(f"Paused problematic torrent: {torrent_hash}")
            
            elif action == CleanupAction.REMOVE_METADATA:
                # Remove torrent but keep downloaded files
                self.api_client.delete_torrent(torrent_hash, delete_files=False)
                self.logger.info(f"Removed torrent metadata: {torrent_hash}")
            
            elif action == CleanupAction.REMOVE_WITH_FILES:
                # Remove torrent and delete files
                self.api_client.delete_torrent(torrent_hash, delete_files=True)
                self.logger.info(f"Removed torrent with files: {torrent_hash}")
            
            # Log to history
            self.cleanup_history.append({
                'hash': torrent_hash,
                'action': action.value,
                'timestamp': time.time()
            })
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to cleanup torrent {torrent_hash}: {e}")
            return False
```

---

## Feature 9: Seed Ratio Management

### Implementation Skeleton

```python
# recovery/seed_manager.py

from dataclasses import dataclass
from typing import Optional

@dataclass
class SeedRatioRule:
    enabled: bool
    ratio_limit: float  # 1.0 = 1:1 ratio
    time_limit_seconds: int  # 0 = unlimited
    pause_on_limit: bool  # False = remove

class SeedRatioManager:
    def __init__(self, api_client, logger=None):
        self.api_client = api_client
        self.logger = logger
        self.global_rule = SeedRatioRule(
            enabled=True,
            ratio_limit=2.0,
            time_limit_seconds=7 * 24 * 3600,  # 7 days
            pause_on_limit=True
        )
    
    def manage_seed_ratios(self) -> dict:
        """Manage all active torrents' seed ratios."""
        torrents = self.api_client.get_torrents()
        actions_taken = {'paused': 0, 'removed': 0}
        
        for torrent in torrents:
            if torrent['state'] != 'uploading':
                continue  # Skip non-completed torrents
            
            # Calculate seed ratio
            total_down = torrent.get('total_downloaded', 0)
            total_up = torrent.get('total_uploaded', 0)
            
            if total_down == 0:
                ratio = 0
            else:
                ratio = total_up / total_down
            
            # Check time seeded
            completion_time = torrent.get('completion_on', 0)
            now = time.time()
            time_seeded = now - completion_time if completion_time > 0 else 0
            
            # Check against rules
            should_stop = False
            reason = ""
            
            if self.global_rule.enabled:
                if ratio >= self.global_rule.ratio_limit:
                    should_stop = True
                    reason = f"Reached ratio limit ({ratio:.2f})"
                
                elif (self.global_rule.time_limit_seconds > 0 and 
                      time_seeded >= self.global_rule.time_limit_seconds):
                    should_stop = True
                    reason = f"Seeded for {time_seeded / 3600:.0f} hours"
            
            if should_stop:
                if self.global_rule.pause_on_limit:
                    self.api_client.pause_torrent(torrent['hash'])
                    actions_taken['paused'] += 1
                    if self.logger:
                        self.logger.info(f"Paused {torrent['name']}: {reason}")
                else:
                    self.api_client.delete_torrent(torrent['hash'], delete_files=False)
                    actions_taken['removed'] += 1
                    if self.logger:
                        self.logger.info(f"Removed {torrent['name']}: {reason}")
        
        return actions_taken
    
    def resume_slow_seeds(self) -> int:
        """Resume paused torrents if ratio dropped."""
        paused = self.api_client.get_torrents(filter='paused')
        resumed_count = 0
        
        for torrent in paused:
            if torrent.get('total_downloaded', 0) == 0:
                continue
            
            ratio = torrent.get('total_uploaded', 0) / torrent['total_downloaded']
            
            # Resume if ratio fell below 50% of limit
            if ratio < self.global_rule.ratio_limit * 0.5:
                self.api_client.resume_torrent(torrent['hash'])
                resumed_count += 1
                if self.logger:
                    self.logger.info(f"Resumed {torrent['name']} (ratio: {ratio:.2f})")
        
        return resumed_count
```

---

## Feature 10: Alert System

### Implementation Skeleton

```python
# alerting/alert_system.py

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict
import json
import smtplib
import requests
from email.mime.text import MIMEText

class AlertLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

@dataclass
class Alert:
    level: AlertLevel
    title: str
    message: str
    context: Dict
    timestamp: float

class EmailNotifier:
    def __init__(self, smtp_server: str, smtp_port: int, 
                 from_addr: str, to_addrs: List[str], 
                 username: Optional[str] = None,
                 password: Optional[str] = None,
                 logger=None):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.from_addr = from_addr
        self.to_addrs = to_addrs
        self.username = username
        self.password = password
        self.logger = logger
    
    def send(self, alert: Alert) -> bool:
        """Send email notification."""
        try:
            subject = f"[qBittorrent] {alert.level.value}: {alert.title}"
            
            body = f"""Alert: {alert.title}
Level: {alert.level.value}

Message: {alert.message}

Context:
{json.dumps(alert.context, indent=2)}

Timestamp: {alert.timestamp}
"""
            
            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'] = self.from_addr
            msg['To'] = ', '.join(self.to_addrs)
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                if self.username and self.password:
                    server.starttls()
                    server.login(self.username, self.password)
                
                server.send_message(msg)
            
            if self.logger:
                self.logger.info(f"Email alert sent: {alert.title}")
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to send email alert: {e}")
            return False

class WebhookNotifier:
    def __init__(self, webhook_urls: Dict[str, str], logger=None):
        # webhook_urls: {'discord': '...', 'slack': '...', 'custom': '...'}
        self.webhook_urls = webhook_urls
        self.logger = logger
    
    def send(self, alert: Alert, channel: str = 'custom') -> bool:
        """Send webhook notification."""
        url = self.webhook_urls.get(channel)
        if not url:
            return False
        
        try:
            payload = {
                'level': alert.level.value,
                'title': alert.title,
                'message': alert.message,
                'timestamp': alert.timestamp,
                'context': alert.context
            }
            
            response = requests.post(url, json=payload, timeout=5)
            
            if response.status_code >= 400:
                if self.logger:
                    self.logger.warning(f"Webhook returned {response.status_code}")
                return False
            
            if self.logger:
                self.logger.info(f"Webhook alert sent to {channel}")
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to send webhook alert: {e}")
            return False

class AlertSystem:
    def __init__(self, config: Dict, logger=None):
        self.logger = logger
        self.config = config
        self.email_notifier = None
        self.webhook_notifier = None
        self.alert_history = deque(maxlen=1000)
        self.throttle_state = {}  # Track throttled alerts
        
        # Initialize notifiers based on config
        if config.get('email', {}).get('enabled'):
            self.email_notifier = EmailNotifier(
                smtp_server=config['email'].get('smtp_server'),
                smtp_port=config['email'].get('smtp_port', 587),
                from_addr=config['email'].get('from_address'),
                to_addrs=config['email'].get('to_addresses', []),
                username=config['email'].get('username'),
                password=config['email'].get('password'),
                logger=logger
            )
        
        if config.get('webhook', {}).get('enabled'):
            self.webhook_notifier = WebhookNotifier(
                webhook_urls=config['webhook'].get('urls', {}),
                logger=logger
            )
    
    def send_alert(self, level: AlertLevel, title: str, message: str, 
                   context: Optional[Dict] = None) -> bool:
        """Send alert through appropriate channels."""
        if context is None:
            context = {}
        
        alert = Alert(
            level=level,
            title=title,
            message=message,
            context=context,
            timestamp=time.time()
        )
        
        # Check if should throttle
        if self._should_throttle(alert):
            if self.logger:
                self.logger.debug(f"Alert throttled: {title}")
            return True
        
        # Route based on level
        if level == AlertLevel.CRITICAL:
            self.email_notifier and self.email_notifier.send(alert)
            self.webhook_notifier and self.webhook_notifier.send(alert, 'discord')
        
        elif level in [AlertLevel.ERROR, AlertLevel.WARNING]:
            self.webhook_notifier and self.webhook_notifier.send(alert, 'custom')
        
        elif level == AlertLevel.INFO:
            # Buffer for digest or skip
            if self.config.get('digest_enabled'):
                return True  # Will be sent in digest
            self.webhook_notifier and self.webhook_notifier.send(alert, 'custom')
        
        self.alert_history.append(alert)
        return True
    
    def _should_throttle(self, alert: Alert) -> bool:
        """Check if alert should be throttled."""
        key = (alert.level.value, alert.title)
        
        throttle_config = self.config.get('throttling', {})
        max_per_hour = throttle_config.get('max_alerts_per_hour', 10)
        dedup_minutes = throttle_config.get('similar_alert_dedupe_minutes', 5)
        
        # Count recent similar alerts
        now = time.time()
        cutoff = now - (dedup_minutes * 60)
        
        recent = [a for a in self.alert_history 
                 if (a.level, a.title) == key and a.timestamp > cutoff]
        
        if len(recent) > 0:
            return True  # Already sent recently
        
        return False
```

---

## Configuration Integration

Add to main `qbittorrent_agent.py`:

```python
from monitoring.torrent_analyzer import TorrentHealthAnalyzer
from monitoring.bandwidth_analyzer import BandwidthIntelligence
from recovery.cleanup_manager import AutoCleanupManager
from recovery.seed_manager import SeedRatioManager
from alerting.alert_system import AlertSystem, AlertLevel

class QBittorrentAgent:
    def __init__(self, args):
        # ... existing init code ...
        
        # Load feature flags
        self.features_enabled = {
            'torrent_health': True,
            'bandwidth_intelligence': True,
            'auto_cleanup': args.enable_cleanup,
            'seed_ratio_management': args.enable_seed_mgmt,
            'alert_system': args.enable_alerts,
        }
        
        # Initialize new analyzers
        if self.features_enabled['torrent_health']:
            self.torrent_analyzer = TorrentHealthAnalyzer(
                self.api_client, self.logger
            )
        
        if self.features_enabled['bandwidth_intelligence']:
            self.bandwidth_analyzer = BandwidthIntelligence(
                self.api_client, self.logger
            )
        
        if self.features_enabled['auto_cleanup']:
            self.cleanup_manager = AutoCleanupManager(
                self.api_client, self.logger
            )
        
        if self.features_enabled['seed_ratio_management']:
            self.seed_manager = SeedRatioManager(
                self.api_client, self.logger
            )
        
        if self.features_enabled['alert_system']:
            alert_config = self._load_alert_config(args.alert_config)
            self.alert_system = AlertSystem(alert_config, self.logger)
    
    def run(self):
        """Modified main loop with new features."""
        while self.running:
            try:
                # Original lag detection
                lag_score, lag_details = self.lag_detector.detect_lag()
                
                # NEW: Collect bandwidth metrics for trending
                if self.features_enabled['bandwidth_intelligence']:
                    self.bandwidth_analyzer.collect_snapshot()
                
                # NEW: Check for problems
                if lag_score > 0:
                    self.logger.warning(
                        f"Lag detected (score: {lag_score:.1f}/100) - {lag_details}"
                    )
                    
                    # Original recovery
                    if not self.args.dry_run:
                        self.recovery_engine.execute_recovery(lag_score)
                    
                    # NEW: Send alerts
                    if self.features_enabled['alert_system']:
                        self.alert_system.send_alert(
                            level=AlertLevel.WARNING if lag_score < 75 else AlertLevel.CRITICAL,
                            title="qBittorrent Lag Detected",
                            message=lag_details,
                            context={'lag_score': lag_score}
                        )
                
                # NEW: Manage cleanup
                if self.features_enabled['auto_cleanup']:
                    problems = self.cleanup_manager.identify_problematic_torrents()
                    for problem in problems:
                        if self.features_enabled['alert_system']:
                            self.alert_system.send_alert(
                                level=AlertLevel.WARNING,
                                title=f"Problematic Torrent: {problem.name}",
                                message=problem.reason
                            )
                
                # NEW: Manage seed ratios
                if self.features_enabled['seed_ratio_management']:
                    actions = self.seed_manager.manage_seed_ratios()
                    if actions['paused'] > 0 or actions['removed'] > 0:
                        self.logger.info(f"Seed management: paused {actions['paused']}, removed {actions['removed']}")
                
                time.sleep(self.args.interval)
            
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}", exc_info=True)
```

---

## Testing Example

```python
# tests/test_features.py

import unittest
from monitoring.torrent_analyzer import TorrentHealthAnalyzer, TorrentHealthStatus
from monitoring.bandwidth_analyzer import BandwidthIntelligence

class TestTorrentHealthAnalyzer(unittest.TestCase):
    def setUp(self):
        # Mock API client
        self.mock_api = MockQBittorrentAPI()
        self.analyzer = TorrentHealthAnalyzer(self.mock_api)
    
    def test_detect_stalled_torrent(self):
        """Test detection of stalled torrent (no peers)."""
        # Create mock torrent with no peers
        torrent = {
            'hash': 'abc123',
            'name': 'Test Torrent',
            'num_seeds': 0,
            'num_leechs': 0,
            'progress': 0.5,
            'added_on': time.time() - 3600,  # 1 hour ago
            'dl_speed': 0
        }
        self.mock_api.add_torrent(torrent)
        
        report = self.analyzer.analyze_torrent('abc123')
        
        assert report.status == TorrentHealthStatus.STALLED
        assert "No peers" in report.issues[0]
    
    def test_detect_corrupted_torrent(self):
        """Test detection of corrupted/incomplete torrent."""
        torrent = {
            'hash': 'def456',
            'name': 'Corrupted Torrent',
            'num_seeds': 5,
            'num_leechs': 2,
            'progress': 0.0,  # No progress
            'added_on': time.time() - 86400,  # 24 hours ago
            'dl_speed': 0
        }
        self.mock_api.add_torrent(torrent)
        
        report = self.analyzer.analyze_torrent('def456')
        
        assert report.status == TorrentHealthStatus.STALLED
        assert "0% progress" in report.issues[0]

if __name__ == '__main__':
    unittest.main()
```

---

## Conclusion

These code skeletons provide the foundation for each feature. Implementation should:

1. Start with `TorrentHealthAnalyzer` (foundational)
2. Add `BandwidthIntelligence` for trending
3. Integrate `AlertSystem` for notifications
4. Add `SeedRatioManager` for resource management
5. Progressively add more advanced features

Each module is designed to work independently while integrating cleanly with the existing agent architecture.
