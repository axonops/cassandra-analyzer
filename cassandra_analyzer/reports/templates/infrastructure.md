## Infrastructure Recommendations

{% for rec in recommendations %}
### {{ rec.title }}

{% if rec.severity.value == 'CRITICAL' %}
⚠️ **CRITICAL ISSUE**: This infrastructure problem requires immediate attention.
{% endif %}

**Current State:** {{ rec.current_value if rec.current_value else 'See analysis below' }}

{{ rec.description }}

{% if 'memory' in rec.title.lower() %}
---

_**Understanding Memory in Cassandra**: Cassandra uses memory for:_
- **Heap Memory**: Used by the JVM for caching and operations
- **Off-heap Memory**: Used for compression, bloom filters, and index summaries  
- **OS Page Cache**: Caches frequently accessed SSTables

_A general rule is to allocate 8GB heap for systems with 32GB+ RAM, and no more than 50% of total RAM._

---
{% elif 'disk' in rec.title.lower() %}
---

_**Disk I/O Considerations**: Cassandra is I/O intensive and requires:_
- **Low latency storage**: SSDs strongly recommended for data directories
- **Separate commit log disk**: Isolates sequential writes from random reads
- **Adequate free space**: Maintain 50% free for compactions

---
{% elif 'cpu' in rec.title.lower() %}
---

_**CPU Requirements**: Cassandra uses CPU for:_
- Compaction (merging data files)
- Compression/decompression
- Query coordination
- Background repairs

_Typical production nodes need 8-16 cores minimum._

---
{% endif %}

**Impact:** {{ rec.impact if rec.impact else 'May affect cluster stability and performance' }}

**Recommended Action:** {{ rec.recommendation }}

{% if rec.reference_url %}
📚 **Learn More:** [{{ rec.reference_url }}]({{ rec.reference_url }})
{% endif %}

---

{% endfor %}