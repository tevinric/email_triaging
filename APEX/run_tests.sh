#!/bin/bash
# Run tests and generate coverage reports for APEX Email Triaging System

# Ensure we're in the root directory (where the script is located)
# No need to cd .. since the script should be run from the root

# Make sure we have the necessary packages
echo "Checking for required packages..."
pip show pytest pytest-cov pytest-asyncio coverage > /dev/null || pip install pytest pytest-cov pytest-asyncio coverage

# Clean previous coverage data
echo "Cleaning previous coverage data..."
rm -rf .coverage htmlcov/

# Run tests and collect coverage
echo "Running tests with coverage..."
python -m pytest tests -v --cov=. --cov-report=term

# Explicitly generate HTML report
echo "Generating HTML coverage report..."
python -m coverage html

# Check if the HTML report was generated
if [ -d "htmlcov" ]; then
    echo "Coverage report generated successfully. Check htmlcov/index.html for the report."
    # List files in the htmlcov directory to confirm
    ls -la htmlcov/
else
    echo "ERROR: HTML coverage report not generated."
    echo "Trying alternative approach..."
    
    # Alternative approach using direct coverage command
    python -m coverage run -m pytest tests
    python -m coverage html
    
    if [ -d "htmlcov" ]; then
        echo "Alternative approach worked. Check htmlcov/index.html for the report."
        ls -la htmlcov/
    else
        echo "ERROR: Failed to generate HTML coverage report using alternative approach."
        echo "Please check that you have write permissions in this directory."
    fi
fi
