"""
Shared fixtures for APEX unit tests.
This file contains fixtures used across multiple test modules.
"""

import pytest
import os
from unittest.mock import patch, MagicMock

# Mock environment variables to avoid dependency on .env file
@pytest.fixture(autouse=True)
def mock_env_variables():
    """Mock environment variables needed by the application."""
    with patch.dict(os.environ, {
        'AZURE_OPENAI_KEY': 'test_openai_key',
        'AZURE_OPENAI_ENDPOINT': 'https://test-endpoint.openai.azure.com/',
        'SQL_SERVER': 'test_server',
        'SQL_DATABASE': 'test_database',
        'SQL_USERNAME': 'test_username',
        'SQL_PASSWORD': 'test_password',
        'CLIENT_ID': 'test_client_id',
        'TENANT_ID': 'test_tenant_id',
        'CLIENT_SECRET': 'test_client_secret',
        'EMAIL_ACCOUNT': 'test@example.com',
        'POLICY_SERVICES': 'policy@example.com',
        'TRACKING_MAILS': 'tracking@example.com',
        'CLAIMS_MAILS': 'claims@example.com',
        'ONLINESUPPORT_MAILS': 'support@example.com',
        'INSURANCEADMIN_MAILS': 'admin@example.com',
        'DIGITALCOMMS_MAILS': 'digital@example.com',
        'CONNEX_TEST': 'connex@example.com'
    }):
        yield

# Mock database connection
@pytest.fixture
def mock_db_connection():
    """Mock SQL database connection."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    
    with patch('pyodbc.connect', return_value=mock_conn):
        yield mock_conn, mock_cursor

# Mock Azure OpenAI client
@pytest.fixture
def mock_openai_client():
    """Mock Azure OpenAI client."""
    mock_client = MagicMock()
    
    with patch('openai.AzureOpenAI', return_value=mock_client):
        yield mock_client

# Mock Microsoft Graph API token
@pytest.fixture
def mock_graph_token():
    """Mock Microsoft Graph API access token."""
    return "mock_access_token"

# Mock email data
@pytest.fixture
def mock_email_data():
    """Mock email data for testing."""
    return {
        'email_id': 'test_email_id',
        'internet_message_id': '<test123@example.com>',
        'to': 'recipient@example.com',
        'from': 'sender@example.com',
        'date_received': '2025-05-01T10:00:00Z',
        'cc': 'cc1@example.com, cc2@example.com',
        'subject': 'Test Email Subject',
        'body_html': '<p>This is a test email body.</p>',
        'body_text': 'This is a test email body.'
    }
