#!/bin/bash
# Run tests and generate coverage reports for APEX Email Triaging System

# Set up virtual environment if needed
if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install required packages
echo "Installing required packages..."
pip install pytest pytest-asyncio pytest-cov coverage

# Run tests
echo "Running tests..."
python -m pytest tests/ -v

# Generate HTML coverage report
echo "Generating coverage report..."
coverage html

echo "Tests complete. Check htmlcov/index.html for coverage report."
