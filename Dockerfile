# Multi-stage build for Cassandra Analyzer
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Copy the application
COPY cassandra_analyzer/ ./cassandra_analyzer/
COPY setup.py .
COPY README.md .
COPY LICENSE .

# Install the application
RUN pip install --user --no-cache-dir .

# Final stage
FROM python:3.11-slim

# Install runtime dependencies for PDF generation (optional)
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 analyzer

# Copy from builder
COPY --from=builder /root/.local /home/analyzer/.local

# Make sure scripts are in PATH
ENV PATH=/home/analyzer/.local/bin:$PATH

# Set working directory
WORKDIR /home/analyzer

# Switch to non-root user
USER analyzer

# Create reports directory
RUN mkdir -p /home/analyzer/reports

# Set the entrypoint
ENTRYPOINT ["cassandra-analyzer"]

# Default command (show help)
CMD ["--help"]