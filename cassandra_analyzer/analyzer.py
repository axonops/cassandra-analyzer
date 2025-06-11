"""
Main analyzer orchestrator
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
import structlog

from .client import AxonOpsClient
from .config import Config
from .collectors import ClusterDataCollector
from .models import ClusterState
from .analyzers import (
    InfrastructureAnalyzer,
    ConfigurationAnalyzer,
    ExtendedConfigurationAnalyzer,
    OperationsAnalyzer,
    OperationsLogAnalyzer,
    DataModelAnalyzer,
    SecurityAnalyzer,
)
from .reports.generator_enhanced import EnhancedReportGenerator

logger = structlog.get_logger()


class CassandraAnalyzer:
    """Main analyzer class that orchestrates the analysis process"""
    
    def __init__(
        self,
        client: AxonOpsClient,
        config: Config,
        org: str,
        cluster_type: str,
        cluster: str,
        start_time: datetime,
        end_time: datetime,
        output_dir: Path
    ):
        self.client = client
        self.config = config
        self.org = org
        self.cluster_type = cluster_type
        self.cluster = cluster
        self.start_time = start_time
        self.end_time = end_time
        self.output_dir = output_dir
        
        # Initialize components
        self.collector = ClusterDataCollector(
            client=client,
            org=org,
            cluster_type=cluster_type,
            cluster=cluster
        )
        
        self.analyzers = {}
        if config.analysis.enable_sections.get("infrastructure", True):
            self.analyzers["infrastructure"] = InfrastructureAnalyzer(config)
        if config.analysis.enable_sections.get("configuration", True):
            self.analyzers["configuration"] = ConfigurationAnalyzer(config)
            self.analyzers["extended_configuration"] = ExtendedConfigurationAnalyzer(config)
        if config.analysis.enable_sections.get("operations", True):
            self.analyzers["operations"] = OperationsAnalyzer(config)
            # Temporarily disabled due to AxonOps API log search limitations
            # self.analyzers["operations_logs"] = OperationsLogAnalyzer(config)
        if config.analysis.enable_sections.get("datamodel", True):
            self.analyzers["datamodel"] = DataModelAnalyzer(config)
        if config.analysis.enable_sections.get("security", True):
            self.analyzers["security"] = SecurityAnalyzer(config)
        
        self.report_generator = EnhancedReportGenerator(output_dir)
    
    def analyze(self, generate_pdf: bool = False) -> Path:
        """Run the complete analysis and generate report
        
        Args:
            generate_pdf: Whether to also generate a PDF version of the report
            
        Returns:
            Path to the generated report
        """
        logger.info(
            "Starting analysis",
            org=self.org,
            cluster=self.cluster,
            start_time=self.start_time,
            end_time=self.end_time
        )
        
        # Step 1: Collect data
        logger.info("Collecting cluster data")
        cluster_state = self._collect_data()
        
        # Step 2: Run analyzers
        logger.info("Running analysis sections")
        analysis_results = self._run_analyzers(cluster_state)
        
        # Step 3: Generate report
        logger.info("Generating report")
        report_path = self._generate_report(cluster_state, analysis_results, generate_pdf)
        
        logger.info("Analysis complete", report_path=str(report_path))
        return report_path
    
    def _collect_data(self) -> ClusterState:
        """Collect all necessary data from AxonOps API"""
        return self.collector.collect(
            start_time=self.start_time,
            end_time=self.end_time,
            metrics_resolution=f"{self.config.analysis.metrics_resolution_seconds}s"
        )
    
    def _run_analyzers(self, cluster_state: ClusterState) -> Dict[str, Any]:
        """Run all enabled analyzers"""
        results = {}
        
        for name, analyzer in self.analyzers.items():
            logger.info(f"Running {name} analyzer")
            try:
                results[name] = analyzer.analyze(cluster_state)
            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                logger.error(f"Error in {name} analyzer", error=str(e), error_type=type(e).__name__, traceback=error_details)
                results[name] = {
                    "error": str(e),
                    "recommendations": []
                }
        
        return results
    
    def _generate_report(
        self,
        cluster_state: ClusterState,
        analysis_results: Dict[str, Any],
        generate_pdf: bool = False
    ) -> Path:
        """Generate the final report"""
        report_data = {
            "cluster_info": {
                "organization": self.org,
                "cluster_type": self.cluster_type,
                "cluster_name": self.cluster,
                "analysis_time": datetime.utcnow().isoformat(),
                "time_range": {
                    "start": self.start_time.isoformat(),
                    "end": self.end_time.isoformat(),
                }
            },
            "cluster_state": cluster_state,
            "analysis_results": analysis_results,
        }
        
        return self.report_generator.generate(report_data, generate_pdf=generate_pdf)