"""
Enhanced report generator for analysis results
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from jinja2 import Environment, FileSystemLoader, select_autoescape
import structlog
from ..models.recommendations import Severity

# Make PDF generation optional
try:
    from .pdf_generator import PDFGenerator
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False


class EnhancedReportGenerator:
    """Generates enhanced analysis reports with better formatting and explanations"""
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up Jinja2 environment
        template_dir = Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=False  # Disable autoescape for markdown output
        )
        
        # Register custom filters
        self.env.filters['format_number'] = self._format_number
        self.env.filters['severity_icon'] = self._severity_icon
        self.env.filters['severity_color'] = self._severity_color
        self.env.filters['severity_text'] = self._severity_text
        self.env.filters['get_attr'] = self._get_attr
    
    def generate(
        self,
        report_data: Dict[str, Any],
        generate_pdf: bool = False,
        for_agent: bool = False,
    ) -> Path:
        """Generate the analysis report

        Args:
            report_data: The analysis data
            generate_pdf: Whether to also generate a PDF version
            for_agent: When True, append the Coverage Manifest + reading
                guide to the markdown report. The JSON sibling always
                contains the manifest data.

        Returns:
            Path to the generated markdown report
        """
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        cluster_name = report_data["cluster_info"]["cluster_name"]

        # Generate enhanced markdown report
        md_path = self.output_dir / f"cassandra_analysis_{cluster_name}_{timestamp}.md"
        self._generate_enhanced_markdown(report_data, md_path, for_agent=for_agent)

        # Generate JSON report for programmatic access
        json_path = self.output_dir / f"cassandra_analysis_{cluster_name}_{timestamp}.json"
        self._generate_json(report_data, json_path)
        
        # Generate PDF if requested
        if generate_pdf:
            if not PDF_AVAILABLE:
                structlog.get_logger().warning("PDF generation requested but dependencies not installed. Install with: pip install weasyprint markdown beautifulsoup4")
            else:
                try:
                    pdf_generator = PDFGenerator()
                    pdf_path = pdf_generator.generate_pdf(md_path)
                    structlog.get_logger().info("PDF report generated", path=str(pdf_path))
                except Exception as e:
                    structlog.get_logger().error("Failed to generate PDF", error=str(e))
                    # Don't fail the entire process if PDF generation fails
        
        return md_path
    
    def _generate_enhanced_markdown(
        self,
        report_data: Dict[str, Any],
        output_path: Path,
        for_agent: bool = False,
    ):
        """Generate enhanced markdown report"""
        # Aggregate recommendations to avoid repetition
        aggregated_results = {}
        node_details = {}  # Store node-specific details for appendix

        for section_name, section_data in report_data["analysis_results"].items():
            if section_data.get("error"):
                aggregated_results[section_name] = section_data
                continue

            recommendations = section_data.get("recommendations", [])
            aggregated_recs = self._aggregate_recommendations(recommendations)

            # Store aggregated recommendations (preserve checks for the manifest)
            aggregated_results[section_name] = {
                **section_data,
                "recommendations": aggregated_recs,
            }

            # Collect node details for appendix
            for agg_rec in aggregated_recs:
                if agg_rec.get("affected_nodes"):
                    issue_key = f"{section_name}:{agg_rec['title']}"
                    node_details[issue_key] = {
                        "section": section_name,
                        "title": agg_rec["title"],
                        "affected_nodes": agg_rec["affected_nodes"],
                    }

        # Process recommendations to group by priority
        recommendations_by_priority = self._group_recommendations_by_priority(aggregated_results)

        # Calculate statistics
        stats = self._calculate_statistics(report_data)

        # Coverage manifest (only meaningful for the agent format)
        coverage = self._coverage_summary(aggregated_results)
        coverage_appendix = (
            self._render_coverage_appendix(aggregated_results, coverage) if for_agent else ""
        )
        agent_preamble = self._render_agent_preamble() if for_agent else ""
        agent_findings = (
            self._build_agent_findings(recommendations_by_priority) if for_agent else []
        )
        if for_agent:
            node_details = self._compact_node_details_for_agent(node_details)

        # Prepare context for template
        context = {
            "cluster_info": report_data["cluster_info"],
            "cluster_state": report_data["cluster_state"],
            "analysis_results": aggregated_results,
            "generation_time": datetime.now(UTC).isoformat(),
            "recommendations_by_priority": recommendations_by_priority,
            "stats": stats,
            "sections": self._prepare_sections(aggregated_results),
            "node_details": node_details,
            "for_agent": for_agent,
            "coverage": coverage,
            "agent_preamble": agent_preamble,
            "coverage_appendix": coverage_appendix,
            "agent_findings": agent_findings,
        }

        # Render template
        template = self._get_enhanced_markdown_template()
        content = template.render(**context)

        # Clean up multiple consecutive empty lines
        content = self._clean_empty_lines(content)
        if for_agent:
            content = self._strip_agent_decorations(content)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

    @staticmethod
    def _coverage_summary(analysis_results: Dict[str, Any]) -> Dict[str, Any]:
        """Aggregate per-section check totals into a single coverage block."""
        per_section: Dict[str, Dict[str, int]] = {}
        totals = {"pass": 0, "fail": 0, "skipped": 0, "no_data": 0}
        for section_name, section in analysis_results.items():
            counts = {"pass": 0, "fail": 0, "skipped": 0, "no_data": 0}
            for check in section.get("checks") or []:
                status = check.get("status") if isinstance(check, dict) else None
                if status in counts:
                    counts[status] += 1
                    totals[status] += 1
            per_section[section_name] = counts
        return {"totals": totals, "by_section": per_section}

    @staticmethod
    def _render_agent_preamble() -> str:
        return (
            "## How to read this report\n\n"
            "This report is the contract between cassandra-analyzer and any downstream\n"
            "consumer (human reviewer or LLM agent). Interpret it as follows:\n\n"
            "- **Findings** under each section are issues the tool detected. Severity\n"
            "  (CRITICAL / WARNING / INFO) is authoritative — use it verbatim. Each\n"
            "  finding maps to a stable `id` listed in the Coverage Manifest.\n"
            "- **Coverage Manifest** (appendix) lists every check the tool considered,\n"
            "  in one of four states:\n"
            "  - `pass` — check ran cleanly, the cluster meets expectations on this\n"
            "    point. Do NOT re-query or re-investigate.\n"
            "  - `fail` — check ran and produced a finding above. Cross-reference by\n"
            "    `id`. Do NOT re-derive.\n"
            "  - `skipped` — a precondition was not met (e.g. single-node cluster).\n"
            "    The check does not apply. Do not surface as an issue.\n"
            "  - `no_data` — the tool would have run this check but the required\n"
            "    data source returned nothing. **This area is not yet evaluated.** If\n"
            "    it is in scope for your output, query the source listed in the\n"
            "    manifest yourself.\n"
            "- The richer machine-readable JSON sibling of this file (same basename,\n"
            "  `.json`) carries the same content with full per-check `data_source`\n"
            "  strings and `recommendation_id` cross-references.\n"
        )

    @staticmethod
    def _strip_agent_decorations(content: str) -> str:
        """Strip emoji from markdown intended for an LLM consumer.

        The agent preamble already declares that severity strings
        (CRITICAL / WARNING / INFO) are authoritative, so the visual icons
        are pure token cost. We also tighten whitespace left behind once
        the icons are gone so cells like `| 🔴 CRITICAL |` collapse to
        `| CRITICAL |` rather than `|  CRITICAL |`.
        """
        import re
        # Broad sweep of common emoji + pictograph ranges plus the ZWJ /
        # variation-selector code points that may follow them.
        emoji_re = re.compile(
            "["
            "\U0001F300-\U0001FAFF"  # symbols & pictographs (incl. supplemental)
            "\U00002600-\U000027BF"  # misc symbols + dingbats
            "\U0001F000-\U0001F02F"  # mahjong/dominoes
            "‍️"           # ZWJ + VS16
            "]+",
            flags=re.UNICODE,
        )
        content = emoji_re.sub("", content)
        # Tighten "|  text" / "text  |" left behind by removed icons.
        # Use [ \t] explicitly — \s would swallow newlines and collapse
        # multi-line tables onto a single line.
        content = re.sub(r"\|[ \t]+", "| ", content)
        content = re.sub(r"[ \t]+\|", " |", content)
        # Collapse remaining runs of inline whitespace within a line.
        content = re.sub(r"[ \t]{2,}", " ", content)
        return content

    @staticmethod
    def _build_agent_findings(
        recommendations_by_priority: Dict[str, List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        """Flatten the priority groups into a single severity-sorted list.

        For agent mode we want one canonical findings table rather than
        separate Immediate / Near Term / Long Term tables — the severity
        column carries the same information in one row.
        """
        findings: List[Dict[str, Any]] = []
        order = (("immediate", "CRITICAL"), ("nearterm", "WARNING"), ("longterm", "INFO"))
        for key, severity in order:
            for rec in recommendations_by_priority.get(key, []):
                ctx = rec.get("context") or {}
                current = rec.get("current_value")
                if current in (None, ""):
                    current = ctx.get("current_value", "")
                recommended = ctx.get("recommended_value", "")
                findings.append({
                    "severity": severity,
                    "section": rec["section"].replace("_", " ").title(),
                    "title": rec.get("title", ""),
                    "description": rec.get("description", "") or "",
                    "current": current or "",
                    "recommended": recommended or "",
                    "affected": rec.get("count", 1),
                    "recommendation": rec.get("recommendation", "") or "",
                    "config_location": ctx.get("config_location", ""),
                })
        return findings

    @staticmethod
    def _compact_node_details_for_agent(
        node_details: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Mark per-issue node detail entries that can collapse to one row.

        When every affected node carries identical detail values, a row
        per node is pure repetition for an LLM consumer. We flag those
        cases so the template can render a single line listing all
        hostnames instead of N identical rows. Mixed values keep the
        per-node table.
        """
        compacted: Dict[str, Any] = {}
        for issue_key, entry in node_details.items():
            affected = entry.get("affected_nodes") or []
            entry_out = dict(entry)
            if len(affected) > 1:
                def _signature(node_info: Dict[str, Any]) -> Tuple:
                    details = node_info.get("details") or {}
                    return tuple(sorted(
                        (k, str(v)) for k, v in details.items() if k != "node_id"
                    ))
                first_sig = _signature(affected[0])
                entry_out["agent_compact"] = all(
                    _signature(n) == first_sig for n in affected[1:]
                )
            else:
                entry_out["agent_compact"] = False
            compacted[issue_key] = entry_out
        return compacted

    def _render_coverage_appendix(
        self, analysis_results: Dict[str, Any], coverage: Dict[str, Any],
    ) -> str:
        """Render the Coverage Manifest appendix as markdown."""
        lines = ["## Coverage Manifest", ""]
        lines.append(
            "_What this tool checked, so downstream consumers know what they can trust "
            "and what they still need to query._"
        )
        lines.append("")
        totals = coverage["totals"]
        lines.append(
            f"**Totals:** {totals['pass']} pass, {totals['fail']} fail, "
            f"{totals['skipped']} skipped, {totals['no_data']} no_data."
        )
        lines.append("")

        lines.append("<details><summary>Checks by section</summary>\n")
        for section_name, section in analysis_results.items():
            checks = section.get("checks") or []
            if not checks:
                continue
            lines.append(f"### {section_name.replace('_', ' ').title()}")
            lines.append("")
            lines.append("| ID | Status | Description | Source / Reason |")
            lines.append("| --- | --- | --- | --- |")
            for check in checks:
                cid = check.get("id", "")
                status = check.get("status", "")
                # Normalize enum → its string value (e.g. CheckStatus.PASS → "pass")
                status_str = status.value if hasattr(status, "value") else str(status)
                desc = (check.get("description") or "").replace("|", "\\|")
                if status_str in {"skipped", "no_data"}:
                    last = (check.get("skipped_reason") or "").replace("|", "\\|")
                else:
                    last = (check.get("data_source") or "").replace("|", "\\|")
                lines.append(f"| `{cid}` | {status_str} | {desc} | {last} |")
            lines.append("")
        lines.append("</details>")
        return "\n".join(lines)
    
    def _generate_json(self, report_data: Dict[str, Any], output_path: Path):
        """Generate JSON report"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, default=str)
    
    def _group_recommendations_by_priority(self, analysis_results: Dict[str, Any]) -> Dict[str, List[Dict]]:
        """Group recommendations by priority level"""
        grouped = {
            "immediate": [],
            "nearterm": [],
            "longterm": []
        }
        
        for section_name, section_data in analysis_results.items():
            if section_data.get("error"):
                continue
                
            for rec in section_data.get("recommendations", []):
                # Handle both dict and object formats
                if isinstance(rec, dict):
                    rec_dict = {
                        "section": section_name,
                        "title": rec.get("title", "Unknown"),
                        "description": rec.get("description", ""),
                        "recommendation": rec.get("recommendation", ""),
                        "current_value": rec.get("current_value"),
                        "impact": rec.get("impact"),
                        "category": rec.get("category", "general"),
                        "context": rec.get("context", {}),
                        "count": rec.get("count", 1),
                    }
                    severity = rec.get("severity", "INFO")
                    if isinstance(severity, str):
                        severity_str = severity.upper()
                    else:
                        severity_str = severity.value.upper()
                else:
                    rec_dict = {
                        "section": section_name,
                        "title": rec.title,
                        "description": rec.description,
                        "recommendation": rec.recommendation,
                        "current_value": rec.current_value,
                        "impact": rec.impact,
                        "category": rec.category,
                        "context": rec.context if hasattr(rec, 'context') else {},
                        "count": 1,
                    }
                    severity_str = rec.severity.value.upper() if hasattr(rec.severity, 'value') else str(rec.severity).upper()
                
                if severity_str == "CRITICAL":
                    grouped["immediate"].append(rec_dict)
                elif severity_str == "WARNING":
                    grouped["nearterm"].append(rec_dict)
                else:
                    grouped["longterm"].append(rec_dict)
        
        return grouped
    
    def _aggregate_recommendations(self, recommendations: List[Any]) -> List[Dict[str, Any]]:
        """Aggregate similar recommendations to avoid repetition for large clusters"""
        aggregated = {}
        
        for rec in recommendations:
            # Extract key fields
            if isinstance(rec, dict):
                title = rec.get("title", "Unknown Issue")
                severity = rec.get("severity", "INFO")
                description_base = rec.get("description", "")
                # Remove node-specific parts from description for grouping
                if "Node " in description_base:
                    import re
                    # Remove node identifiers to create a generic description
                    description_base = re.sub(r'Node [^\s]+ ', 'Node(s) ', description_base)
                    description_base = re.sub(r'nodes? [^\s]+ ', 'affected node(s) ', description_base)
                
                # Special handling for swap space warnings to aggregate them
                if title == "Swap Usage Detected" and "swap space" in description_base:
                    # Remove the specific percentage to allow aggregation
                    description_base = re.sub(r'is using \d+\.\d+% of swap space', 'is using swap space', description_base)
                
                impact = rec.get("impact", "")
                recommendation = rec.get("recommendation", "")
                current_value = rec.get("current_value", "")
                context = rec.get("context", {})
                node_id = context.get("node_id", "")
                
            else:
                title = rec.title
                severity = rec.severity
                description_base = rec.description
                # Remove node-specific parts from description for grouping
                if "Node " in description_base:
                    import re
                    description_base = re.sub(r'Node [^\s]+ ', 'Node(s) ', description_base)
                    description_base = re.sub(r'nodes? [^\s]+ ', 'affected node(s) ', description_base)
                
                # Special handling for swap space warnings to aggregate them
                if title == "Swap Usage Detected" and "swap space" in description_base:
                    # Remove the specific percentage to allow aggregation
                    description_base = re.sub(r'is using \d+\.\d+% of swap space', 'is using swap space', description_base)
                
                impact = rec.impact
                recommendation = rec.recommendation
                current_value = rec.current_value
                context = rec.context if hasattr(rec, 'context') else {}
                node_id = context.get("node_id", "")
            
            # Create aggregation key based on title and base description
            agg_key = f"{title}|{description_base}"
            
            if agg_key not in aggregated:
                aggregated[agg_key] = {
                    "title": title,
                    "severity": severity,
                    "description_base": description_base,
                    "impact": impact,
                    "recommendation": recommendation,
                    "current_value": current_value,
                    "affected_nodes": [],
                    "context": context,
                    "count": 0
                }
            
            # Add node to affected list if it has a node_id
            if node_id:
                node_info = {
                    "node_id": node_id,
                    "details": context
                }
                aggregated[agg_key]["affected_nodes"].append(node_info)
            aggregated[agg_key]["count"] += 1
        
        # Convert to list and update descriptions with counts
        result = []
        for agg_data in aggregated.values():
            if agg_data["count"] > 1:
                # Special handling for swap space to show range
                if agg_data["title"] == "Swap Usage Detected" and "swap space" in agg_data["description_base"]:
                    # Extract swap percentages from all affected nodes
                    swap_percentages = []
                    for node_info in agg_data["affected_nodes"]:
                        swap_pct = node_info["details"].get("swap_percentage", 0)
                        if swap_pct > 0:
                            swap_percentages.append(swap_pct)
                    
                    if swap_percentages:
                        min_swap = min(swap_percentages)
                        max_swap = max(swap_percentages)
                        if min_swap == max_swap:
                            agg_data["description"] = f"Node(s) is using {min_swap:.1f}% of swap space ({agg_data['count']} nodes affected)"
                        else:
                            agg_data["description"] = f"Node(s) is using {min_swap:.1f}-{max_swap:.1f}% of swap space ({agg_data['count']} nodes affected)"
                    else:
                        agg_data["description"] = f"{agg_data['description_base']} ({agg_data['count']} nodes affected)"
                else:
                    agg_data["description"] = f"{agg_data['description_base']} ({agg_data['count']} nodes affected)"
            else:
                agg_data["description"] = agg_data["description_base"]
            result.append(agg_data)
        
        return result
    
    def _calculate_statistics(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate report statistics"""
        total_recommendations = 0
        critical_count = 0
        warning_count = 0
        info_count = 0
        
        for section_name, section_data in report_data["analysis_results"].items():
            if section_data.get("error"):
                continue
                
            for rec in section_data.get("recommendations", []):
                total_recommendations += 1
                
                # Handle both dict and object formats
                if isinstance(rec, dict):
                    severity = rec.get("severity", "INFO")
                    if isinstance(severity, str):
                        severity_str = severity.upper()
                    else:
                        severity_str = severity.value.upper() if hasattr(severity, 'value') else str(severity).upper()
                else:
                    severity_str = rec.severity.value.upper() if hasattr(rec.severity, 'value') else str(rec.severity).upper()
                
                if severity_str == "CRITICAL":
                    critical_count += 1
                elif severity_str == "WARNING":
                    warning_count += 1
                else:
                    info_count += 1
        
        return {
            "total_recommendations": total_recommendations,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "info_count": info_count
        }
    
    def _prepare_sections(self, analysis_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Prepare sections with enhanced metadata"""
        sections = []
        
        section_metadata = {
            "infrastructure": {
                "icon": "🖥️",
                "title": "Infrastructure",
                "order": 1,
                "brief": "Hardware and OS configuration supporting your cluster"
            },
            "configuration": {
                "icon": "⚙️",
                "title": "Configuration",
                "order": 2,
                "brief": "Cassandra settings and JVM parameters"
            },
            "operations": {
                "icon": "📊",
                "title": "Operations",
                "order": 3,
                "brief": "Performance metrics and operational health"
            },
            "operations_logs": {
                "icon": "📝",
                "title": "Operations Logs",
                "order": 4,
                "brief": "Log analysis and error patterns"
            },
            "datamodel": {
                "icon": "📐",
                "title": "Data Model",
                "order": 5,
                "brief": "Schema design and table optimization"
            },
            "security": {
                "icon": "🔐",
                "title": "Security",
                "order": 6,
                "brief": "Authentication, authorization, and encryption"
            },
            "extended_configuration": {
                "icon": "🔧",
                "title": "Extended Configuration",
                "order": 7,
                "brief": "Advanced settings and fine-tuning"
            }
        }
        
        for section_name, section_data in analysis_results.items():
            metadata = section_metadata.get(section_name, {
                "icon": "📋",
                "title": section_name.replace("_", " ").title(),
                "order": 99,
                "brief": "Additional analysis"
            })
            
            sections.append({
                "name": section_name,
                "icon": metadata["icon"],
                "title": metadata["title"],
                "brief": metadata["brief"],
                "data": section_data,
                "order": metadata["order"]
            })
        
        # Sort by order
        sections.sort(key=lambda x: x["order"])
        return sections
    
    def _format_number(self, value) -> str:
        """Format numbers with appropriate units"""
        if value is None:
            return "N/A"
        
        try:
            num = float(value)
            if num >= 1_000_000_000:
                return f"{num/1_000_000_000:.1f}B"
            elif num >= 1_000_000:
                return f"{num/1_000_000:.1f}M"
            elif num >= 1_000:
                return f"{num/1_000:.1f}K"
            else:
                return str(int(num))
        except:
            return str(value)
    
    def _severity_icon(self, severity) -> str:
        """Get icon for severity level"""
        if severity is None:
            return "⚪"
            
        if hasattr(severity, 'value'):
            severity_str = severity.value
        else:
            severity_str = str(severity)
            
        icons = {
            "CRITICAL": "🔴",
            "WARNING": "🟡",
            "INFO": "🔵"
        }
        return icons.get(severity_str.upper(), "⚪")
    
    def _severity_color(self, severity) -> str:
        """Get color for severity level"""
        if hasattr(severity, 'value'):
            severity = severity.value
            
        colors = {
            "CRITICAL": "red",
            "WARNING": "yellow",
            "INFO": "blue"
        }
        return colors.get(severity.upper(), "gray")
    
    def _severity_text(self, severity) -> str:
        """Get text representation of severity level"""
        if severity is None:
            return "INFO"
            
        if hasattr(severity, 'value'):
            return severity.value.upper()
        else:
            return str(severity).upper()
    
    def _get_attr(self, obj, attr_name, default=None):
        """Get attribute from object or dict"""
        if isinstance(obj, dict):
            return obj.get(attr_name, default)
        else:
            return getattr(obj, attr_name, default)
    
    def _clean_empty_lines(self, content: str) -> str:
        """Clean up multiple consecutive empty lines in markdown content"""
        import re
        
        # Replace multiple consecutive newlines with a maximum of 2
        content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)
        
        # Clean up empty lines between markdown elements
        # Remove empty lines after headers
        content = re.sub(r'(^#+[^\n]+)\n\s*\n', r'\1\n', content, flags=re.MULTILINE)
        
        # Remove empty lines before headers  
        content = re.sub(r'\n\s*\n(^#+[^\n]+)', r'\n\1', content, flags=re.MULTILINE)
        
        # Clean up empty lines around horizontal rules
        content = re.sub(r'\n\s*\n---\n\s*\n', '\n\n---\n\n', content)
        
        # Remove trailing whitespace on each line
        content = re.sub(r'[ \t]+$', '', content, flags=re.MULTILINE)
        
        # Ensure file ends with single newline
        content = content.rstrip() + '\n'
        
        return content
    
    def _get_enhanced_markdown_template(self) -> str:
        """Get the enhanced markdown template"""
        return self.env.from_string("""
# Cassandra Cluster Health Assessment

**Cluster:** {{ cluster_info.cluster_name }}
**Organization:** {{ cluster_info.organization }}
**Generated:** {{ generation_time }}

---
{% if for_agent %}
{{ agent_preamble }}
---
{% endif %}
## Executive Summary

{% if not for_agent %}
{% if stats.critical_count > 0 %}
### 🔴 **Critical Issues Detected**

Your cluster has **{{ stats.critical_count }} critical issue(s)** requiring immediate attention. Critical issues indicate:
- Severe misconfigurations that could lead to failures
- Resource constraints that may cause node instability
- Configuration conflicts preventing proper cluster operation

**Action Required:** Review critical issues below and implement fixes as soon as possible.

{% elif stats.warning_count > 0 %}
### 🟡 **Performance Optimization Needed**

Your cluster has **{{ stats.warning_count }} warning(s)** that should be addressed for optimal performance. While not immediately critical, these can lead to:
- Reduced performance and higher latencies
- Increased operational costs
- Risk of escalation to critical issues

**Action Required:** Plan to address these warnings within 1-2 weeks.

{% else %}
### ✅ **Healthy Cluster**

Excellent! No critical issues or warnings detected. Your cluster is well-configured and operating within recommended parameters.

**Next Steps:** Review informational recommendations for further optimization opportunities.
{% endif %}
{% endif %}

### Key Metrics

| Metric | Value | Status |
|--------|-------|--------|
| Total Nodes | {{ cluster_state.get_total_nodes() if cluster_state.get_total_nodes else 'N/A' }} | {% if cluster_state.get_total_nodes() and cluster_state.get_total_nodes() >= 3 %}✅ Good{% else %}⚠️ Review{% endif %} |
| Active Nodes | {{ cluster_state.get_active_nodes() if cluster_state.get_active_nodes else 'N/A' }} | {% if cluster_state.get_active_nodes() == cluster_state.get_total_nodes() %}✅ All Active{% else %}🔴 Some Down{% endif %} |
| Datacenters | {{ cluster_state.get_datacenters() | length if cluster_state.get_datacenters() else 'N/A' }} | {% if cluster_state.get_datacenters() and cluster_state.get_datacenters() | length > 1 %}✅ Multi-DC{% else %}⚠️ Single DC{% endif %} |
| Recommendations | {{ stats.total_recommendations }} | {{ stats.critical_count }} Critical, {{ stats.warning_count }} Warnings, {{ stats.info_count }} Info |

---

{% if for_agent %}
## Findings

| Severity | Section | Issue | Description | Current → Recommended | Affected | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
{% for rec in agent_findings %}| {{ rec.severity }} | {{ rec.section }} | {{ rec.title }} | {{ rec.description }}{% if rec.config_location %} ({{ rec.config_location }}){% endif %} | {% if rec.current or rec.recommended %}{{ rec.current }} → {{ rec.recommended }}{% else %}—{% endif %} | {{ rec.affected }} | {{ rec.recommendation }} |
{% endfor %}
{% else %}
## Summary of Findings

{% if recommendations_by_priority.immediate %}
### Immediate Issues

These critical issues require immediate attention to prevent service disruption or data loss.

| Issue | Section | Description | Action Required |
|-------|---------|-------------|----------------|
{% for rec in recommendations_by_priority.immediate %}| **{{ rec.title }}** | {{ rec.section.replace('_', ' ').title() }} | {{ rec.description }}{% if rec.context.get('config_location') %} ({{ rec.context.get('config_location') }}){% endif %} | {{ rec.recommendation if rec.recommendation else 'Review immediately' }} |
{% endfor %}
{% endif %}

{% if recommendations_by_priority.nearterm %}
### Near Term Changes

These warnings should be addressed within your next maintenance window.

| Issue | Section | Description | Priority |
|-------|---------|-------------|----------|
{% for rec in recommendations_by_priority.nearterm %}| **{{ rec.title }}** | {{ rec.section.replace('_', ' ').title() }} | {{ rec.description }}{% if rec.context.get('config_location') %} ({{ rec.context.get('config_location') }}){% endif %} | {{ rec.severity }} |
{% endfor %}
{% endif %}

{% if recommendations_by_priority.longterm %}
### Long Term Optimizations

These informational items represent optimization opportunities.

| Optimization | Section | Description | Benefit |
|--------------|---------|-------------|----------|
{% for rec in recommendations_by_priority.longterm %}| {{ rec.title }} | {{ rec.section.replace('_', ' ').title() }} | {{ rec.description }}{% if rec.context.get('config_location') %} ({{ rec.context.get('config_location') }}){% endif %} | {{ rec.impact if rec.impact else 'Performance improvement' }} |
{% endfor %}
{% endif %}
{% endif %}

---

## Cluster Overview

### Topology Summary

Your Cassandra cluster consists of {{ cluster_state.get_total_nodes() if cluster_state.get_total_nodes() else 'unknown number of' }} nodes distributed across {{ cluster_state.get_datacenters() | length if cluster_state.get_datacenters() else 'unknown' }} datacenter(s).

{% if cluster_state.nodes %}
{# Group nodes by datacenter and rack for counting #}
{% set dc_rack_counts = {} %}
{% set dc_seed_counts = {} %}
{% set dc_versions = {} %}
{# First extract all seed hostnames from seed provider #}
{% set all_seed_hostnames = [] %}
{% for node_id, temp_node in cluster_state.nodes.items() %}
  {% set seed_provider = temp_node.Details.get('comp_seed_provider', '') %}
  {% if seed_provider and 'seeds=' in seed_provider and not all_seed_hostnames %}
    {% set seeds_part = seed_provider.split('seeds=')[1].split('}')[0] %}
    {% for seed in seeds_part.split(',') %}
      {# Remove port number from seed hostname #}
      {% set seed_host = seed.strip().split(':')[0] %}
      {% set _ = all_seed_hostnames.append(seed_host) %}
    {% endfor %}
  {% endif %}
{% endfor %}
{% for node_id, node in cluster_state.nodes.items() %}
  {% set dc = node.DC if node.DC else 'Unknown' %}
  {% set rack = node.rack if node.rack else 'default' %}
  {% set node_hostname = node.Details.get('host_Hostname', '') %}
  {% set node_listen = node.Details.get('comp_listen_address', '') %}
  {% set node_broadcast = node.Details.get('comp_broadcast_address', '') %}
  {# Check if node is a seed. Seeds may be hostnames or IPs and identify the
     gossip address, so match against hostname + listen/broadcast addresses
     (not rpc_address). Also tolerate domain mismatches on hostnames.
     A namespace is needed so writes inside {% for %} are visible outside. #}
  {% set seed_ns = namespace(is_seed=false) %}
  {% set node_addrs = [] %}
  {% if node_hostname %}{% set _ = node_addrs.append(node_hostname) %}{% endif %}
  {% if node_listen %}{% set _ = node_addrs.append(node_listen) %}{% endif %}
  {% if node_broadcast %}{% set _ = node_addrs.append(node_broadcast) %}{% endif %}
  {% for addr in node_addrs if not seed_ns.is_seed %}
    {% if addr in all_seed_hostnames %}
      {% set seed_ns.is_seed = true %}
    {% elif '.' in addr and not addr.replace('.', '').isdigit() %}
      {% set node_base = addr.split('.')[0] %}
      {% for seed in all_seed_hostnames if not seed_ns.is_seed %}
        {% if '.' in seed and not seed.replace('.', '').isdigit() %}
          {% if node_base == seed.split('.')[0] %}
            {% set seed_ns.is_seed = true %}
          {% endif %}
        {% endif %}
      {% endfor %}
    {% endif %}
  {% endfor %}
  {% set is_seed = seed_ns.is_seed %}
  {% set version = node.Details.get('comp_releaseVersion', node.Details.get('release_version', 'Unknown')) %}
  
  {# Count nodes per DC/rack #}
  {% if dc not in dc_rack_counts %}
    {% set _ = dc_rack_counts.update({dc: {}}) %}
  {% endif %}
  {% if rack not in dc_rack_counts[dc] %}
    {% set _ = dc_rack_counts[dc].update({rack: 0}) %}
  {% endif %}
  {% set _ = dc_rack_counts[dc].update({rack: dc_rack_counts[dc][rack] + 1}) %}
  
  {# Count seeds per DC #}
  {% if dc not in dc_seed_counts %}
    {% set _ = dc_seed_counts.update({dc: 0}) %}
  {% endif %}
  {% if is_seed %}
    {% set _ = dc_seed_counts.update({dc: dc_seed_counts[dc] + 1}) %}
  {% endif %}
  
  {# Track versions per DC #}
  {% if dc not in dc_versions %}
    {% set _ = dc_versions.update({dc: []}) %}
  {% endif %}
  {% if version not in dc_versions[dc] %}
    {% set _ = dc_versions[dc].append(version) %}
  {% endif %}
{% endfor %}

| Datacenter | Rack Configuration | Total Nodes | Seed Nodes | Versions |
|------------|-------------------|-------------|------------|----------|
{% for dc in dc_rack_counts.keys() | sort %}{% set racks = dc_rack_counts[dc] %}{% set total_dc_nodes = racks.values() | sum %}{% set versions_list = dc_versions[dc] | sort %}| {{ dc }} | {% if racks | length > 1 %}{{ racks | length }} racks ({% for rack, count in racks.items() | sort %}{{ rack }}: {{ count }}{% if not loop.last %}, {% endif %}{% endfor %}){% else %}{% for rack, count in racks.items() %}{{ rack }}{% endfor %}{% endif %} | {{ total_dc_nodes }} | {{ dc_seed_counts.get(dc, 0) }} | {{ versions_list | join(', ') }} |
{% endfor %}

**Cluster Health**: {% if cluster_state.get_active_nodes() == cluster_state.get_total_nodes() %}✅ All nodes active{% else %}⚠️ {{ cluster_state.get_total_nodes() - cluster_state.get_active_nodes() }} node(s) down{% endif %}
{% endif %}

---
{% if not for_agent %}
_**Best Practice**: Each datacenter should have at least 2 seed nodes for optimal cluster discovery and gossip propagation. Ensure seed nodes are well-distributed across racks._

---
{% endif %}

### Keyspaces

{% if cluster_state.keyspaces %}
{% set app_keyspaces = [] %}
{% for ks_name, ks in cluster_state.keyspaces.items() %}
    {% if not ks_name.startswith('system') %}
        {% set _ = app_keyspaces.append((ks_name, ks)) %}
    {% endif %}
{% endfor %}

Your cluster contains **{{ app_keyspaces | length }} application keyspace(s)** storing business data.

| Keyspace | Tables | Type |
|----------|--------|------|
{% for ks_name, ks in cluster_state.keyspaces.items() %}| {{ ks_name }} | {{ ks.Tables | length if ks.Tables else 0 }} | {% if ks_name.startswith('system') %}System{% else %}Application{% endif %} |
{% endfor %}
{% endif %}

---

{% if not for_agent %}
{% for section in sections %}
## {{ section.icon }} {{ section.title }}

{{ section.brief }}

{% if section.data.error %}
⚠️ **Analysis Error:** {{ section.data.error }}

_Unable to complete {{ section.title }} analysis. This may indicate missing permissions or incomplete data collection._

{% elif section.data.recommendations %}

{% if section.name == 'infrastructure' %}
### Infrastructure Summary

| Component | Status | Issues Found | Priority |
|-----------|---------|--------------|----------|
{% set issue_counts = {} %}{% for rec in section.data.recommendations %}{% set component = rec.context.get('component', 'General') %}{% if component not in issue_counts %}{% set _ = issue_counts.update({component: []}) %}{% endif %}{% set _ = issue_counts[component].append(rec) %}{% endfor %}{% for component, recs in issue_counts.items() %}| {{ component }} | {% if recs | selectattr('severity', 'equalto', 'critical') | list %}🔴 Critical{% elif recs | selectattr('severity', 'equalto', 'warning') | list %}🟡 Warning{% else %}🔵 Info{% endif %} | {{ recs | length }} | {{ recs | selectattr('severity', 'equalto', 'critical') | list | length }} critical, {{ recs | selectattr('severity', 'equalto', 'warning') | list | length }} warnings |
{% endfor %}

### Detailed Findings

| Issue | Component | Nodes Affected | Current Value | Recommended Value | Impact |
|-------|-----------|----------------|---------------|-------------------|---------|
{% for rec in section.data.recommendations %}| {{ rec | get_attr('title', 'Unknown Issue') }} | {{ rec.context.get('component', 'General') }} | {{ rec.count if rec.count else 1 }} | {{ rec | get_attr('current_value', 'N/A') }} | {{ rec.context.get('recommended_value', rec | get_attr('recommendation', 'See recommendation')) }} | {{ rec | get_attr('severity') | severity_text }} |
{% endfor %}

{% elif section.name == 'operations' %}
### Operations Metrics Summary

| Metric | Current State | Threshold | Status |
|--------|---------------|-----------|--------|
{% for rec in section.data.recommendations %}| {{ rec | get_attr('title', 'Unknown Metric') }} | {{ rec | get_attr('current_value', 'N/A') }} | {{ rec.context.get('threshold', 'N/A') }} | {{ rec | get_attr('severity') | severity_icon }} {{ rec | get_attr('severity') | severity_text }} |
{% endfor %}

{% elif section.name == 'operations_logs' %}
### Log Analysis Summary

| Event Type | Nodes Affected | Total Occurrences | Rate (per hour) | Severity |
|------------|----------------|-------------------|-----------------|----------|
{% for rec in section.data.recommendations %}| {{ rec | get_attr('title', 'Unknown Event') }}{% if 'Batch' in rec.title and 'Detected via Histogram' in rec.title %} †{% endif %} | {{ rec.count if rec.count else 1 }} | {{ rec.context.get('total_count', 'N/A') }} | {{ rec.context.get('hourly_rate', 'N/A') }} | {{ rec | get_attr('severity') | severity_icon }} {{ rec | get_attr('severity') | severity_text }} |
{% endfor %}

{% set batch_warnings = [] %}
{% for rec in section.data.recommendations %}
  {% if 'Batch' in rec.title and 'Histogram' in rec.title %}
    {% set _ = batch_warnings.append(rec) %}
  {% endif %}
{% endfor %}
{% if batch_warnings %}
† **Important Note about Batch Activity Detection**: The AxonOps histogram API detects batch-related activity patterns, but individual batch warning log entries may not be retrievable through the logs search API. This is a known limitation. To verify batch warnings:
- Check your Cassandra system.log files directly for "Batch" warnings
- Monitor batch size metrics: `batch_size_warn_threshold_in_kb` and `batch_size_fail_threshold_in_kb` in cassandra.yaml
- Use nodetool to check batch performance metrics
{% endif %}

{% elif section.name == 'configuration' %}
### Configuration Analysis Summary

| Configuration Area | Status | Issues Found | Priority |
|-------------------|---------|--------------|----------|
{% set config_areas = {} %}{% for rec in section.data.recommendations %}{% set area = 'JVM Settings' if 'jvm' in rec.title.lower() or 'heap' in rec.title.lower() or 'gc' in rec.title.lower() else 'Cassandra Settings' if 'authenticat' in rec.title.lower() or 'disk' in rec.title.lower() or 'commitlog' in rec.title.lower() else 'Configuration Consistency' %}{% if area not in config_areas %}{% set _ = config_areas.update({area: []}) %}{% endif %}{% set _ = config_areas[area].append(rec) %}{% endfor %}{% for area, recs in config_areas.items() %}| {{ area }} | {% if recs | selectattr('severity', 'equalto', 'critical') | list %}🔴 Critical{% elif recs | selectattr('severity', 'equalto', 'warning') | list %}🟡 Warning{% else %}🔵 Info{% endif %} | {{ recs | length }} | {{ recs | selectattr('severity', 'equalto', 'critical') | list | length }} critical, {{ recs | selectattr('severity', 'equalto', 'warning') | list | length }} warnings |
{% endfor %}

### Detailed Configuration Issues

| Issue | Area | Current State | Config Location | Impact | Recommendation |
|-------|------|---------------|-----------------|---------|----------------|
{% for rec in section.data.recommendations %}| {{ rec | get_attr('title', 'Unknown Issue') }}{% if rec.title == 'Multiple Configuration Mismatches Detected' %} (See Appendix){% endif %} | {% if 'jvm' in rec.title.lower() or 'heap' in rec.title.lower() or 'gc' in rec.title.lower() %}JVM{% elif 'authenticat' in rec.title.lower() or 'authoriz' in rec.title.lower() %}Security{% elif 'mismatch' in rec.title.lower() %}Consistency{% else %}General{% endif %} | {{ rec | get_attr('current_value', rec.description[:50] + '...' if rec.description and rec.description|length > 50 else rec.description) }} | {{ rec.context.get('config_location', 'cassandra.yaml') }} | {{ rec | get_attr('severity') | severity_icon }} {{ rec | get_attr('impact', 'See description') }} | {{ rec | get_attr('recommendation', 'Review settings') }} |
{% endfor %}

{% elif section.name == 'extended_configuration' %}
_All extended configuration settings are found in **cassandra.yaml** unless otherwise noted._

### Extended Configuration Summary

| Setting Category | Issues | Severity | Action Required |
|-----------------|--------|----------|-----------------|
{% set ext_config_areas = {} %}{% for rec in section.data.recommendations %}{% set category = 'Thread Pools' if 'thread' in rec.title.lower() or 'flush' in rec.title.lower() else 'Network' if 'snitch' in rec.title.lower() else 'Memory' if 'memtable' in rec.title.lower() or 'cache' in rec.title.lower() else 'Compaction' if 'compact' in rec.title.lower() else 'Other' %}{% if category not in ext_config_areas %}{% set _ = ext_config_areas.update({category: []}) %}{% endif %}{% set _ = ext_config_areas[category].append(rec) %}{% endfor %}{% for category, recs in ext_config_areas.items() %}| {{ category }} | {{ recs | length }} | {% if recs | selectattr('severity', 'equalto', 'critical') | list %}🔴 Critical{% elif recs | selectattr('severity', 'equalto', 'warning') | list %}🟡 Warning{% else %}🔵 Info{% endif %} | {% set recommendation_text = recs[0].recommendation if recs and recs[0].recommendation else 'Review configuration' %}{{ recommendation_text.replace(' in cassandra.yaml', '').replace(' in JVM startup flags', '') }} |
{% endfor %}

### Extended Configuration Details

| Parameter | Node/Cluster | Current Value | Recommended | Impact |
|-----------|--------------|---------------|-------------|---------|
{% for rec in section.data.recommendations %}{% set node_id = rec.context.get('node_id') %}{% if node_id and cluster_state.nodes.get(node_id) %}{% set node = cluster_state.nodes.get(node_id) %}{% set node_display = node.Details.get('host_Hostname', 'unknown') + '/' + node.Details.get('listen_address', node.Details.get('comp_listen_address', node_id[:8] + '...')) %}{% else %}{% set node_display = 'Cluster-wide' %}{% endif %}| {{ rec | get_attr('title', 'Unknown Parameter') }} | {{ node_display }} | {{ rec | get_attr('current_value', 'N/A') }} | {{ rec.context.get('recommended_value', rec | get_attr('recommendation', 'See details')) }} | {{ rec | get_attr('severity') | severity_text }} |
{% endfor %}

{% elif section.name == 'datamodel' %}
### Data Model Analysis Summary

| Category | Issues Found | Critical | Warnings | Info |
|----------|--------------|----------|----------|------|
{% set datamodel_categories = {} %}{% for rec in section.data.recommendations %}{% set category = 'Table Design' if 'partition' in rec.title.lower() or 'clustering' in rec.title.lower() or 'primary key' in rec.title.lower() else 'Tombstones' if 'tombstone' in rec.title.lower() else 'Compaction' if 'compact' in rec.title.lower() or 'sstable' in rec.title.lower() else 'Secondary Indexes' if 'index' in rec.title.lower() else 'Materialized Views' if 'view' in rec.title.lower() else 'Replication' if 'replication' in rec.title.lower() or 'consistency' in rec.title.lower() else 'Collections' if 'collection' in rec.title.lower() or 'list' in rec.title.lower() or 'map' in rec.title.lower() or 'set' in rec.title.lower() else 'Performance' %}{% if category not in datamodel_categories %}{% set _ = datamodel_categories.update({category: []}) %}{% endif %}{% set _ = datamodel_categories[category].append(rec) %}{% endfor %}{% for category, recs in datamodel_categories.items() %}| {{ category }} | {{ recs | length }} | {{ recs | selectattr('severity', 'equalto', 'critical') | list | length }} | {{ recs | selectattr('severity', 'equalto', 'warning') | list | length }} | {{ recs | selectattr('severity', 'equalto', 'info') | list | length }} |
{% endfor %}

### Table-Specific Issues

| Keyspace.Table | Issue Type | Current State | Impact | Action Required |
|----------------|------------|---------------|---------|-----------------|
{% for rec in section.data.recommendations %}{% if rec.context.get('keyspace') or rec.context.get('table') %}| {{ rec.context.get('keyspace', '') }}{% if rec.context.get('keyspace') and rec.context.get('table') %}.{% endif %}{{ rec.context.get('table', '') }} | {{ rec | get_attr('title', 'Unknown Issue') }} | {{ rec | get_attr('current_value', 'See details') }} | {{ rec | get_attr('severity') | severity_icon }} {{ rec | get_attr('impact', 'Performance impact') }} | {{ rec | get_attr('recommendation', 'Review design') }} |
{% endif %}{% endfor %}

### General Data Model Issues

| Issue | Description | Severity | Recommendation |
|-------|-------------|----------|----------------|
{% for rec in section.data.recommendations %}{% if not rec.context.get('keyspace') and not rec.context.get('table') %}| {{ rec | get_attr('title', 'Unknown Issue') }} | {{ rec | get_attr('description', 'No description') }}{% if rec.title == 'Unused Tables Detected' and rec.context.get('unused_tables') %} (See Appendix for table list){% elif rec.title == 'Collection Types Usage' and rec.context.get('collection_tables') %} (See Appendix for schemas){% endif %} | {{ rec | get_attr('severity') | severity_icon }} {{ rec | get_attr('severity') | severity_text }} | {{ rec | get_attr('recommendation', 'Review data model') }} |
{% endif %}{% endfor %}

{% elif section.name == 'security' %}
_Security settings are configured in **cassandra.yaml** unless otherwise noted._

### Security Configuration Overview

| Security Area | Status | Configuration | Risk Level |
|---------------|--------|---------------|------------|
{% set auth_enabled = section.data.summary.get('auth_enabled', False) %}{% set authz_enabled = section.data.summary.get('authz_enabled', False) %}{% set authenticator = section.data.summary.get('authenticator', 'Unknown') %}{% set authorizer = section.data.summary.get('authorizer', 'Unknown') %}| Authentication | {{ '✅ Enabled' if auth_enabled else '❌ Disabled' }} | {{ authenticator }} | {{ '✅ Low' if auth_enabled else '🔴 High' }} |
| Authorization | {{ '✅ Enabled' if authz_enabled else '❌ Disabled' }} | {{ authorizer }} | {{ '✅ Low' if authz_enabled else '🔴 High' }} |
{# Encryption options disabled since AxonOps does not return this information #}
{#
| Encryption in Transit | ❓ Unknown | Not checked | 🟡 Medium |
| Encryption at Rest | ❓ Unknown | Not checked | 🟡 Medium |
#}

### Security Issues Detail

| Issue | Current State | Risk | Impact | Action Required |
|-------|---------------|------|---------|-----------------|
{% for rec in section.data.recommendations %}| {{ rec | get_attr('title', 'Unknown Issue') }} | {{ rec | get_attr('current_value', 'See description') }} | {{ rec | get_attr('severity') | severity_icon }} {{ rec | get_attr('severity') | severity_text }} | {{ rec | get_attr('impact', 'Security risk') }} | {{ rec | get_attr('recommendation', 'Enable security feature') }} |
{% endfor %}

{% else %}
{% for rec in section.data.recommendations %}
### {{ rec | get_attr('title', 'Unknown Issue') }}

**Current State:** {{ rec | get_attr('current_value', 'See details below') }}  
**Severity:** {{ rec | get_attr('severity') | severity_icon }} {{ rec | get_attr('severity') | severity_text }}
{% if rec.context.get('config_location') %}
**Configuration Location:** {{ rec.context.get('config_location') }}
{% endif %}

{{ rec | get_attr('description', 'No description available') }}

{% if rec | get_attr('impact') %}
**Impact if not addressed:** {{ rec | get_attr('impact') }}
{% endif %}

**Recommendation:** {{ rec | get_attr('recommendation', 'No recommendation provided') }}

{% if section.name == 'configuration' and 'heap' in (rec | get_attr('title', '')).lower() %}
---

_**Noted for reference**: JVM heap size directly affects how much data Cassandra can cache in memory. Too small leads to frequent GC, too large causes long GC pauses._

---
{% elif section.name == 'datamodel' and 'tombstone' in (rec | get_attr('title', '')).lower() %}
---

_**Consideration**: Tombstones are deletion markers that remain in the system until compaction. High tombstone counts significantly impact read performance._

---
{% elif section.name == 'security' and (rec | get_attr('severity') | severity_text) == 'CRITICAL' %}
---

**⚠️ Security Warning**: This issue represents a significant security risk and should be addressed immediately to prevent unauthorized access or data breaches.

---
{% endif %}

{% endfor %}
{% endif %}

{% else %}
✅ **No issues detected** in {{ section.title.lower() }} configuration.

{% if section.name == 'security' %}
---

_**Noted for reference**: Even with no issues detected, regularly review security settings and ensure authentication/authorization are properly configured for production environments._

---
{% endif %}
{% endif %}

{% endfor %}
{% endif %}

---

{% if not for_agent %}
## Next Steps

1. **Address Critical Issues** - Resolve any {{ stats.critical_count }} critical items immediately
2. **Plan Warning Fixes** - Schedule {{ stats.warning_count }} warning items for next maintenance
3. **Review Optimizations** - Consider {{ stats.info_count }} informational recommendations
4. **Monitor Progress** - Re-run analysis after changes to verify improvements
5. **Schedule Regular Checks** - Plan quarterly health assessments

---

## Appendix: Understanding Cassandra Concepts

### Key Terms

**Node**: A single server running Cassandra
**Datacenter**: Logical grouping of nodes (often geographic)
**Keyspace**: Top-level data container (like a database)
**Replication Factor (RF)**: Number of data copies across nodes
**Consistency Level**: How many nodes must respond to queries
**Compaction**: Process of merging and cleaning data files
**Tombstone**: Marker indicating deleted data
**Partition**: Unit of data distribution across nodes
{% endif %}

## Appendix: Cluster Node Details

### Complete Node List

This section provides a detailed view of all nodes in the cluster.

{% if cluster_state.nodes %}
{# Prepare node details with all information #}
{# First extract all seed hostnames #}
{% set all_seed_hostnames = [] %}
{% for node_id, temp_node in cluster_state.nodes.items() %}
  {% set seed_provider = temp_node.Details.get('comp_seed_provider', '') %}
  {% if seed_provider and 'seeds=' in seed_provider and not all_seed_hostnames %}
    {% set seeds_part = seed_provider.split('seeds=')[1].split('}')[0] %}
    {% for seed in seeds_part.split(',') %}
      {# Remove port number from seed hostname #}
      {% set seed_host = seed.strip().split(':')[0] %}
      {% set _ = all_seed_hostnames.append(seed_host) %}
    {% endfor %}
  {% endif %}
{% endfor %}
{% set node_list = [] %}
{% for node_id, node in cluster_state.nodes.items() %}
  {% set node_hostname = node.Details.get('host_Hostname', '') %}
  {% set node_listen = node.Details.get('comp_listen_address', '') %}
  {% set node_broadcast = node.Details.get('comp_broadcast_address', '') %}
  {# Seeds map to gossip addresses, which may be hostnames or IPs. Match
     against hostname + listen/broadcast addresses (not rpc_address) and
     tolerate domain mismatches on hostnames. Namespace required so writes
     inside {% for %} propagate to the outer scope. #}
  {% set seed_ns = namespace(is_seed=false) %}
  {% set node_addrs = [] %}
  {% if node_hostname %}{% set _ = node_addrs.append(node_hostname) %}{% endif %}
  {% if node_listen %}{% set _ = node_addrs.append(node_listen) %}{% endif %}
  {% if node_broadcast %}{% set _ = node_addrs.append(node_broadcast) %}{% endif %}
  {% for addr in node_addrs if not seed_ns.is_seed %}
    {% if addr in all_seed_hostnames %}
      {% set seed_ns.is_seed = true %}
    {% elif '.' in addr and not addr.replace('.', '').isdigit() %}
      {% set node_base = addr.split('.')[0] %}
      {% for seed in all_seed_hostnames if not seed_ns.is_seed %}
        {% if '.' in seed and not seed.replace('.', '').isdigit() %}
          {% if node_base == seed.split('.')[0] %}
            {% set seed_ns.is_seed = true %}
          {% endif %}
        {% endif %}
      {% endfor %}
    {% endif %}
  {% endfor %}
  {% set is_seed = seed_ns.is_seed %}
  {% set node_info = {
    'dc': node.DC if node.DC else 'Unknown',
    'rack': node.rack if node.rack else 'default',
    'hostname': node.Details.get('host_Hostname', 'unknown'),
    'ip': node.Details.get('listen_address', node.Details.get('comp_listen_address', node_id[:8] + '...')),
    'version': node.Details.get('comp_releaseVersion', node.Details.get('release_version', 'Unknown')),
    'is_seed': is_seed,
    'is_active': node.is_active,
    'sort_key': node.DC + '||' + (node.rack if node.rack else 'default') + '||' + node.Details.get('listen_address', node.Details.get('comp_listen_address', node.Details.get('host_Hostname', node_id)))
  } %}
  {% set _ = node_list.append(node_info) %}
{% endfor %}

| Datacenter | Rack | Node | Version | Seed | Status |
|------------|------|------|---------|------|--------|
{% for node_info in node_list | sort(attribute='sort_key') %}| {{ node_info.dc }} | {{ node_info.rack }} | {{ node_info.hostname }}/{{ node_info.ip }} | {{ node_info.version }} | {{ '✅ Yes' if node_info.is_seed else '❌ No' }} | {{ '✅ Active' if node_info.is_active else '🔴 Down' }} |
{% endfor %}
{% endif %}

{% if node_details %}
## Appendix: Node-Specific Issue Details

This section provides detailed information about which nodes are affected by each issue identified in the report.

{% for issue_key, details in node_details.items() %}
### {{ details.title }}
**Section:** {{ details.section.replace('_', ' ').title() }}  
**Affected Nodes:** {{ details.affected_nodes | length }}
{% set config_location = details.affected_nodes[0].details.get('config_location', 'cassandra.yaml') if details.affected_nodes else 'cassandra.yaml' %}
{% if '(' in details.title and ')' in details.title %}
  {% set start = details.title.rfind('(') + 1 %}
  {% set end = details.title.rfind(')') %}
  {% set param_name = details.title[start:end] %}
{% else %}
  {% set param_name = details.title %}
{% endif %}
**Configuration:** `{{ config_location }}` - `{{ param_name }}`

{% set has_config_location = details.affected_nodes and details.affected_nodes[0].details.get('config_location') %}
{% if details.agent_compact %}
{% set node_labels = [] %}
{% for node_info in details.affected_nodes %}{% set node = cluster_state.nodes.get(node_info.node_id) %}{% set _ = node_labels.append((node.Details.get('host_Hostname', 'unknown') if node else 'unknown') ~ '/' ~ (node.Details.get('listen_address', node.Details.get('comp_listen_address', node_info.node_id[:8] ~ '...')) if node else node_info.node_id[:8] ~ '...')) %}{% endfor %}
**Affected ({{ details.affected_nodes | length }}):** {{ node_labels | join(', ') }}
{% set sample = details.affected_nodes[0].details %}
{% if has_config_location %}
**Current → Recommended:** {{ sample.get('current_value', 'N/A') }} → {{ sample.get('recommended_value', 'See recommendation') }}
{% else %}
**Details:** {% for key, value in sample.items() if key not in ['node_id', 'component'] and value %}{{ key.replace('comp_', '') }}: {{ value }}{% if not loop.last %}, {% endif %}{% endfor %}
{% endif %}
{% elif has_config_location %}
| Node | Current Value | Recommended |
|------|---------------|-------------|
{% for node_info in details.affected_nodes %}{% set node = cluster_state.nodes.get(node_info.node_id) %}| {{ node.Details.get('host_Hostname', 'unknown') if node else 'unknown' }}/{{ node.Details.get('listen_address', node.Details.get('comp_listen_address', node_info.node_id[:8] + '...')) if node else node_info.node_id[:8] + '...' }} | {% if 'memtable_allocation_type' in node_info.details %}{{ node_info.details.get('memtable_allocation_type', 'N/A') }}{% elif 'memtable_flush_writers' in node_info.details %}{{ node_info.details.get('memtable_flush_writers', 'N/A') }}{% elif 'concurrent_reads' in node_info.details and 'Low Concurrent Reads' in details.title %}{{ node_info.details.get('concurrent_reads', 'N/A') }}{% elif 'concurrent_writes' in node_info.details and 'Low Concurrent Writes' in details.title %}{{ node_info.details.get('concurrent_writes', 'N/A') }}{% elif 'native_transport_max_threads' in node_info.details %}{{ node_info.details.get('native_transport_max_threads', 'N/A') }}{% elif 'sysctl_value' in node_info.details %}{{ node_info.details.get('sysctl_value', 'N/A') }}{% else %}{{ node_info.details.get('current_value', 'N/A') }}{% endif %} | {{ node_info.details.get('recommended_value', 'See recommendation') }} |
{% endfor %}
{% else %}
| Node | Details |
|------|---------|
{% for node_info in details.affected_nodes %}{% set node = cluster_state.nodes.get(node_info.node_id) %}| {{ node.Details.get('host_Hostname', 'unknown') if node else 'unknown' }}/{{ node.Details.get('listen_address', node.Details.get('comp_listen_address', node_info.node_id[:8] + '...')) if node else node_info.node_id[:8] + '...' }} | {% for key, value in node_info.details.items() if key not in ['node_id', 'component'] and value %}{{ key.replace('comp_', '') }}: {{ value }}{% if not loop.last %}, {% endif %}{% endfor %} |
{% endfor %}
{% endif %}

{% endfor %}
{% endif %}

## Appendix: Data Model Details

{% for section_name, section_data in analysis_results.items() %}
  {% if section_name == 'datamodel' and 'recommendations' in section_data %}
    {% for rec in section_data.recommendations %}
      {% if rec.get('title') == 'Speculative Retry Enabled (Multiple Tables)' and rec.get('context', {}).get('tables_affected') %}
        {% set tables_affected = rec.get('context', {}).get('tables_affected', []) %}
        {% set retry_setting = rec.get('context', {}).get('speculative_retry', 'unknown') %}
        {% if tables_affected %}
### Tables with Speculative Retry Enabled

The following {{ tables_affected | length }} tables have speculative_retry set to '{{ retry_setting }}':

| Table | Current Setting | Recommended |
|-------|-----------------|-------------|
{% for table in tables_affected | sort %}| {{ table }} | speculative_retry={{ retry_setting }} | NEVER |
{% endfor %}

**Impact:** Speculative retry can cause unnecessary load and is often counterproductive in modern deployments.

**To fix all tables in a keyspace:**
```cql
-- Example for a specific keyspace
{% set sample_keyspace = tables_affected[0].split('.')[0] if tables_affected else 'keyspace_name' %}
{% for table in tables_affected[:3] %}{% if table.startswith(sample_keyspace + '.') %}
ALTER TABLE {{ table }} WITH speculative_retry = 'NEVER';{% endif %}{% endfor %}
-- ... repeat for all affected tables
```
        {% endif %}
      {% elif rec.get('title') == 'Unused Tables Detected' and rec.get('context', {}).get('unused_tables') %}
        {% set unused_tables = rec.get('context', {}).get('unused_tables', []) %}
        {% if unused_tables %}
### Unused Tables

These tables have shown no read or write activity during the analysis period:

| Table | Action |
|-------|--------|
{% for table in unused_tables %}| {{ table }} | Verify if still needed before dropping |
{% endfor %}
        {% endif %}
      {% elif rec.get('title') == 'Collection Types Usage' and rec.get('context', {}).get('collection_table_details') %}
        {% set collection_details = rec.get('context', {}).get('collection_table_details', []) %}
        {% if collection_details %}
### Tables with Collections

The following tables use collection types (list, set, map):

{% for table_detail in collection_details %}
#### {{ table_detail.table }}

```sql
{{ table_detail.schema }}
```

{% endfor %}
        {% endif %}
      {% endif %}
    {% endfor %}
  {% endif %}
{% endfor %}

## Appendix: Configuration Details

{% for section_name, section_data in analysis_results.items() %}
  {% if section_name == 'configuration' and 'recommendations' in section_data %}
    {% for rec in section_data.recommendations %}
      {% if rec.get('title') == 'Multiple Configuration Mismatches Detected' and rec.get('context', {}).get('mismatches') %}
        {% set mismatches = rec.get('context', {}).get('mismatches', []) %}
        {% if mismatches %}
### Configuration Mismatches

The following configuration parameters have different values across nodes:

{% for mismatch in mismatches %}
#### {{ mismatch.setting }}

| Value | Node Count | Example Nodes |
|-------|------------|---------------|
{% for value, nodes in mismatch.get('values', {}).items() %}| {{ value }} | {{ nodes | length }} | {{ nodes[:3] | join(', ') }}{% if nodes | length > 3 %}...{% endif %} |
{% endfor %}

{% endfor %}
        {% endif %}
      {% endif %}
    {% endfor %}
  {% endif %}
{% endfor %}

---
{% if not for_agent %}
### Common Issues Explained

**Large Partitions**: When too much data accumulates under one partition key, causing:
- Slow queries as entire partition must be read
- Memory pressure on nodes
- Uneven data distribution

**Tombstone Accumulation**: Deleted data markers that:
- Must be scanned during reads
- Slow down queries significantly
- Eventually removed by compaction

**GC Pauses**: Java garbage collection freezing the application to free memory:
- Short pauses (< 200ms) are normal
- Long pauses (> 1s) impact performance
- Caused by heap pressure or poor tuning

---
{% endif %}
{% if for_agent %}
{{ coverage_appendix }}

---
{% endif %}
_Report generated by Cassandra AxonOps Analyzer v1.0_
_Analysis completed in {{ cluster_state.collection_duration_seconds | round(2) if cluster_state.collection_duration_seconds else 'N/A' }} seconds_
""")