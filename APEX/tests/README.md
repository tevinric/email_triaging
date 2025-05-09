# APEX Unit Testing Guide

This directory contains unit tests for the APEX Email Triaging System. The tests are designed to verify the functionality of the system, especially the AI classification capabilities.

## Test Structure

The tests are organized into the following files:

- `test_apex.py`: Tests for the AI classification functionality
- `test_email_client.py`: Tests for email retrieval and forwarding
- `test_email_utils.py`: Tests for email content extraction
- `test_apex_logging.py`: Tests for logging and database interactions

Mock data for testing is provided in the `mock_data` directory.

## Running the Tests

There are several ways to run the tests:

### Using the run_tests.sh script

The simplest way to run all tests is to use the provided script:

```
./run_tests.sh
```

This script will:
1. Create a virtual environment if it doesn't exist
2. Install required test dependencies
3. Run all tests with coverage reporting
4. Generate an HTML coverage report

### Using pytest directly

If you prefer to run tests manually:

```
# Run all tests
pytest

# Run a specific test file
pytest tests/test_apex.py

# Run a specific test function
pytest tests/test_apex.py::test_apex_categorise_amendments

# Run with verbose output
pytest -v

# Generate coverage report
pytest --cov=. --cov-report=html
```

## Test Coverage

The tests aim to cover:

1. **Classification Accuracy**: Verifying that emails are correctly categorized based on their content
2. **Action Verification**: Testing the determination of whether an email requires action
3. **Category Prioritization**: Testing the prioritization of categories when multiple apply
4. **Error Handling**: Ensuring the system gracefully handles API failures
5. **Email Processing**: Testing email content extraction and forwarding
6. **Logging**: Verifying that actions are correctly logged to the database

## SonarQube Integration

These tests are designed to be compatible with SonarQube for code quality analysis. The test results and coverage reports can be imported into SonarQube.

To generate the necessary coverage report for SonarQube:

```
pytest --cov=. --cov-report=xml:coverage.xml
```

This will create a `coverage.xml` file that can be used by SonarQube.

## Adding New Tests

When adding new tests:

1. Follow the existing naming conventions: test files should be named `test_*.py`
2. Use pytest fixtures where appropriate to avoid code duplication
3. Add mock data in the `mock_data` directory if needed
4. Make sure to test both success and failure cases
5. For testing Azure OpenAI API calls, use the provided mock fixtures

## Test Data

The `mock_data/email_samples.py` file contains sample emails for testing each category of classification. These samples represent realistic email content that should trigger specific classifications.
