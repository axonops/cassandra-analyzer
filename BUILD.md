# Building Cassandra AxonOps Analyzer

This guide provides detailed instructions for building and packaging Cassandra AxonOps Analyzer in various formats.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Running from Source](#running-from-source)
- [Building Python Packages](#building-python-packages)
- [Building Standalone Executables](#building-standalone-executables)
- [Building Linux Packages](#building-linux-packages)
- [Building Docker Images](#building-docker-images)
- [Automated Builds with GitHub Actions](#automated-builds-with-github-actions)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### For Running from Source
- Python 3.11 or higher
- pip (Python package manager)
- git

### For Building Executables
- All prerequisites for running from source
- PyInstaller (installed automatically with dev dependencies)
- Operating system matching your target platform

### For Building Linux Packages
- All prerequisites for building executables
- Ruby and RubyGems
- fpm (Effing Package Management)

## Running from Source

This is the recommended approach for development and for users who want the latest changes.

### 1. Clone the Repository

```bash
git clone https://github.com/axonops/cassandra-analyzer.git
cd cassandra-analyzer
```

### 2. Set Up Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On Linux/macOS:
source venv/bin/activate
# On Windows:
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
# For basic usage
pip install -r requirements.txt
pip install -e .

# For development (includes build tools)
make install-dev
# Or manually:
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -e .
```

### 4. Run the Analyzer

```bash
# Using the installed command
cassandra-analyzer --config config.yaml

# Or using Python module
python -m cassandra_analyzer --config config.yaml

# Or using make
make run-example
```

## Building Python Packages

Build standard Python distribution packages (wheel and source distribution).

### Using Make

```bash
make build
```

### Manual Build

```bash
# Install build tools
pip install build wheel

# Build packages
python -m build

# Check the packages
pip install twine
twine check dist/*
```

The packages will be in the `dist/` directory:
- `cassandra_axonops_analyzer-X.X.X-py3-none-any.whl` - Wheel package
- `cassandra_axonops_analyzer-X.X.X.tar.gz` - Source distribution

## Building Standalone Executables

Create single-file executables that include Python and all dependencies.

### Using Make (Recommended)

```bash
# Build single-file executable
make build-exe

# Build one-folder executable (for debugging)
make build-exe-onedir
```

### Manual Build with PyInstaller

```bash
# Install PyInstaller
pip install pyinstaller

# Build using spec file
pyinstaller cassandra-analyzer.spec --clean

# Or build from scratch
pyinstaller --onefile \
  --name cassandra-analyzer \
  --add-data "cassandra_analyzer/reports/templates:cassandra_analyzer/reports/templates" \
  cassandra_analyzer_main.py
```

### Output

The executable will be in the `dist/` directory:
- **Linux/macOS**: `dist/cassandra-analyzer`
- **Windows**: `dist/cassandra-analyzer.exe`

### Platform Notes

- **Size**: Executables are approximately 53MB (includes Python interpreter and all dependencies)
- **Platform-specific**: You can only build for the platform you're currently on
- **Performance**: First startup may be slower as the executable extracts itself
- **Limitations**: PDF generation is NOT available in executables due to system dependencies (WeasyPrint requires Cairo, Pango, etc.)

## Building Linux Packages

Create DEB and RPM packages for Linux distributions.

### Prerequisites

```bash
# Install Ruby (if not already installed)
sudo apt-get install ruby ruby-dev  # Debian/Ubuntu
sudo yum install ruby ruby-devel     # RHEL/CentOS

# Install fpm
sudo gem install --no-document fpm
```

### Build DEB Package

```bash
# First build the executable
make build-exe

# Create package structure
mkdir -p pkg/usr/bin
cp dist/cassandra-analyzer pkg/usr/bin/
mkdir -p pkg/usr/share/doc/cassandra-analyzer
cp README.md LICENSE pkg/usr/share/doc/cassandra-analyzer/

# Build DEB package
fpm -s dir -t deb \
  -n cassandra-analyzer \
  -v 0.1.0 \
  --description "Comprehensive Cassandra cluster analysis tool powered by AxonOps" \
  --url "https://github.com/axonops/cassandra-analyzer" \
  --license "Apache-2.0" \
  --vendor "AxonOps" \
  --maintainer "support@axonops.com" \
  --architecture amd64 \
  -C pkg \
  usr
```

### Build RPM Package

```bash
# Build RPM package
fpm -s dir -t rpm \
  -n cassandra-analyzer \
  -v 0.1.0 \
  --description "Comprehensive Cassandra cluster analysis tool powered by AxonOps" \
  --url "https://github.com/axonops/cassandra-analyzer" \
  --license "Apache-2.0" \
  --vendor "AxonOps" \
  --architecture x86_64 \
  -C pkg \
  usr
```

## Building Docker Images

### Using Make

```bash
make docker-build
```

### Manual Build

```bash
# Build image
docker build -t cassandra-analyzer:latest .

# Run container
docker run -v $(pwd)/config.yaml:/config.yaml:ro \
  -v $(pwd)/reports:/home/analyzer/reports \
  cassandra-analyzer:latest --config /config.yaml
```

## Automated Builds with GitHub Actions

The project uses GitHub Actions to automatically build releases when tags are pushed.

### Release Process

1. **Tag the release**:
   ```bash
   # For official release (builds as release)
   git tag v0.1.0
   git push origin v0.1.0
   
   # For pre-release (builds as pre-release)
   git tag v0.1.0-beta1
   git push origin v0.1.0-beta1
   ```

2. **GitHub Actions will automatically**:
   - Build Python packages
   - Build executables for all platforms:
     - Linux (amd64)
     - macOS (Intel amd64 and Apple Silicon arm64)
     - Windows (amd64)
   - Build DEB and RPM packages
   - Create a GitHub release with all artifacts
   - Upload to PyPI (when configured)
   - Build and push Docker images

### Release Artifacts

Each release includes:
- Python wheel and source distribution
- Standalone executables for all platforms
- DEB package for Debian/Ubuntu
- RPM package for RHEL/CentOS/Fedora
- SHA256 checksums for all files

## Troubleshooting

### PyInstaller Issues

**Import errors when running executable**:
- Ensure all dependencies are properly installed
- Check that hidden imports are included in the spec file
- Try building in one-folder mode for easier debugging

**Large executable size**:
- This is normal - the executable includes Python and all dependencies
- Use UPX compression if needed (add `--upx-dir=/path/to/upx` to PyInstaller)

**Antivirus warnings**:
- Some antivirus software may flag PyInstaller executables
- Sign your executables with a code signing certificate
- Submit false positive reports to antivirus vendors

### Platform-Specific Issues

**Linux: GLIBC version errors**:
- Build on the oldest supported Linux distribution
- The GitHub Actions builds use Ubuntu 20.04 for compatibility

**macOS: "cannot be opened" error**:
- Remove quarantine attribute: `xattr -d com.apple.quarantine cassandra-analyzer`
- Sign the executable with an Apple Developer certificate

**Windows: Missing DLL errors**:
- Ensure Visual C++ Redistributables are installed
- Build on Windows 10 for maximum compatibility

### Build Environment Issues

**Module not found errors**:
- Ensure you're in the activated virtual environment
- Reinstall dependencies: `pip install -r requirements-dev.txt`

**Permission errors**:
- Don't use `sudo` with pip in virtual environments
- Ensure you have write permissions in the project directory

## Advanced Topics

### Cross-Platform Building

While PyInstaller doesn't support cross-compilation, you can:
- Use GitHub Actions for automated multi-platform builds
- Set up virtual machines for each target platform
- Use Docker containers for Linux builds

### Customizing the Build

Edit `cassandra-analyzer.spec` to:
- Add additional data files
- Include/exclude specific modules
- Customize executable properties
- Add version information and icons

### Size Optimization

To reduce executable size:
1. Use `--onefile` mode only when necessary
2. Exclude unused modules in the spec file
3. Use UPX compression (may trigger antivirus)
4. Consider using Nuitka as an alternative to PyInstaller

## Getting Help

- Check the [GitHub Issues](https://github.com/axonops/cassandra-analyzer/issues) for known problems
- Join the [Discussions](https://github.com/axonops/cassandra-analyzer/discussions) for questions
- Review the [Contributing Guide](CONTRIBUTING.md) for development setup