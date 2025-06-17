async def send_autoresponse(account, sender_email, email_subject, email_data):
    """
    Send an autoresponse email to the sender.
    Enhanced with comprehensive loop prevention to avoid infinite autoresponse cycles.
    
    Args:
        account (str): Email account to send from (should match one in EMAIL_ACCOUNTS)
        sender_email (str): Email address to send autoresponse to
        email_subject (str): Original email subject
        email_data (dict): Original email data
        
    Returns:
        bool: True if successful, False otherwise
    """
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        # Get the recipient email (where the original email was sent to)
        recipient_email = email_data.get('to', '').split(',')[0].strip()
        
        # Get email body for enhanced analysis
        email_body = email_data.get('body_text', '') or email_data.get('body_html', '')
        
        # DEBUG LOGGING - Log what we're about to check
        print(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - "
              f"CHECKING autoresponse eligibility: ACCOUNT={account} SENDER={sender_email} "
              f"RECIPIENT={recipient_email} SUBJECT='{email_subject}'")
        
        # ENHANCED LOOP PREVENTION: Check if we should skip sending autoresponse
        # Using the new time-based loop protection with content similarity
        should_skip, skip_reason = await should_skip_autoresponse(
            recipient_email, 
            sender_email, 
            email_subject, 
            email_body
        )
        
        if should_skip:
            print(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - "
                  f"SKIPPING autoresponse: {skip_reason}")
            return False  # Return False to indicate no autoresponse was sent (not an error)
        
        print(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - "
              f"Autoresponse allowed, proceeding to send...")
            
        # Continue with existing autoresponse logic...
        # Get access token for Microsoft Graph API
        access_token = await get_access_token()
        if not access_token:
            print(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Failed to obtain access token for autoresponse")
            return False
        
        # Get template from Azure Blob Storage
        template_content, template_folder = await get_template_from_blob(recipient_email)
        
        # If no template found, use a default template
        if not template_content:
            print(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - No template found for {recipient_email}, using default template")
            template_content = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #0056b3;">Thank you for contacting us</h2>
                    
                    <p>We have received your email and will respond as soon as possible.</p>
                    
                    <p>Reference number: <strong>{{REFERENCE_ID}}</strong></p>
                    
                    <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #dddddd; font-size: 12px; color: #666666;">
                        <p>This is an automated response. Please do not reply to this email.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            template_folder = None  # No folder for default template
        
        # Process the template to replace variables and update image references
        processed_template = await process_template(template_content, template_folder, email_data)
        
        # Create subject line for autoresponse using the new mapping
        subject = get_subject_line_for_template(template_folder, email_subject)
        
        print(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Using subject line: {subject} for template: {template_folder}")
        
        # Extract plain text version from HTML (simplified)
        plain_text = "Thank you for your email. We have received your message and will respond as soon as possible. This is an automated response. Please do not reply to this email."
        
        # Send the email with enhanced encoding handling
        print(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Sending autoresponse to {sender_email}")
        result = await send_email(
            access_token,
            account,
            sender_email,
            subject,
            processed_template,
            plain_text
        )
        
        if result:
            print(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Autoresponse sent successfully to {sender_email}")
            return True
        else:
            print(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Failed to send autoresponse to {sender_email}")
            return False
            
    except Exception as e:
        print(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Error sending autoresponse: {str(e)}")
        import traceback
        print(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Traceback: {traceback.format_exc()}")
        return False
    
async def send_email(access_token, account, to_email, subject, body_html, body_text):
    """
    Send a new email using Microsoft Graph API with enhanced encoding handling.
    Focus on proper delivery mechanism rather than content manipulation.
    
    Args:
        access_token (str): Valid access token for Microsoft Graph API
        account (str): Email account to send from
        to_email (str): Recipient email address
        subject (str): Email subject
        body_html (str): HTML body content
        body_text (str): Plain text body content
        
    Returns:
        bool: True if successful, False otherwise
    """
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        # Method 1: Try sending with proper charset and encoding headers
        success = await _send_email_with_charset(access_token, account, to_email, subject, body_html, body_text, timestamp)
        if success:
            return True
        
        # Method 2: If that fails, try with base64 encoding
        print(f">> {timestamp} Script: autoresponse.py - Function: send_email - First method failed, trying base64 encoding")
        success = await _send_email_with_base64(access_token, account, to_email, subject, body_html, body_text, timestamp)
        return success
        
    except Exception as e:
        print(f">> {timestamp} Script: autoresponse.py - Function: send_email - Error in send_email: {str(e)}")
        return False
    
async def _send_email_fallback(access_token, account, to_email, subject, body_html, body_text, timestamp):
    """
    Final fallback: Send with minimal processing.
    """
    try:
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }
        
        message_body = {
            'message': {
                'subject': subject,
                'body': {
                    'contentType': 'html',
                    'content': body_html
                },
                'toRecipients': [
                    {
                        'emailAddress': {
                            'address': to_email
                        }
                    }
                ]
            },
            'saveToSentItems': 'true'
        }
        
        endpoint = f'https://graph.microsoft.com/v1.0/users/{account}/sendMail'
        
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, json=message_body) as response:
                if response.status == 202:
                    print(f">> {timestamp} Script: autoresponse.py - Function: _send_email_fallback - Email sent successfully with fallback method")
                    return True
                else:
                    response_text = await response.text()
                    print(f">> {timestamp} Script: autoresponse.py - Function: _send_email_fallback - Final fallback failed with status {response.status}: {response_text}")
                    return False
    
    except Exception as e:
        print(f">> {timestamp} Script: autoresponse.py - Function: _send_email_fallback - Exception: {str(e)}")
        return False
    
async def _send_email_with_base64(access_token, account, to_email, subject, body_html, body_text, timestamp):
    """
    Second attempt: Send email with base64 encoded content to preserve encoding.
    """
    try:
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        
        # Base64 encode the HTML content to preserve all characters
        html_content_b64 = base64.b64encode(body_html.encode('utf-8')).decode('ascii')
        
        message_body = {
            'message': {
                'subject': subject,
                'body': {
                    'contentType': 'html',
                    'content': html_content_b64,
                    'isBase64': True  # This might not be supported, but worth trying
                },
                'toRecipients': [
                    {
                        'emailAddress': {
                            'address': to_email
                        }
                    }
                ]
            },
            'saveToSentItems': 'true'
        }
        
        endpoint = f'https://graph.microsoft.com/v1.0/users/{account}/sendMail'
        
        async with aiohttp.ClientSession() as session:
            json_payload = json.dumps(message_body)
            
            async with session.post(endpoint, headers=headers, data=json_payload.encode('utf-8')) as response:
                if response.status == 202:
                    print(f">> {timestamp} Script: autoresponse.py - Function: _send_email_with_base64 - Email sent successfully with base64")
                    return True
                else:
                    response_text = await response.text()
                    print(f">> {timestamp} Script: autoresponse.py - Function: _send_email_with_base64 - Failed with status {response.status}: {response_text}")
                    
                    # If base64 approach failed, try without the isBase64 flag
                    return await _send_email_fallback(access_token, account, to_email, subject, body_html, body_text, timestamp)
    
    except Exception as e:
        print(f">> {timestamp} Script: autoresponse.py - Function: _send_email_with_base64 - Exception: {str(e)}")
        return False
    
async def _send_email_with_charset(access_token, account, to_email, subject, body_html, body_text, timestamp):
    """
    First attempt: Send email with proper charset declarations and headers.
    """
    try:
        # Ensure HTML has proper charset declaration
        if body_html:
            # Check if HTML already has proper structure
            if not '<!DOCTYPE html>' in body_html.upper():
                # Wrap in proper HTML structure with charset
                body_html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
</head>
<body>
{body_html}
</body>
</html>'''
            elif not '<meta charset=' in body_html.lower() and not 'content-type' in body_html.lower():
                # Add charset to existing HTML
                if '<head>' in body_html.lower():
                    head_pos = body_html.lower().find('<head>') + 6
                    charset_meta = '\n<meta charset="UTF-8">\n<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">\n'
                    body_html = body_html[:head_pos] + charset_meta + body_html[head_pos:]
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json; charset=utf-8',
            'Accept': 'application/json',
        }
        
        message_body = {
            'message': {
                'subject': subject,
                'body': {
                    'contentType': 'html',
                    'content': body_html
                },
                'toRecipients': [
                    {
                        'emailAddress': {
                            'address': to_email
                        }
                    }
                ]
            },
            'saveToSentItems': 'true'
        }
        
        endpoint = f'https://graph.microsoft.com/v1.0/users/{account}/sendMail'
        
        # Create session with specific encoding settings
        connector = aiohttp.TCPConnector(force_close=True)
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # Serialize JSON with proper UTF-8 handling
            json_payload = json.dumps(message_body, ensure_ascii=False, separators=(',', ':'))
            
            async with session.post(endpoint, headers=headers, data=json_payload.encode('utf-8')) as response:
                if response.status == 202:
                    print(f">> {timestamp} Script: autoresponse.py - Function: _send_email_with_charset - Email sent successfully")
                    return True
                else:
                    response_text = await response.text()
                    print(f">> {timestamp} Script: autoresponse.py - Function: _send_email_with_charset - Failed with status {response.status}: {response_text}")
                    return False
    
    except Exception as e:
        print(f">> {timestamp} Script: autoresponse.py - Function: _send_email_with_charset - Exception: {str(e)}")
        return False

async def process_template(template_content, template_folder, email_data):
    """
    Process the template by replacing variables with actual values and updating image references.
    IMPORTANT: Template is taken as-is with minimal manipulation per user requirements.
    
    Args:
        template_content (str): The HTML template content
        template_folder (str): The folder name in blob storage for this template
        email_data (dict): Original email data
        
    Returns:
        str: Processed template content
    """
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        if not template_content:
            return template_content
        
        # Process image references to use absolute URLs for blob storage - THIS IS THE KEY STEP
        if template_folder:
            print(f">> {timestamp} Script: autoresponse.py - Function: process_template - Starting image processing for folder: {template_folder}")
            processed_content = await process_template_images(template_content, template_folder)
        else:
            print(f">> {timestamp} Script: autoresponse.py - Function: process_template - No template folder provided, skipping image processing")
            processed_content = template_content
        
        # Generate a reference ID (could be based on the email ID or a UUID)
        reference_id = email_data.get('internet_message_id', '')
        if not reference_id:
            reference_id = str(uuid.uuid4())
        
        # Truncate if too long - take last 10 characters
        if len(reference_id) > 10:
            reference_id = reference_id[-10:]
        
        # Replace variables in the template - ONLY the reference ID placeholder
        processed_content = processed_content.replace('{{REFERENCE_ID}}', reference_id)
        
        # Log completion
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template - Template processing completed successfully")
        
        return processed_content
        
    except Exception as e:
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template - Error processing template: {str(e)}")
        return template_content  # Return original content if processing failsimport asyncio
import datetime
import os
import re
import uuid
import aiohttp
import json
import base64
from bs4 import BeautifulSoup
from azure.storage.blob.aio import BlobServiceClient
from email_processor.email_client import get_access_token
from apex_llm.apex_logging import check_email_processed
from config import (
    AZURE_STORAGE_CONNECTION_STRING, 
    BLOB_CONTAINER_NAME, 
    AZURE_STORAGE_PUBLIC_URL, 
    EMAIL_TO_FOLDER_MAPPING, 
    EMAIL_SUBJECT_MAPPING,
    EMAIL_ACCOUNTS,
    SQL_SERVER,
    SQL_DATABASE,
    SQL_USERNAME,
    SQL_PASSWORD
)
import pyodbc

# Configuration for time-based loop protection
# These could be moved to config.py if needed for easier management
TIME_WINDOW_HOURS = 24      # Time window to check for previous responses (in hours)
MAX_RESPONSES_IN_WINDOW = 1  # Maximum number of autoresponses allowed in time window

class AutoResponseLoopProtection:
    """
    Time-based loop protection for autoresponses that prevents sending
    multiple autoresponses to the same sender within a configurable time period.
    """
    
    def __init__(self, time_window_hours=TIME_WINDOW_HOURS, max_messages=MAX_RESPONSES_IN_WINDOW):
        """
        Initialize the loop protection with configurable parameters.
        
        Args:
            time_window_hours (int): Number of hours to look back for previous responses
            max_messages (int): Maximum number of messages allowed in the time window
        """
        self.time_window_hours = time_window_hours
        self.max_messages = max_messages
        
        # Log initialization
        timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
        print(f">> {timestamp} Time-based loop protection initialized with {time_window_hours}h window, {max_messages} max messages")
    
    async def should_skip_autoresponse(self, recipient_email, sender_email, subject=None, email_body=None):
        """
        Determine if autoresponse should be skipped based on time-based rules.
        
        Args:
            recipient_email (str): Email address where the original email was sent to
            sender_email (str): Email address of the original sender
            subject (str): Email subject line (optional but recommended)
            email_body (str): Email body content (optional but recommended)
            
        Returns:
            tuple: (should_skip: bool, reason: str) - True if autoresponse should be skipped
        """
        timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
        
        # STEP 1: BASIC VALIDATION
        if not sender_email:
            return True, "No sender email found"
        
        if not recipient_email:
            return True, "No recipient email found"
        
        # Clean up email addresses for comparison
        sender_clean = sender_email.lower().strip()
        
        # STEP 2: PRIMARY TIME-BASED LOOP PROTECTION
        # Check if we've already sent an autoresponse to this sender within the time window
        try:
            # Check for similar emails from this sender, considering subject and body content
            recent_similar_responses = await self._check_recent_responses(sender_clean, subject, email_body)
            
            if recent_similar_responses >= self.max_messages:
                reason = f"Found {recent_similar_responses} similar emails from {sender_email} within last {self.time_window_hours} hours"
                print(f">> {timestamp} SKIPPING autoresponse (similar content detected): {reason}")
                return True, reason
            
            # Log that we're allowing this autoresponse based on time window check
            print(f">> {timestamp} Time window check passed: No similar emails from {sender_email} within {self.time_window_hours}h window")
            
        except Exception as e:
            # If there's any error in the time-based check, log it but continue to other checks
            print(f">> {timestamp} Error in time-based loop protection: {str(e)}")
            # We don't return here - continue to system message detection
        
        # STEP 3: FALLBACK SYSTEM MESSAGE DETECTION
        # Only run these checks if the time-based check passed or had an error
        try:
            # Check if this is an automated or system message
            is_system, system_reason = self._is_system_message(sender_email, subject, email_body)
            if is_system:
                print(f">> {timestamp} SKIPPING autoresponse (system message): {system_reason}")
                return True, system_reason
                
            # Check if this is a direct email to an autoresponse account
            if self._is_direct_to_autoresponse(recipient_email):
                reason = f"Email sent directly to autoresponse account: {recipient_email}"
                print(f">> {timestamp} SKIPPING autoresponse (direct): {reason}")
                return True, reason
                
            # Check if sender is also an autoresponse account (self-loop)
            if self._is_autoresponse_account(sender_email):
                reason = f"Sender is also an autoresponse account: {sender_email}"
                print(f">> {timestamp} SKIPPING autoresponse (self-loop): {reason}")
                return True, reason
                
        except Exception as e:
            # If there's any error in system message detection, log it
            print(f">> {timestamp} Error in system message detection: {str(e)}")
            # Continue - we don't want errors to block autoresponses
        
        # If we made it here, all checks passed - allow the autoresponse
        print(f">> {timestamp} ALLOWING autoresponse to {sender_email}")
        return False, "Autoresponse allowed - all checks passed"
    
    async def _check_recent_responses(self, sender_email, subject=None, email_body=None):
        """
        Enhanced check for similar emails sent within the time window.
        Performs a comprehensive similarity check using multiple factors:
        1. Sender email address
        2. Similar subject lines (if provided)
        3. Similar email content (if provided)
        
        Args:
            sender_email (str): Clean sender email address to check
            subject (str): Subject of the current email (optional)
            email_body (str): Body of the current email (optional)
            
        Returns:
            int: Number of similar autoresponses found in the time window
        """
        timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
        
        try:
            # Calculate the timestamp for the start of the time window
            window_start = datetime.datetime.now() - datetime.timedelta(hours=self.time_window_hours)
            window_start_str = window_start.strftime('%Y-%m-%d %H:%M:%S')
            
            # Create database connection
            conn = pyodbc.connect(
                f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SQL_SERVER};DATABASE={SQL_DATABASE};UID={SQL_USERNAME};PWD={SQL_PASSWORD}'
            )
            cursor = conn.cursor()
            
            # Start with a base query for the sender
            search_params = [f'%{sender_email}%', window_start_str]
            base_query = """
            SELECT eml_id, eml_frm, eml_sub, eml_bdy, dttm_proc
            FROM [dbo].[logs] 
            WHERE eml_frm LIKE ? 
            AND dttm_proc >= ?
            AND auto_response_sent = 'success'
            """
            
            # Execute the base query to get potential matching emails
            cursor.execute(base_query, search_params)
            
            # Fetch all matching rows
            potential_matches = cursor.fetchall()
            
            # Count of confirmed similar emails
            similar_email_count = 0
            
            # Process each potential match to check for similarity
            for row in potential_matches:
                similarity_score = 0
                max_score = 0
                
                # Extract values from the row
                db_email_id = row[0] if row[0] else ""
                db_from = row[1] if row[1] else ""
                db_subject = row[2] if row[2] else ""
                db_body = row[3] if row[3] else ""
                db_timestamp = row[4] if row[4] else None
                
                # SIMILARITY CHECK 1: Sender email exact match (highest weight)
                if sender_email.lower() in db_from.lower():
                    similarity_score += 40
                max_score += 40
                
                # SIMILARITY CHECK 2: Subject line similarity (if available)
                if subject and db_subject:
                    # Clean and normalize subject lines
                    clean_subject = re.sub(r'(re:|fwd:|fw:)\s*', '', subject.lower()).strip()
                    clean_db_subject = re.sub(r'(re:|fwd:|fw:)\s*', '', db_subject.lower()).strip()
                    
                    # Exact subject match
                    if clean_subject == clean_db_subject:
                        similarity_score += 30
                    # Subject contains or is contained in the db subject
                    elif clean_subject in clean_db_subject or clean_db_subject in clean_subject:
                        similarity_score += 20
                    # Check for partial match using key words (more than 3 chars)
                    else:
                        subject_words = set([w for w in clean_subject.split() if len(w) > 3])
                        db_subject_words = set([w for w in clean_db_subject.split() if len(w) > 3])
                        common_words = subject_words.intersection(db_subject_words)
                        if len(common_words) >= 2:  # At least 2 significant words in common
                            similarity_score += 15
                    
                    max_score += 30
                
                # SIMILARITY CHECK 3: Email body similarity (if available)
                if email_body and db_body:
                    # Only use the first 200 characters for comparison to keep it efficient
                    clean_body = email_body[:200].lower().strip()
                    clean_db_body = db_body[:200].lower().strip()
                    
                    # Calculate content similarity
                    # For simplicity, we check if there are significant matching chunks
                    # A more sophisticated approach could use proper text similarity algorithms
                    
                    # Check for exact paragraph matches
                    body_chunks = [chunk.strip() for chunk in clean_body.split('\n') if len(chunk.strip()) > 20]
                    db_body_chunks = [chunk.strip() for chunk in clean_db_body.split('\n') if len(chunk.strip()) > 20]
                    
                    for chunk in body_chunks:
                        for db_chunk in db_body_chunks:
                            if chunk in db_chunk or db_chunk in chunk:
                                similarity_score += 20
                                break
                    
                    # Check for common phrases (5+ words)
                    body_phrases = self._extract_phrases(clean_body, 5)
                    db_body_phrases = self._extract_phrases(clean_db_body, 5)
                    
                    common_phrases = set(body_phrases).intersection(set(db_body_phrases))
                    if common_phrases:
                        similarity_score += min(10, len(common_phrases) * 5)  # Cap at 10 points
                    
                    max_score += 30
                
                # Calculate final similarity percentage
                similarity_percentage = (similarity_score / max_score * 100) if max_score > 0 else 0
                
                # Log the similarity analysis for debugging
                if similarity_percentage > 0:
                    print(f">> {timestamp} Email similarity: {similarity_percentage:.1f}% with previous email from {db_from} sent at {db_timestamp}")
                
                # Count as similar if similarity is above threshold (60%)
                if similarity_percentage >= 60:
                    similar_email_count += 1
                    print(f">> {timestamp} Similar email match found! ID: {db_email_id}, From: {db_from}, Date: {db_timestamp}")
            
            cursor.close()
            conn.close()
            
            if similar_email_count > 0:
                print(f">> {timestamp} Found {similar_email_count} similar emails from {sender_email} within the last {self.time_window_hours} hours")
            else:
                print(f">> {timestamp} No similar emails found from {sender_email} within the last {self.time_window_hours} hours")
                
            return similar_email_count
            
        except Exception as e:
            # If there's any error querying the database, log it and return 0
            print(f">> {timestamp} Error checking recent responses: {str(e)}")
            return 0
    
    def _extract_phrases(self, text, min_words=5):
        """
        Extract phrases of a minimum number of words from text.
        Used for content similarity comparison.
        
        Args:
            text (str): The text to extract phrases from
            min_words (int): Minimum number of words in a phrase
            
        Returns:
            list: List of phrases extracted from the text
        """
        if not text:
            return []
            
        # Split text into sentences
        sentences = re.split(r'[.!?]', text)
        
        phrases = []
        for sentence in sentences:
            # Clean the sentence
            clean_sentence = re.sub(r'[^\w\s]', '', sentence).strip().lower()
            words = clean_sentence.split()
            
            # Skip sentences that are too short
            if len(words) < min_words:
                continue
                
            # Create phrases from the sentence
            for i in range(len(words) - min_words + 1):
                phrase = ' '.join(words[i:i+min_words])
                phrases.append(phrase)
                
        return phrases
    
    def _is_system_message(self, sender_email, subject=None, email_body=None):
        """
        Check if this appears to be a system message or bounce notification.
        This is a fallback check in case the time-based protection fails.
        
        Args:
            sender_email (str): Email address of the sender
            subject (str): Email subject line (optional)
            email_body (str): Email body content (optional)
            
        Returns:
            tuple: (is_system: bool, reason: str)
        """
        # Clean up sender email for comparison
        sender_clean = sender_email.lower().strip()
        
        # 1. MICROSOFT EXCHANGE SYSTEM DETECTION
        exchange_patterns = [
            r'microsoftexchange[a-f0-9]+@',
            r'exchange[a-f0-9]+@',
            r'[a-f0-9]{32}@'
        ]
        
        for pattern in exchange_patterns:
            if re.search(pattern, sender_clean):
                return True, f"Microsoft Exchange system sender detected"
        
        # 2. SYSTEM ADDRESS DETECTION
        system_indicators = [
            'noreply', 'no-reply', 'donotreply', 'do-not-reply',
            'mailer-daemon', 'postmaster', 'daemon', 'mail-daemon'
        ]
        
        for indicator in system_indicators:
            if indicator in sender_clean:
                return True, f"System/automated sender detected"
        
        # 3. SUBJECT LINE ANALYSIS - Only if a subject is provided
        if subject:
            subject_clean = subject.lower().strip()
            bounce_subject_indicators = [
                'undeliverable', 'delivery failure', 'mail delivery failed',
                'returned mail', 'bounce', 'not delivered'
            ]
            
            for indicator in bounce_subject_indicators:
                if indicator in subject_clean:
                    return True, f"Bounce message detected in subject"
        
        # 4. EMAIL BODY ANALYSIS - Only if body content is provided
        if email_body:
            body_clean = email_body.lower().strip()
            bounce_body_indicators = [
                'rejected your message', 'message could not be delivered',
                'recipient mailbox is full', 'delivery failed'
            ]
            
            for indicator in bounce_body_indicators:
                if indicator in body_clean:
                    return True, f"Bounce message detected in body content"
        
        # Not a system message
        return False, "Not a system message"
    
    def _is_direct_to_autoresponse(self, recipient_email):
        """
        Check if this email was sent directly to an autoresponse account.
        
        Args:
            recipient_email (str): Email address the message was sent to
            
        Returns:
            bool: True if sent directly to an autoresponse account
        """
        if not recipient_email:
            return False
            
        recipient_clean = recipient_email.lower().strip()
        
        if EMAIL_ACCOUNTS:
            for account in EMAIL_ACCOUNTS:
                if account and account.lower().strip() == recipient_clean:
                    return True
        
        return False
    
    def _is_autoresponse_account(self, sender_email):
        """
        Check if the sender is also an autoresponse account.
        
        Args:
            sender_email (str): Email address of the sender
            
        Returns:
            bool: True if sender is an autoresponse account
        """
        if not sender_email:
            return False
            
        sender_clean = sender_email.lower().strip()
        
        if EMAIL_ACCOUNTS:
            for account in EMAIL_ACCOUNTS:
                if account and account.lower().strip() == sender_clean:
                    return True
        
        return False


# Create a singleton instance of the loop protection
loop_protection = AutoResponseLoopProtection()

async def should_skip_autoresponse(recipient_email, sender_email, subject=None, email_body=None):
    """
    Global function to determine if autoresponse should be skipped.
    This maintains the existing function signature for compatibility.
    
    Args:
        recipient_email (str): Email address where the original email was sent to
        sender_email (str): Email address of the original sender
        subject (str): Email subject line (optional but recommended)
        email_body (str): Email body content (optional but recommended)
        
    Returns:
        tuple: (should_skip: bool, reason: str) - True if autoresponse should be skipped
    """
    # Delegate to the loop protection instance
    return await loop_protection.should_skip_autoresponse(recipient_email, sender_email, subject, email_body)

async def get_template_from_blob(recipient_email):
    """
    Retrieve template from Azure Blob Storage based on recipient email.
    Enhanced with proper encoding handling to preserve original template content.
    
    Args:
        recipient_email (str): Email address the message was sent to
        
    Returns:
        tuple: (template_content, template_folder) if found, (None, None) otherwise
    """
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        # Extract the mailbox name and domain from the email address
        email_parts = recipient_email.lower().split('@')
        mailbox_name = email_parts[0]
        domain = email_parts[1] if len(email_parts) > 1 else 'company.co.za'  # Default domain if not present
        
        # Check if we have a custom folder mapping for this email address
        folder_name = None
        
        # Try to match the full email address first
        if recipient_email.lower() in EMAIL_TO_FOLDER_MAPPING:
            folder_name = EMAIL_TO_FOLDER_MAPPING[recipient_email.lower()]
            print(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Using custom folder mapping for {recipient_email}: {folder_name}")
        # Then try to match just the mailbox part
        elif mailbox_name in EMAIL_TO_FOLDER_MAPPING:
            folder_name = EMAIL_TO_FOLDER_MAPPING[mailbox_name]
            print(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Using custom folder mapping for {mailbox_name}: {folder_name}")
        # If no mapping found, use the mailbox name as before
        else:
            folder_name = mailbox_name
            print(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - No custom mapping found, using mailbox name: {folder_name}")
        
        # Template file is in the folder with the same name as specified in the mapping
        # Use the domain from the email instead of hardcoding 'mail.co.za'
        template_path = f"{folder_name}/{mailbox_name}@{domain}.htm"
        
        print(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Retrieving template from path: {template_path}")
        
        # Create BlobServiceClient
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        
        # Get container client
        container_client = blob_service_client.get_container_client(BLOB_CONTAINER_NAME)
        
        # Get blob client
        blob_client = container_client.get_blob_client(template_path)
        
        # Check if blob exists
        if await blob_client.exists():
            # Download blob content - let's try to preserve original encoding
            download_stream = await blob_client.download_blob()
            template_content_bytes = await download_stream.readall()
            
            # Try UTF-8 first, then fall back to Windows-1252 (common for Word HTML)
            try:
                template_content = template_content_bytes.decode('utf-8')
                print(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Successfully decoded with UTF-8")
            except UnicodeDecodeError:
                try:
                    template_content = template_content_bytes.decode('windows-1252')
                    print(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Successfully decoded with Windows-1252")
                except UnicodeDecodeError:
                    # Final fallback
                    template_content = template_content_bytes.decode('utf-8', errors='replace')
                    print(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Used UTF-8 with error replacement")
            
            return template_content, folder_name
        else:
            # Try fallback to html extension
            alt_template_path = f"{folder_name}/{mailbox_name}@{domain}.html"
            blob_client = container_client.get_blob_client(alt_template_path)
            
            if await blob_client.exists():
                download_stream = await blob_client.download_blob()  
                template_content_bytes = await download_stream.readall()
                
                # Apply same encoding handling
                try:
                    template_content = template_content_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        template_content = template_content_bytes.decode('windows-1252')
                    except UnicodeDecodeError:
                        template_content = template_content_bytes.decode('utf-8', errors='replace')
                
                return template_content, folder_name
            else:
                # Try one more fallback to a simple named file
                simple_template_path = f"{folder_name}/{folder_name}.html"
                blob_client = container_client.get_blob_client(simple_template_path)
                
                if await blob_client.exists():
                    download_stream = await blob_client.download_blob()
                    template_content_bytes = await download_stream.readall()
                    
                    # Apply same encoding handling
                    try:
                        template_content = template_content_bytes.decode('utf-8')
                    except UnicodeDecodeError:
                        try:
                            template_content = template_content_bytes.decode('windows-1252')
                        except UnicodeDecodeError:
                            template_content = template_content_bytes.decode('utf-8', errors='replace')
                    
                    return template_content, folder_name
                else:
                    print(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Template not found in blob storage for folder: {folder_name}")
                    return None, None
            
    except Exception as e:
        print(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Error retrieving template from blob storage: {str(e)}")
        return None, None

def get_subject_line_for_template(template_folder, original_subject):
    """
    Get the appropriate subject line for the autoresponse based on template folder.
    
    Args:
        template_folder (str): The template folder name
        original_subject (str): Original email subject line
        
    Returns:
        str: Subject line for the autoresponse
    """
    try:
        # Get custom subject line from mapping, or use default
        if template_folder and template_folder in EMAIL_SUBJECT_MAPPING:
            return EMAIL_SUBJECT_MAPPING[template_folder]
        else:
            return EMAIL_SUBJECT_MAPPING.get("default", "Thank you for contacting us")
    except Exception as e:
        print(f"Error getting subject line for template {template_folder}: {str(e)}")
        return "Thank you for contacting us"

async def validate_blob_storage_config():
    """
    Validate that blob storage configuration is properly set up.
    
    Returns:
        bool: True if configuration is valid, False otherwise
    """
    if not AZURE_STORAGE_CONNECTION_STRING:
        print("ERROR: AZURE_STORAGE_CONNECTION_STRING is not configured")
        return False
    
    if not BLOB_CONTAINER_NAME:
        print("ERROR: BLOB_CONTAINER_NAME is not configured")
        return False
    
    if not AZURE_STORAGE_PUBLIC_URL:
        print("ERROR: AZURE_STORAGE_PUBLIC_URL is not configured")
        return False
    
    return True

async def check_image_exists_in_blob(blob_container_client, template_folder, image_filename):
    """
    Check if an image file exists in blob storage.
    
    Args:
        blob_container_client: Azure blob container client
        template_folder (str): Template folder name
        image_filename (str): Image filename to check
        
    Returns:
        bool: True if image exists, False otherwise
    """
    try:
        image_path = f"{template_folder}/{image_filename}"
        blob_client = blob_container_client.get_blob_client(image_path)
        return await blob_client.exists()
    except Exception as e:
        print(f"Error checking if image exists in blob: {str(e)}")
        return False

async def process_template_images(template_content, template_folder):
    """
    Process the template to update image references to point to blob storage.
    Enhanced with better error handling, validation, and comprehensive image reference processing.
    
    Args:
        template_content (str): HTML template content
        template_folder (str): Folder name in blob storage for this template
        
    Returns:
        str: Updated template content with absolute image URLs
    """
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    
    if not template_content or not template_folder:
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Missing template content or folder")
        return template_content
    
    # Validate blob storage configuration
    if not await validate_blob_storage_config():
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Blob storage configuration invalid")
        return template_content
    
    try:
        # Parse HTML using BeautifulSoup with proper HTML parser
        soup = BeautifulSoup(template_content, 'html.parser')
        
        # Base URL for images in blob storage - images are in the same folder as the template
        base_url = f"{AZURE_STORAGE_PUBLIC_URL.rstrip('/')}/{BLOB_CONTAINER_NAME}/{template_folder}"
        
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Processing images with base URL: {base_url}")
        
        # Create blob container client for validation (optional - can be disabled for performance)
        container_client = None
        try:
            blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
            container_client = blob_service_client.get_container_client(BLOB_CONTAINER_NAME)
        except Exception as e:
            print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Error creating blob client for validation: {str(e)}")
        
        # Track processed images for debugging
        processed_images = []
        
        # Find and process all img tags
        img_tags = soup.find_all('img')
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Found {len(img_tags)} img tags")
        
        for img in img_tags:
            if img.get('src'):
                original_src = img['src']
                
                # Skip if already an absolute URL
                if original_src.startswith('http'):
                    print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Skipping absolute URL: {original_src}")
                    continue
                
                # Clean up the source path
                src = original_src.replace('\\', '/').strip()
                img_filename = None
                
                # Handle different image reference patterns
                if '_files/' in src:
                    # Word HTML export pattern: "onlinesupport@brand.co.za_files/image001.png"
                    img_filename = src.split('_files/')[-1]
                elif '/' in src:
                    # General path pattern: "images/logo.jpg"  
                    img_filename = src.split('/')[-1]
                else:
                    # Simple filename: "logo.jpg"
                    img_filename = src
                
                if img_filename:
                    # Create absolute URL
                    absolute_url = f"{base_url}/{img_filename}"
                    
                    # Validate image exists in blob storage (optional - can be disabled for performance)
                    if container_client:
                        try:
                            image_exists = await check_image_exists_in_blob(container_client, template_folder, img_filename)
                            if not image_exists:
                                print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - WARNING: Image not found in blob storage: {img_filename}")
                        except Exception as check_error:
                            print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Error checking image existence: {str(check_error)}")
                    
                    # Update the src attribute
                    img['src'] = absolute_url
                    processed_images.append({
                        'original': original_src,
                        'filename': img_filename,
                        'absolute_url': absolute_url
                    })
                    
                    print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Updated img src: {original_src} -> {absolute_url}")
        
        # Find and process VML imagedata tags (used in Outlook HTML)
        vml_images = soup.find_all('v:imagedata')
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Found {len(vml_images)} VML imagedata tags")
        
        for vml_img in vml_images:
            if vml_img.get('src'):
                original_src = vml_img['src']
                
                if not original_src.startswith('http'):
                    src = original_src.replace('\\', '/').strip()
                    img_filename = None
                    
                    if '_files/' in src:
                        img_filename = src.split('_files/')[-1]
                    elif '/' in src:
                        img_filename = src.split('/')[-1]
                    else:
                        img_filename = src
                    
                    if img_filename:
                        absolute_url = f"{base_url}/{img_filename}"
                        vml_img['src'] = absolute_url
                        print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Updated VML imagedata src: {original_src} -> {absolute_url}")
        
        # Find and process background images in inline styles
        elements_with_style = soup.find_all(lambda tag: tag.has_attr('style') and 'background-image' in tag['style'])
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Found {len(elements_with_style)} elements with background-image styles")
        
        for elem in elements_with_style:
            style = elem['style']
            original_style = style
            
            # Use regex to find and replace URL references in CSS
            def replace_bg_url(match):
                url = match.group(1).strip('\'"')
                
                if url.startswith('http'):
                    return match.group(0)  # Keep as is if already absolute
                
                # Process relative URL
                img_filename = None
                if '_files/' in url:
                    img_filename = url.split('_files/')[-1]
                elif '/' in url:
                    img_filename = url.split('/')[-1]
                else:
                    img_filename = url
                
                if img_filename:
                    absolute_url = f"{base_url}/{img_filename}"
                    return f"url('{absolute_url}')"
                
                return match.group(0)
            
            # Replace all url() references in the style
            updated_style = re.sub(r'url\([\'"]?([^\'"]+?)[\'"]?\)', replace_bg_url, style)
            
            if updated_style != original_style:
                elem['style'] = updated_style
                print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Updated background image style")
        
        # Summary logging
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Processed {len(processed_images)} images successfully")
        
        # Convert back to string and return
        processed_html = str(soup)
        
        # Additional validation - check if we actually made changes
        if processed_html == template_content:
            print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - WARNING: No changes were made to template")
        else:
            print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Template successfully updated with blob storage URLs")
        
        return processed_html
        
    except Exception as e:
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Error processing template images: {str(e)}")
        import traceback
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Traceback: {traceback.format_exc()}")
        # Return original content if processing fails
        return template_content
