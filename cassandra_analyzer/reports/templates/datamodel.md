## Data Model Analysis

{% for rec in recommendations %}
### {{ rec.title }}

**Severity:** {{ rec.severity | severity_icon }} {{ rec.severity.value.upper() }}  
**Affected Tables:** {{ rec.current_value if rec.current_value else 'See details below' }}

{{ rec.description }}

{% if 'partition' in rec.title.lower() %}
#### Understanding Partition Sizes

Partitions are the fundamental unit of data distribution in Cassandra. Large partitions cause:
- **Performance Issues**: Entire partition must be read into memory
- **Compaction Problems**: Large partitions slow down compaction
- **Node Imbalance**: Some nodes handle disproportionate load

**Recommended Limits:**
- Warning: > 100MB
- Critical: > 1GB
- Maximum: 2GB (hard limit)

---

_**Design Tip**: If partitions are too large, consider:_
1. Adding a time component to partition key (e.g., daily buckets)
2. Using composite partition keys to increase cardinality
3. Denormalizing data across multiple tables

---
{% elif 'tombstone' in rec.title.lower() %}
#### Tombstone Impact

Tombstones are deletion markers that must be read before being filtered out. High tombstone counts cause:
- **Read Latency**: Every tombstone must be read and discarded
- **Memory Pressure**: Tombstones consume heap during queries
- **Timeout Risk**: Queries may timeout scanning tombstones

**Your tombstone statistics:** {{ rec.current_value }}

---

_**Best Practices for Tombstone Management:**_
- Set appropriate `gc_grace_seconds` (default: 10 days)
- Use TTL instead of explicit deletes when possible
- Consider time-series data models that naturally expire
- Run repairs regularly to ensure tombstone consistency

---
{% elif 'secondary_index' in rec.title.lower() %}
#### Secondary Index Considerations

Secondary indexes in Cassandra create hidden tables that must be maintained. They work best when:
- Cardinality is low to medium (not unique values)
- Queries include the partition key
- Index covers a small portion of the table

**Current indexes:** {{ rec.current_value }}

---

_**Alternative Approaches**:_
- Materialized Views (automated denormalization)
- Manual denormalization tables
- Search integration (Elasticsearch, Solr)
- SAI indexes (Storage-Attached Indexing) in newer versions

---
{% elif 'gc_grace' in rec.title.lower() %}
#### GC Grace Seconds Configuration

Controls when tombstones can be purged. Must be longer than your repair cycle.

**Current settings:** {{ rec.current_value }}

**Formula:** `gc_grace_seconds > max_repair_duration * 2`

---

_**Noted for reference**: Reducing gc_grace_seconds requires more frequent repairs but allows faster tombstone cleanup. Default is 864000 (10 days)._

---
{% endif %}

**Impact on your cluster:** {{ rec.impact if rec.impact else 'May cause performance degradation or operational issues' }}

**Recommended Action:** {{ rec.recommendation }}

{% if rec.reference_url %}
📚 **Learn More:** [{{ rec.reference_url }}]({{ rec.reference_url }})
{% endif %}

---

{% endfor %}