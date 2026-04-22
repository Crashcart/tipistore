# Advanced Monitoring and Recovery Features for qBittorrent Intelligent Agent

## Executive Summary

This proposal outlines 10 advanced monitoring and recovery features to enhance the qBittorrent Intelligent Recovery Agent. Each feature is based on research into qBittorrent Web API v2 (up to v5.0+) capabilities, common lag causes, and industry best practices. Features are prioritized by implementation complexity and real-world impact.

**Key Findings:**
- qBittorrent Web API v2 provides comprehensive access to torrent health, peer, and bandwidth metrics
- Common lag causes: stalled torrents, low peer counts, incomplete pieces, port/firewall issues, and upload/download ratio imbalance
- Existing agent can be extended with minimal invasiveness to detect problems before they escalate

---

## Feature Proposals

### 1. Torrent Health Analysis

**Description:**
Detect problematic torrents by analyzing completion percentage, peer health, and download speed trends. Identifies torrents that are stalled, stuck on specific pieces, or experiencing degradation.

**Key Metrics to Monitor:**
- Availability percentage (pieces available in swarm)
- Time since last piece download
- Progress stalled for N minutes
- Seed/peer ratio in swarm
- Number of connected seeds vs. leechers
- Piece count distribution (gaps in downloaded pieces)

**Feasibility:** Medium

**Data Sources:**
- `/api/v2/torrents/info` - Progress, num_seeds, num_leechs, availability
- `/api/v2/torrents/pieces` - Piece hashes (to detect missing/corrupt pieces)
- Historical metrics stored locally with timestamps

**Implementation Details:**
```python
class TorrentHealthAnalyzer:
    def analyze_torrent_health(torrent_hash: str) -> TorrentHealthStatus:
        # Check if torrent is in "stalled" state
        # Monitor pieces not downloaded in last N minutes
        # Compare availability % to expected completion
        # Flag torrents with < 2 seeds or extreme ratios
        # Track piece download speed trends
```

**Impact on Performance:** Minimal (1-2 API calls per torrent, cached locally)

**Integration Points:**
- Extend `LagDetector._check_performance()` to include per-torrent analysis
- Add torrent-specific recovery (re-announce to tracker, add backup trackers, pause/resume)
- Populate alert system with health scores

**Recovery Actions:**
1. Re-announce torrent to trackers
2. Add backup trackers (from public tracker lists)
3. Pause and resume torrent to reset state
4. Remove torrent if stuck for >30 minutes with no peers

---

### 2. Peer Analysis and Swarm Health

**Description:**
Analyze peer distribution, connection quality, and swarm health metrics to identify when peers are unreachable, hostile, or unable to provide data.

**Key Metrics:**
- Peers connected / peers in swarm ratio
- Peer upload/download distribution (many slow seeders vs. few fast ones)
- Peer version distribution (detect malicious clients)
- Connection timeout rate per peer
- Geographic distribution of peers (if available via GeoIP)
- Peer choke events and unchoke delays

**Feasibility:** Hard

**Data Sources:**
- `/api/v2/torrents/{hash}/peers` - Full peer list with IP, port, client, dl_speed, up_speed, progress
- `/api/v2/log/peers` - Peer blocking/ban log with timestamps
- System-level socket metrics (`netstat`, `/proc/net/tcp`)

**Implementation Details:**
```python
class SwarmHealthAnalyzer:
    def analyze_swarm_health(torrent_hash: str) -> SwarmHealthReport:
        peers = api_client.get_torrent_peers(torrent_hash)
        # Classify peers: dead (0 speed > 1min), slow (<100KB/s), 
        # fast (>1MB/s), seeds, leechers
        # Calculate connection success rate
        # Detect peer IP blacklisting patterns
        # Warn if >80% of peers are slow or dead
```

**Impact on Performance:** Medium (one API call per torrent, can be cached)

**Integration Points:**
- Add to `LagDetector` as new factor in lag scoring
- Use peer data to inform bandwidth allocation decisions
- Feed into recovery engine for connection reset

**Recovery Actions:**
1. Disconnect from slowest N peers
2. Force new peer discovery via DHT/trackers
3. Ban known bad peers
4. Adjust upload/download priorities based on peer capability
5. Trigger connection re-negotiation

**API Endpoint Notes:**
The `/api/v2/torrents/{hash}/peers` endpoint returns IP addresses, port, client version, and speed metrics for all connected peers. This is the primary data source for swarm analysis.

---

### 3. Protocol Optimization (IPv4 vs IPv6 vs UDP vs TCP)

**Description:**
Monitor protocol-level performance to identify when IPv4 or IPv6 connectivity is degraded, or when UDP (µTP) is performing poorly vs TCP. Auto-switch protocols or adjust prefer_tcp mode.

**Key Metrics:**
- IPv4 vs IPv6 connection success rate
- TCP vs µTP connection distribution
- TCP vs µTP bandwidth efficiency ratio
- Protocol-specific peer count
- Socket timeout frequency by protocol
- NAT/UPnP success rate

**Feasibility:** Hard

**Data Sources:**
- System-level: `/proc/net/tcp`, `/proc/net/tcp6`, socket statistics
- qBittorrent preferences: `bittorrent/protocol_prefer_tcp`, `bittorrent/ipv6`, `network/bind_interface`
- Connection logs (parse qBittorrent debug logs if available)

**Implementation Details:**
```python
class ProtocolOptimizer:
    def analyze_protocol_health(self) -> ProtocolReport:
        # Sample socket states for TCP/UDP
        ipv4_conns = self._count_protocol_sockets('inet', 'tcp')
        ipv6_conns = self._count_protocol_sockets('inet6', 'tcp')
        # Compare bandwidth efficiency of TCP vs uTP
        # Flag if IPv6 is enabled but producing 0 connections
        # Warn if prefer_tcp misaligned with connection distribution
```

**Impact on Performance:** Medium (requires /proc parsing, done infrequently)

**Integration Points:**
- Monitor in `SystemMetrics` or new `ProtocolMetrics` module
- Feed into recovery engine to toggle prefer_tcp, IPv6 settings
- Inform peer selection strategy

**Recovery Actions:**
1. Toggle `bittorrent/protocol_prefer_tcp` (True/False based on performance)
2. Disable IPv6 if showing 0 connections
3. Enable IPv4 dual-stack if available
4. Adjust UPnP/NAT-PMP settings
5. Reset network bindings

**Known Issues Found:**
Research revealed that when binding to a specific VPN interface, only IPv6 traffic sometimes gets through with IPv4 showing disconnected. This suggests protocol-level troubleshooting is critical for dual-stack scenarios.

---

### 4. Bandwidth Intelligence and Dynamic Allocation

**Description:**
Track bandwidth patterns, detect throttling, predict available capacity, and dynamically adjust per-torrent limits based on swarm health and system resources.

**Key Metrics:**
- Actual bandwidth vs configured limits (gap = unused capacity)
- Upload/download ratio and its effect on performance
- Bandwidth stability over time (variance/jitter)
- Per-torrent bandwidth distribution
- Throttling detection (pattern recognition)
- Available system bandwidth (estimate from network card stats)

**Feasibility:** Medium

**Data Sources:**
- `/api/v2/transfer/info` - Global dl/ul speeds, rate limits
- `/api/v2/torrents/info` - Per-torrent speeds
- `psutil.net_io_counters()` - System-wide bandwidth
- Historical metrics (deque-based trending)

**Implementation Details:**
```python
class BandwidthIntelligence:
    def analyze_bandwidth_patterns(self) -> BandwidthReport:
        stats = api_client.get_transfer_info()
        # Track: actual_dl vs limit_dl gap
        # Detect if upload is capping download (known issue)
        # Flag if recent_speeds << historical_max
        # Calculate sustainable bandwidth for active torrents
        # Recommend limit adjustments per torrent
        
    def predict_available_bandwidth(self) -> int:
        # Estimate unused capacity for new torrents
        # Based on current allocation vs system resources
```

**Impact on Performance:** Low (uses existing metrics)

**Integration Points:**
- Extend `monitoring/metrics.py` with historical trending
- Inform `dynamic_limits` recovery strategy
- Populate adaptive bandwidth scheduler

**Recovery Actions:**
1. Adjust global download/upload limits
2. Redistribute limits across active torrents
3. Pause lowest-priority torrents if network saturated
4. Reduce connections per torrent to lower overhead
5. Enable upload rate limiting if detected as bottleneck

**Research Finding:**
A critical optimization: setting upload limits too low dramatically slows downloads through the torrent protocol's choking mechanism. The agent should monitor this ratio and warn when imbalanced.

---

### 5. Advanced Metrics: Piece Download Speeds and Connection Distribution

**Description:**
Monitor piece-level download metrics to detect slow pieces, missing data, and optimize download priorities. Track connection efficiency to identify over/under-utilized peers.

**Key Metrics:**
- Average piece download time (should track which pieces are slow)
- Bytes downloaded per active connection (efficiency)
- Connections/torrent distribution (load balancing)
- First/last piece priority effects (completion time)
- Block request queue depth and response times
- Piece hash verification time (slow disks vs normal)

**Feasibility:** Medium-Hard

**Data Sources:**
- `/api/v2/torrents/pieces` - Per-piece download status and hash verification
- `/api/v2/torrents/info` - Overall progress metrics
- `/api/v2/torrents/{hash}/peers` - Individual peer speeds
- System disk performance (`iostat`, `fio`)

**Implementation Details:**
```python
class PieceMetricsAnalyzer:
    def analyze_piece_distribution(torrent_hash: str) -> PieceMetricsReport:
        pieces = api_client.get_torrent_pieces(torrent_hash)
        # Group by state: not_downloaded, downloading, done, hash_failed
        # Calculate piece_count / time_elapsed = piece_rate
        # Identify "slow piece" if download_time > 2x average
        # Flag if hash failures > 0.1% (indicates disk corruption)
        
    def analyze_connection_efficiency(torrent_hash: str) -> ConnectionReport:
        peers = api_client.get_torrent_peers(torrent_hash)
        # bytes_downloaded / connection_duration = efficiency
        # Find underutilized connections (< 10KB/s)
        # Recommend disconnecting lowest-efficiency peers
```

**Impact on Performance:** Medium (piece data can be large, cache aggressively)

**Integration Points:**
- Extend `TorrentHealthAnalyzer` with piece-level detail
- Inform priority/queueing decisions in recovery
- Detect disk I/O bottlenecks

**Recovery Actions:**
1. Prioritize slow pieces for expedited download
2. Pause non-essential torrents to free bandwidth
3. Reduce piece block size if hash failures detected
4. Move torrent to faster storage (if available)
5. Disconnect slowest peers and retry handshakes

---

### 6. Predictive Recovery: Early Warning System

**Description:**
Detect early signs of degradation before complete lag occurs. Use machine learning or heuristic rules to identify patterns that precede failures (lagging, stalling, crashing).

**Key Indicators:**
- Speed trending downward over N samples
- Peer count declining consistently
- Hash failure rate increasing
- DHT node count dropping
- Memory/CPU trending upward
- Connection timeouts increasing
- Tracker announce failures

**Feasibility:** Easy-Medium

**Data Sources:**
- Historical deque of metrics (already in `LagDetector.metrics_history`)
- Extended history for trend analysis (longer windows)
- Error/warning logs from qBittorrent

**Implementation Details:**
```python
class PredictiveRecoveryEngine:
    def detect_degradation_patterns(self) -> DegradationAlert:
        # Simple linear regression on 5-min windows
        # Flag if speed_trend < -50KB/s per min
        # Flag if peer_count declining at > 5% per min
        # Flag if hash_failures trending upward
        # Trigger recovery at YELLOW alert before RED
        
    def calculate_time_to_failure(self) -> Optional[datetime]:
        # Extrapolate current trends to predict critical state
        # If peer_count declining: days until 0 peers?
        # If memory growing: hours until OOM?
```

**Impact on Performance:** Low (uses existing metrics)

**Integration Points:**
- Extend `LagDetector` with trend prediction
- Trigger early recovery actions (before lag_score threshold)
- Feed into alert system with ETA

**Recovery Actions:**
1. Preemptively pause least-healthy torrents
2. Trigger connection refresh before completely stalled
3. Perform preventive recheck on vulnerable torrents
4. Auto-adjust limits before system crashes
5. Send early warning alerts (yellow, orange, red)

**Implementation Approach:**
Use simple statistical methods (mean, std dev, trend line) rather than complex ML. This keeps the agent lightweight and predictable.

---

### 7. Auto-Cleanup: Identify and Remove Problematic Torrents

**Description:**
Automatically identify torrents that are permanently stuck, corrupted, or unprofitable, and optionally remove them to free resources.

**Criteria for Removal:**
- No peers for >N hours (stalled permanently)
- 0% progress for >N hours
- Hash failures exceeding threshold (corrupted data)
- Seed ratio exceeded but torrent still downloading (misconfiguration)
- Torrent size exceeds available disk space
- Same torrent already exists (duplicate)

**Feasibility:** Medium

**Data Sources:**
- `/api/v2/torrents/info` - State, progress, added_on, seen_complete, upspeed
- `/api/v2/torrents/trackers` - Tracker status (all dead?)
- Disk free space from `/api/v2/transfer/info`
- Hash of torrent content (duplicate detection)

**Implementation Details:**
```python
class AutoCleanupManager:
    def identify_problematic_torrents(self) -> List[ProblematicTorrent]:
        torrents = api_client.get_torrents()
        problems = []
        
        for torrent in torrents:
            # Check: no peers + stalled
            if torrent['num_seeds'] + torrent['num_leechs'] == 0:
                if time_stalled(torrent) > 3600:  # 1 hour
                    problems.append(TorrentIssue.NO_PEERS)
            
            # Check: 0% progress + stalled
            if torrent['progress'] == 0 and time_added(torrent) > 86400:
                problems.append(TorrentIssue.STUCK)
            
            # Check: corrupted (high hash failure rate)
            # ... (requires per-piece analysis from feature #5)
            
            # Check: duplicate (same infohash already exists)
            # ... (requires bloom filter or hash table)
        
        return problems
    
    def cleanup_torrent(torrent_hash: str, strategy: str):
        # strategy: pause_only | remove_torrent | remove_with_files
```

**Impact on Performance:** Low (one API call, filtered locally)

**Integration Points:**
- Use `TorrentHealthAnalyzer` results
- Add optional automatic cleanup flag (default: pause_only)
- Track cleanup actions in detailed logs
- Integrate with seed ratio management

**Recovery Actions:**
1. Pause problematic torrent
2. Log issue details for user review
3. Optionally remove torrent metadata (keep files)
4. Optionally delete torrent + files
5. Send notification to user

**Safety Measures:**
- Default behavior: pause only (never auto-delete)
- Require explicit enable for destructive operations
- Log all removals with full torrent details
- Keep removal history for recovery (7 days)
- Provide manual override commands

---

### 8. Network Optimization: Connection Pooling and Rate Limiting

**Description:**
Optimize connection pooling strategies, implement adaptive rate limiting, and fine-tune protocol parameters to maximize throughput and stability.

**Key Parameters to Optimize:**
- Max connections (global and per-torrent)
- Max half-open connections (connection establishment limit)
- Connection timeout values
- Rate limiting buckets (algorithm selection)
- Buffer sizes for read/write
- TCP window scaling settings
- µTP/TCP mode selection (prefer_tcp, peer_proportional)

**Feasibility:** Medium

**Data Sources:**
- `/api/v2/app/preferences` - All qBittorrent settings
- System-level socket stats
- Libtorrent settings_pack (underlying engine)

**Implementation Details:**
```python
class NetworkOptimizer:
    def optimize_connection_pooling(self) -> OptimizationPlan:
        prefs = api_client.get_preferences()
        stats = api_client.get_server_state()
        
        # Rule: max_connections = 500 + (available_bandwidth_mbps * 10)
        # Rule: max_half_open = min(20, max_connections / 25)
        # Rule: connections_per_torrent = max_connections / active_torrent_count
        
        # Detect if current settings are causing bottlenecks
        if actual_conns < max_conns * 0.5:
            # Unused capacity - can increase limits
            pass
        
    def apply_rate_limiting_strategy(self, strategy: str):
        # Strategy: token_bucket | leaky_bucket | window_based
        # Also consider: apply_to_utp, include_overhead, alt_speeds
```

**Impact on Performance:** Low-Medium (preference updates are asynchronous)

**Integration Points:**
- Extend `dynamic_limits` recovery strategy
- Use `BandwidthIntelligence` metrics
- Hook into periodic tuning loop

**Tuning Actions:**
1. Increase max_connections if utilizing < 50% of limit
2. Decrease if causing context-switch overhead
3. Adjust per-torrent limits based on swarm health
4. Enable µTP/TCP mixed mode intelligently
5. Configure rate limiting buckets dynamically

**Research Finding:**
qBittorrent recommends max half-open connections no higher than 10-20 to avoid excessive socket churn. The agent should monitor this and warn/adjust if exceeded.

---

### 9. Seed Ratio Management: Auto-Pause/Stop Based on Ratios

**Description:**
Implement advanced seed ratio management beyond qBittorrent's native controls. Auto-pause or remove torrents based on configurable ratio/time limits, with per-category overrides.

**Key Features:**
- Global seed ratio limits (0.5x, 1.0x, 2.0x, etc.)
- Per-torrent overrides (important content: no limit)
- Time-based seeding (seed for N hours, then pause)
- Hybrid mode (seed until ratio OR time, whichever comes first)
- Pause vs. Remove decision logic
- Seed ratio resume (resume when ratio drops below X)

**Feasibility:** Easy

**Data Sources:**
- `/api/v2/torrents/info` - seed, upload, progress (for ratio calculation)
- `/api/v2/app/preferences` - seed ratio limit
- Torrent categories/tags for per-group settings

**Implementation Details:**
```python
class SeedRatioManager:
    def manage_seed_ratios(self, seed_ratio_limit: float):
        torrents = api_client.get_torrents(filter='completed')
        
        for torrent in torrents:
            # Calculate current ratio
            ratio = torrent['total_uploaded'] / max(torrent['total_downloaded'], 1)
            
            if ratio >= seed_ratio_limit:
                action = self.decide_action(torrent)  # pause vs remove
                self.apply_action(torrent['hash'], action)
                self.logger.info(f"Stopped seeding {torrent['name']} (ratio: {ratio:.2f})")
    
    def resume_slow_seeds(self):
        # Resume paused torrents if ratio dropped below threshold
        paused = api_client.get_torrents(filter='paused')
        for torrent in paused:
            if should_resume(torrent):
                api_client.resume_torrent(torrent['hash'])
```

**Impact on Performance:** Minimal (one API call)

**Integration Points:**
- Extend `recovery_engine.py` with seed management
- Integrate with auto-cleanup (decide: pause or remove)
- Add configuration options for ratio/time limits

**Management Actions:**
1. Pause torrent when ratio reached
2. Resume torrent if ratio drops below threshold
3. Remove torrent + files when max_seed_time exceeded
4. Per-category overrides (e.g., ISO category: never pause)
5. Notification when action taken

**Configuration Example:**
```ini
[SeedRatioManagement]
enabled = true
global_ratio_limit = 2.0
global_time_limit = 604800  # 7 days in seconds
important_category_ratio = 0  # No limit for important
```

---

### 10. Alert System: Email/Webhook Notifications

**Description:**
Send alerts to external systems (email, Discord, Slack, Ntfy.sh, Webhook) when critical issues are detected. Support filtering, throttling, and digest modes.

**Alert Types:**
- CRITICAL: Lag score > 85, about to restart
- ERROR: Recovery strategy failed, torrent corrupted, disk full
- WARNING: Lag detected, peer issues, protocol problems
- INFO: Torrent completed, seed ratio reached, cleanup performed
- DEBUG: Configuration changes, tuning actions (optional)

**Feasibility:** Easy

**Data Sources:**
- Log events from detector, recovery, and cleanup modules
- Formatted alert strings with context

**Implementation Details:**
```python
class AlertSystem:
    def send_alert(self, level: str, title: str, message: str, context: dict):
        alert = Alert(level=level, title=title, message=message, context=context)
        
        # Route based on level
        if level == "CRITICAL":
            self.send_email(alert)
            self.send_webhook(alert, "critical")
        elif level == "WARNING":
            if self.should_throttle(alert):  # Rate limit
                return
            self.send_webhook(alert, "warning")
        elif level == "INFO":
            if self.digest_mode:
                self.buffer_for_digest(alert)
                return
            self.send_webhook(alert, "info")

class EmailNotifier:
    def send_email(self, alert: Alert):
        # Use smtplib or sendmail
        subject = f"[qBittorrent] {alert.level}: {alert.title}"
        body = format_email_body(alert)
        # Send to configured email address
    
class WebhookNotifier:
    def send_webhook(self, alert: Alert, channel: str):
        # Send to Discord, Slack, custom webhook, Ntfy.sh
        payload = {
            'level': alert.level,
            'title': alert.title,
            'message': alert.message,
            'timestamp': datetime.now().isoformat(),
            'context': alert.context
        }
        # POST to configured webhook URL
```

**Impact on Performance:** Low (async/background sending)

**Integration Points:**
- Modify logger to emit structured alerts
- Hook into detector, recovery, and cleanup modules
- Add configuration for notification endpoints

**Configuration Example:**
```ini
[Notifications]
enabled = true

[Notifications.Email]
enabled = false
smtp_server = smtp.gmail.com
smtp_port = 587
from_address = agent@example.com
to_addresses = admin@example.com
level_threshold = WARNING

[Notifications.Webhook]
enabled = true
discord_webhook = https://discord.com/api/webhooks/...
slack_webhook = https://hooks.slack.com/services/...
custom_webhook = https://ntfy.sh/qbittorrent_alerts
level_threshold = WARNING

[Notifications.Throttling]
max_alerts_per_hour = 10
similar_alert_dedupe_minutes = 5

[Notifications.Digest]
enabled = false
send_time = 08:00  # Daily digest at 8am
```

**Alert Routing Logic:**
- CRITICAL → All channels (email + webhooks)
- ERROR → Webhooks only
- WARNING → Webhooks only (with throttling)
- INFO → Optional digest mode
- DEBUG → Disabled by default

**Safety Considerations:**
- Never send API credentials in alerts
- Mask sensitive paths (IP addresses, file paths)
- Include context but keep messages concise
- Provide action recommendations
- Include link to logs for investigation

---

## Implementation Priority

### Phase 1 (High Impact, Easy): Weeks 1-2
1. **Torrent Health Analysis** - Foundation for other features
2. **Seed Ratio Management** - Simple, immediate resource savings
3. **Predictive Recovery** - Minimal code, high value
4. **Alert System** - Critical for operational awareness

### Phase 2 (Medium Impact, Medium Effort): Weeks 3-4
5. **Bandwidth Intelligence** - Improves performance significantly
6. **Piece Download Metrics** - Enhanced diagnostics
7. **Auto-Cleanup** - Frees resources automatically

### Phase 3 (Advanced, Optional): Weeks 5+
8. **Peer Analysis** - Complex but powerful
9. **Protocol Optimization** - System-level integration
10. **Connection Pooling** - Fine-tuning for advanced users

---

## Architecture Changes Required

### New Modules

**`monitoring/torrent_analyzer.py`**
- `TorrentHealthAnalyzer` class
- Piece distribution analysis
- Connection efficiency metrics

**`monitoring/bandwidth_analyzer.py`**
- `BandwidthIntelligence` class
- Pattern detection and trending
- Throttling detection

**`monitoring/protocol_analyzer.py`**
- `ProtocolOptimizer` class
- IPv4/IPv6/TCP/µTP metrics
- Socket-level analysis

**`recovery/cleanup_manager.py`**
- `AutoCleanupManager` class
- Problematic torrent detection
- Safe removal strategies

**`recovery/seed_manager.py`**
- `SeedRatioManager` class
- Ratio/time-based actions
- Per-category overrides

**`alerting/alert_system.py`**
- `AlertSystem` class
- Multiple notifiers (email, webhook, Discord, Slack)
- Alert filtering and throttling

### Modified Modules

**`detectors/lag_detector.py`**
- Integrate torrent health scores
- Add predictive degradation detection
- Expand trend analysis

**`recovery/recovery_engine.py`**
- Add auto-cleanup strategy
- Add seed ratio management
- Add network optimization tuning

**`monitoring/metrics.py`**
- Add protocol-level metrics
- Add extended history for predictions
- Add GeoIP peer tracking (optional)

**`qbittorrent_agent.py`**
- Initialize new analyzers
- Hook alert system into main loop
- Add feature flags for selective enable/disable

---

## Data Storage Considerations

### In-Memory State (deque, dict)
- Metrics history (rolling 5-10 minutes)
- Peer state cache (updated once per torrent per check)
- Connection efficiency tracking

### Disk-Based State (optional, JSON/SQLite)
- Alert history (for deduplication)
- Cleanup history (for reversal/recovery)
- Performance statistics (for trending over days/weeks)
- Configuration overrides (per-torrent rules)

### API Caching
- Cache `/api/v2/torrents/info` for 30 seconds
- Cache `/api/v2/transfer/info` for 5 seconds
- Cache preferences for 5 minutes
- Cache peers list for 60 seconds (expensive)

---

## Testing Strategy

### Unit Tests
- Torrent health scoring logic
- Peer analysis algorithms
- Bandwidth trending calculations
- Alert filtering and routing

### Integration Tests
- Full lag detection with new analyzers
- Recovery strategy execution with cleanup
- Alert system end-to-end
- Configuration override behavior

### Manual Testing Scenarios
1. Stalled torrent (0 peers) → Should trigger cleanup warning
2. Very slow torrent (< 10KB/s) → Should trigger health alert
3. High lag score → Should trigger predictive recovery
4. Seed ratio exceeded → Should trigger pause + notification
5. Hash failure detected → Should flag corruption + recommendation
6. Protocol mismatch (IPv6 only) → Should trigger protocol optimization

---

## Configuration Schema

Add to `qbittorrent.conf` or separate `agent_config.ini`:

```ini
[Features]
torrent_health_analysis = true
peer_analysis = true
protocol_optimization = true
bandwidth_intelligence = true
piece_metrics = true
predictive_recovery = true
auto_cleanup = true
network_optimization = true
seed_ratio_management = true
alert_system = true

[TorrentHealth]
stalled_threshold_minutes = 10
availability_warning_percent = 20
slow_piece_threshold_seconds = 60
hash_failure_warning_rate = 0.001

[AutoCleanup]
enabled = false  # Default: disabled (pause only)
no_peers_threshold_hours = 1
stuck_threshold_hours = 24
remove_on_cleanup = false  # If true, delete files

[SeedRatioManagement]
enabled = true
global_ratio_limit = 2.0
global_time_limit = 604800
pause_on_ratio = true
resume_on_ratio_drop = true

[Notifications]
enabled = true
critical_channels = email,webhook
warning_throttle = 10  # Max 10 per hour
digest_enabled = false
digest_time = 08:00
```

---

## Backward Compatibility

All new features are **opt-in** via configuration flags. Default behavior unchanged:
- Existing lag detection continues unchanged
- Recovery strategies execution unchanged
- New analyzers disabled by default until explicitly enabled
- No new required dependencies

Migration path:
1. Deploy with all features disabled
2. Enable one feature at a time
3. Monitor for 1 week
4. Enable next feature

---

## Known Limitations and Future Work

### Limitations
- Peer analysis requires `/api/v2/torrents/{hash}/peers` endpoint (available in qBT 4.1+)
- Piece analysis expensive for large torrents (>10,000 pieces)
- Protocol optimization requires system-level socket access (might need elevated privileges)
- GeoIP-based peer analysis requires external IP database
- Alert system requires SMTP/webhook infrastructure

### Future Enhancements
- Machine learning for predictive failure (degradation pattern detection)
- Advanced swarm analysis with peer reputation scoring
- Torrent swarm simulation (predict completion time given current peers)
- Bandwidth forecasting (predict future available bandwidth)
- Disk performance profiling
- Encrypted peer detection and handling
- Integration with Sonarr/Radarr for completion notifications

---

## Research Sources

### qBittorrent Web API Documentation
- [qBittorrent Web API v5.0 - GitHub Wiki](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-(qBittorrent-5.0))
- [qbittorrent-api Python Package](https://qbittorrent-api.readthedocs.io/)
- [qbittorrent-api GitHub](https://github.com/qbittorrent/qBittorrent)

### Performance and Optimization
- [Best qBittorrent Settings 2026](https://www.rapidseedbox.com/blog/qbittorrent-settings)
- [qBittorrent Stalled Fix Guide](https://www.rapidseedbox.com/blog/qbittorrent-stalled)
- [Speed Up qBittorrent Downloads](https://www.makeuseof.com/speed-up-downloads-qbittorrent/)

### Protocol and Network Optimization
- [Libtorrent Reference - Settings Pack](https://www.libtorrent.org/reference-Settings.html)
- [GitHub Issue: IPv4/IPv6 Mixup](https://github.com/qbittorrent/qBittorrent/issues/14552)
- [GitHub Issue: Protocol Performance](https://github.com/qbittorrent/qBittorrent/issues/16359)

### Health Monitoring Tools
- [qBitrr Health Monitoring Documentation](https://feramance.github.io/qBitrr/features/health-monitoring/)
- [Grafana Dashboard for qBittorrent](https://grafana.com/grafana/dashboards/23784-qbittorrent/)
- [qBittorrent WebUI Stats](https://github.com/gzili/qbittorrent-webui-stats)

### Piece and Corruption Detection
- [Libtorrent Reference Manual](https://libtorrent.org/single-page-ref.html)
- [GitHub Issue: Piece Corruption](https://github.com/arvidn/libtorrent/issues/8198)
- [Rechecking Resume Data Issues](https://valegas.sedes.ma.gov.br/qbittorrent-checking-resume-data/)

### Seed Ratio and Notifications
- [Home Assistant qBittorrent Integration](https://www.home-assistant.io/integrations/qbittorrent/)
- [TRaSH Guides - 3rd Party Tools](https://trash-guides.info/Downloaders/3rd-party-tools/)

---

## Conclusion

These 10 features provide a comprehensive upgrade to the qBittorrent Intelligent Recovery Agent, transforming it from a reactive lag detection system to a proactive health monitoring and optimization platform. By implementing features in priority order, the agent can be incrementally enhanced without overwhelming complexity or risk.

The modular architecture allows features to be independently enabled/disabled, making adoption flexible and low-risk. All features are grounded in actual qBittorrent API capabilities and best practices documented by the community.

**Recommended Next Steps:**
1. Review this proposal with stakeholders
2. Prioritize Phase 1 features based on your deployment needs
3. Create task tickets for Phase 1 implementation
4. Set up testing environment for validation
5. Plan rollout schedule for Phase 2 and 3
