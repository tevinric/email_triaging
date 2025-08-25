import aiohttp
import asyncio
import datetime
import time
from msal import ConfidentialClientApplication
from config import CLIENT_ID, TENANT_ID, CLIENT_SECRET, AUTHORITY, SCOPE, POLICY_SERVICES, TRACKING_MAILS, ONLINESUPPORT_MAILS, DIGITALCOMMS_MAILS, CC_EXCLUSION_LIST
from email_processor.email_utils import create_email_details

async def get_access_token():
    """
    Obtain an access token from Microsoft Graph API using MSAL.
    
    Returns:
        str: Access token if successful, None otherwise
    """
    try:
        app = ConfidentialClientApplication(
            CLIENT_ID,
            authority=AUTHORITY,
            client_credential=CLIENT_SECRET,
        )
        result = await asyncio.to_thread(app.acquire_token_for_client, scopes=SCOPE)
        if 'access_token' in result:
            return result['access_token']
        else:
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client - Function: get_access_token - Failed to obtain access token.")
            print(f"Error: {result.get('error', 'Unknown error')}")
            print(f"Error description: {result.get('error_description', 'No description')}")
            return None
    except Exception as e:
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client - Function: get_access_token - Exception while obtaining access token: {str(e)}")
        return None

async def fetch_unread_emails(access_token, user_id, max_retries=3):
    """
    Fetch unread emails from the specified user's mailbox.
    
    Args:
        access_token (str): Valid access token for Microsoft Graph API
        user_id (str): Email address of the user whose mailbox to fetch from
        max_retries (int): Maximum number of retry attempts on failure
        
    Returns:
        list: List of tuples containing (email_details, message_id) for each unread email
    """
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }

    endpoint = f'https://graph.microsoft.com/v1.0/users/{user_id}/messages?$filter=isRead eq false'
    
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        messages = data.get('value', [])
                        
                        if not messages:
                            # print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: fetch_unread_emails - No unread messages found for user {user_id}")
                            return []
                            
                        email_details_list = []
                        for msg in messages:
                            try:
                                # Create email details for each message
                                email_details = create_email_details(msg)
                                email_details_list.append((email_details, msg['id']))
                            except Exception as e:
                                print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: fetch_unread_emails - Error processing message {msg.get('id', 'unknown')}: {str(e)}")
                                # Continue with other messages even if one fails
                                continue
                                
                        return email_details_list
                    elif response.status == 401:
                        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: fetch_unread_emails - Authentication failed for user {user_id}: {response.status}")
                        print(await response.text())
                        # Don't retry on auth failure
                        return []
                    else:
                        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: fetch_unread_emails - Failed to retrieve messages for user {user_id}: {response.status}")
                        print(await response.text())
        except aiohttp.ClientError as e:
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: fetch_unread_emails - HTTP client error: {str(e)}")
        except Exception as e:
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: fetch_unread_emails - Unexpected error: {str(e)}")
        
        # Implement exponential backoff for retries
        if attempt < max_retries - 1:
            backoff_time = 2 ** attempt
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: fetch_unread_emails - Retrying in {backoff_time} seconds (attempt {attempt + 1}/{max_retries})...")
            await asyncio.sleep(backoff_time)
    
    # If we've exhausted all retries, return an empty list
    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: fetch_unread_emails - Failed to fetch unread emails after {max_retries} attempts.")
    return []

async def mark_email_as_read(access_token: str, user_id: str, message_id: str, max_retries: int = 3) -> bool:
    """
    Mark a specific email message as read.
    
    Args:
        access_token (str): Valid access token for Microsoft Graph API
        user_id (str): Email address of the user whose mailbox to modify
        message_id (str): ID of the message to mark as read
        max_retries (int): Maximum number of retry attempts on failure
        
    Returns:
        bool: True if successful, False otherwise
    """
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }
    endpoint = f'https://graph.microsoft.com/v1.0/users/{user_id}/messages/{message_id}'
    body = {
        'isRead': True
    }
    
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.patch(endpoint, headers=headers, json=body) as response:
                    if response.status == 200:
                        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: mark_email_as_read - Marked message {message_id} as read.")
                        return True
                    else:
                        response_text = await response.text()
                        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: mark_email_as_read - Failed to mark message {message_id} as read: {response.status}")
                        print(f"Response: {response_text}")
                        
                        # If the message doesn't exist or access is denied, don't retry
                        if response.status in [404, 403]:
                            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: mark_email_as_read - Message not found or access denied. Not retrying.")
                            return False
        except aiohttp.ClientError as e:
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: mark_email_as_read - HTTP client error: {str(e)}")
        except Exception as e:
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: mark_email_as_read - Error marking message {message_id} as read: {str(e)}")
        
        # Implement exponential backoff for retries
        if attempt < max_retries - 1:
            backoff_time = 2 ** attempt
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: mark_email_as_read - Retrying in {backoff_time} seconds (attempt {attempt + 1}/{max_retries})...")
            await asyncio.sleep(backoff_time)
    
    return False

async def force_mark_emails_as_read(access_token: str, user_id: str, message_ids: list) -> dict:
    """
    Attempt to mark multiple emails as read, reporting success/failure for each.
    
    Args:
        access_token (str): Valid access token for Microsoft Graph API
        user_id (str): Email address of the user whose mailbox to modify
        message_ids (list): List of message IDs to mark as read
        
    Returns:
        dict: Dictionary mapping message IDs to success status (True/False)
    """
    results = {}
    for message_id in message_ids:
        try:
            success = await mark_email_as_read(access_token, user_id, message_id)
            results[message_id] = success
        except Exception as e:
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: force_mark_emails_as_read - Error processing message {message_id}: {str(e)}")
            results[message_id] = False
    return results

async def forward_email(access_token, user_id, message_id, original_sender, forward_to, email_data, forwardMsg=""):
    """
    Forward an email to another address while preserving metadata.
    
    Args:
        access_token (str): Valid access token for Microsoft Graph API
        user_id (str): Email address of the user whose mailbox contains the message
        message_id (str): ID of the message to forward
        original_sender (str): Email address of the original sender
        forward_to (str): Email address to forward to
        email_data (dict): Dictionary containing email data
        forwardMsg (str): Optional message to include in the forwarded email
        
    Returns:
        bool: True if successfully forwarded, False otherwise
    """
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': "application/json; odata.metadata=minimal; odata.streaming=true; IEEE754Compatible=false; charset=utf-8",
    }
    
    # Implement multiple retry attempts with exponential backoff
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: Check if email has attachments and validate it's safe to forward
                email_details_endpoint = f'https://graph.microsoft.com/v1.0/users/{user_id}/messages/{message_id}/'
                
                async with session.get(email_details_endpoint, headers=headers) as get_response:
                    if get_response.status != 200:
                        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Failed to get original message: {get_response.status}")
                        print(await get_response.text())
                        
                        # If message doesn't exist, don't retry
                        if get_response.status == 404:
                            return False
                    
                    original_message = await get_response.json()
                    
                    # Format CC recipients from comma-separated string
                    cc_recipients = []
                    try:
                        if email_data.get('cc'):                         
                            
                            ## New code start

                            # Split the CC string and remove any whitespace
                            cc_list = [email.strip() for email in email_data.get('cc').split(',') if email.strip()]
                            
                            # GET THE LIST OF EXLUDED MAILS FROM THE CC EXCLUSION LIST
                            EXCLUDED_EMAILS_SET = get_excluded_emails_set(CC_EXCLUSION_LIST) 
                            
                            
                            # Exclude emails in EXCLUDED_EMAILS_SET
                            filtered_cc_list = [cc for cc in cc_list if cc.lower() not in {e.lower() for e in EXCLUDED_EMAILS_SET}]

                            # Create properly formatted recipient objects for each CC
                            cc_recipients = [
                                {
                                    "emailAddress": {
                                        "address": cc
                                    }
                                } for cc in filtered_cc_list if cc  # Additional check to ensure no empty emails
                            ]
                            
                            ## New code end
                            
                    except Exception as cc_err:
                        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Error formatting CC recipients: {str(cc_err)}")
                        # Continue without CC recipients if there's an error
                        cc_recipients = []
                    
                    # Check if email has attachments               
                    if original_message.get('hasAttachments') == True:
                        
                        get_attachments_endpoint = f'https://graph.microsoft.com/v1.0/users/{user_id}/messages/{message_id}/attachments'
                        async with session.get(get_attachments_endpoint, headers=headers) as get_attachments_response:
                            
                            # Validate attachment response
                            if get_attachments_response.status != 200:
                                print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Failed to get attachments: {get_attachments_response.status}")
                                print(await get_attachments_response.text())
                                
                                # If we can't get attachment details, retry later
                                if attempt < max_retries - 1:
                                    await asyncio.sleep(2 ** attempt)
                                    continue
                                return False
                            
                            get_attachments_data = await get_attachments_response.json() 
                            
                            # Check if attachment scan is in progress
                            try:
                                if get_attachments_data.get('value') and get_attachments_data.get('value')[0]['name'] == "Safe Attachments Scan In Progress":
                                    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Attachment scan in progress. Will not forward.")
                                    return False 
                            except (KeyError, IndexError) as e:
                                print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Error checking attachment scan status: {str(e)}")
                                # If we can't determine attachment status, retry later
                                if attempt < max_retries - 1:
                                    await asyncio.sleep(2 ** attempt)
                                    continue
                                # For safety, don't forward if we can't validate attachments
                                return False
                    
                    # Whether there are attachments or not, proceed with forwarding
                    
                    # Step 2: Create the forward email draft
                    create_forward_endpoint = f'https://graph.microsoft.com/v1.0/users/{user_id}/messages/{message_id}/createForward'
                    async with session.post(create_forward_endpoint, headers=headers) as create_response:
                        if create_response.status != 201:
                            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Failed to create forward: {create_response.status}")
                            print(await create_response.text())
                            
                            # If authorization failed, don't retry
                            if create_response.status in [401, 403]:
                                return False
                                
                            # If we can't create forward, retry with backoff
                            if attempt < max_retries - 1:
                                await asyncio.sleep(2 ** attempt)
                                continue
                            return False
                        
                        forward_message = await create_response.json()
                        forward_id = forward_message['id']

                    # Step 3: Update the forward email with proper headers
                    update_endpoint = f'https://graph.microsoft.com/v1.0/users/{user_id}/messages/{forward_id}'
                    update_body = {
                        "toRecipients": [
                            {
                                "emailAddress": {
                                    "address": forward_to
                                }
                            }
                        ],
                        "ccRecipients": cc_recipients if cc_recipients else [],
                        "replyTo": [
                            {
                                "emailAddress": {
                                    "address": original_sender
                                }
                            }
                        ],
                        "body": {
                            "contentType": forward_message['body']['contentType'],
                            "content": f"{forward_message['body']['content']}"
                        }
                    }

                    async with session.patch(update_endpoint, headers=headers, json=update_body) as update_response:
                        if update_response.status != 200:
                            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Failed to update forward: {update_response.status}")
                            print(await update_response.text())
                            
                            # If we can't update the forward, retry with backoff
                            if attempt < max_retries - 1:
                                await asyncio.sleep(2 ** attempt)
                                continue
                            return False

                    # Step 4: Send the forward email
                    send_endpoint = f'https://graph.microsoft.com/v1.0/users/{user_id}/messages/{forward_id}/send'
                    async with session.post(send_endpoint, headers=headers) as send_response:
                        if send_response.status != 202:
                            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Failed to send forward: {send_response.status}")
                            print(await send_response.text())
                            
                            # If we can't send the forward, retry with backoff
                            if attempt < max_retries - 1:
                                await asyncio.sleep(2 ** attempt)
                                continue
                            return False
                        
                        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Successfully forwarded message to {forward_to} with reply-to set to {original_sender}")
                        return True
                        
        except aiohttp.ClientError as e:
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - HTTP client error: {str(e)}")
        except Exception as e:
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - An error occurred: {str(e)}")
        
        # Implement exponential backoff for retries
        if attempt < max_retries - 1:
            backoff_time = 2 ** attempt
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Retrying in {backoff_time} seconds (attempt {attempt + 1}/{max_retries})...")
            await asyncio.sleep(backoff_time)
    
    # If we've exhausted all retries, return False
    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Failed to forward email after {max_retries} attempts.")
    return False
                
# Keeping the synchronous version for compatibility with existing code
def get_access_token_sync():
    """
    Synchronous wrapper for get_access_token
    
    Returns:
        str: Access token if successful, None otherwise
    """
    return asyncio.run(get_access_token())

def fetch_unread_emails_sync(access_token, user_id):
    """
    Synchronous wrapper for fetch_unread_emails
    
    Args:
        access_token (str): Valid access token for Microsoft Graph API
        user_id (str): Email address of the user whose mailbox to fetch from
        
    Returns:
        list: List of tuples containing (email_details, message_id) for each unread email
    """
    return asyncio.run(fetch_unread_emails(access_token, user_id))

def forward_email_sync(access_token, user_id, message_id, original_sender, forward_to, email_data, forwardMsg="Forwarded message"):
    """
    Synchronous wrapper for forward_email
    
    Args:
        access_token (str): Valid access token for Microsoft Graph API
        user_id (str): Email address of the user whose mailbox contains the message
        message_id (str): ID of the message to forward
        original_sender (str): Email address of the original sender
        forward_to (str): Email address to forward to
        email_data (dict): Dictionary containing email data
        forwardMsg (str): Optional message to include in the forwarded email
        
    Returns:
        bool: True if successfully forwarded, False otherwise
    """
    return asyncio.run(forward_email(access_token, user_id, message_id, original_sender, forward_to, email_data, forwardMsg))


## 10/07/2025 - Adding new function to parse exclusion mails in the cc field and return a list of emails for APEX to exclude if found in the the email cc field
def get_excluded_emails_set(EMAIL_LIST):
    """
    Parse the excluded emails list from environment variable into a set.
    
    Returns:
        set: Set of email addresses to exclude (lowercase for case-insensitive comparison)
    """
    excluded_emails = EMAIL_LIST.strip()
    if not excluded_emails:
        return set()
    
    # Split by comma, strip whitespace, and convert to lowercase for case-insensitive comparison
    email_list = [email.strip().lower() for email in excluded_emails.split(',') if email.strip()]
    return set(email_list)