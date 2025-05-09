"""
Unit tests for the email_client module which handles interactions with Microsoft Graph API.
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import aiohttp
from email_processor.email_client import (
    get_access_token,
    fetch_unread_emails,
    mark_email_as_read,
    forward_email
)

# Mock responses for Microsoft Graph API
@pytest.fixture
def mock_token_response():
    return {"access_token": "mock_token", "expires_in": 3600}

@pytest.fixture
def mock_fetch_response():
    return {
        "value": [
            {
                "id": "email_id_1",
                "subject": "Test Email 1",
                "from": {"emailAddress": {"address": "sender1@example.com"}},
                "toRecipients": [{"emailAddress": {"address": "recipient1@example.com"}}],
                "ccRecipients": [],
                "receivedDateTime": "2025-05-01T10:00:00Z",
                "body": {"contentType": "text", "content": "This is test email 1"}
            },
            {
                "id": "email_id_2",
                "subject": "Test Email 2",
                "from": {"emailAddress": {"address": "sender2@example.com"}},
                "toRecipients": [{"emailAddress": {"address": "recipient2@example.com"}}],
                "ccRecipients": [{"emailAddress": {"address": "cc@example.com"}}],
                "receivedDateTime": "2025-05-01T11:00:00Z",
                "body": {"contentType": "html", "content": "<p>This is test email 2</p>"}
            }
        ]
    }

# Test get_access_token function
@pytest.mark.asyncio
async def test_get_access_token(mock_token_response):
    """Test successful retrieval of access token."""
    with patch('msal.ConfidentialClientApplication') as mock_app:
        mock_instance = MagicMock()
        mock_instance.acquire_token_for_client.return_value = mock_token_response
        mock_app.return_value = mock_instance
        
        token = await get_access_token()
        
        # Verify token value
        assert token == "mock_token"
        
        # Verify MSAL was called correctly
        mock_app.assert_called_once()
        mock_instance.acquire_token_for_client.assert_called_once()

@pytest.mark.asyncio
async def test_get_access_token_failure():
    """Test handling of token acquisition failure."""
    with patch('msal.ConfidentialClientApplication') as mock_app:
        mock_instance = MagicMock()
        mock_instance.acquire_token_for_client.return_value = {"error": "unauthorized", "error_description": "Invalid client"}
        mock_app.return_value = mock_instance
        
        token = await get_access_token()
        
        # Verify no token was returned
        assert token is None

# Test fetch_unread_emails function
@pytest.mark.asyncio
async def test_fetch_unread_emails(mock_fetch_response):
    """Test successful fetching of unread emails."""
    with patch('aiohttp.ClientSession.get') as mock_get:
        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json.return_value = mock_fetch_response
        mock_get.return_value.__aenter__.return_value = mock_response
        
        emails = await fetch_unread_emails("mock_token", "test@example.com")
        
        # Verify we got the expected number of emails
        assert len(emails) == 2
        
        # Verify email details were correctly extracted
        email_data, message_id = emails[0]
        assert message_id == "email_id_1"
        assert email_data["subject"] == "Test Email 1"
        assert email_data["from"] == "sender1@example.com"

@pytest.mark.asyncio
async def test_fetch_unread_emails_no_emails():
    """Test behavior when no unread emails are found."""
    with patch('aiohttp.ClientSession.get') as mock_get:
        # Mock the HTTP response with no emails
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json.return_value = {"value": []}
        mock_get.return_value.__aenter__.return_value = mock_response
        
        emails = await fetch_unread_emails("mock_token", "test@example.com")
        
        # Verify we got an empty list
        assert emails == []

@pytest.mark.asyncio
async def test_fetch_unread_emails_error():
    """Test handling of HTTP errors during email fetching."""
    with patch('aiohttp.ClientSession.get') as mock_get:
        # Mock a 401 unauthorized response
        mock_response = MagicMock()
        mock_response.status = 401
        mock_response.text.return_value = "Unauthorized"
        mock_get.return_value.__aenter__.return_value = mock_response
        
        emails = await fetch_unread_emails("mock_token", "test@example.com")
        
        # Verify we got an empty list on error
        assert emails == []

# Test mark_email_as_read function
@pytest.mark.asyncio
async def test_mark_email_as_read_success():
    """Test successfully marking an email as read."""
    with patch('aiohttp.ClientSession.patch') as mock_patch:
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_patch.return_value.__aenter__.return_value = mock_response
        
        result = await mark_email_as_read("mock_token", "test@example.com", "email_id_1")
        
        # Verify success result
        assert result is True
        
        # Verify request was made correctly
        mock_patch.assert_called_once()

@pytest.mark.asyncio
async def test_mark_email_as_read_failure():
    """Test handling failure when marking an email as read."""
    with patch('aiohttp.ClientSession.patch') as mock_patch:
        # Mock failure response
        mock_response = MagicMock()
        mock_response.status = 404
        mock_response.text.return_value = "Not Found"
        mock_patch.return_value.__aenter__.return_value = mock_response
        
        result = await mark_email_as_read("mock_token", "test@example.com", "email_id_1")
        
        # Verify failure result
        assert result is False

# Test forward_email function
@pytest.mark.asyncio
async def test_forward_email_success():
    """Test successfully forwarding an email."""
    # We need to mock multiple API calls
    with patch('aiohttp.ClientSession.get') as mock_get, \
            patch('aiohttp.ClientSession.post') as mock_post, \
            patch('aiohttp.ClientSession.patch') as mock_patch:
        
        # Mock responses for each API call
        
        # 1. Get email details
        get_response = MagicMock()
        get_response.status = 200
        get_response.json.return_value = {
            "id": "email_id_1",
            "hasAttachments": False,
            "subject": "Test Email"
        }
        mock_get.return_value.__aenter__.return_value = get_response
        
        # 2. Create forward draft
        create_response = MagicMock()
        create_response.status = 201
        create_response.json.return_value = {
            "id": "forward_id_1",
            "body": {
                "contentType": "text",
                "content": "Original email content"
            }
        }
        
        # 3. Update forward
        update_response = MagicMock()
        update_response.status = 200
        
        # 4. Send forward
        send_response = MagicMock()
        send_response.status = 202
        
        # Configure the post mock to return different responses
        mock_post.return_value.__aenter__.side_effect = [create_response, send_response]
        
        # Configure the patch mock
        mock_patch.return_value.__aenter__.return_value = update_response
        
        # Mock email data
        email_data = {
            "subject": "Test Email",
            "body_text": "Email content",
            "cc": "cc1@example.com, cc2@example.com"
        }
        
        result = await forward_email(
            "mock_token",
            "test@example.com",
            "email_id_1",
            "sender@example.com",
            "forward@example.com",
            email_data,
            "Forwarded message"
        )
        
        # Verify success result
        assert result is True
        
        # Verify API calls were made
        assert mock_get.call_count == 1
        assert mock_post.call_count == 2
        assert mock_patch.call_count == 1

@pytest.mark.asyncio
async def test_forward_email_attachments_scan():
    """Test handling of emails with attachments being scanned."""
    with patch('aiohttp.ClientSession.get') as mock_get:
        # Mock response for email details with attachments
        email_details_response = MagicMock()
        email_details_response.status = 200
        email_details_response.json.return_value = {
            "id": "email_id_1",
            "hasAttachments": True
        }
        
        # Mock response for attachments with scan in progress
        attachments_response = MagicMock()
        attachments_response.status = 200
        attachments_response.json.return_value = {
            "value": [
                {
                    "id": "attachment_id_1",
                    "name": "Safe Attachments Scan In Progress"
                }
            ]
        }
        
        # Configure get mock to return different responses
        mock_get.return_value.__aenter__.side_effect = [email_details_response, attachments_response]
        
        # Mock email data
        email_data = {
            "subject": "Test Email",
            "body_text": "Email content"
        }
        
        result = await forward_email(
            "mock_token",
            "test@example.com",
            "email_id_1",
            "sender@example.com",
            "forward@example.com",
            email_data
        )
        
        # Verify we did not forward the email
        assert result is False
        assert mock_get.call_count == 2
