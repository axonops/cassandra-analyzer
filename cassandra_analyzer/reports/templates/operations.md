## Operational Health Analysis

{% for rec in recommendations %}
### {{ rec.title }}

**Severity:** {{ rec.severity | severity_icon }} {{ rec.severity.value.upper() }}  
**Current Metrics:** {{ rec.current_value if rec.current_value else 'See analysis below' }}

{{ rec.description }}

{% if 'gc_pause' in rec.title.lower() %}
#### Garbage Collection Analysis

JVM garbage collection pauses stop all application threads. Your GC metrics show:

{{ rec.current_value }}

**Pause Duration Guidelines:**
- ✅ Excellent: < 200ms
- ⚠️ Warning: 200ms - 1s  
- 🔴 Critical: > 1s

---

_**GC Tuning Tips**:_
- Use G1GC for heaps 8GB-32GB
- Consider ZGC for very large heaps
- Monitor heap usage trends
- Tune `-XX:MaxGCPauseMillis` target

---
{% elif 'dropped_message' in rec.title.lower() %}
#### Understanding Dropped Messages

Cassandra drops internal messages when overwhelmed. Common types:

- **READ**: Read requests that timed out
- **MUTATION**: Write requests that timed out
- **HINT**: Hints for temporarily down nodes
- **REQUEST_RESPONSE**: Coordinator timeouts

**Your dropped messages:** {{ rec.current_value }}

---

_**Common Causes**:_
1. **Overloaded nodes**: CPU or I/O saturation
2. **Large queries**: Scanning too much data
3. **Network issues**: Packet loss or high latency
4. **GC pressure**: Long pause times

_Monitor trends rather than absolute numbers._

---
{% elif 'hint' in rec.title.lower() %}
#### Hinted Handoff Explained

When a replica is temporarily unavailable, coordinators store "hints" - mutations to replay when the node returns.

**Current hint statistics:** {{ rec.current_value }}

**Hint Lifecycle:**
1. Node becomes unavailable
2. Coordinators store hints (up to `max_hint_window_in_ms`)
3. Node returns online
4. Hints replay to catch up
5. Hints are deleted after successful delivery

---

_**Warning Signs**:_
- Consistently high hint counts
- Hints not draining after nodes return
- Hint replay failures
- Full hint storage

---
{% elif 'repair' in rec.title.lower() %}
#### Repair Operations

Repairs ensure data consistency by comparing replicas and fixing discrepancies.

**Recent repair activity:** {{ rec.current_value }}

**Repair Best Practices:**
- Run within `gc_grace_seconds` (default: 10 days)
- Use incremental repair for efficiency
- Monitor repair progress and duration
- Stagger repairs across the cluster

---

_**Repair Strategies**:_
- **Full Repair**: Compares all data (expensive)
- **Incremental Repair**: Only unrepaired data
- **Subrange Repair**: Specific token ranges
- **Primary Range**: Only locally-owned data

---
{% elif 'batch' in rec.title.lower() %}
#### Batch Warning Analysis

Cassandra logged batch operations indicate potential anti-patterns:

**Batch statistics:** {{ rec.current_value }}

**Batch Guidelines:**
- ✅ Use for atomicity within a partition
- ⚠️ Avoid multi-partition batches
- 🔴 Never use for performance optimization

---

_**Why Batches Can Be Harmful**:_
1. Coordinator must manage all mutations
2. Large batches cause memory pressure
3. Timeout affects entire batch
4. No performance benefit vs. async writes

_Consider using async writes with proper error handling instead._

---
{% endif %}

**Business Impact:** {{ rec.impact if rec.impact else 'May affect application performance and reliability' }}

**Action Required:** {{ rec.recommendation }}

{% if rec.reference_url %}
📖 **Reference:** [{{ rec.reference_url }}]({{ rec.reference_url }})
{% endif %}

---

{% endfor %}