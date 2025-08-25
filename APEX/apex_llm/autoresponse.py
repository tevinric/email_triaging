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
from apex_llm.apex_logging import email_log  # Import email_log for system logging
from config import (
    AZURE_STORAGE_CONNECTION_STRING, 
    BLOB_CONTAINER_NAME, 
    AZURE_STORAGE_PUBLIC_URL, 
    EMAIL_TO_FOLDER_MAPPING, 
    EMAIL_SUBJECT_MAPPING,
    EMAIL_ACCOUNTS  # Added import for loop prevention
)

# Default mapping from email address to blob store folder
# If not defined in config.py, use the empty mapping
DEFAULT_EMAIL_TO_FOLDER_MAPPING = {}

def should_skip_autoresponse(recipient_email, sender_email, subject=None, email_body=None):
    """
    Determine if autoresponse should be skipped to prevent infinite loops.
    Enhanced with comprehensive bounce/error message detection.
    
    IMPORTANT: This function assumes that the account processing emails (recipient_email) is the same account that sends autoresponses. This should be the case as the consolidation bin is used to send the autoresponses.
    
    Args:
        recipient_email (str): Email address where the original email was sent to
        sender_email (str): Email address of the original sender
        subject (str): Email subject line (optional but recommended)
        email_body (str): Email body content (optional but recommended)
        
    Returns:
        tuple: (should_skip: bool, reason: str) - True if autoresponse should be skipped
    """
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    
    
    ## IF any of the following loop check conditions are met, we return True to skip the autoresponse.
    try:
        email_log(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - Starting autoresponse loop prevention analysis")
        email_log(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - Recipient: {recipient_email}, Sender: {sender_email}, Subject: {subject}")
        
        # 1. BASIC VALIDATION - Skip if sender email is empty - Not likely to happen but worthwhile checking - SEE UT 1 
        if not sender_email or sender_email==None or sender_email=='' or len(sender_email.strip())<5:
            reason = "No sender email found"
            email_log(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - SKIPPING: {reason}")
            return True, reason
        
        # 2. BASIC VALIDATION - Skip if no recipient email - Not likely to happen but worthwhile checking
        if not recipient_email or recipient_email==None or recipient_email=='' or len(recipient_email.strip())<5:
            reason = "No recipient email found"
            email_log(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - SKIPPING: {reason}")
            return True, reason
        
        # Clean up email addresses for comparison - push to lower case and strip whitespace
        sender_clean = sender_email.lower().strip()
        recipient_clean = recipient_email.lower().strip()
        
        # DEBUG LOGGING - Added comprehensive logging for troubleshooting
        email_log(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - "
              f"ANALYZING: FROM='{sender_email}' TO='{recipient_email}' SUBJECT='{subject}'")
        email_log(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - "
              f"EMAIL_ACCOUNTS: {EMAIL_ACCOUNTS}")
        
        # 3. PRIMARY LOOP PREVENTION - Skip if email was sent TO any autoresponse account
        # This should catch emails sent directly to autoresponse account - We should not send autoresponses since the customer should not be sending mails directly to the autoresponse account 
        if EMAIL_ACCOUNTS:
            for account in EMAIL_ACCOUNTS:
                if account:
                    account_clean = account.lower().strip()
                    email_log(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - "
                          f"COMPARING recipient '{recipient_clean}' with account '{account_clean}'")

                    # CHECKING -> Was the email sent to the autoresponse account/ consolidation bin?
                    if recipient_clean == account_clean:
                        reason = f"Email sent directly to autoresponse account: {recipient_email}"
                        email_log(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - SKIPPING: {reason}")
                        return True, reason
        
        # 4. SECONDARY LOOP PREVENTION - Skip if sender is also an autoresponse account. Prevention againt self initiatied loops
        if EMAIL_ACCOUNTS:
            for account in EMAIL_ACCOUNTS:
                if account:
                    account_clean = account.lower().strip()
                    if sender_clean == account_clean:
                        reason = f"Sender is also an autoresponse account: {sender_email}"
                        email_log(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - SKIPPING: {reason}")
                        return True, reason
        
        # 5. MICROSOFT EXCHANGE SYSTEM DETECTION - Primary defense against bounce loops
        # Microsoft Exchange generates addresses like: MicrosoftExchange329e71ec88ae4615bbc36ab6ce41109e@company.co.za
        exchange_patterns = [
            r'microsoftexchange[a-f0-9]+@',  # Standard Exchange pattern
            r'exchange[a-f0-9]+@',          # Alternative Exchange pattern
            r'[a-f0-9]{32}@'                # Generic 32-character hex @ domain
        ]
        
        for pattern in exchange_patterns:
            if re.search(pattern, sender_clean):
                reason = f"Microsoft Exchange system sender detected: {sender_email} (matches pattern '{pattern}')"
                email_log(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - SKIPPING: {reason}")
                return True, reason
        
        
        ## 6. ADDED NEW CHECK AFTER DISCUSSION WITH INFRASTRUCTURE TEAM (LEO)
        # If the sender clean email address contains both 'microsoftexchange' and 'telesure.co.za', we skip the autoresponse.
        if "microsoftexchange" in sender_clean and "telesure.co.za" in sender_clean:
            reason = "Sender is Microsoft Exchange system at telesure.co.za"
            email_log(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - SKIPPING: {reason}")
            return True, reason
        
        
        # 7. SYSTEM ADDRESS DETECTION - Enhanced list including Exchange-specific terms
        system_indicators = [
            'noreply', 'no-reply', 'donotreply', 'do-not-reply',
            'mailer-daemon', 'postmaster', 'daemon', 'mail-daemon',
            'microsoftexchange', 'exchange', 'outlook-com', 
            'auto-reply', 'autoreply', 'bounce', 'delivery',
            'system', 'noresponse', 'no-response'
        ]
        
        # Check if sender contains any system indicators
        for indicator in system_indicators:
            if indicator in sender_clean:
                reason = f"System/automated sender detected: {sender_email} (contains '{indicator}')"
                email_log(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - SKIPPING: {reason}")
                return True, reason
        
        # 8. SUBJECT LINE ANALYSIS - Check for bounce/error indicators
        if subject:
            subject_clean = subject.lower().strip()
            bounce_subject_indicators = [
                'undeliverable', 'undelivered', 'delivery status notification', 
                'delivery failure', 'mail delivery failed', 'returned mail', 
                'bounce notification', 'message not delivered', 'delivery report', 
                'non-delivery report', 'ndr', 'mail delivery subsystem', 
                'postmaster notification', 'auto-reply', 'automatic reply', 
                'out of office', 'mailbox full', 'user unknown', 
                'address not found', 'relay access denied', 'message blocked',
                'delivery incomplete', 'message rejected', 'smtp error'
            ]
            
            for indicator in bounce_subject_indicators:
                if indicator in subject_clean:
                    reason = f"Bounce/error message detected in subject: '{subject}' (contains '{indicator}')"
                    email_log(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - SKIPPING: {reason}")
                    return True, reason
            
            # Special check for subjects that start with common bounce prefixes
            bounce_prefixes = ['undeliverable:', 'delivery failure:', 'returned mail:', 'ndr:']
            for prefix in bounce_prefixes:
                if subject_clean.startswith(prefix):
                    reason = f"Bounce message detected by subject prefix: '{subject}' (starts with '{prefix}')"
                    email_log(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - SKIPPING: {reason}")
                    return True, reason
        
        # 9. EMAIL BODY ANALYSIS - Check for common bounce message content
        if email_body:
            body_clean = email_body.lower().strip()
            bounce_body_indicators = [
                'rejected your message', 'message could not be delivered',
                'recipient mailbox is full', 'user is over quota',
                'address not found', 'user unknown', 'mailbox unavailable',
                'delivery failed', 'permanent failure', 'temporary failure',
                'bounce message', 'non-delivery report', 'postmaster',
                'mail delivery subsystem', 'delivery status notification',
                'smtp error', 'relay access denied', 'message blocked',
                'mailbox does not exist', 'invalid recipient'
            ]
            
            for indicator in bounce_body_indicators:
                if indicator in body_clean:
                    reason = f"Bounce/error message detected in body content (contains '{indicator}')"
                    email_log(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - SKIPPING: {reason}")
                    return True, reason
        
        # 10. AUTORESPONSE LOOP DETECTION - Check for existing autoresponse indicators
        if subject:
            subject_clean = subject.lower().strip()
            autoresponse_indicators = [
                'thank you for contacting us', 'auto response', 'automatic response',
                'we have received your email', 'automated reply', 'auto-reply',
            ]
            
            for indicator in autoresponse_indicators:
                if indicator in subject_clean:
                    reason = f"Potential autoresponse loop detected in subject: '{subject}' (contains '{indicator}')"
                    email_log(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - SKIPPING: {reason}")
                    return True, reason
        
        # 11. DOMAIN-BASED SUSPICIOUS PATTERN DETECTION
        if '@' in sender_email:
            sender_domain = sender_email.split('@')[1].lower()
            recipient_domain = recipient_email.split('@')[1].lower() if '@' in recipient_email else ''
            
            # Check for internal system communications (same domain, system-like sender)
            if sender_domain == recipient_domain:
                # If it's the same domain and has system characteristics, be extra cautious
                if any(indicator in sender_clean for indicator in ['exchange', 'system', 'daemon', 'admin']):
                    reason = f"Internal system communication detected: {sender_email} to {recipient_email}"
                    email_log(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - SKIPPING: {reason}")
                    return True, reason
        
        # 12. DEBUGGING LOG - Always log what we're allowing for troubleshooting
        email_log(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - "
              f"ALLOWING autoresponse: FROM={sender_email} TO={recipient_email} SUBJECT='{subject}'")
        
        return False, "Autoresponse allowed"
        
    except Exception as e:
        # If there's any error in the analysis, err on the side of caution and skip autoresponse
        error_msg = f"Error in autoresponse analysis: {str(e)}"
        email_log(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - ERROR: {error_msg}")
        return True, error_msg

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
        email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Starting template retrieval for {recipient_email}")
        
        # Extract the mailbox name and domain from the email address
        email_parts = recipient_email.lower().split('@')
        mailbox_name = email_parts[0]
        domain = email_parts[1] if len(email_parts) > 1 else 'company.co.za'  # Default domain if not present
        
        email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Extracted mailbox: {mailbox_name}, domain: {domain}")
        
        # Check if we have a custom folder mapping for this email address
        folder_name = None
        
        # Try to match the full email address first
        if recipient_email.lower() in EMAIL_TO_FOLDER_MAPPING:
            folder_name = EMAIL_TO_FOLDER_MAPPING[recipient_email.lower()]
            email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Using custom folder mapping for {recipient_email}: {folder_name}")
        # Then try to match just the mailbox part
        elif mailbox_name in EMAIL_TO_FOLDER_MAPPING:
            folder_name = EMAIL_TO_FOLDER_MAPPING[mailbox_name]
            email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Using custom folder mapping for {mailbox_name}: {folder_name}")
        # If no mapping found, use the mailbox name as before
        else:
            folder_name = mailbox_name
            email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - No custom mapping found, using mailbox name: {folder_name}")
        
        # Template file is in the folder with the same name as specified in the mapping
        # Use the domain from the email instead of hardcoding 'mail.co.za'
        template_path = f"{folder_name}/{mailbox_name}@{domain}.htm"
        
        email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Retrieving template from path: {template_path}")
        
        # Create BlobServiceClient
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        
        # Get container client
        container_client = blob_service_client.get_container_client(BLOB_CONTAINER_NAME)
        
        # Get blob client
        blob_client = container_client.get_blob_client(template_path)
        
        # Check if blob exists
        if await blob_client.exists():
            email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Template found at primary path: {template_path}")
            # Download blob content - let's try to preserve original encoding
            download_stream = await blob_client.download_blob()
            template_content_bytes = await download_stream.readall()
            
            # Try UTF-8 first, then fall back to Windows-1252 (common for Word HTML)
            try:
                template_content = template_content_bytes.decode('utf-8')
                email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Successfully decoded with UTF-8")
            except UnicodeDecodeError:
                try:
                    template_content = template_content_bytes.decode('windows-1252')
                    email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Successfully decoded with Windows-1252")
                except UnicodeDecodeError:
                    # Final fallback
                    template_content = template_content_bytes.decode('utf-8', errors='replace')
                    email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Used UTF-8 with error replacement")
            
            return template_content, folder_name
        else:
            # Try fallback to html extension
            alt_template_path = f"{folder_name}/{mailbox_name}@{domain}.html"
            email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Primary template not found, trying alternative path: {alt_template_path}")
            blob_client = container_client.get_blob_client(alt_template_path)
            
            if await blob_client.exists():
                email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Template found at alternative path: {alt_template_path}")
                download_stream = await blob_client.download_blob()  
                template_content_bytes = await download_stream.readall()
                
                # Apply same encoding handling
                try:
                    template_content = template_content_bytes.decode('utf-8')
                    email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Successfully decoded alternative template with UTF-8")
                except UnicodeDecodeError:
                    try:
                        template_content = template_content_bytes.decode('windows-1252')
                        email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Successfully decoded alternative template with Windows-1252")
                    except UnicodeDecodeError:
                        template_content = template_content_bytes.decode('utf-8', errors='replace')
                        email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Used UTF-8 with error replacement for alternative template")
                
                return template_content, folder_name
            else:
                # Try one more fallback to a simple named file
                simple_template_path = f"{folder_name}/{folder_name}.html"
                email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Alternative template not found, trying simple path: {simple_template_path}")
                blob_client = container_client.get_blob_client(simple_template_path)
                
                if await blob_client.exists():
                    email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Template found at simple path: {simple_template_path}")
                    download_stream = await blob_client.download_blob()
                    template_content_bytes = await download_stream.readall()
                    
                    # Apply same encoding handling
                    try:
                        template_content = template_content_bytes.decode('utf-8')
                        email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Successfully decoded simple template with UTF-8")
                    except UnicodeDecodeError:
                        try:
                            template_content = template_content_bytes.decode('windows-1252')
                            email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Successfully decoded simple template with Windows-1252")
                        except UnicodeDecodeError:
                            template_content = template_content_bytes.decode('utf-8', errors='replace')
                            email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Used UTF-8 with error replacement for simple template")
                    
                    return template_content, folder_name
                else:
                    email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - WARNING: Template not found in blob storage for folder: {folder_name}")
                    return None, None
            
    except Exception as e:
        email_log(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - ERROR: Error retrieving template from blob storage: {str(e)}")
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
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        # Get custom subject line from mapping, or use default
        if template_folder and template_folder in EMAIL_SUBJECT_MAPPING:
            subject_line = EMAIL_SUBJECT_MAPPING[template_folder]
            email_log(f">> {timestamp} Script: autoresponse.py - Function: get_subject_line_for_template - Using custom subject for {template_folder}: {subject_line}")
            return subject_line
        else:
            default_subject = EMAIL_SUBJECT_MAPPING.get("default", "Thank you for contacting us")
            email_log(f">> {timestamp} Script: autoresponse.py - Function: get_subject_line_for_template - Using default subject for {template_folder}: {default_subject}")
            return default_subject
    except Exception as e:
        error_msg = f"Error getting subject line for template {template_folder}: {str(e)}"
        email_log(f">> {timestamp} Script: autoresponse.py - Function: get_subject_line_for_template - ERROR: {error_msg}")
        return "Thank you for contacting us"

async def validate_blob_storage_config():
    """
    Validate that blob storage configuration is properly set up.
    
    Returns:
        bool: True if configuration is valid, False otherwise
    """
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    
    email_log(f">> {timestamp} Script: autoresponse.py - Function: validate_blob_storage_config - Validating blob storage configuration")
    
    if not AZURE_STORAGE_CONNECTION_STRING:
        email_log(f">> {timestamp} Script: autoresponse.py - Function: validate_blob_storage_config - ERROR: AZURE_STORAGE_CONNECTION_STRING is not configured")
        return False
    
    if not BLOB_CONTAINER_NAME:
        email_log(f">> {timestamp} Script: autoresponse.py - Function: validate_blob_storage_config - ERROR: BLOB_CONTAINER_NAME is not configured")
        return False
    
    if not AZURE_STORAGE_PUBLIC_URL:
        email_log(f">> {timestamp} Script: autoresponse.py - Function: validate_blob_storage_config - ERROR: AZURE_STORAGE_PUBLIC_URL is not configured")
        return False
    
    email_log(f">> {timestamp} Script: autoresponse.py - Function: validate_blob_storage_config - Blob storage configuration validated successfully")
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
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        image_path = f"{template_folder}/{image_filename}"
        blob_client = blob_container_client.get_blob_client(image_path)
        exists = await blob_client.exists()
        email_log(f">> {timestamp} Script: autoresponse.py - Function: check_image_exists_in_blob - Image {image_path} exists: {exists}")
        return exists
    except Exception as e:
        email_log(f">> {timestamp} Script: autoresponse.py - Function: check_image_exists_in_blob - ERROR: Error checking if image exists in blob: {str(e)}")
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
        email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - WARNING: Missing template content or folder")
        return template_content
    
    email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Starting image processing for template folder: {template_folder}")
    
    # Validate blob storage configuration
    if not await validate_blob_storage_config():
        email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - ERROR: Blob storage configuration invalid")
        return template_content
    
    try:
        # Parse HTML using BeautifulSoup with proper HTML parser
        soup = BeautifulSoup(template_content, 'html.parser')
        
        # Base URL for images in blob storage - images are in the same folder as the template
        base_url = f"{AZURE_STORAGE_PUBLIC_URL.rstrip('/')}/{BLOB_CONTAINER_NAME}/{template_folder}"
        
        email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Processing images with base URL: {base_url}")
        
        # Create blob container client for validation (optional - can be disabled for performance)
        container_client = None
        try:
            blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
            container_client = blob_service_client.get_container_client(BLOB_CONTAINER_NAME)
            email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Blob container client created successfully")
        except Exception as e:
            email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - WARNING: Error creating blob client for validation: {str(e)}")
        
        # Track processed images for debugging
        processed_images = []
        
        # Find and process all img tags
        img_tags = soup.find_all('img')
        email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Found {len(img_tags)} img tags")
        
        for img in img_tags:
            if img.get('src'):
                original_src = img['src']
                
                # Skip if already an absolute URL
                if original_src.startswith('http'):
                    email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Skipping absolute URL: {original_src}")
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
                                email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - WARNING: Image not found in blob storage: {img_filename}")
                        except Exception as check_error:
                            email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - ERROR: Error checking image existence: {str(check_error)}")
                    
                    # Update the src attribute
                    img['src'] = absolute_url
                    processed_images.append({
                        'original': original_src,
                        'filename': img_filename,
                        'absolute_url': absolute_url
                    })
                    
                    email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Updated img src: {original_src} -> {absolute_url}")
        
        # Find and process VML imagedata tags (used in Outlook HTML)
        vml_images = soup.find_all('v:imagedata')
        email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Found {len(vml_images)} VML imagedata tags")
        
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
                        email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Updated VML imagedata src: {original_src} -> {absolute_url}")
        
        # Find and process background images in inline styles
        elements_with_style = soup.find_all(lambda tag: tag.has_attr('style') and 'background-image' in tag['style'])
        email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Found {len(elements_with_style)} elements with background-image styles")
        
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
                email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Updated background image style")
        
        # Summary logging
        email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Processed {len(processed_images)} images successfully")
        
        # Convert back to string and return
        processed_html = str(soup)
        
        # Additional validation - check if we actually made changes
        if processed_html == template_content:
            email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - WARNING: No changes were made to template")
        else:
            email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Template successfully updated with blob storage URLs")
        
        return processed_html
        
    except Exception as e:
        email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - ERROR: Error processing template images: {str(e)}")
        import traceback
        email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Traceback: {traceback.format_exc()}")
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
            email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template - WARNING: No template content provided")
            return template_content
        
        email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template - Starting template processing")
        
        # Process image references to use absolute URLs for blob storage - THIS IS THE KEY STEP
        if template_folder:
            email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template - Starting image processing for folder: {template_folder}")
            processed_content = await process_template_images(template_content, template_folder)
        else:
            email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template - No template folder provided, skipping image processing")
            processed_content = template_content
        
        # Generate a reference ID (could be based on the email ID or a UUID)
        reference_id = email_data.get('internet_message_id', '')
        if not reference_id:
            reference_id = str(uuid.uuid4())
        
        # Truncate if too long - take last 10 characters
        if len(reference_id) > 10:
            reference_id = reference_id[-10:]
        
        email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template - Using reference ID: {reference_id}")
        
        # Replace variables in the template - ONLY the reference ID placeholder
        processed_content = processed_content.replace('{{REFERENCE_ID}}', reference_id)
        
        # Log completion
        email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template - Template processing completed successfully")
        
        return processed_content
        
    except Exception as e:
        email_log(f">> {timestamp} Script: autoresponse.py - Function: process_template - ERROR: Error processing template: {str(e)}")
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
        email_log(f">> {timestamp} Script: autoresponse.py - Function: send_email - Starting email send process")
        email_log(f">> {timestamp} Script: autoresponse.py - Function: send_email - From: {account}, To: {to_email}, Subject: {subject}")
        
        # Method 1: Try sending with proper charset and encoding headers
        success = await _send_email_with_charset(access_token, account, to_email, subject, body_html, body_text, timestamp)
        if success:
            email_log(f">> {timestamp} Script: autoresponse.py - Function: send_email - Email sent successfully using charset method")
            return True
        
        # Method 2: If that fails, try with base64 encoding
        email_log(f">> {timestamp} Script: autoresponse.py - Function: send_email - First method failed, trying base64 encoding")
        success = await _send_email_with_base64(access_token, account, to_email, subject, body_html, body_text, timestamp)
        if success:
            email_log(f">> {timestamp} Script: autoresponse.py - Function: send_email - Email sent successfully using base64 method")
        else:
            email_log(f">> {timestamp} Script: autoresponse.py - Function: send_email - ERROR: All email sending methods failed")
        return success
        
    except Exception as e:
        email_log(f">> {timestamp} Script: autoresponse.py - Function: send_email - ERROR: Error in send_email: {str(e)}")
        return False

async def _send_email_with_charset(access_token, account, to_email, subject, body_html, body_text, timestamp):
    """
    First attempt: Send email with proper charset declarations and headers.
    """
    try:
        email_log(f">> {timestamp} Script: autoresponse.py - Function: _send_email_with_charset - Attempting to send with charset method")
        
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
                email_log(f">> {timestamp} Script: autoresponse.py - Function: _send_email_with_charset - Added HTML structure with charset")
            elif not '<meta charset=' in body_html.lower() and not 'content-type' in body_html.lower():
                # Add charset to existing HTML
                if '<head>' in body_html.lower():
                    head_pos = body_html.lower().find('<head>') + 6
                    charset_meta = '\n<meta charset="UTF-8">\n<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">\n'
                    body_html = body_html[:head_pos] + charset_meta + body_html[head_pos:]
                    email_log(f">> {timestamp} Script: autoresponse.py - Function: _send_email_with_charset - Added charset meta tags to existing HTML")
        
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
                    email_log(f">> {timestamp} Script: autoresponse.py - Function: _send_email_with_charset - Email sent successfully")
                    return True
                else:
                    response_text = await response.text()
                    email_log(f">> {timestamp} Script: autoresponse.py - Function: _send_email_with_charset - ERROR: Failed with status {response.status}: {response_text}")
                    return False
    
    except Exception as e:
        email_log(f">> {timestamp} Script: autoresponse.py - Function: _send_email_with_charset - ERROR: Exception: {str(e)}")
        return False

async def _send_email_with_base64(access_token, account, to_email, subject, body_html, body_text, timestamp):
    """
    Second attempt: Send email with base64 encoded content to preserve encoding.
    """
    try:
        email_log(f">> {timestamp} Script: autoresponse.py - Function: _send_email_with_base64 - Attempting to send with base64 encoding")
        
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
                    email_log(f">> {timestamp} Script: autoresponse.py - Function: _send_email_with_base64 - Email sent successfully with base64")
                    return True
                else:
                    response_text = await response.text()
                    email_log(f">> {timestamp} Script: autoresponse.py - Function: _send_email_with_base64 - ERROR: Failed with status {response.status}: {response_text}")
                    
                    # If base64 approach failed, try without the isBase64 flag
                    return await _send_email_fallback(access_token, account, to_email, subject, body_html, body_text, timestamp)
    
    except Exception as e:
        email_log(f">> {timestamp} Script: autoresponse.py - Function: _send_email_with_base64 - ERROR: Exception: {str(e)}")
        return False

async def _send_email_fallback(access_token, account, to_email, subject, body_html, body_text, timestamp):
    """
    Final fallback: Send with minimal processing.
    """
    try:
        email_log(f">> {timestamp} Script: autoresponse.py - Function: _send_email_fallback - Attempting fallback email send method")
        
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
                    email_log(f">> {timestamp} Script: autoresponse.py - Function: _send_email_fallback - Email sent successfully with fallback method")
                    return True
                else:
                    response_text = await response.text()
                    email_log(f">> {timestamp} Script: autoresponse.py - Function: _send_email_fallback - ERROR: Final fallback failed with status {response.status}: {response_text}")
                    return False
    
    except Exception as e:
        email_log(f">> {timestamp} Script: autoresponse.py - Function: _send_email_fallback - ERROR: Exception: {str(e)}")
        return False

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
        email_log(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Starting autoresponse process")
        email_log(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Account: {account}, Sender: {sender_email}, Subject: {email_subject}")
        
        # Get the recipient email (where the original email was sent to)
        recipient_email = email_data.get('to', '').split(',')[0].strip()
        
        # Get email body for enhanced analysis
        email_body = email_data.get('body_text', '') or email_data.get('body_html', '')
        
        # DEBUG LOGGING - Log what we're about to check
        email_log(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - "
              f"CHECKING autoresponse eligibility: ACCOUNT={account} SENDER={sender_email} "
              f"RECIPIENT={recipient_email} SUBJECT='{email_subject}'")
        
        # ENHANCED LOOP PREVENTION: Check if we should skip sending autoresponse
        should_skip, skip_reason = should_skip_autoresponse(
            recipient_email, 
            sender_email, 
            email_subject, 
            email_body
        )
        
        if should_skip:
            email_log(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - "
                  f"SKIPPING autoresponse: {skip_reason}")
            return False  # Return False to indicate no autoresponse was sent (not an error)
        
        email_log(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - "
              f"Autoresponse allowed, proceeding to send...")
            
        # Continue with existing autoresponse logic...
        # Get access token for Microsoft Graph API
        email_log(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Obtaining access token")
        access_token = await get_access_token()
        if not access_token:
            email_log(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - ERROR: Failed to obtain access token for autoresponse")
            return False
        
        email_log(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Access token obtained successfully")
        
        # Get template from Azure Blob Storage
        email_log(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Retrieving template from blob storage")
        template_content, template_folder = await get_template_from_blob(recipient_email)
        
        # If no template found, use a default template
        if not template_content:
            email_log(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - No template found for {recipient_email}, using default template")
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
                    
                    <p>Good day,</p>
                    <br>
                    <p>Welcome to Auto&General where you are always serviced right.</p>
                    <br>
                    <p>Thank you for reaching out to us. One of our dedicated consultants from the Services team will be in contact with you during operating hours within the next business day.</p>
                    <br> 
                    <p>Can’t wait till then? Download the A&G app now and get access to your policy 24/7.</p>
                    <br>
                    <p>Please do not reply to this e-mail as it is an automated response.</p>
                    <br>
                    <p>Regards,</p>
                    <p>The Auto&General Team</p>
                    
                                        
                    <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #dddddd; font-size: 12px; color: #666666;">
                        <p>This is an automated response. Please do not reply to this email.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            template_folder = None  # No folder for default template
        else:
            email_log(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Template found and loaded from folder: {template_folder}")
        
        # Process the template to replace variables and update image references
        email_log(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Processing template")
        processed_template = await process_template(template_content, template_folder, email_data)
        
        # Create subject line for autoresponse using the new mapping
        subject = get_subject_line_for_template(template_folder, email_subject)
        
        email_log(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Using subject line: {subject} for template: {template_folder}")
        
        # Extract plain text version from HTML (simplified)
        plain_text = "Thank you for your email. We have received your message and will respond as soon as possible. This is an automated response. Please do not reply to this email."
        
        # Send the email with enhanced encoding handling
        email_log(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Sending autoresponse to {sender_email}")
        result = await send_email(
            access_token,
            account,
            sender_email,
            subject,
            processed_template,
            plain_text
        )
        
        if result:
            email_log(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - SUCCESS: Autoresponse sent successfully to {sender_email}")
            return True
        else:
            email_log(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - ERROR: Failed to send autoresponse to {sender_email}")
            return False
            
    except Exception as e:
        email_log(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - ERROR: Error sending autoresponse: {str(e)}")
        import traceback
        email_log(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - ERROR: Traceback: {traceback.format_exc()}")
        return False
