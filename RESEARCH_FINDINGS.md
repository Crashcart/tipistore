# Research Findings: qBittorrent API & Optimization

This document summarizes research conducted on qBittorrent Web API capabilities, common lag causes, and optimization best practices.

---

## qBittorrent Web API Capabilities

### Current Version
- **Latest Version:** qBittorrent 5.1.4
- **Web API Version:** v2.11.4 (as of November 2025)
- **Python Client:** qbittorrent-api 2025.11.2+
- **Documentation:** [GitHub Wiki - WebUI API v5.0](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-(qBittorrent-5.0))

### Available Data Endpoints

#### Torrent Information (`/api/v2/torrents/info`)
**Returns:**
- `hash` - Unique torrent identifier
- `name` - Torrent name
- `state` - Current state (downloading, uploading, paused, etc.)
- `progress` - Completion percentage
- `num_seeds` - Number of seeds in swarm
- `num_leechs` - Number of leechers in swarm
- `num_complete` - Number of peers with 100%
- `num_incomplete` - Number of peers with < 100%
- `availability` - Percentage of pieces available in swarm
- `dl_speed` - Current download speed (bytes/sec)
- `up_speed` - Current upload speed (bytes/sec)
- `total_downloaded` - Total bytes downloaded
- `total_uploaded` - Total bytes uploaded
- `added_on` - Timestamp when added
- `completion_on` - Timestamp when completed
- `seen_complete` - Timestamp when last seed seen
- `eta` - Estimated completion time

**Critical for:** Torrent health analysis, stall detection, seed ratio management

#### Transfer Statistics (`/api/v2/transfer/info`)
**Returns:**
- `dl_info_speed` - Global download speed
- `up_info_speed` - Global upload speed
- `dl_info_data` - Total downloaded this session
- `up_info_data` - Total uploaded this session
- `dl_rate_limit` - Download rate limit (0 = unlimited)
- `up_rate_limit` - Upload rate limit (0 = unlimited)
- `dht_nodes` - Number of DHT nodes connected
- `total_peer_connections` - Active peer connections
- `total_torrents_count` - Total torrents tracked
- etc.

**Critical for:** Bandwidth intelligence, throttling detection

#### Peer Information (`/api/v2/torrents/{hash}/peers`)
**Returns per peer:**
- `ip` - Peer IP address
- `port` - Peer port number
- `client` - Client version/name
- `dl_speed` - Download speed from this peer
- `up_speed` - Upload speed to this peer
- `progress` - Peer's progress percentage
- `flags` - Flags (e.g., "X" = timeout/blocked)

**Critical for:** Peer analysis, swarm health, quality assessment

**Note:** Introduced in qBittorrent 4.1 (Web API v2.0). Some older versions may have limited peer data.

#### Piece Information (`/api/v2/torrents/{hash}/pieces`)
**Returns per piece:**
- `hashes` - Individual piece hashes (for V2 torrents)
- `availability` - Number of peers with this piece
- `state` - Downloaded, missing, downloading, etc.

**Critical for:** Corruption detection, missing piece analysis

#### Server State (`/api/v2/app/serverState`)
**Returns:**
- All of transfer/info data combined with:
- `proxy_type` - Proxy configuration
- `private_mode` - If private mode enabled
- etc.

**Critical for:** Overall health snapshot

#### Preferences (`/api/v2/app/preferences`)
**Returns:**
- `max_active_downloads` - Max downloading torrents
- `max_active_torrents` - Max active torrents
- `max_connections` - Global connection limit
- `max_connections_per_torrent` - Per-torrent limit
- `max_half_open` - Max half-open connections
- `listen_port` - Listening port
- `use_upnp` - UPnP enabled
- `use_pex` - Peer exchange enabled
- `dht` - DHT enabled
- `ltep` - Extensions enabled
- `bittorrent/protocol_prefer_tcp` - TCP preference
- etc.

**Critical for:** Protocol optimization, connection tuning

#### Tracker Status (`/api/v2/torrents/{hash}/trackers`)
**Returns per tracker:**
- `url` - Tracker URL
- `status` - Working, disabled, not contacted, etc.
- `num_peers` - Peers from this tracker
- `num_seeds` - Seeds from this tracker
- `num_leeches` - Leeches from this tracker

**Critical for:** Detecting dead trackers, swarm health

#### Peer Logs (`/api/v2/log/peers`)
**Returns:**
- `ip` - Peer IP
- `timestamp` - When blocked/banned
- `blocked` - If blocked by user

**Critical for:** Detecting ban patterns, malicious peers

---

## Common Lag Causes & Solutions

### 1. Stalled Torrents (No Peers)

**Symptoms:**
- 0% progress after 1+ hours
- 0 seeds + 0 leechers in swarm
- "Checking resume data" stuck for days

**Root Causes:**
- Torrent is very new (no seeds yet)
- Torrent is dead (no active seeders)
- Network connectivity issue
- Tracker unavailable

**Detection:**
```python
if torrent['num_seeds'] + torrent['num_leechs'] == 0:
    if time_since_added > 3600:  # 1 hour
        ALERT: "Stalled: No peers available"
```

**Solutions:**
1. Re-announce to trackers (forces update)
2. Add backup trackers with good peer counts
3. Check if peer list is being retrieved
4. Pause and resume torrent (resets internal state)
5. If >24 hours, likely dead - pause or remove

### 2. Slow Swarms

**Symptoms:**
- Only 1-2 seeds
- Seed/leech ratio 100:1+ (all seeds, no leechers)
- Download < 10 KB/s despite good connection

**Root Causes:**
- Torrent was popular then abandoned
- Seeds have limited upload capacity
- All seeders are on slow connections

**Detection:**
```python
if torrent['num_seeds'] > 0 and torrent['num_leechs'] == 0:
    ALERT: "Slow swarm: Only seeds available"

if availability < 20:  # <20% of pieces in swarm
    ALERT: "Low availability: {availability}%"
```

**Solutions:**
1. Nothing can fix this - seeds are slow
2. Option: Pause torrent, resume later when more leechers join
3. Accept slow speed or remove torrent

### 3. Corrupted/Incomplete Pieces

**Symptoms:**
- Hash check failures
- "Checking resume data" hangs
- Some pieces won't download/verify

**Root Causes:**
- Disk corruption or bad sectors
- Network packet corruption
- Resume data mismatch (torrent moved/modified)

**Detection:**
```python
# Track hash_failures over time
if hash_failures > 0 and trending_up:
    ALERT: "Possible corruption: hash failures increasing"
```

**Solutions:**
1. Force recheck all pieces (slow but safe)
2. Move torrent to different storage (test if disk issue)
3. If persists: remove torrent, re-download
4. Check disk health (`smartctl`, `fsck`)

### 4. Upload Limit Throttling Download

**Symptoms:**
- Upload speed near limit
- Download speed drops significantly when upload maxes out
- Can't achieve theoretical max bandwidth

**Root Causes:**
- TCP congestion control: if upload saturates, TCP stack throttles download
- Rate limiting applied to both DL+UL
- Upload overhead (ACK packets) takes download capacity

**Detection:**
```python
if upload_speed / upload_limit > 0.8 and upload_limit > 0:
    if download_speed < historical_average * 0.7:
        ALERT: "Upload may be throttling download"
```

**Solutions:**
1. **CRITICAL:** Don't set upload limit too low!
   - Rule: UL_limit should be ~30% of connection speed
   - Setting UL_limit = 100KB/s can kill 10Mbps connection
2. Never leave upload unlimited on consumer connections (bufferbloat)
3. Increase UL_limit if DL improved
4. Use dynamic adjustment based on load

**Research Finding (Important):**
> "Limiting upload rates compromises download rates through the torrent client's choking mechanism, making downloads much slower. Upload speed directly controls download performance; if upload saturates your connection, peer negotiation stalls."

### 5. Protocol Issues: IPv4 vs IPv6

**Symptoms:**
- IPv6 enabled but showing only IPv6 connections
- IPv4 connections showing X (timeout)
- Dual-stack host not working properly

**Root Causes:**
- VPN/interface binding forcing one protocol only
- ISP has IPv6 but it's broken
- IPv4 firewall blocking
- Dual-stack not properly configured

**Detection:**
```python
# Monitor connection protocol distribution
ipv4_count = count_socket_connections('AF_INET')
ipv6_count = count_socket_connections('AF_INET6')

if ipv6_enabled and ipv4_count == 0:
    ALERT: "IPv6 only, no IPv4 connections"
    RECOMMEND: "Check IPv4 connectivity or disable IPv6"
```

**Solutions:**
1. Check both IPv4 and IPv6 are working
2. If one is broken, disable it in preferences
3. Don't bind to specific interface (use 0.0.0.0)
4. Test with `curl http://ipv4.test.local` and `curl http://ipv6.test.local`

**Research Finding:**
> "When binding to specific interface, only IPv6 traffic gets through with IPv4 addresses showing X and disappearing after seconds. qBittorrent-nox on dual-stack hosts is unable to communicate with IPv6 peers when interface binding is used."

### 6. TCP vs µTP (uTP) Performance

**Symptoms:**
- Inconsistent speeds
- Fluctuating performance with same torrent
- Can't tell if connection type matters

**Root Causes:**
- µTP (Micro Transport Protocol) designed to yield to TCP
- Mixed TCP/µTP swarms have complex behavior
- Prefer_tcp mode setting mismatch

**Solutions:**
1. Monitor current protocol distribution
2. If mostly µTP and slow: try prefer_tcp = true
3. If mostly TCP and you have spare bandwidth: try prefer_tcp = false
4. Watch for improvement and adjust accordingly

### 7. Port/Firewall Issues

**Symptoms:**
- Can't accept incoming connections
- UPnP/NAT-PMP not working
- Listening port shows as closed

**Detection:**
```python
# Check if port is actually listening
import socket
sock = socket.socket()
try:
    sock.connect(('localhost', listen_port))
    sock.close()
    # Port is open locally
except:
    ALERT: "Listening port not responding"
```

**Solutions:**
1. Enable UPnP/NAT-PMP in qBittorrent
2. Manually forward port if router doesn't support UPnP
3. Verify port is not blocked by firewall
4. Use port tester service to verify external visibility

### 8. Too Many Active Torrents

**Symptoms:**
- Bandwidth spread thin
- All torrents get low speeds
- CPU/memory high

**Root Causes:**
- Connections distributed across too many torrents
- Limit connections reached, not being used effectively
- Memory bloat from metadata

**Detection:**
```python
active = count_active_torrents()
max_conns = get_max_connections()
avg_conns_per = max_conns / active

if avg_conns_per < 5:
    ALERT: "Too many torrents, connections spread thin"
```

**Solutions:**
1. Pause lowest-priority torrents
2. Increase global connection limit if system can handle
3. Increase per-torrent connection limit
4. Auto-pause torrents with ratio > X

---

## Optimization Best Practices

### Connection Settings

**Maximum Connections (Global)**
```
Recommended: 500 + (available_bandwidth_mbps * 10)
Examples:
- 10 Mbps connection: 600 connections
- 100 Mbps connection: 1500 connections
- 1 Gbps connection: 10000 connections (test carefully)

Minimum: 50 (never lower)
```

**Maximum Connections Per Torrent**
```
Recommended: 100-200 for most torrents
Formula: global_max / (active_torrents * 2)

More connections = more peers tried = faster discovery
Too many = overhead and connection failures
```

**Maximum Half-Open Connections**
```
CRITICAL: max 10-20 (never higher)
Too many = excessive socket churn, system overload
```

### Rate Limiting

**Upload Limit**
```
Rule of Thumb:
- Never leave unlimited on consumer connections (bufferbloat)
- Set to ~30% of available bandwidth
- If 100 Mbps connection: set to 30 Mbps (3.75 MB/s)

Example calculation:
- Available bandwidth: 100 Mbps = 12.5 MB/s
- Upload limit: 30% = 3750 KB/s
- Download should still get: ~8.75 MB/s
```

**Download Limit**
```
Set to: available_bandwidth * 0.8 (leave 20% headroom)
Or leave unlimited if upload limit set properly
```

### Protocol Settings

**Prefer TCP (bittorrent/protocol_prefer_tcp)**
```
Default: false (allow µTP)

Change to true if:
- Mostly TCP peers and good bandwidth
- µTP connections getting starved

Change to false if:
- Want to maximize utilization
- Have many µTP peers
```

**DHT, PEX, LSD (Local Peer Discovery)**
```
Enable ALL THREE for maximum peer discovery:
- DHT: Decentralized network (don't rely on trackers)
- PEX: Peer exchange (peers tell you about other peers)
- LSD: Find local peers on same network (fast)
```

### Piece Priority Strategy

**First/Last Piece Priority**
```
Enable this to:
- Complete torrents faster (first pieces allow start)
- Preview files before complete (last pieces)

Disable if:
- Limited bandwidth (jump around = slower overall)
```

### Advanced Tuning (libtorrent settings)

These are set via qBittorrent preferences but require understanding:

```
max_connections: Don't exceed system limits (/proc/sys/fs/file-max)
max_open_files: Related to above

connection_speed: How many connections per second
(Higher = faster peering, but more overhead)

peer_turnover: Aggressively drop dead connections
(Higher = more aggressive cleanup, lower = loyal to peers)

request_queue_size: Block request pipeline
(Higher = faster, but more retransmits if unreliable)

mixed_mode_algorithm: TCP/µTP mixing strategy
(prefer_tcp=0, prefer_utp=1, proportional=2)
```

---

## Torrent Health Metrics Reference

### Piece Availability
```
Definition: Percentage of unique pieces available in swarm

Rule of Thumb:
- >90%: Excellent, fast download
- 50-90%: Good, normal download
- 20-50%: Degraded, will be slow
- <20%: Poor, very slow download
- 0%: Impossible (wait for seeder)

Impact: Each missing piece requires special effort to find
```

### Seed/Leech Ratio
```
Definition: Ratio of seeds to leechers

Rule of Thumb:
- >1.0: More seeds than leechers (good for downloading)
- 0.5-1.0: Balanced (normal)
- <0.5: Few seeds (may be slow)
- <0.1: Mostly leechers (very slow)

Impact: Leechers can't provide full pieces, only parts
Seeds can provide complete pieces (faster)
```

### Peer Quality Score (Custom)
```
Classify peers as:
- FAST (>1 MB/s): Premium, prioritize
- NORMAL (100 KB/s - 1 MB/s): Regular
- SLOW (1-100 KB/s): Low priority
- DEAD (<1 KB/s): Disconnect

Percentage breakdown indicates swarm health:
- >70% FAST: Excellent swarm
- >50% NORMAL: Good swarm
- >70% SLOW/DEAD: Poor swarm (slow downloads)
```

### Availability Distribution
```
Instead of single %, track distribution:
- N pieces: 100% (complete in swarm)
- M pieces: 50-99% (redundant)
- K pieces: 1-49% (rare)
- 0 pieces: 0% (missing from swarm)

Alert if many pieces stuck at <10%
```

---

## Performance Impact Analysis

### Storage I/O Bottlenecks

**Indicator: Hash verification slow**
```
Normal: 100-500 MB/s (SSD)
Slow: <50 MB/s (HDD, or controller issue)

Solution:
1. Check disk health: smartctl -a /dev/sdX
2. Monitor disk I/O: iostat -x 1
3. If HDD: move to SSD if possible
4. If controller: check RAID/NVMe settings
```

**Indicator: Piece download stalls during verification**
```
Means: Disk can't keep up with network

Solution:
1. Reduce max connections (less concurrent downloads)
2. Increase piece size (fewer pieces to verify)
3. Move to faster storage
```

### Memory Usage

**Per torrent overhead:**
- ~100-200 KB base
- Plus peer list (10 KB per peer)
- Plus block cache (configurable)

**Calculation:**
```
Total RAM = base + (num_torrents * 200KB) + (total_peers * 10KB)
```

**Optimization:**
- Monitor `/proc/[pid]/status` or `psutil`
- If >80% system RAM: pause some torrents
- Adjust block cache size in preferences

### CPU Usage

**Typically low (<5%) unless:**
- Hash checking/verification (CPU-intensive)
- Encryption enabled (crypto overhead)
- Many peers (peer handshakes)
- Too many connections (context switching)

**Optimization:**
- Enable hardware AES-NI if available
- Reduce max half-open (less handshake churn)
- Batch operations

---

## Research Sources

All findings based on:

1. **Official Documentation**
   - [qBittorrent GitHub Wiki](https://github.com/qbittorrent/qBittorrent/wiki)
   - [WebUI API v5.0](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-(qBittorrent-5.0))
   - [Explanation of Options](https://github.com/qbittorrent/qBittorrent/wiki/Explanation-of-Options-in-qBittorrent)

2. **Performance & Optimization**
   - [Best qBittorrent Settings 2026 - RapidSeedbox](https://www.rapidseedbox.com/blog/qbittorrent-settings)
   - [How to Fix Stalled Torrents - RapidSeedbox](https://www.rapidseedbox.com/blog/qbittorrent-stalled)
   - [Speed Up qBittorrent - MakeUseOf](https://www.makeuseof.com/speed-up-downloads-qbittorrent/)

3. **Protocol & Implementation**
   - [Libtorrent Reference Manual](https://www.libtorrent.org/reference-Settings.html)
   - [GitHub Issues (IPv4/IPv6)](https://github.com/qbittorrent/qBittorrent/issues)
   - [GitHub Discussions (Performance)](https://github.com/qbittorrent/qBittorrent/discussions)

4. **Health Monitoring Tools**
   - [qBitrr Health Monitoring](https://feramance.github.io/qBitrr/features/health-monitoring/)
   - [Grafana Dashboard](https://grafana.com/grafana/dashboards/23784-qbittorrent/)

---

## Recommendations

### For Immediate Implementation
1. **Monitor upload limit** - Biggest common mistake
2. **Detect stalled torrents** - Simple but high impact
3. **Track peer quality** - Identifies bad swarms early
4. **Monitor speed trends** - Detect degradation early

### For Future Enhancement
1. **Protocol analysis** - Automatically tune TCP/µTP
2. **Peer reputation scoring** - Ban consistently bad peers
3. **Predictive modeling** - Estimate completion times
4. **Torrent swarm simulation** - Predict outcomes

### Testing Recommendations
1. Test with 10, 100, 500 torrents (scaling)
2. Verify on different networks (home, office, VPS)
3. Test with different torrent types (large files, many small files)
4. Monitor during peak/off-peak usage
5. Validate on edge cases (stalled, corrupted, no peers)

---

## Conclusion

The qBittorrent Web API v2 provides comprehensive access to all necessary metrics for intelligent monitoring and recovery. The most impactful optimizations address:

1. **Stalled torrents** (no peers) - Early detection + recovery
2. **Upload/download imbalance** - Proper ratio tuning
3. **Protocol selection** - IPv4/IPv6 and TCP/µTP optimization
4. **Peer quality** - Focus bandwidth on fast peers
5. **Predictive recovery** - Detect issues before critical state

All proposed features are feasible with existing APIs and require no modifications to qBittorrent itself.

