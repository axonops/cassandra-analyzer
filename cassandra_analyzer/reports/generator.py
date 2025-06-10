"""
Report generator for analysis results
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from jinja2 import Environment, FileSystemLoader, select_autoescape


class ReportGenerator:
    """Generates analysis reports in various formats"""
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up Jinja2 environment
        template_dir = Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(['html', 'xml'])
        )
    
    def generate(self, report_data: Dict[str, Any]) -> Path:
        """Generate the analysis report"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        cluster_name = report_data["cluster_info"]["cluster_name"]
        
        # Generate markdown report
        md_path = self.output_dir / f"cassandra_analysis_{cluster_name}_{timestamp}.md"
        self._generate_markdown(report_data, md_path)
        
        # Generate JSON report for programmatic access
        json_path = self.output_dir / f"cassandra_analysis_{cluster_name}_{timestamp}.json"
        self._generate_json(report_data, json_path)
        
        return md_path
    
    def _generate_markdown(self, report_data: Dict[str, Any], output_path: Path):
        """Generate markdown report"""
        template = self._get_markdown_template()
        
        content = template.render(
            cluster_info=report_data["cluster_info"],
            cluster_state=report_data["cluster_state"],
            analysis_results=report_data["analysis_results"],
            generation_time=datetime.utcnow().isoformat()
        )
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def _generate_json(self, report_data: Dict[str, Any], output_path: Path):
        """Generate JSON report"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, default=str)
    
    def _get_markdown_template(self) -> str:
        """Get the markdown template (inline for now)"""
        return self.env.from_string("""
# Cassandra Cluster Health Assessment Report

**Generated:** {{ generation_time }}  
**Cluster:** {{ cluster_info.cluster_name }}  
**Organization:** {{ cluster_info.organization }}  
**Analysis Period:** {{ cluster_info.time_range.start }} to {{ cluster_info.time_range.end }}

---

## Executive Summary

This report provides a comprehensive health assessment of your Apache Cassandra cluster using real-time data from AxonOps monitoring. The analysis evaluates your cluster across five critical dimensions:

1. **Infrastructure** - Hardware resources, operating system configuration, and physical deployment
2. **Configuration** - Cassandra settings, JVM parameters, and cluster-wide configurations
3. **Operations** - Performance metrics, error patterns, and operational health indicators
4. **Data Model** - Schema design, table optimization, and compaction strategies
5. **Security** - Authentication, authorization, and encryption settings

### Understanding This Report

This report is designed to be accessible to both experienced and new Cassandra administrators. Each section includes:
- **What We're Checking** - Plain English explanation of what we're analyzing
- **Why It Matters** - The impact on your cluster's performance and reliability
- **What We Found** - Your cluster's current state with context
- **What You Should Do** - Specific, actionable recommendations

> 💡 **New to Cassandra?** Look for these helpful callout boxes throughout the report that explain key concepts and terminology.

{% set total_recommendations = 0 %}
{% set critical_count = 0 %}
{% set warning_count = 0 %}
{% set info_count = 0 %}

{% for section_name, section_data in analysis_results.items() %}
    {% set total_recommendations = total_recommendations + (section_data.recommendations | length) %}
    {% for rec in section_data.recommendations %}
        {% if rec.severity == 'CRITICAL' %}
            {% set critical_count = critical_count + 1 %}
        {% elif rec.severity == 'WARNING' %}
            {% set warning_count = warning_count + 1 %}
        {% else %}
            {% set info_count = info_count + 1 %}
        {% endif %}
    {% endfor %}
{% endfor %}

### Summary of Findings

| Priority Level | Count | Action Required | Typical Response Time |
|----------------|-------|-----------------|----------------------|
| **🔴 Critical Issues** | {{ critical_count }} | Immediate attention required - may impact stability or cause data loss | Within 24 hours |
| **🟡 Warnings** | {{ warning_count }} | Should be addressed to ensure optimal performance | Within 1-2 weeks |
| **🔵 Informational** | {{ info_count }} | Best practice recommendations for long-term optimization | Next maintenance window |
| **Total Recommendations** | {{ total_recommendations }} | - | - |

{% if critical_count > 0 %}
### ⚠️ **Immediate Action Required**
This cluster has **{{ critical_count }} critical issue(s)** that require immediate attention. Critical issues can lead to:
- **Data Loss** - Potential loss of committed writes or corrupted data
- **Service Outages** - Complete or partial cluster unavailability
- **Performance Degradation** - Severe impact on read/write latencies
- **Cascading Failures** - Issues that can spread to healthy nodes

**Next Steps:** Review the critical issues in the detailed analysis below and implement the recommended fixes immediately.

{% elif warning_count > 0 %}
### ⚡ **Performance Optimization Needed**
This cluster has **{{ warning_count }} warning(s)** that should be addressed to ensure optimal performance. While not immediately critical, these issues can:
- **Reduce Performance** - Higher latencies and lower throughput than optimal
- **Increase Costs** - Inefficient resource utilization requiring more hardware
- **Risk Escalation** - May develop into critical issues if left unaddressed
- **Impact Stability** - Can contribute to occasional timeouts or errors

**Next Steps:** Plan to address these warnings in your next maintenance window or within 1-2 weeks.

{% else %}
### ✅ **Healthy Cluster Status**
**Excellent!** No critical issues or warnings detected. Your cluster appears to be well-configured and operating within recommended parameters. This indicates:
- **Stable Operations** - Your cluster is running smoothly
- **Good Configuration** - Settings align with best practices
- **Proper Sizing** - Resources appear adequate for your workload
- **Effective Maintenance** - Regular operations are being performed correctly

**Next Steps:** Continue regular monitoring and maintenance. Review the informational recommendations for potential optimizations.
{% endif %}

> 💡 **Understanding Priority Levels:**
> - **Critical** = Can cause immediate problems (outages, data loss)
> - **Warning** = Performance or reliability concerns that will worsen over time
> - **Informational** = Opportunities to optimize or follow best practices

---

## Cluster Overview

### What Is Your Cassandra Cluster?

Your Cassandra cluster is a distributed database system consisting of multiple nodes (servers) working together to store and serve your data. Key characteristics include:

- **Nodes** - Individual servers running Cassandra software
- **Datacenters** - Logical groupings of nodes, often representing physical locations
- **Keyspaces** - Top-level data containers (similar to databases in traditional systems)
- **Replication** - How many copies of your data exist across nodes

### Current Cluster State

| Attribute | Value | Assessment | What This Means |
|-----------|-------|------------|-----------------|
| **Total Nodes** | {{ cluster_state.get_total_nodes() if cluster_state.get_total_nodes else 'N/A' }} | {% if cluster_state.get_total_nodes() and cluster_state.get_total_nodes() >= 3 %}✅ Sufficient for production{% else %}⚠️ Consider adding nodes for redundancy{% endif %} | {% if cluster_state.get_total_nodes() %}{% if cluster_state.get_total_nodes() >= 3 %}You have enough nodes to handle failures while maintaining availability{% else %}With fewer than 3 nodes, losing one node could impact availability{% endif %}{% else %}Unable to determine node count{% endif %} |
| **Active Nodes** | {{ cluster_state.get_active_nodes() if cluster_state.get_active_nodes else 'N/A' }} | {% if cluster_state.get_active_nodes() == cluster_state.get_total_nodes() %}✅ All nodes active{% else %}⚠️ Some nodes may be down{% endif %} | {% if cluster_state.get_active_nodes() == cluster_state.get_total_nodes() %}All nodes are responding and healthy{% else %}{{ cluster_state.get_total_nodes() - cluster_state.get_active_nodes() }} node(s) appear to be down or unresponsive{% endif %} |
| **Datacenters** | {{ cluster_state.get_datacenters() | join(', ') if cluster_state.get_datacenters else 'N/A' }} | {% if cluster_state.get_datacenters() and cluster_state.get_datacenters() | length > 1 %}✅ Multi-DC deployment{% else %}⚠️ Single DC - consider multi-DC for HA{% endif %} | {% if cluster_state.get_datacenters() and cluster_state.get_datacenters() | length > 1 %}Data is replicated across multiple datacenters for disaster recovery{% else %}All nodes are in one datacenter - vulnerable to site-wide failures{% endif %} |
| **Keyspaces** | {{ cluster_state.keyspaces | length }} | {% if cluster_state.keyspaces | length > 0 %}✅ {{ cluster_state.keyspaces | length }} keyspace(s) detected{% else %}ℹ️ No application keyspaces found{% endif %} | {% set app_ks_count = 0 %}{% for ks_name in cluster_state.keyspaces.keys() %}{% if not ks_name.startswith('system') %}{% set app_ks_count = app_ks_count + 1 %}{% endif %}{% endfor %}You have {{ app_ks_count }} application keyspace(s) storing business data |
| **Analysis Duration** | {{ cluster_state.collection_duration_seconds | round(2) if cluster_state.collection_duration_seconds else 'N/A' }} seconds | ℹ️ Data collection time | Time taken to gather all monitoring data for this report |

> 💡 **Why These Numbers Matter:**
> - **3+ nodes** = Can lose one node without data loss (with RF=3)
> - **Multi-DC** = Can survive entire datacenter failures
> - **All nodes active** = Maximum performance and redundancy
> - **Multiple keyspaces** = Logical separation of different applications/data

---

{% for section_name, section_data in analysis_results.items() %}
## {{ section_name.title().replace('_', ' ') }} Analysis

{% if section_name == 'infrastructure' %}
### 🖥️ What We're Checking
Infrastructure analysis examines the underlying hardware and operating system configuration that supports your Cassandra cluster. Think of this as checking the foundation of a building - if the foundation isn't solid, everything built on top is at risk.

### 📊 Key Areas Evaluated
- **CPU Resources** - Processing power available for database operations
- **Memory (RAM)** - Critical for caching and performance
- **Disk I/O** - Storage performance and capacity
- **Network Configuration** - Communication between nodes
- **Operating System Settings** - Kernel parameters and system limits
- **Java Version** - Runtime environment compatibility

### ⚡ Why This Matters
Poor infrastructure configuration can cause:
- **Performance Bottlenecks** - Slow queries and high latencies
- **Node Failures** - Crashes due to resource exhaustion
- **Data Loss Risk** - Inadequate disk space or I/O errors
- **Cluster Instability** - Network issues causing node disconnections

{% elif section_name == 'configuration' %}
### 🔧 What We're Checking
Configuration analysis reviews Cassandra settings, JVM parameters, and other configuration options that control how your database operates. These settings are like the tuning knobs on a race car - proper adjustment is essential for optimal performance.

### 📊 Key Areas Evaluated
- **Memory Settings** - Heap size, garbage collection tuning
- **Compaction Settings** - How data files are merged and cleaned
- **Replication Configuration** - Data redundancy across nodes
- **Timeout Settings** - How long operations wait before failing
- **Concurrent Operations** - Parallelism and thread pool sizes
- **Caching Configuration** - What data stays in memory for fast access

### ⚡ Why This Matters
Misconfiguration can lead to:
- **Memory Pressure** - Frequent garbage collection pauses
- **Slow Queries** - Inefficient resource utilization
- **Dropped Requests** - Timeouts under load
- **Wasted Resources** - Over or under-provisioning

{% elif section_name == 'operations' or section_name == 'operations_logs' %}
### 🚨 What We're Checking
Operations analysis evaluates your cluster's real-time health by examining performance metrics and log patterns. This is like a health checkup - we're looking for symptoms of problems that might not be obvious yet.

### 📊 Key Areas Evaluated
- **Error Rates** - Failed operations and their patterns
- **Performance Metrics** - Read/write latencies and throughput
- **Resource Utilization** - CPU, memory, and disk usage trends
- **Log Patterns** - Warnings and errors in system logs
- **Garbage Collection** - JVM pause frequency and duration
- **Dropped Messages** - Internal communication failures

### ⚡ Why This Matters
Operational issues indicate:
- **Degraded Performance** - Users experiencing slow responses
- **Impending Failures** - Problems that will escalate if ignored
- **Capacity Issues** - Need for scaling or optimization
- **Application Problems** - Inefficient query patterns or data models

{% elif section_name == 'datamodel' %}
### 📐 What We're Checking
Data model analysis examines how your data is structured and stored in Cassandra. Unlike traditional databases, Cassandra requires careful schema design for optimal performance. Think of this as reviewing the blueprint of your data architecture.

### 📊 Key Areas Evaluated
- **Table Design** - Primary keys, clustering columns, and partitioning
- **Partition Sizes** - Data distribution and hot spots
- **Compaction Strategies** - How data files are managed over time
- **Secondary Indexes** - Performance impact of additional indexes
- **Materialized Views** - Automated data duplication patterns
- **Compression Settings** - Storage efficiency vs. CPU usage

### ⚡ Why This Matters
Poor data modeling causes:
- **Hot Partitions** - Uneven load distribution
- **Large Partitions** - Slow queries and memory issues
- **Tombstone Accumulation** - Deleted data affecting reads
- **Inefficient Storage** - Wasted disk space and I/O

{% elif section_name == 'security' %}
### 🔐 What We're Checking
Security analysis validates that your cluster is properly protected against unauthorized access and data breaches. This covers authentication (who can connect), authorization (what they can do), and encryption (protecting data in transit and at rest).

### 📊 Key Areas Evaluated
- **Authentication** - User/password requirements and management
- **Authorization** - Role-based access controls
- **Encryption** - SSL/TLS for client and inter-node communication
- **Audit Logging** - Tracking of security-relevant events
- **Network Security** - Firewall and access restrictions
- **Default Accounts** - Removal of insecure defaults

### ⚡ Why This Matters
Security gaps can lead to:
- **Data Breaches** - Unauthorized access to sensitive information
- **Compliance Violations** - Failure to meet regulatory requirements
- **Data Tampering** - Malicious modification of data
- **Service Disruption** - Denial of service attacks

{% elif section_name == 'extended_configuration' %}
### 🔍 What We're Checking
Extended configuration analysis dives deeper into advanced Cassandra settings that affect specialized features and fine-tuning options. These are the expert-level adjustments that can squeeze out extra performance or enable specific capabilities.

### 📊 Key Areas Evaluated
- **Advanced Compaction Options** - Fine-tuning for specific workloads
- **Streaming Configuration** - Node rebuild and repair efficiency
- **Hinted Handoff Settings** - Temporary failure handling
- **Bloom Filter Configuration** - Read optimization settings
- **Compression Options** - Algorithm selection and chunk sizes
- **Custom Settings** - Non-standard configurations

### ⚡ Why This Matters
These settings affect:
- **Specialized Workloads** - Time-series, write-heavy, or read-heavy patterns
- **Operational Efficiency** - Repair and maintenance performance
- **Resource Optimization** - Fine-tuning for specific hardware
- **Feature Enablement** - Advanced Cassandra capabilities

{% endif %}

{% if section_data.error %}
⚠️ **Analysis Error:** Unable to complete {{ section_name.replace('_', ' ') }} analysis due to: {{ section_data.error }}

*This may indicate missing permissions, incomplete data collection, or configuration issues that prevent full analysis.*

{% else %}
{% if section_data.recommendations %}

### Summary Table

| Finding | Current Value | Recommended Action | Priority | Impact |
|---------|---------------|-------------------|----------|--------|
{% for rec in section_data.recommendations %}
| {{ rec.title }} | {{ rec.current_value if rec.current_value else 'See details' }} | {{ rec.recommendation }} | {{ rec.severity.value.upper() if rec.severity.value else rec.severity }} | {{ rec.impact if rec.impact else rec.description }} |
{% endfor %}

### Detailed Analysis and Recommendations

{% for rec in section_data.recommendations %}
#### {{ rec.title }}

**Current State:** {{ rec.current_value if rec.current_value else 'See description below' }}  
**Priority:** {{ rec.severity.value.upper() if rec.severity.value else rec.severity }}  
**Category:** {{ rec.category.title() }}

**Description:** {{ rec.description }}

{% if rec.impact %}
**Impact:** {{ rec.impact }}
{% endif %}

**Recommended Action:** {{ rec.recommendation }}

{% if rec.reference_url %}
**Additional Information:** [{{ rec.reference_url }}]({{ rec.reference_url }})
{% endif %}

---

{% endfor %}

{% else %}
✅ **No Issues Detected**

The {{ section_name.replace('_', ' ') }} analysis found no configuration issues or optimization opportunities. Your cluster appears to be well-configured in this area.

{% endif %}
{% endif %}

{% endfor %}

---

## Operational Health Overview

### 📊 Understanding Your Cluster's Health

Operational health is determined by analyzing patterns in your cluster's logs and metrics. Think of this as reading your cluster's vital signs - each type of event tells us something about what's happening inside your database.

### Log Events Analysis

The following table summarizes operational events detected during the analysis period. These are extracted from your Cassandra system logs and indicate various conditions that may require attention.

> 💡 **Reading This Table:**
> - **Event Type** = What Cassandra detected
> - **Count** = How many times it occurred
> - **Severity** = Impact on cluster health
> - **Description** = What this means for your cluster

{% if cluster_state.log_events %}
| Event Type | Count | Severity | Description |
|------------|-------|----------|-------------|
{% for event_type, histogram_data in cluster_state.log_events.items() %}
{% if histogram_data and histogram_data.get('metadata') %}
{% set count = histogram_data.metadata.get('_count', 0) | int %}
| {{ event_type.replace('_', ' ').title() }} | {{ count }} | {% if event_type == 'batch_warnings' and count > 1000 %}🔴 High{% elif event_type == 'large_partitions' and count > 50 %}🟡 Medium{% elif event_type == 'repair_failures' and count > 100 %}🟡 Medium{% elif count > 0 %}🔵 Low{% else %}✅ None{% endif %} | {% if event_type == 'prepared_statements' %}Too many unique queries are being prepared, causing memory pressure. Applications should reuse prepared statements.{% elif event_type == 'batch_warnings' %}Applications are sending batches that are too large (>5kb or >50 statements). This can cause memory issues and timeouts.{% elif event_type == 'tombstone_warnings' %}Queries are reading through many deleted records (tombstones), which slows down reads significantly.{% elif event_type == 'aggregation_queries' %}COUNT, SUM, or AVG queries that process large amounts of data. These are expensive in Cassandra.{% elif event_type == 'gc_pauses' %}Java garbage collector is pausing the application to free memory. Long pauses affect performance.{% elif event_type == 'gossip_pauses' %}Node-to-node communication is experiencing delays, possibly due to network issues or overload.{% elif event_type == 'large_partitions' %}Some data partitions have grown beyond recommended size (100MB), affecting read performance.{% elif event_type == 'dropped_hints' %}Temporary writes (hints) meant for offline nodes are being discarded due to overload.{% elif event_type == 'aborted_hints' %}Previously stored hints could not be delivered when nodes came back online.{% elif event_type == 'commitlog_sync' %}Write-ahead log is being flushed to disk. Normal operation but high counts may indicate I/O issues.{% elif event_type == 'repair_failures' %}Anti-entropy repair operations are running to ensure data consistency across nodes.{% else %}Unknown operational event type{% endif %} |
{% endif %}
{% endfor %}

#### Event Analysis Insights

{% for event_type, histogram_data in cluster_state.log_events.items() %}
{% if histogram_data and histogram_data.get('metadata') %}
{% set count = histogram_data.metadata.get('_count', 0) | int %}
{% if count > 0 %}
- **{{ event_type.replace('_', ' ').title() }}**: {{ count }} events detected.
  {% if event_type == 'batch_warnings' and count > 1000 %}*High volume of batch warnings suggests reviewing application batch size limits.*
  {% elif event_type == 'large_partitions' and count > 50 %}*Large partition warnings indicate potential data model optimization opportunities.*
  {% elif event_type == 'repair_failures' and count > 100 %}*Multiple repair operations detected - this is normal for active clusters.*
  {% endif %}
{% endif %}
{% endif %}
{% endfor %}

{% else %}
*No log event data available for analysis. This may indicate logging is not configured or accessible.*
{% endif %}

---

## Cluster Topology

### Node Configuration

{% if cluster_state.nodes %}
| Node ID | Datacenter | Rack | Cassandra Version | Status | Health |
|---------|------------|------|-------------------|--------|--------|
{% for node_id, node in cluster_state.nodes.items() %}
| `{{ node_id[:8] }}...` | {{ node.datacenter }} | {{ node.rack if node.rack else 'default' }} | {{ node.cassandra_version if node.cassandra_version else 'Unknown' }} | {{ '🟢 Active' if node.is_active else '🔴 Inactive' }} | {% if node.is_active %}Normal{% else %}Requires Investigation{% endif %} |
{% endfor %}

### Topology Analysis

{% set active_nodes = cluster_state.get_active_nodes() %}
{% set total_nodes = cluster_state.get_total_nodes() %}
{% set datacenters = cluster_state.get_datacenters() %}

- **Node Health**: {{ active_nodes }}/{{ total_nodes }} nodes are active
- **Geographic Distribution**: {{ datacenters | length }} datacenter(s): {{ datacenters | join(', ') if datacenters else 'Unknown' }}
- **Availability**: {% if datacenters | length > 1 %}Multi-datacenter deployment provides high availability{% else %}Single datacenter - consider multi-DC for production resilience{% endif %}

{% else %}
*No node topology information available.*
{% endif %}

---

## Keyspace and Data Model Overview

{% if cluster_state.keyspaces %}
| Keyspace | Tables | Type | Notes |
|----------|--------|------|-------|
{% for ks_name, keyspace in cluster_state.keyspaces.items() %}
| `{{ ks_name }}` | {{ keyspace.Tables | length }} | {% if ks_name.startswith('system') %}System{% else %}Application{% endif %} | {% if ks_name.startswith('system') %}Cassandra internal{% else %}User data{% endif %} |
{% endfor %}

### Data Model Health

- **Total Keyspaces**: {{ cluster_state.keyspaces | length }}
- **Application Keyspaces**: {% set app_ks_count = 0 %}{% for ks_name in cluster_state.keyspaces.keys() %}{% if not ks_name.startswith('system') %}{% set app_ks_count = app_ks_count + 1 %}{% endif %}{% endfor %}{{ app_ks_count }}
- **Total Tables**: {{ cluster_state.keyspaces.values() | map(attribute='Tables') | map('length') | sum }}

{% else %}
*No keyspace information available for analysis.*
{% endif %}

---

## Recommendations Summary

### Immediate Actions (Critical Priority)

{% set critical_recommendations = [] %}
{% for section_name, section_data in analysis_results.items() %}
  {% if not section_data.error %}
    {% for rec in section_data.recommendations %}
      {% if rec.severity == 'CRITICAL' %}
        {% set _ = critical_recommendations.append(rec) %}
      {% endif %}
    {% endfor %}
  {% endif %}
{% endfor %}

{% if critical_recommendations %}
{% for rec in critical_recommendations %}
1. **{{ rec.title }}** ({{ rec.category.title() }})
   - Issue: {{ rec.description }}
   - Action: {{ rec.recommendation }}
{% endfor %}
{% else %}
*No critical issues requiring immediate action.*
{% endif %}

### Near-Term Improvements (Warning Priority)

{% set warning_recommendations = [] %}
{% for section_name, section_data in analysis_results.items() %}
  {% if not section_data.error %}
    {% for rec in section_data.recommendations %}
      {% if rec.severity == 'WARNING' %}
        {% set _ = warning_recommendations.append(rec) %}
      {% endif %}
    {% endfor %}
  {% endif %}
{% endfor %}

{% if warning_recommendations %}
{% for rec in warning_recommendations %}
1. **{{ rec.title }}** ({{ rec.category.title() }})
   - Current: {{ rec.current_value if rec.current_value else 'See analysis' }}
   - Recommendation: {{ rec.recommendation }}
{% endfor %}
{% else %}
*No warning-level issues detected.*
{% endif %}

### Long-Term Optimizations (Informational)

{% set info_recommendations = [] %}
{% for section_name, section_data in analysis_results.items() %}
  {% if not section_data.error %}
    {% for rec in section_data.recommendations %}
      {% if rec.severity == 'INFO' %}
        {% set _ = info_recommendations.append(rec) %}
      {% endif %}
    {% endfor %}
  {% endif %}
{% endfor %}

{% if info_recommendations %}
{% for rec in info_recommendations %}
1. **{{ rec.title }}** ({{ rec.category.title() }})
   - Opportunity: {{ rec.description }}
   - Benefit: {{ rec.impact if rec.impact else 'Performance optimization' }}
{% endfor %}
{% else %}
*No additional optimization opportunities identified.*
{% endif %}

---

## Next Steps

1. **Review Critical Issues**: Address any critical priority items immediately
2. **Plan Warning Items**: Schedule resolution of warning-level issues within the next maintenance window
3. **Consider Optimizations**: Evaluate informational recommendations for future improvements
4. **Monitor Progress**: Re-run this analysis after implementing changes to validate improvements
5. **Regular Assessment**: Schedule periodic health assessments to maintain optimal cluster performance

---

*This report was generated by Cassandra AxonOps Analyzer using real-time monitoring data. For questions about specific recommendations or implementation guidance, consult your database administration team or Cassandra experts.*

**Report Generation Details:**
- Analysis Duration: {{ cluster_state.collection_duration_seconds | round(2) if cluster_state.collection_duration_seconds else 'N/A' }} seconds
- Data Sources: AxonOps monitoring metrics, configuration data, and operational logs
- Generated: {{ generation_time }}
""")
    
    def _get_event_description(self, event_type: str) -> str:
        """Get description for event types"""
        descriptions = {
            "prepared_statements": "Prepared statement cache pressure events",
            "batch_warnings": "Large batch size warnings",
            "tombstone_warnings": "Tombstone scan performance issues",
            "aggregation_queries": "Aggregation query usage patterns",
            "gc_pauses": "JVM garbage collection pause events",
            "gossip_pauses": "Gossip failure detector disruptions",
            "large_partitions": "Large partition warnings",
            "dropped_hints": "Dropped hints events",
            "aborted_hints": "Failed hint replay events", 
            "commitlog_sync": "Commit log sync operations",
            "repair_failures": "Repair operation events"
        }
        return descriptions.get(event_type, "Unknown event type")