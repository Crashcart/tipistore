# Feature Summary: Quick Reference

## Overview

10 advanced monitoring and recovery features for qBittorrent Intelligent Agent, organized by priority and complexity.

---

## Feature Matrix

| # | Feature | Complexity | Priority | Data Source | Impact | Module |
|---|---------|-----------|----------|-------------|--------|--------|
| 1 | Torrent Health Analysis | Medium | P1 | `/torrents/info` | High | `torrent_analyzer.py` |
| 2 | Peer Analysis | Hard | P3 | `/torrents/{hash}/peers` | Medium | `peer_analyzer.py` |
| 3 | Protocol Optimization | Hard | P3 | `/proc/net/*` | Medium | `protocol_analyzer.py` |
| 4 | Bandwidth Intelligence | Medium | P2 | `/transfer/info` | High | `bandwidth_analyzer.py` |
| 5 | Advanced Metrics | Medium-Hard | P2 | `/torrents/pieces` | Medium | `piece_metrics.py` |
| 6 | Predictive Recovery | Easy-Medium | P1 | Historical metrics | High | `predictive_detector.py` |
| 7 | Auto-Cleanup | Medium | P2 | `/torrents/info` | High | `cleanup_manager.py` |
| 8 | Network Optimization | Medium | P3 | `/app/preferences` | Medium | Recovery engine |
| 9 | Seed Ratio Management | Easy | P1 | `/torrents/info` | High | `seed_manager.py` |
| 10 | Alert System | Easy | P1 | Log events | High | `alert_system.py` |

---

## Phased Rollout Plan

### Phase 1: Foundation (Weeks 1-2)
Essential features that enable everything else:
- **Feature 1: Torrent Health Analysis** - Identifies problematic torrents
- **Feature 6: Predictive Recovery** - Detects degradation early
- **Feature 9: Seed Ratio Management** - Frees resources automatically
- **Feature 10: Alert System** - Operational awareness

**Expected Impact:** 30% reduction in manual intervention, early warnings

### Phase 2: Intelligence (Weeks 3-4)
Analytics and optimization:
- **Feature 4: Bandwidth Intelligence** - Detects throttling and optimizes limits
- **Feature 5: Advanced Metrics** - Piece-level diagnostics
- **Feature 7: Auto-Cleanup** - Removes problematic torrents automatically

**Expected Impact:** 40% improvement in bandwidth utilization, fewer stalled torrents

### Phase 3: Advanced (Weeks 5+)
Fine-tuning for power users:
- **Feature 2: Peer Analysis** - Swarm health metrics
- **Feature 3: Protocol Optimization** - IPv4/IPv6/TCP/µTP tuning
- **Feature 8: Network Optimization** - Connection pool tuning

**Expected Impact:** 50%+ improvement in edge cases, better protocol selection

---

## Common Lag Causes Addressed

| Problem | Feature | Detection | Recovery |
|---------|---------|-----------|----------|
| Stalled torrent (0 peers) | 1, 6 | No seeds/leechs for N hours | Re-announce, add trackers, pause |
| Slow swarm | 2, 4, 5 | <10% available pieces | Trigger peer discovery, pause others |
| Corrupted pieces | 5, 7 | Hash failures trending up | Recheck, move to faster disk |
| Upload bottleneck | 4 | Upload near limit + slow DL | Reduce UL limit temporarily |
| Protocol issues | 3 | IPv6 only, no IPv4 connections | Toggle prefer_tcp, disable IPv6 |
| Disk bottleneck | 5 | Piece verification slow | Check disk health, move to SSD |
| Too many torrents | 7, 9 | Bandwidth spread too thin | Auto-pause low-priority torrents |
| Excessive seeding | 9 | High ratio torrents still active | Pause/remove high-ratio torrents |

---

## API Endpoints Used

### Core Data
- `/api/v2/torrents/info` - Torrent list, progress, speeds, peer counts
- `/api/v2/transfer/info` - Global bandwidth stats, limits
- `/api/v2/app/preferences` - Configuration values

### Analysis Data
- `/api/v2/torrents/{hash}/peers` - Individual peer details (IP, speed, client)
- `/api/v2/torrents/pieces` - Per-piece download status and hashes
- `/api/v2/torrents/trackers` - Tracker status per torrent

### Management
- `/api/v2/torrents/pause` - Pause torrent
- `/api/v2/torrents/resume` - Resume torrent
- `/api/v2/torrents/delete` - Remove torrent
- `/api/v2/app/setPreferences` - Update settings

### Advanced
- `/api/v2/log/peers` - Peer block log (for ban detection)
- `/api/v2/transfer/banPeers` - Ban specific peers

---

## New Configuration Options

### Feature Flags
```ini
[Features]
torrent_health_analysis = true
bandwidth_intelligence = true
auto_cleanup = false  # Disabled by default (destructive)
seed_ratio_management = true
alert_system = true
```

### Thresholds
```ini
[TorrentHealth]
stalled_threshold_minutes = 10
availability_warning_percent = 20
slow_piece_threshold_seconds = 60

[AutoCleanup]
no_peers_threshold_hours = 1
stuck_threshold_hours = 24
remove_on_cleanup = false

[SeedRatioManagement]
global_ratio_limit = 2.0
global_time_limit = 604800  # 7 days

[Notifications]
enabled = true
critical_level = email,webhook
warning_level = webhook
throttle_per_hour = 10
```

---

## Metrics Collected

### Real-Time (Every 60s)
- Download/upload speeds
- Active peer counts
- Torrent progress
- System CPU/memory

### Trending (Last 5-10 minutes)
- Speed trend (up/down)
- Peer count trend
- Hash failure rate trend
- Bandwidth utilization

### Historical (Per-torrent)
- Completion time
- Average speed
- Peer quality distribution
- Stall duration

---

## Alert Types

| Level | Condition | Channel | Action |
|-------|-----------|---------|--------|
| CRITICAL | Lag > 85, about to restart | Email + Discord | Immediate |
| ERROR | Recovery failed, corruption | Discord | Review logs |
| WARNING | Lag detected, peers low | Discord | Monitor |
| INFO | Torrent completed, cleanup done | Optional | Optional |
| DEBUG | Config changes, tuning | Disabled | Disabled |

---

## Performance Considerations

### CPU Usage
- Torrent analysis: ~0.1% per 100 torrents
- Bandwidth analysis: <0.01% (uses cached metrics)
- Peer analysis: ~1% per 100 torrents (expensive, cache 60s)

### Memory Usage
- Metrics history (60 samples): ~50 KB
- Torrent cache (100 torrents): ~100 KB
- Alert history (1000 alerts): ~200 KB
- Total additional: <500 KB

### API Calls
- Baseline (lag detection): 3 calls/60s
- With health analysis: 8 calls/60s
- With peer analysis: 20 calls/60s (cached)
- With all features: ~25 calls/60s (sustainable)

### Caching Strategy
- Server state: 5 second TTL
- Torrent health: 30 second TTL
- Peers: 60 second TTL (most expensive)
- Preferences: 5 minute TTL (rarely changes)

---

## Safety & Guardrails

### Defaults
- All destructive features (cleanup, removal) **disabled by default**
- Alert throttling: 10 alerts/hour (prevents spam)
- Recovery: least invasive strategies first
- Dry-run mode: test without making changes

### Validation
- Config validation before startup
- API connectivity check before action
- Torrent hash validation before removal
- Space check before large operations

### Logging
- All actions logged with timestamps
- Context captured for investigation
- Cleanup history kept for 7 days
- Alert history deduplication

---

## Dependencies

### No New Required Dependencies
- All features use existing Python stdlib or psutil
- qBittorrent Web API v2.0+ (already required)

### Optional Dependencies
- `smtplib` - Email notifications (stdlib)
- `requests` - Webhook notifications (already required)
- `geoip2` - Geographic peer analysis (optional)

---

## Rollout Checklist

### Pre-Deployment
- [ ] Review all new code with team
- [ ] Load test with 100+ torrents
- [ ] Verify API endpoint availability
- [ ] Set up alert channels (email/webhook)
- [ ] Create test configuration

### Deployment Phase 1
- [ ] Deploy with P1 features
- [ ] Monitor for 1 week
- [ ] Verify lag detection working
- [ ] Verify alerts functioning
- [ ] Measure CPU/memory impact

### Deployment Phase 2
- [ ] Enable P2 features
- [ ] Validate bandwidth analysis
- [ ] Verify no false positives
- [ ] Measure performance improvement

### Deployment Phase 3
- [ ] Enable optional P3 features
- [ ] Fine-tune thresholds
- [ ] Optimize caching strategy
- [ ] Document custom settings

---

## Monitoring the Monitor

### Health Checks
- Agent uptime
- API connectivity
- Disk space for logs
- Memory usage trending
- Alert system latency

### Metrics to Track
- Lag detections per day
- Recovery actions triggered
- Average lag score
- Torrents cleaned up
- Alerts sent per level

---

## Troubleshooting

### High False Positive Rate
→ Increase lag detection thresholds (conservative mode)

### Missing Peer Data
→ Verify `/api/v2/torrents/{hash}/peers` endpoint available (qBT 4.1+)

### Alerts Not Sending
→ Check webhook URLs, SMTP settings, verify connectivity

### High CPU Usage
→ Reduce monitoring interval, disable peer analysis, increase cache TTL

### Out of Memory
→ Reduce metrics history size, decrease alert history limit

---

## Success Metrics

After 1 month of deployment, target:
- **30%** reduction in stalled torrents
- **40%** improvement in average speeds
- **50%** less manual intervention
- **0** unhandled exceptions in logs
- **<1 second** median alert latency

---

## References

- **API Docs:** [qBittorrent Web API v5.0](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-(qBittorrent-5.0))
- **Optimization Guide:** [Best qBittorrent Settings 2026](https://www.rapidseedbox.com/blog/qbittorrent-settings)
- **Troubleshooting:** [qBittorrent Stalled Torrents](https://www.rapidseedbox.com/blog/qbittorrent-stalled)
- **Health Monitoring:** [qBitrr Documentation](https://feramance.github.io/qBitrr/features/health-monitoring/)

---

## Next Steps

1. **Review** - Share this proposal with team, get feedback
2. **Prioritize** - Confirm Phase 1 features match your needs
3. **Plan** - Create detailed tickets for Phase 1
4. **Code** - Implement following `IMPLEMENTATION_GUIDE.md`
5. **Test** - Unit tests + integration tests
6. **Deploy** - Gradual rollout with monitoring
7. **Iterate** - Gather feedback, optimize thresholds

