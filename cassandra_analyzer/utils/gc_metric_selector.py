"""
GC Metric Selector - Determines which GC metrics to use based on JVM configuration
"""

import re
from typing import Dict, List, Optional, Tuple


class GCMetricSelector:
    """Selects appropriate GC metrics based on JVM configuration"""
    
    # GC type to metric mapping based on the dashboards file
    GC_METRICS = {
        'G1GC': {
            'count': 'jvm_GarbageCollector_G1_Young_Generation',
            'time': 'jvm_GarbageCollector_G1_Young_Generation',
            'display_name': 'G1 Young Generation'
        },
        'CMS': {
            # For CMS, ParNew handles young generation, ConcurrentMarkSweep handles old generation
            'count': 'jvm_GarbageCollector_ParNew',
            'time': 'jvm_GarbageCollector_ParNew',
            'old_count': 'jvm_GarbageCollector_ConcurrentMarkSweep',
            'old_time': 'jvm_GarbageCollector_ConcurrentMarkSweep',
            'display_name': 'ParNew + CMS'
        },
        'ParallelGC': {
            'count': 'jvm_GarbageCollector_ParNew',
            'time': 'jvm_GarbageCollector_ParNew',
            'display_name': 'ParNew'
        },
        'ZGC': {
            'count': 'jvm_GarbageCollector_ZGC',
            'time': 'jvm_GarbageCollector_ZGC',
            'display_name': 'ZGC'
        },
        'ShenandoahGC': {
            'count': 'jvm_GarbageCollector_Shenandoah_Cycles',
            'time': 'jvm_GarbageCollector_Shenandoah_Cycles',
            'pauses': 'jvm_GarbageCollector_Shenandoah_Pauses',
            'display_name': 'Shenandoah'
        }
    }
    
    @staticmethod
    def detect_gc_type(jvm_args: str) -> Optional[str]:
        """Detect GC type from JVM arguments"""
        if '-XX:+UseG1GC' in jvm_args:
            return 'G1GC'
        elif '-XX:+UseConcMarkSweepGC' in jvm_args:
            return 'CMS'
        elif '-XX:+UseParallelGC' in jvm_args or '-XX:+UseParallelOldGC' in jvm_args:
            return 'ParallelGC'
        elif '-XX:+UseZGC' in jvm_args:
            return 'ZGC'
        elif '-XX:+UseShenandoahGC' in jvm_args:
            return 'ShenandoahGC'
        elif '-XX:+UseSerialGC' in jvm_args:
            return 'SerialGC'
        else:
            # Default to G1GC for newer Java versions
            return 'G1GC'
    
    @classmethod
    def get_gc_metrics(cls, jvm_args: str) -> Dict[str, str]:
        """Get appropriate GC metrics based on JVM configuration"""
        gc_type = cls.detect_gc_type(jvm_args)
        
        if gc_type in cls.GC_METRICS:
            return cls.GC_METRICS[gc_type]
        else:
            # Default to G1GC metrics
            return cls.GC_METRICS['G1GC']
    
    @classmethod
    def build_gc_queries(cls, jvm_args: str, dc: str = None, rack: str = None, 
                        host_id: str = None) -> Dict[str, str]:
        """Build GC metric queries with filters"""
        metrics = cls.get_gc_metrics(jvm_args)
        queries = {}
        
        # Build filter string
        filters = []
        if dc:
            filters.append(f"dc=~'{dc}'")
        if rack:
            filters.append(f"rack=~'{rack}'")
        if host_id:
            filters.append(f"host_id=~'{host_id}'")
        
        filter_str = ','.join(filters)
        if filter_str:
            filter_str = '{' + filter_str + '}'
        
        # GC count per second query
        if 'count' in metrics:
            queries['gc_count_rate'] = (
                f"{metrics['count']}"
                f"{{axonfunction='rate',function='CollectionCount'{(',' + filter_str[1:-1]) if filter_str else ''}}}"
            )
        
        # GC duration query
        if 'time' in metrics:
            queries['gc_duration_rate'] = (
                f"{metrics['time']}"
                f"{{axonfunction='rate',function='CollectionTime'{(',' + filter_str[1:-1]) if filter_str else ''}}}"
            )
        
        # Shenandoah-specific pause metric
        if 'pauses' in metrics:
            queries['gc_pauses_rate'] = (
                f"{metrics['pauses']}"
                f"{{axonfunction='rate',function='CollectionTime'{(',' + filter_str[1:-1]) if filter_str else ''}}}"
            )
        
        return queries
    
    @classmethod
    def get_gc_recommendations(cls, gc_type: str, heap_size_gb: int) -> List[str]:
        """Get GC-specific recommendations"""
        recommendations = []
        
        if gc_type == 'G1GC':
            if heap_size_gb < 20:
                recommendations.append(
                    "G1GC performs best with heap sizes >= 20GB. "
                    "Consider increasing heap or using ParallelGC for smaller heaps."
                )
            if heap_size_gb > 32:
                recommendations.append(
                    "Heap size > 32GB loses compressed OOPs benefit. "
                    "Consider multiple instances or ZGC for very large heaps."
                )
        
        elif gc_type == 'CMS':
            recommendations.append(
                "CMS is deprecated. Consider migrating to G1GC (20-31GB heaps) "
                "or ZGC (very large heaps)."
            )
        
        elif gc_type == 'ZGC':
            if heap_size_gb < 32:
                recommendations.append(
                    "ZGC is designed for very large heaps (>32GB). "
                    "Consider G1GC for heaps < 32GB."
                )
        
        elif gc_type == 'ShenandoahGC':
            if heap_size_gb < 8:
                recommendations.append(
                    "ShenandoahGC may have overhead for small heaps (<8GB). "
                    "Consider ParallelGC or G1GC."
                )
        
        return recommendations