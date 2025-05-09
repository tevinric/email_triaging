"""
Unit tests for email_utils module that handles email content extraction and formatting.
"""

import pytest
from email_processor.email_utils import get_email_body, create_email_details

# Sample email data for testing
@pytest.fixture
def html_email_msg():
    return {
        'body': {
            'contentType': 'html',
            'content': '<p>This is a <strong>HTML</strong> email.</p>'
        }
    }

@pytest.fixture
def text_email_msg():
    return {
        'body': {
            'contentType': 'text',
            'content': 'This is a plain text email.'
        }
    }

@pytest.fixture
def empty_email_msg():
    return {
        'body': {
            'contentType': 'text',
            'content': ''
        }
    }

@pytest.fixture
def no_body_email_msg():
    return {}

@pytest.fixture
def full_email_msg():
    return {
        'id': 'email_id_1',
        'internetMessageId': '<message123@example.com>',
        'subject': 'Test Subject',
        'from': {
            'emailAddress': {
                'address': 'sender@example.com'
            }
        },
        'toRecipients': [
            {
                'emailAddress': {
                    'address': 'recipient1@example.com'
                }
            },
            {
                'emailAddress': {
                    'address': 'recipient2@example.com'
                }
            }
        ],
        'ccRecipients': [
            {
                'emailAddress': {
                    'address': 'cc1@example.com'
                }
            },
            {
                'emailAddress': {
                    'address': 'cc2@example.com'
                }
            }
        ],
        'receivedDateTime': '2025-05-01T10:00:00Z',
        'body': {
            'contentType': 'html',
            'content': '<p>This is the email body.</p>'
        }
    }

# Test get_email_body function
def test_get_email_body_html(html_email_msg):
    """Test extracting body from HTML email."""
    body = get_email_body(html_email_msg)
    
    # Verify HTML is preserved
    assert body['html'] == '<p>This is a <strong>HTML</strong> email.</p>'
    
    # Verify plain text was converted
    assert 'This is a' in body['text']
    assert 'HTML' in body['text']

def test_get_email_body_text(text_email_msg):
    """Test extracting body from plain text email."""
    body = get_email_body(text_email_msg)
    
    # Verify text content
    assert body['text'] == 'This is a plain text email.'
    
    # Verify HTML is empty
    assert body['html'] == ''

def test_get_email_body_empty(empty_email_msg):
    """Test handling empty email body."""
    body = get_email_body(empty_email_msg)
    
    # Verify both fields are empty
    assert body['text'] == ''
    assert body['html'] == ''

def test_get_email_body_no_body(no_body_email_msg):
    """Test handling missing body field."""
    body = get_email_body(no_body_email_msg)
    
    # Verify both fields are empty
    assert body['text'] == ''
    assert body['html'] == ''

# Test create_email_details function
def test_create_email_details_full(full_email_msg):
    """Test creating email details from a complete message."""
    details = create_email_details(full_email_msg)
    
    # Verify all fields are extracted correctly
    assert details['email_id'] == 'email_id_1'
    assert details['internet_message_id'] == '<message123@example.com>'
    assert details['subject'] == 'Test Subject'
    assert details['from'] == 'sender@example.com'
    assert details['to'] == 'recipient1@example.com, recipient2@example.com'
    assert details['cc'] == 'cc1@example.com, cc2@example.com'
    assert details['date_received'] == '2025-05-01T10:00:00Z'
    assert details['body_html'] == '<p>This is the email body.</p>'
    assert 'This is the email body.' in details['body_text']

def test_create_email_details_minimal():
    """Test creating email details from a minimal message."""
    minimal_msg = {
        'id': 'email_id_2',
        'subject': 'Minimal Subject',
        'from': {
            'emailAddress': {
                'address': 'sender@example.com'
            }
        },
        'toRecipients': [],
        'ccRecipients': [],
        'receivedDateTime': '2025-05-01T11:00:00Z',
        'body': {
            'contentType': 'text',
            'content': 'Minimal body'
        }
    }
    
    details = create_email_details(minimal_msg)
    
    # Verify fields are extracted correctly
    assert details['email_id'] == 'email_id_2'
    assert details['to'] == ''
    assert details['cc'] == ''
    assert details['body_text'] == 'Minimal body'
