#!/bin/bash
# Test runner script for Cassandra Analyzer

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Running Cassandra Analyzer Tests${NC}"
echo "=================================="

# Check if virtual environment is activated
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo -e "${YELLOW}Warning: No virtual environment detected${NC}"
    echo "Consider running: source venv/bin/activate"
    echo
fi

# Default to running all tests
TEST_PATH="${1:-tests}"

# Run tests with coverage
echo -e "${GREEN}Running tests with coverage...${NC}"
pytest "$TEST_PATH" \
    -v \
    --cov=cassandra_analyzer \
    --cov-report=term-missing \
    --cov-report=html \
    --cov-fail-under=70

# Check if tests passed
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    
    # Show coverage summary
    echo
    echo -e "${GREEN}Coverage Summary:${NC}"
    coverage report --skip-empty --skip-covered
    
    echo
    echo -e "${GREEN}HTML coverage report generated at: htmlcov/index.html${NC}"
else
    echo -e "${RED}✗ Tests failed${NC}"
    exit 1
fi

# Run linting if requested
if [[ "$2" == "--lint" ]]; then
    echo
    echo -e "${GREEN}Running linters...${NC}"
    make lint
fi