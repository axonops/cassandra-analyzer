"""
Main cluster data collector
"""

from datetime import datetime
from typing import Dict, List, Any, Optional
import structlog

from ..client import AxonOpsClient
from ..models import ClusterState, Node, Keyspace, Table, MetricData, MetricPoint
from ..utils.gc_metric_selector import GCMetricSelector

logger = structlog.get_logger()


class ClusterDataCollector:
    """Collects all cluster data from AxonOps API"""
    
    def __init__(self, client: AxonOpsClient, org: str, cluster_type: str, cluster: str):
        self.client = client
        self.org = org
        self.cluster_type = cluster_type
        self.cluster = cluster
    
    def collect(
        self,
        start_time: datetime,
        end_time: datetime,
        metrics_resolution: str = "60s"
    ) -> ClusterState:
        """Collect all cluster data"""
        start_collection = datetime.utcnow()
        
        cluster_state = ClusterState(
            name=self.cluster,
            cluster_type=self.cluster_type
        )
        
        # Collect basic cluster information  
        # Collect nodes
        logger.info("Collecting node information")
        cluster_state.nodes = self._collect_nodes()
        
        # Collect schema
        logger.info("Collecting keyspace and table information")
        cluster_state.keyspaces = self._collect_keyspaces()
        
        # Collect metrics
        logger.info("Collecting metrics")
        cluster_state.metrics = self._collect_metrics(
            start_time, end_time, metrics_resolution
        )
        
        # Skip events collection - API has timeout issues
        logger.info("Skipping events collection - API timeout issues")
        cluster_state.events = []
        
        # Collect log events for operations analysis
        # Temporarily disabled due to AxonOps API log search limitations
        # logger.info("Collecting log events for operations analysis")
        # cluster_state.log_events = self._collect_log_events(start_time, end_time)
        cluster_state.log_events = {}  # Empty dict to avoid issues
        
        # Set collection metadata
        cluster_state.collection_duration_seconds = (
            datetime.utcnow() - start_collection
        ).total_seconds()
        
        logger.info(
            "Data collection complete",
            duration_seconds=cluster_state.collection_duration_seconds
        )
        
        return cluster_state
    
    
    
    def _collect_nodes(self) -> Dict[str, Node]:
        """Collect node information"""
        nodes = {}
        
        try:
            node_list = self.client.get_nodes_full(
                self.org, self.cluster_type, self.cluster
            )
            
            for node_data in node_list:
                node = Node(
                    host_id=node_data.get("host_id", ""),
                    org=node_data.get("org", self.org),
                    type=node_data.get("type", self.cluster_type),
                    cluster=node_data.get("cluster", self.cluster),
                    DC=node_data.get("DC", ""),
                    Details=node_data.get("Details", {})
                )
                nodes[node.host_id] = node
                
        except Exception as e:
            logger.error("Failed to collect nodes", error=str(e))
        
        return nodes
    
    def _collect_keyspaces(self) -> Dict[str, Keyspace]:
        """Collect keyspace and table information"""
        keyspaces = {}
        
        try:
            ks_list = self.client.get_keyspaces(
                self.org, self.cluster_type, self.cluster
            )
            
            for ks_data in ks_list:
                # Convert table data
                tables = []
                for table_data in ks_data.get("Tables", []):
                    table = Table(
                        Name=table_data.get("Name", ""),
                        Keyspace=table_data.get("Keyspace", ""),
                        GCGrace=table_data.get("GCGrace", 864000),
                        CompactionStrategy=table_data.get("CompactionStrategy", ""),
                        ID=table_data.get("ID", ""),
                        CQL=table_data.get("CQL", "")
                    )
                    tables.append(table)
                
                # Parse replication parameters
                replication_params = ks_data.get("ReplicationParams", "")
                replication_strategy = ks_data.get("ReplicationStrategy", "")
                
                # Extract strategy class name from ReplicationStrategy string
                if "@" in replication_strategy:
                    replication_strategy = replication_strategy.split("@")[0]
                    if "." in replication_strategy:
                        replication_strategy = replication_strategy.split(".")[-1]
                
                # Parse replication options from ReplicationParams string
                replication_options = {}
                if "ReplicationParams{" in replication_params:
                    # Extract the parameters between the curly braces
                    params_str = replication_params[replication_params.find("{")+1:replication_params.rfind("}")]
                    # Split by comma and parse key=value pairs
                    for param in params_str.split(", "):
                        if "=" in param:
                            key, value = param.split("=", 1)
                            if key == "class":
                                continue  # Skip the class parameter
                            replication_options[key] = value
                
                keyspace = Keyspace(
                    Name=ks_data.get("Name", ""),
                    Tables=tables,
                    replication_strategy=replication_strategy,
                    replication_options=replication_options
                )
                
                keyspaces[keyspace.name] = keyspace
                
        except Exception as e:
            logger.error("Failed to collect keyspaces", error=str(e))
        
        return keyspaces
    
    def _collect_metrics(
        self,
        start_time: datetime,
        end_time: datetime,
        resolution: str
    ) -> Dict[str, Any]:
        """Collect metrics data"""
        metrics = {}
        
        # Define key metrics to collect based on the dashboard configuration and available AxonOps metrics
        # All queries must include org filter for AxonOps
        org_filter = f'org="{self.org}"'
        cluster_filter = f'cluster="{self.cluster}"'
        type_filter = f'type="{self.cluster_type}"'
        
        # Host-level metrics use different filter pattern
        host_filter = f'{org_filter},{cluster_filter},{type_filter}'
        
        # Detect GC type from nodes to select appropriate metric
        gc_metric = self._detect_gc_metric()
        
        metric_queries = {
            # System/Node metrics
            "cpu_usage": f'host_CPU_Percent_Merge{{{org_filter},{cluster_filter},{type_filter},time="real"}}',
            "memory_usage_percent": f'host_Memory_UsedPercent{{{org_filter},{cluster_filter},{type_filter}}}',
            "disk_read_rate": f'host_Disk_SectorsRead{{{org_filter},{cluster_filter},{type_filter},axonfunction="rate"}}',
            "disk_write_rate": f'host_Disk_SectorsWrite{{{org_filter},{cluster_filter},{type_filter},axonfunction="rate"}}',
            "disk_usage_percent": f'host_Disk_UsedPercent{{{org_filter},{cluster_filter},{type_filter}}}',
            
            # JVM metrics
            "heap_usage": f'jvm_Memory_{{{org_filter},{cluster_filter},{type_filter},function="used",scope="HeapMemoryUsage"}}',
            # Dynamically selected GC metric based on detected GC type
            "gc_young_rate": f'{gc_metric}{{{org_filter},{cluster_filter},{type_filter},axonfunction="rate",function="CollectionTime"}}',
            
            # Cassandra core metrics
            "dropped_messages": f'cas_DroppedMessage_Dropped{{{org_filter},{cluster_filter},{type_filter},axonfunction="rate"}}',
            # Specific dropped message scopes
            "dropped_mutations": f'cas_DroppedMessage_Dropped{{{org_filter},{cluster_filter},{type_filter},axonfunction="rate",function="Count",scope="MUTATION_REQ"}}',
            "dropped_mutation_responses": f'cas_DroppedMessage_Dropped{{{org_filter},{cluster_filter},{type_filter},axonfunction="rate",function="Count",scope="MUTATION_RSP"}}',
            "dropped_reads": f'cas_DroppedMessage_Dropped{{{org_filter},{cluster_filter},{type_filter},axonfunction="rate",function="Count",scope="READ"}}',
            "dropped_hints": f'cas_DroppedMessage_Dropped{{{org_filter},{cluster_filter},{type_filter},axonfunction="rate",function="Count",scope="HINT"}}',
            "dropped_hint_responses": f'cas_DroppedMessage_Dropped{{{org_filter},{cluster_filter},{type_filter},axonfunction="rate",function="Count",scope="HINT_RSP"}}',
            "pending_compactions": f'cas_Compaction_PendingTasks{{{org_filter},{cluster_filter},{type_filter}}}',
            "compaction_bytes_rate": f'cas_Compaction_BytesCompacted{{{org_filter},{cluster_filter},{type_filter},axonfunction="rate"}}',
            "total_hints": f'cas_Storage_TotalHints{{{org_filter},{cluster_filter},{type_filter},axonfunction="rate"}}',
            "hints_in_progress": f'cas_Storage_TotalHintsInProgress{{{org_filter},{cluster_filter},{type_filter}}}',
            
            # Thread pool metrics
            "thread_pool_blocked": f'cas_ThreadPools_internal{{{org_filter},{cluster_filter},{type_filter},key="TotalBlockedTasks"}}',
            "thread_pool_active": f'cas_ThreadPools_internal{{{org_filter},{cluster_filter},{type_filter},key="ActiveTasks"}}',
            
            # Client request metrics
            "read_latency_p99": f'cas_ClientRequest_Latency{{{org_filter},{cluster_filter},{type_filter},scope="Read",function="99thPercentile"}}',
            "write_latency_p99": f'cas_ClientRequest_Latency{{{org_filter},{cluster_filter},{type_filter},scope="Write",function="99thPercentile"}}',
            "read_failures": f'cas_ClientRequest_Failures{{{org_filter},{cluster_filter},{type_filter},axonfunction="rate",scope="Read"}}',
            "write_failures": f'cas_ClientRequest_Failures{{{org_filter},{cluster_filter},{type_filter},axonfunction="rate",scope="Write"}}',
            
            # Note: Table-level metrics are now collected per-table in datamodel analyzer
            # These generic queries are removed to avoid errors,
            
            # Enhanced datamodel-specific metrics from dashboard analysis
            "bloom_filter_false_ratio": f'cas_Table_BloomFilterFalseRatio{{{org_filter},{cluster_filter},{type_filter}}}',
            "bloom_filter_disk_space": f'cas_Table_BloomFilterDiskSpaceUsed{{{org_filter},{cluster_filter},{type_filter}}}',
            "compression_ratio": f'cas_Table_CompressionRatio{{{org_filter},{cluster_filter},{type_filter}}}',
            "compression_metadata_memory": f'cas_Table_CompressionMetadataOffHeapMemoryUsed{{{org_filter},{cluster_filter},{type_filter}}}',
            
            # Table performance metrics from dashboard charts c3b59572 and 55124fe2
            "table_coordinator_reads": f'cas_Table_CoordinatorReadLatency{{{org_filter},{cluster_filter},{type_filter},axonfunction="rate",function="Count"}}',
            "table_coordinator_writes": f'cas_Table_CoordinatorWriteLatency{{{org_filter},{cluster_filter},{type_filter},axonfunction="rate",function="Count"}}',
            
            # SSTable metrics
            "table_sstable_count": f'cas_Table_LiveSSTableCount{{{org_filter},{cluster_filter},{type_filter}}}',
            "table_disk_space_used": f'cas_Table_LiveDiskSpaceUsed{{{org_filter},{cluster_filter},{type_filter}}}',
            
            # Cache metrics
            "table_row_cache_hit": f'cas_Table_RowCacheHit{{{org_filter},{cluster_filter},{type_filter},axonfunction="rate"}}',
            "table_row_cache_miss": f'cas_Table_RowCacheMiss{{{org_filter},{cluster_filter},{type_filter},axonfunction="rate"}}',
            "key_cache_hit_rate": f'cas_Cache_HitRate{{{org_filter},{cluster_filter},{type_filter},scope="KeyCache"}}',
        }
        
        for metric_name, query in metric_queries.items():
            try:
                result = self.client.query_range(
                    query=query,
                    start=start_time,
                    end=end_time,
                    step=resolution
                )
                
                if result is not None:
                    metrics[metric_name] = self._parse_prometheus_result(result)
                else:
                    logger.debug(f"Query returned None for metric {metric_name}")
                    metrics[metric_name] = []
                
            except Exception as e:
                logger.error(
                    f"Failed to collect metric {metric_name}",
                    error=str(e),
                    query=query
                )
        
        return metrics
    
    # def _collect_events(
    #     self,
    #     start_time: datetime,
    #     end_time: datetime
    # ) -> List[Dict[str, Any]]:
    #     """Collect cluster events"""
    #     try:
    #         # Use full time range for events collection
    #         logger.debug(f"Collecting events from {start_time} to {end_time}")
    #         
    #         return self.client.get_events(
    #             self.org,
    #             self.cluster_type,
    #             self.cluster,
    #             start_time,
    #             end_time
    #         )
    #     except Exception as e:
    #         logger.error("Failed to collect events", error=str(e))
    #         # Events are not critical for analysis since log analysis is disabled
    #         return []
    
    def _collect_log_events(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Dict[str, Any]]:
        """Collect specific log events for operations analysis"""
        log_events = {}
        
        # Define log searches based on Montecristo operations analysis
        # Use histograms for efficient counting of log patterns
        # Note: The AxonOps histogram API appears to use different indexing than the search API
        # These patterns work with the histogram API but may not return the same results with search
        # IMPORTANT: The 'batch_warnings' pattern detects batch-related activity in the histogram API
        # but actual log entries may not be retrievable via the search API due to API differences
        log_searches = {
            "prepared_statements": '"prepared statements"',
            "batch_warnings": 'Batch',  # Simplified pattern - histogram detects activity but logs may not be searchable
            "tombstone_warnings": 'tombstone',
            "aggregation_queries": 'Aggregation query',
            "gc_pauses": 'GCInspector',
            "gossip_pauses": 'FailureDetector',
            "large_partitions": 'large partition',
            # Note: dropped_hints now tracked via metrics (cas_DroppedMessage_Dropped with scope=HINT)
            "commitlog_sync": 'PERIODIC-COMMIT-LOG-SYNC',
            "repair_failures": 'repair',
        }
        
        for search_key, message_filter in log_searches.items():
            try:
                # Use histogram for efficient counting
                histogram_response = self.client.get_logs_histogram(
                    self.org,
                    self.cluster_type,
                    self.cluster,
                    start_time,
                    end_time,
                    message_filter
                )
                log_events[search_key] = histogram_response
                
                # Extract total count for logging
                total_count = 0
                if histogram_response and "metadata" in histogram_response:
                    total_count = int(histogram_response["metadata"].get("_count", 0))
                
                logger.debug(f"Collected histogram for {search_key}: {total_count} total events")
                
            except Exception as e:
                logger.error(
                    f"Failed to collect log histogram for {search_key}",
                    error=str(e),
                    filter=message_filter
                )
                log_events[search_key] = {}
        
        return log_events
    
    def _detect_gc_metric(self) -> str:
        """Detect the appropriate GC metric based on cluster nodes' JVM configuration"""
        try:
            # Get nodes to check JVM arguments
            node_list = self.client.get_nodes_full(
                self.org, self.cluster_type, self.cluster
            )
            
            if not node_list:
                logger.warning("No nodes found, defaulting to G1 GC metric")
                return "jvm_GarbageCollector_G1_Young_Generation"
            
            # Check the first node's JVM arguments
            first_node = node_list[0]
            # JVM args are in the Details section
            details = first_node.get('Details', {})
            jvm_args = details.get('comp_jvm_input arguments', '')
            
            # Use GCMetricSelector to determine the appropriate metric
            gc_type = GCMetricSelector.detect_gc_type(jvm_args)
            gc_metrics = GCMetricSelector.get_gc_metrics(jvm_args)
            
            # Get the metric name for collection time
            metric_name = gc_metrics.get('time', 'jvm_GarbageCollector_G1_Young_Generation')
            
            logger.info(f"Detected GC type: {gc_type}, using metric: {metric_name}")
            return metric_name
            
        except Exception as e:
            logger.warning(f"Failed to detect GC type, defaulting to G1: {str(e)}")
            return "jvm_GarbageCollector_G1_Young_Generation"
    
    def _parse_prometheus_result(self, result: Dict[str, Any]) -> List[MetricData]:
        """Parse Prometheus query result into MetricData objects"""
        metric_data_list = []
        
        if not result or result.get("status") != "success":
            return metric_data_list
        
        data = result.get("data", {})
        if data is None:
            return metric_data_list
            
        result_type = data.get("resultType", "")
        
        if result_type == "matrix":
            result_list = data.get("result", [])
            if result_list is None:
                return metric_data_list
                
            for series in result_list:
                metric = series.get("metric", {})
                values = series.get("values", [])
                
                data_points = []
                for timestamp, value in values:
                    try:
                        data_points.append(MetricPoint(
                            timestamp=datetime.fromtimestamp(timestamp),
                            value=float(value)
                        ))
                    except (ValueError, TypeError):
                        continue
                
                if data_points:
                    metric_data = MetricData(
                        metric_name=metric.get("__name__", "unknown"),
                        labels=metric,
                        data_points=data_points
                    )
                    metric_data_list.append(metric_data)
        
        return metric_data_list