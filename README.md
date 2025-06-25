<p align="center">
  <img src="logo.svg" alt="Cassandra AxonOps Analyzer Logo" width="200">
</p>

<h1 align="center">Cassandra® AxonOps Analyser</h1>

<p align="center">
  <strong>Comprehensive Cassandra Cluster Analysis Tool Powered by AxonOps™</strong>
</p>

> ⚠️ **DEVELOPMENT STATUS**: This project is currently under active development and is not yet ready for production use. Features may change, and stability is not guaranteed. Please wait for the official release announcement before using in production environments.

<p align="center">
  <a href="https://github.com/axonops/cassandra-analyzer/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License">
  </a>
  <a href="https://github.com/axonops/cassandra-analyzer/issues">
    <img src="https://img.shields.io/github/issues/axonops/cassandra-analyzer" alt="Issues">
  </a>
  <a href="https://github.com/axonops/cassandra-analyzer/discussions">
    <img src="https://img.shields.io/github/discussions/axonops/cassandra-analyzer" alt="Discussions">
  </a>
  <a href="#installation">
    <img src="https://img.shields.io/badge/PyPI-Coming%20Soon-orange" alt="PyPI">
  </a>
  <a href="https://github.com/axonops/cassandra-analyzer/actions">
    <img src="https://github.com/axonops/cassandra-analyzer/workflows/CI/badge.svg" alt="CI Status">
  </a>
</p>

---

## 🚀 Overview

Cassandra AxonOps Analyzer is a powerful diagnostic tool that performs comprehensive analysis of Apache Cassandra clusters using the [AxonOps](https://axonops.com) monitoring platform. Unlike traditional diagnostic tools that require manual collection of logs and metrics, Cassandra AxonOps Analyzer connects directly to your AxonOps instance to provide real-time insights and recommendations.

### ✨ Key Features

- **🔍 Real-time Analysis** - Analyze live clusters through AxonOps API without manual data collection
- **📊 Comprehensive Health Checks** - Infrastructure, configuration, operations, data model, and security analysis
- **🎯 Actionable Recommendations** - Get specific, prioritized recommendations for improvements
- **📈 Performance Insights** - Identify bottlenecks, resource constraints, and optimization opportunities
- **🏗️ Best Practices Validation** - Ensure your cluster follows Cassandra best practices
- **📄 Professional Reports** - Generate detailed Markdown and PDF reports for documentation

### 🛠️ Analysis Categories

| Category | Description |
|----------|-------------|
| **Infrastructure** | CPU, memory, disk usage, network metrics, and hardware recommendations |
| **Configuration** | JVM settings, Cassandra configuration, and tuning opportunities |
| **Operations** | Compactions, repairs, garbage collection, and operational metrics |
| **Data Model** | Table design, partition sizes, tombstones, and schema optimizations |
| **Security** | Authentication, authorization, encryption, and security best practices |

## 📋 Requirements

- Python 3.11 or higher
- Access to [AxonOps](https://axonops.com) monitoring platform
- AxonOps API token with appropriate permissions

## 🔧 Installation

### From PyPI (Coming Soon)

The package will be available on PyPI soon. In the meantime, please install from source or use the standalone executables.

```bash
# Coming soon:
# pip install cassandra-axonops-analyzer
```

### From Source (Currently Recommended)

```bash
git clone https://github.com/axonops/cassandra-analyzer.git
cd cassandra-analyzer
pip install -r requirements.txt
pip install -e .
```

### Using Standalone Executable (Coming Soon)

Pre-built executables will be available from the [releases page](https://github.com/axonops/cassandra-analyzer/releases) soon:

- **Linux**: `cassandra-analyzer-linux-amd64` (coming soon)
- **macOS**: `cassandra-analyzer-macos-amd64` (coming soon)
- **Windows**: `cassandra-analyzer-windows-amd64.exe` (coming soon)

## 🚀 Quick Start

1. **Create a configuration file** (`config.yaml`):

```yaml
cluster:
  org: "your-organization"
  cluster: "your-cluster-name"
  cluster_type: "cassandra"  # or "dse"

axonops:
  api_url: "https://dash.axonops.cloud/"
  token: "your-api-token"  # Or use AXONOPS_API_TOKEN env var

analysis:
  hours: 24  # Hours of history to analyze
```

2. **Run the analyzer**:

```bash
cassandra-analyzer --config config.yaml
```

3. **View the generated report** in the `reports` directory.

## 📖 Documentation

### Command Line Options

```bash
cassandra-analyzer [OPTIONS]

Options:
  --config PATH         Path to configuration file (required)
  --output-dir PATH     Output directory for reports (default: ./reports)
  --verbose            Enable verbose logging
  --pdf                Generate PDF report in addition to Markdown
  --help               Show this message and exit
```

### Environment Variables

- `AXONOPS_API_TOKEN` - AxonOps API token (alternative to config file)
- `CA_LOG_LEVEL` - Log level (DEBUG, INFO, WARNING, ERROR)

### Configuration Reference

See [example_config.yaml](example_config.yaml) for a complete configuration example with all available options.

## 🔬 Advanced Usage

### Custom Thresholds

Customize analysis thresholds in your configuration:

```yaml
analysis:
  thresholds:
    cpu_usage_warn: 80.0
    memory_usage_warn: 85.0
    heap_usage_warn: 75.0
    gc_pause_warn_ms: 200
    pending_compactions_warn: 100
```

### PDF Generation

To generate PDF reports, install additional dependencies:

```bash
pip install weasyprint
```

Then run with the `--pdf` flag:

```bash
cassandra-analyzer --config config.yaml --pdf
```

### Programmatic Usage

```python
from cassandra_analyzer import CassandraAnalyzer
from cassandra_analyzer.config import Config

config = Config.from_file("config.yaml")
analyzer = CassandraAnalyzer(config)
report = analyzer.analyze()
```

## 🏗️ Architecture

```
cassandra-analyzer/
├── analyzers/         # Analysis modules
├── client/           # AxonOps API client
├── collectors/       # Data collection
├── models/          # Data models
├── reports/         # Report generation
└── utils/           # Utilities
```

## 🧪 Development

### Quick Start

```bash
# Clone the repository
git clone https://github.com/axonops/cassandra-analyzer.git
cd cassandra-analyzer

# Install development dependencies
make install-dev

# Run tests
make test

# Run linting
make lint

# Format code
make format

# Run all CI checks locally
make ci
```

### Available Make Commands

```bash
make help         # Show all available commands
make test         # Run unit tests
make test-coverage # Run tests with coverage report
make lint         # Run code linters
make format       # Auto-format code
make type-check   # Run type checking
make security-check # Run security scan
make build        # Build distribution packages
make docker-build # Build Docker image
make run-example  # Run with example configuration
```

### Testing

The project uses pytest for testing and follows Test-Driven Development (TDD) principles:

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_infrastructure_analyzer.py

# Run with coverage
pytest --cov=cassandra_analyzer --cov-report=html

# Run tests in watch mode
pytest-watch

# Test multiple Python versions
tox
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests first (TDD)
4. Implement your feature
5. Ensure all tests pass (`make test`)
6. Check code quality (`make lint`)
7. Commit your changes (`git commit -m 'Add amazing feature'`)
8. Push to the branch (`git push origin feature/amazing-feature`)
9. Open a Pull Request

## 📝 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## 🤝 Community & Support

### Get Involved

- 💡 **Share Ideas**: Visit our [GitHub Discussions](https://github.com/axonops/cassandra-analyzer/discussions) to propose new features
- 🐛 **Report Issues**: Found a bug? [Open an issue](https://github.com/axonops/cassandra-analyzer/issues)
- 🤝 **Contribute**: We welcome pull requests! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines
- ⭐ **Star Us**: If you find Cassandra AxonOps Analyzer useful, please star our repository!

### Stay Connected

- 🌐 **Website**: [axonops.com](https://axonops.com)
- 📧 **Contact**: Visit our website for support options

## 🙏 Acknowledgements

Cassandra AxonOps Analyzer builds upon the foundation laid by several open-source projects, particularly Apache Cassandra. We extend our sincere gratitude to the Apache Cassandra community for their outstanding work and contributions to the field of distributed databases.

Apache Cassandra is a free and open-source, distributed, wide-column store, NoSQL database management system designed to handle large amounts of data across many commodity servers, providing high availability with no single point of failure.

### Apache Cassandra Resources

- **Official Website**: [cassandra.apache.org](https://cassandra.apache.org)
- **Source Code**: Available on [GitHub](https://github.com/apache/cassandra) or the Apache Git repository at [gitbox.apache.org/repos/asf/cassandra.git](https://gitbox.apache.org/repos/asf/cassandra.git)
- **Documentation**: Comprehensive guides and references available at the [Apache Cassandra website](https://cassandra.apache.org/doc/latest/)

Cassandra AxonOps Analyzer incorporates and extends functionality from various Cassandra tools and utilities, enhancing them to provide comprehensive cluster analysis capabilities for Cassandra operators and DBAs.

We encourage users to explore and contribute to the main Apache Cassandra project, as well as to provide feedback and suggestions for Cassandra AxonOps Analyzer through our GitHub discussions and issues pages.

## ⚖️ Legal Notices

This project may contain trademarks or logos for projects, products, or services. Any use of third-party trademarks or logos are subject to those third-party's policies.

**Important**: This project is not affiliated with, endorsed by, or sponsored by the Apache Software Foundation or the Apache Cassandra project. It is an independent tool developed by [AxonOps](https://axonops.com) to analyze Apache Cassandra clusters.

- **AxonOps** is a registered trademark of AxonOps Limited.
- **Apache**, **Apache Cassandra**, **Cassandra**, **Apache Spark**, **Spark**, **Apache TinkerPop**, **TinkerPop**, **Apache Kafka** and **Kafka** are either registered trademarks or trademarks of the Apache Software Foundation or its subsidiaries in Canada, the United States and/or other countries.

---

<p align="center">
  Made with ❤️ by the AxonOps Team
</p>
