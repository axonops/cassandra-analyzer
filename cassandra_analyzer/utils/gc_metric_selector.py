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
    def get_gc_recommendations(
        cls,
        gc_type: str,
        heap_size_gb: float,
        system_memory_gb: Optional[float] = None,
        cassandra_version: Optional[str] = None,
        java_major: Optional[int] = None,
    ) -> List[str]:
        """Get GC-specific recommendations.

        ``system_memory_gb`` constrains heap-sizing advice so we never suggest a
        heap the host cannot afford. Cassandra guidance is to keep heap at
        25-50% of system RAM (the rest is needed for page cache and off-heap
        structures), so a 20GB G1GC heap implies ~40GB RAM minimum.

        ``cassandra_version`` and ``java_major`` (when supplied) let us
        recommend Shenandoah exclusively on Cassandra 5.x + JDK 17 — the
        stack where G1GC is no longer the right default.
        """
        recommendations = []

        # 50% of RAM is the absolute upper bound for the JVM heap on Cassandra.
        max_safe_heap_gb = (system_memory_gb / 2) if system_memory_gb else None

        # Cassandra 5.x + JDK 17 → Shenandoah only (no G1GC fallback).
        try:
            from .version import V5_0, version_at_least  # type: ignore
            is_5x = version_at_least(cassandra_version, V5_0) if cassandra_version else False
        except Exception:
            # Fall back to a string check so the selector stays usable in
            # contexts where the version helpers aren't importable.
            is_5x = bool(cassandra_version and cassandra_version.lstrip('v').startswith(('5.', '6.', '7.')))
        shenandoah_only = bool(is_5x and java_major is not None and java_major >= 17)

        if gc_type == 'G1GC':
            if shenandoah_only:
                recommendations.append(
                    "On Cassandra 5.x + JDK 17, Shenandoah is the recommended "
                    "GC algorithm; G1GC is not recommended on this stack."
                )
            if heap_size_gb < 20:
                if max_safe_heap_gb is not None and max_safe_heap_gb < 20:
                    # Host is too small to ever run a 20GB heap safely — do not
                    # tell the operator to raise the heap to a level that would
                    # starve the page cache. Suggest a low-pause GC instead.
                    recommendations.append(
                        f"G1GC performs best with heap sizes >= 20GB, but this host "
                        f"only has {system_memory_gb:.1f}GB RAM (heap should stay "
                        f"<=50% of system memory, i.e. <= {max_safe_heap_gb:.0f}GB). "
                        f"Consider Shenandoah (or ParallelGC) for low-pause "
                        f"behaviour on smaller heaps rather than enlarging the heap."
                    )
                elif not shenandoah_only:
                    recommendations.append(
                        "G1GC performs best with heap sizes >= 20GB. "
                        "Consider increasing heap or using ParallelGC for smaller heaps."
                    )
            if heap_size_gb > 31:
                recommendations.append(
                    "Heap size > 31GB loses compressed OOPs benefit. "
                    "Consider multiple instances or Shenandoah for very large heaps."
                )

        elif gc_type == 'CMS':
            if shenandoah_only:
                recommendations.append(
                    "CMS is deprecated. On Cassandra 5.x + JDK 17, migrate to "
                    "Shenandoah (G1GC is not recommended on this stack)."
                )
            else:
                recommendations.append(
                    "CMS is deprecated. Consider migrating to G1GC (20-31GB heaps) "
                    "or Shenandoah (low-pause / large heaps)."
                )

        elif gc_type == 'ZGC':
            # Non-generational ZGC (the only flavour available on JDK 17) is
            # not recommended for Cassandra due to allocation-rate / throughput
            # behaviour on write-heavy workloads. Generational ZGC would be
            # acceptable, but it requires JDK 21+, which Cassandra 5.0 does
            # not yet support. Steer users to Shenandoah (or G1GC on older
            # stacks where Shenandoah-only doesn't apply).
            if shenandoah_only:
                recommendations.append(
                    "ZGC is not recommended for Cassandra on JDK 17. Generational "
                    "ZGC (the recommended flavour) requires JDK 21+, which "
                    "Cassandra 5.0 does not yet support. Migrate to Shenandoah "
                    "(recommended on Cassandra 5.x + JDK 17)."
                )
            else:
                recommendations.append(
                    "ZGC is not recommended for Cassandra on JDK 17. Generational "
                    "ZGC (the recommended flavour) requires JDK 21+, which "
                    "Cassandra 5.0 does not yet support. Consider migrating to "
                    "G1GC (20-31GB heaps) or Shenandoah."
                )
        
        elif gc_type == 'ShenandoahGC':
            if heap_size_gb < 8:
                recommendations.append(
                    "ShenandoahGC may have overhead for small heaps (<8GB). "
                    "Consider ParallelGC or G1GC."
                )
        
        return recommendations