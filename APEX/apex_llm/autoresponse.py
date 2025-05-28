import asyncio
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
from config import AZURE_STORAGE_CONNECTION_STRING, BLOB_CONTAINER_NAME, AZURE_STORAGE_PUBLIC_URL, EMAIL_TO_FOLDER_MAPPING, EMAIL_SUBJECT_MAPPING

# Default mapping from email address to blob store folder
# If not defined in config.py, use the empty mapping
DEFAULT_EMAIL_TO_FOLDER_MAPPING = {}

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
        
async def process_template_images(template_content, template_folder):
    """
    Process the template to update image references to point to blob storage.
    
    Args:
        template_content (str): HTML template content
        template_folder (str): Folder name in blob storage for this template
        
    Returns:
        str: Updated template content with absolute image URLs
    """
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    
    if not template_content or not template_folder:
        return template_content
    
    try:
        # Parse HTML using BeautifulSoup with proper HTML parser
        soup = BeautifulSoup(template_content, 'html.parser')
        
        # Find all image tags
        img_tags = soup.find_all('img')
        
        # Base URL for images in blob storage - images are in the same folder as the template
        base_url = f"{AZURE_STORAGE_PUBLIC_URL}/{BLOB_CONTAINER_NAME}/{template_folder}"
        
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Processing {len(img_tags)} images with base URL: {base_url}")
        
        # Update image src attributes
        for img in img_tags:
            if img.get('src'):
                src = img['src']
                original_src = src
                
                # Check if already an absolute URL
                if src.startswith('http'):
                    continue
                
                # Replace backslashes with forward slashes
                src = src.replace('\\', '/')
                
                # If the source has a file structure with folders, extract just the filename
                # This handles Word HTML exports with references like "onlinesupport@brand.co.za_files/image001.png"
                if '_files/' in src:
                    img_filename = src.split('_files/')[-1]
                    # The images are in the same folder as the HTML file
                    absolute_url = f"{base_url}/{img_filename}"
                    img['src'] = absolute_url
                    print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Updated _files/ image: {original_src} -> {absolute_url}")
                elif '/' in src:
                    # For any other path with folders
                    img_filename = src.split('/')[-1]
                    absolute_url = f"{base_url}/{img_filename}"
                    img['src'] = absolute_url
                    print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Updated path image: {original_src} -> {absolute_url}")
                else:
                    # For simple filename references
                    absolute_url = f"{base_url}/{src}"
                    img['src'] = absolute_url
                    print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Updated simple image: {original_src} -> {absolute_url}")
                
        # Find all VML image references (used in Outlook HTML)
        vml_images = soup.find_all('v:imagedata')
        for vml_img in vml_images:
            if vml_img.get('src'):
                src = vml_img['src']
                original_src = src
                
                if not src.startswith('http'):
                    src = src.replace('\\', '/')
                    if '_files/' in src:
                        img_filename = src.split('_files/')[-1]
                        absolute_url = f"{base_url}/{img_filename}"
                        vml_img['src'] = absolute_url
                        print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Updated VML image: {original_src} -> {absolute_url}")
        
        # Find all background image references in inline styles
        elements_with_style = soup.find_all(lambda tag: tag.has_attr('style') and 'background-image' in tag['style'])
        
        for elem in elements_with_style:
            style = elem['style']
            original_style = style
            # Use regex to find and replace URL references
            url_matches = re.findall(r'url\([\'"]?([^\'"]+)[\'"]?\)', style)
            
            for url in url_matches:
                if url.startswith('http'):
                    # Skip if already absolute URL
                    continue
                    
                # Extract filename
                if '_files/' in url:
                    img_filename = url.split('_files/')[-1]
                    absolute_url = f"{base_url}/{img_filename}"
                    style = style.replace(f"url({url})", f"url({absolute_url})")
                elif '/' in url:
                    img_filename = url.split('/')[-1]
                    absolute_url = f"{base_url}/{img_filename}"
                    style = style.replace(f"url({url})", f"url({absolute_url})")
                else:
                    absolute_url = f"{base_url}/{url}"
                    style = style.replace(f"url({url})", f"url({absolute_url})")
            
            if style != original_style:
                elem['style'] = style
                print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Updated background image style")
        
        # Convert back to string
        return str(soup)
        
    except Exception as e:
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Error processing template images: {str(e)}")
        # Return original content if processing fails
        return template_content

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
        
        # Process image references to use absolute URLs for blob storage
        if template_folder:
            processed_content = await process_template_images(template_content, template_folder)
        else:
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
        
        # REMOVED: Customer name replacement per user requirement
        # The template should be taken as-is without name manipulation
        
        return processed_content
        
    except Exception as e:
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template - Error processing template: {str(e)}")
        return template_content  # Return original content if processing fails

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

async def send_autoresponse(account, sender_email, email_subject, email_data):
    """
    Send an autoresponse email to the sender.
    
    Args:
        account (str): Email account to send from
        sender_email (str): Email address to send autoresponse to
        email_subject (str): Original email subject
        email_data (dict): Original email data
        
    Returns:
        bool: True if successful, False otherwise
    """
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        # Skip autoresponse if sender email is empty or appears to be a system address
        if not sender_email or any(system_domain in sender_email.lower() for system_domain in ['noreply', 'no-reply', 'donotreply', 'mailer-daemon']):
            print(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Skipping autoresponse to system address: {sender_email}")
            return False
            
        # Get access token for Microsoft Graph API
        access_token = await get_access_token()
        if not access_token:
            print(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Failed to obtain access token for autoresponse")
            return False
        
        # Get the recipient email (where the original email was sent to)
        recipient_email = email_data.get('to', '').split(',')[0].strip()
        
        # Get template from Azure Blob Storage
        template_content, template_folder = await get_template_from_blob(recipient_email)
        
        # If no template found, use a default template
        if not template_content:
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
            template_folder = None
        
        # Process the template to replace variables and update image references
        # NO content manipulation - preserve original encoding
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
        return False
