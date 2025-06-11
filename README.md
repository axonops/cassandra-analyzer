# Cassandra AxonOps Analyzer

A Python-based Cassandra cluster analysis tool that performs analysis using AxonOps API as the data source instead of diagnostic tarballs.

## Overview

This tool connects to AxonOps API to collect cluster metrics, configuration, and events, then performs comprehensive analysis to generate recommendations for:
- Infrastructure optimization
- Configuration improvements
- Performance tuning
- Data model best practices
- Operational health

## Features

- **API-based data collection** - No need for diagnostic tarballs
- **Real-time analysis** - Analyze live clusters through AxonOps
- **Comprehensive checks** - Covers infrastructure, configuration, operations, and data model
- **Markdown reports** - Generates detailed analysis reports
- **Modular architecture** - Easy to extend with new analysis sections

## Requirements

- Python 3.8+
- Access to AxonOps API
- API authentication token

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Basic usage with configuration file
python -m cassandra_analyzer --config config.yaml

# With custom output directory
python -m cassandra_analyzer --config config.yaml --output-dir /path/to/reports

# With verbose logging
python -m cassandra_analyzer --config config.yaml --verbose

# Generate PDF report in addition to markdown
python -m cassandra_analyzer --config config.yaml --pdf
```

### PDF Generation

To generate PDF reports, install the additional dependencies:

```bash
pip install weasyprint markdown beautifulsoup4
```

**Note**: WeasyPrint requires system dependencies. On Ubuntu/Debian:
```bash
sudo apt-get install python3-cffi python3-brotli libpango-1.0-0 libpangoft2-1.0-0
```

On macOS:
```bash
brew install pango
```

## Configuration

A configuration file is **required** to run the analyzer. Create a `config.yaml` file:

```yaml
# Cluster identification (required)
cluster:
  org: "your-organization-name"
  cluster: "your-cluster-name"
  cluster_type: "cassandra"  # or "dse" for DataStax Enterprise

# AxonOps API configuration (required)
axonops:
  api_url: "http://localhost:9090"
  token: "your-api-token-here"  # Can also be set via AXONOPS_API_TOKEN env var

# Analysis configuration (optional - defaults shown)
analysis:
  # Number of hours to analyze (from current time backwards)
  hours: 24
  
  # Metrics query resolution (seconds)
  metrics_resolution_seconds: 60
  
  # Analysis thresholds (optional)
  thresholds:
    cpu_usage_warn: 80.0
    memory_usage_warn: 85.0
    disk_usage_warn: 80.0
    heap_usage_warn: 75.0
    gc_pause_warn_ms: 200
    gc_pause_critical_ms: 1000
    dropped_messages_warn: 1000
    dropped_messages_critical: 10000
    pending_compactions_warn: 100
    pending_compactions_critical: 1000
```

See `example_config.yaml` for a complete configuration example with all available options.

## Architecture

The analyzer is organized into modules:

- **client/** - AxonOps API client
- **collectors/** - Data collection modules
- **analyzers/** - Analysis sections (infrastructure, configuration, operations, datamodel)
- **models/** - Data models for cluster state
- **reports/** - Report generation
- **utils/** - Utilities and helpers

## Development

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=cassandra_analyzer

# Format code
black cassandra_analyzer

# Lint
flake8 cassandra_analyzer
```

## License

Apache License 2.0