## Configuration Analysis

{% for rec in recommendations %}
### {{ rec.title }}

**Setting:** `{{ rec.current_value if rec.current_value else 'Not configured' }}`  
**Priority:** {{ rec.severity | severity_icon }} {{ rec.severity.value.upper() }}

{{ rec.description }}

{% if 'concurrent_compactors' in rec.title.lower() %}
The `concurrent_compactors` setting controls parallel compaction tasks. Default uses min(number of cores, number of disks).

**Current setting:** {{ rec.current_value }}

---

_**Noted for reference**: Compaction throughput is shared between all compactor threads. If you have 4 compactors and 64MB/s throughput, each gets ~16MB/s._

---
{% elif 'heap' in rec.title.lower() %}
JVM heap size affects caching and GC behavior. Common configurations:
- **8GB heap**: Standard for nodes with 32GB+ RAM
- **12-16GB heap**: For cache-heavy workloads
- **Never exceed 32GB**: Loses compressed OOPs benefit

**Your current heap:** {{ rec.current_value }}

---

_**Consideration**: Large heaps (>12GB) may experience long GC pauses. Monitor GC logs and consider G1GC or ZGC for large heaps._

---
{% elif 'compaction_throughput' in rec.title.lower() %}
Controls the rate limit for compaction I/O to prevent overwhelming the system.

**Current limit:** {{ rec.current_value }}MB/s

---

_**Best Practice**: Start conservative (16-32 MB/s) and increase based on I/O headroom. Setting to 0 removes limits but risks impacting query performance._

---
{% endif %}

**Why this matters:** {{ rec.impact if rec.impact else 'Affects cluster performance and stability' }}

**Action Required:** {{ rec.recommendation }}

{% if rec.reference_url %}
📖 **Documentation:** [{{ rec.reference_url }}]({{ rec.reference_url }})
{% endif %}

---

{% endfor %}