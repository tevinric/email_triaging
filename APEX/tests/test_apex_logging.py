"""
Unit tests for apex_logging module that handles database logging functionality.
"""

import pytest
import datetime
from unittest.mock import patch, MagicMock, AsyncMock
import pyodbc
from apex_llm.apex_logging import (
    create_log,
    add_to_log,
    log_apex_success,
    log_apex_fail,
    insert_log_to_db,
    check_email_processed
)

# Test create_log function
def test_create_log():
    """Test creating a new log entry."""
    email_data = {
        'email_id': 'test_email_id',
        'internet_message_id': '<test123@example.com>',
        'to': 'recipient@example.com',
        'from': 'sender@example.com',
        'date_received': '2025-05-01T10:00:00Z',
        'cc': 'cc@example.com',
        'subject': 'Test Subject',
        'body_text': 'Test body'
    }
    
    log = create_log(email_data)
    
    # Verify log has the expected fields
    assert 'id' in log
    assert log['eml_id'] == 'test_email_id'
    assert log['internet_message_id'] == '<test123@example.com>'
    assert log['eml_to'] == 'recipient@example.com'
    assert log['eml_frm'] == 'sender@example.com'
    assert log['eml_cc'] == 'cc@example.com'
    assert log['eml_sub'] == 'Test Subject'
    assert log['eml_bdy'] == 'Test body'
    assert 'dttm_rec' in log
    assert 'dttm_proc' in log

def test_create_log_missing_fields():
    """Test creating a log with missing email data fields."""
    email_data = {
        'email_id': 'test_email_id',
        # Missing several fields
        'subject': 'Test Subject'
    }
    
    log = create_log(email_data)
    
    # Verify log handles missing fields gracefully
    assert 'id' in log
    assert log['eml_id'] == 'test_email_id'
    assert log['eml_sub'] == 'Test Subject'
    assert log['eml_to'] == ''  # Empty string for missing fields
    assert log['eml_frm'] == ''
    assert log['eml_cc'] == ''
    assert log['eml_bdy'] == ''

# Test add_to_log function
def test_add_to_log():
    """Test adding values to a log."""
    log = {}
    
    # Add various data types
    add_to_log('string_key', 'string_value', log)
    add_to_log('int_key', 123, log)
    add_to_log('float_key', 45.67, log)
    add_to_log('none_key', None, log)
    add_to_log('date_key', datetime.datetime(2025, 5, 1, 10, 0, 0), log)
    
    # Verify values were added correctly
    assert log['string_key'] == 'string_value'
    assert log['int_key'] == 123
    assert log['float_key'] == 45.67
    assert log['none_key'] == ''  # None converted to empty string
    assert isinstance(log['date_key'], datetime.datetime)

# Test log_apex_success function
def test_log_apex_success():
    """Test logging successful APEX classification."""
    log = {}
    apex_response = {
        'message': {
            'classification': 'amendments',
            'rsn_classification': 'This is an amendment request',
            'action_required': 'yes',
            'sentiment': 'neutral',
            'apex_cost_usd': 0.00025,
            'top_categories': ['amendments', 'document request', 'other']
        }
    }
    
    log_apex_success(apex_response, log)
    
    # Verify log fields were updated correctly
    assert log['apex_class'] == 'amendments'
    assert log['apex_class_rsn'] == 'This is an amendment request'
    assert log['apex_action_req'] == 'yes'
    assert log['apex_sentiment'] == 'neutral'
    assert log['apex_cost_usd'] == 0.00025
    assert log['apex_top_categories'] == 'amendments, document request, other'

def test_log_apex_success_with_string_categories():
    """Test logging with top_categories as a string."""
    log = {}
    apex_response = {
        'message': {
            'classification': 'amendments',
            'rsn_classification': 'This is an amendment request',
            'action_required': 'yes',
            'sentiment': 'neutral',
            'apex_cost_usd': 0.00025,
            'top_categories': 'amendments, document request, other'  # Already a string
        }
    }
    
    log_apex_success(apex_response, log)
    
    # Verify log field was updated correctly
    assert log['apex_top_categories'] == 'amendments, document request, other'

# Test log_apex_fail function
def test_log_apex_fail():
    """Test logging failed APEX classification."""
    log = {}
    error_message = "API Error: Rate limit exceeded"
    
    log_apex_fail(log, error_message)
    
    # Verify log fields were updated with error information
    assert log['apex_class'] == 'error'
    assert 'API Error: Rate limit exceeded' in log['apex_class_rsn']
    assert log['apex_action_req'] == 'error'
    assert log['apex_sentiment'] == 'error'
    assert log['apex_cost_usd'] == 0.00
    assert log['apex_top_categories'] == ''
    assert log['apex_intervention'] == 'false'

# Test insert_log_to_db function
@pytest.mark.asyncio
async def test_insert_log_to_db_success(mock_db_connection):
    """Test successfully inserting a log to the database."""
    mock_conn, mock_cursor = mock_db_connection
    
    # Simple log for testing
    test_log = {
        'id': 'test-uuid',
        'eml_id': 'email-123',
        'eml_sub': 'Test Subject'
    }
    
    # Execute function
    success = await insert_log_to_db(test_log)
    
    # Verify database was called correctly
    assert success is True
    mock_conn.cursor.assert_called_once()
    mock_cursor.execute.assert_called_once()
    mock_conn.commit.assert_called_once()

@pytest.mark.asyncio
async def test_insert_log_to_db_error(mock_db_connection):
    """Test handling database errors when inserting a log."""
    mock_conn, mock_cursor = mock_db_connection
    
    # Configure cursor to raise an exception
    mock_cursor.execute.side_effect = pyodbc.Error("Database error")
    
    # Simple log for testing
    test_log = {
        'id': 'test-uuid',
        'eml_id': 'email-123',
        'eml_sub': 'Test Subject'
    }
    
    # Execute function with retry count of 1 to speed up test
    success = await insert_log_to_db(test_log, max_retries=1)
    
    # Verify result indicates failure
    assert success is False
    mock_cursor.execute.assert_called_once()
    # Commit should not be called after an error
    mock_conn.commit.assert_not_called()

# Test check_email_processed function
@pytest.mark.asyncio
async def test_check_email_processed_found(mock_db_connection):
    """Test checking for an email that has been processed."""
    mock_conn, mock_cursor = mock_db_connection
    
    # Configure cursor to return 1 row (email found)
    mock_cursor.fetchone.return_value = [1]
    
    # Execute function
    result = await check_email_processed('<test123@example.com>')
    
    # Verify result indicates email was found
    assert result is True
    mock_cursor.execute.assert_called_once()

@pytest.mark.asyncio
async def test_check_email_processed_not_found(mock_db_connection):
    """Test checking for an email that has not been processed."""
    mock_conn, mock_cursor = mock_db_connection
    
    # Configure cursor to return 0 rows (email not found)
    mock_cursor.fetchone.return_value = [0]
    
    # Execute function
    result = await check_email_processed('<test123@example.com>')
    
    # Verify result indicates email was not found
    assert result is False
    mock_cursor.execute.assert_called_once()

@pytest.mark.asyncio
async def test_check_email_processed_db_error(mock_db_connection):
    """Test handling database errors when checking for processed emails."""
    mock_conn, mock_cursor = mock_db_connection
    
    # Configure cursor to raise an exception
    mock_cursor.execute.side_effect = pyodbc.Error("Database error")
    
    # Execute function with retry count of 1 to speed up test
    result = await check_email_processed('<test123@example.com>', max_retries=1)
    
    # Verify result indicates email was not found (safe default)
    assert result is False
    mock_cursor.execute.assert_called_once()
