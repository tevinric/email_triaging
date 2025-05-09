#!/bin/bash
# Run tests and generate coverage reports for APEX Email Triaging System


# Step back the to the root directory
cd ..

# Run tests
echo "Running tests..."
cd tests
python -m pytest -v

# Generate HTML coverage report
echo "Generating coverage report..."
coverage html

echo "Tests complete. Check htmlcov/index.html for coverage report."
