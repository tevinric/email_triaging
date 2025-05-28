import asyncio
import datetime
import os
import re
import uuid
import aiohttp
from bs4 import BeautifulSoup
from azure.storage.blob.aio import BlobServiceClient
from email_processor.email_client import get_access_token
from config import AZURE_STORAGE_CONNECTION_STRING, BLOB_CONTAINER_NAME, AZURE_STORAGE_PUBLIC_URL, EMAIL_TO_FOLDER_MAPPING

# Default mapping from email address to blob store folder
# If not defined in config.py, use the empty mapping
DEFAULT_EMAIL_TO_FOLDER_MAPPING = {}

async def get_template_from_blob(recipient_email):
    """
    Retrieve template from Azure Blob Storage based on recipient email.
    
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
            # Download blob content
            download_stream = await blob_client.download_blob()
            template_content = await download_stream.readall()
            return template_content.decode('utf-8'), folder_name
        else:
            # Try fallback to html extension
            alt_template_path = f"{folder_name}/{mailbox_name}@{domain}.html"
            blob_client = container_client.get_blob_client(alt_template_path)
            
            if await blob_client.exists():
                download_stream = await blob_client.download_blob()
                template_content = await download_stream.readall()
                return template_content.decode('utf-8'), folder_name
            else:
                # Try one more fallback to a simple named file
                simple_template_path = f"{folder_name}/{folder_name}.html"
                blob_client = container_client.get_blob_client(simple_template_path)
                
                if await blob_client.exists():
                    download_stream = await blob_client.download_blob()
                    template_content = await download_stream.readall()
                    return template_content.decode('utf-8'), folder_name
                else:
                    print(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Template not found in blob storage for folder: {folder_name}")
                    # Return None
                    return None, None
            
    except Exception as e:
        print(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Error retrieving template from blob storage: {str(e)}")
        return None, None
        
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
        # Parse HTML using BeautifulSoup
        soup = BeautifulSoup(template_content, 'html.parser')
        
        # Find all image tags
        img_tags = soup.find_all('img')
        
        # Base URL for images in blob storage - images are in the same folder as the template
        base_url = f"{AZURE_STORAGE_PUBLIC_URL}/{BLOB_CONTAINER_NAME}/{template_folder}"
        
        # Update image src attributes
        for img in img_tags:
            if img.get('src'):
                src = img['src']
                
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
                elif '/' in src:
                    # For any other path with folders
                    img_filename = src.split('/')[-1]
                    absolute_url = f"{base_url}/{img_filename}"
                    img['src'] = absolute_url
                else:
                    # For simple filename references
                    absolute_url = f"{base_url}/{src}"
                    img['src'] = absolute_url
                
        # Find all background image references in inline styles
        elements_with_style = soup.find_all(lambda tag: tag.has_attr('style') and 'background-image' in tag['style'])
        
        for elem in elements_with_style:
            style = elem['style']
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
            
            elem['style'] = style
        
        # Convert back to string
        return str(soup)
        
    except Exception as e:
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Error processing template images: {str(e)}")
        # Return original content if processing fails
        return template_content

async def process_template(template_content, template_folder, email_data):
    """
    Process the template by replacing variables with actual values and updating image references.
    
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
            template_content = await process_template_images(template_content, template_folder)
        
        # Generate a reference ID (could be based on the email ID or a UUID)
        reference_id = email_data.get('internet_message_id', '')
        if not reference_id:
            reference_id = str(uuid.uuid4())
        
        # Truncate if too long - take last 10 characters
        if len(reference_id) > 10:
            reference_id = reference_id[-10:]
        
        # Replace variables in the template
        processed_content = template_content.replace('{{REFERENCE_ID}}', reference_id)
        
        # Replace any dynamic variables with customer data
        customer_name = email_data.get('from', '').split('@')[0].capitalize()
        processed_content = processed_content.replace('Dear brand Customer', f'Dear {customer_name}')
        
        return processed_content
        
    except Exception as e:
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template - Error processing template: {str(e)}")
        return template_content  # Return original content if processing fails

async def send_email(access_token, account, to_email, subject, body_html, body_text):
    """
    Send a new email using Microsoft Graph API.
    
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
    
    # Implement retry logic similar to other functions
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, headers=headers, json=message_body) as response:
                    if response.status == 202:  # 202 Accepted indicates success for sendMail
                        print(f">> {timestamp} Script: autoresponse.py - Function: send_email - Email sent successfully to {to_email}")
                        return True
                    else:
                        print(f">> {timestamp} Script: autoresponse.py - Function: send_email - Failed to send email: {response.status}")
                        response_text = await response.text()
                        print(f"Response: {response_text}")
                        
                        # Don't retry for certain status codes
                        if response.status in [401, 403]:
                            print(f">> {timestamp} Script: autoresponse.py - Function: send_email - Authentication error. Not retrying.")
                            return False
        except Exception as e:
            print(f">> {timestamp} Script: autoresponse.py - Function: send_email - Error sending email: {str(e)}")
        
        # Implement exponential backoff
        if attempt < max_retries - 1:
            backoff_time = 2 ** attempt
            print(f">> {timestamp} Script: autoresponse.py - Function: send_email - Retrying in {backoff_time} seconds (attempt {attempt + 1}/{max_retries})...")
            await asyncio.sleep(backoff_time)
    
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
        
        # Process the template to replace variables and update image references
        processed_template = await process_template(template_content, template_folder, email_data)
        
        # Create subject line for autoresponse
        subject = f"Re: {email_subject}"
        
        # Extract plain text version from HTML (simplified - in production you'd want a better HTML to text converter)
        plain_text = "Thank you for your email. We have received your message and will respond as soon as possible. This is an automated response. Please do not reply to this email."
        
        # Send the email
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
