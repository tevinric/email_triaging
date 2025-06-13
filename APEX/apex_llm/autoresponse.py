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

# Default time window for loop protection (in hours)
DEFAULT_LOOP_PROTECTION_WINDOW = 24

# Default maximum number of messages in the window before suppressing
DEFAULT_MAX_MESSAGES_IN_WINDOW = 1

class AutoResponseLoopProtection:
    """
    Enhanced loop protection for autoresponses that uses a time-based window
    to prevent sending multiple autoresponses to the same sender within a 
    configurable time period.
    """
    
    def __init__(self, time_window_hours=DEFAULT_LOOP_PROTECTION_WINDOW, max_messages=DEFAULT_MAX_MESSAGES_IN_WINDOW):
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
        print(f">> {timestamp} AutoResponseLoopProtection initialized with {time_window_hours}h window, {max_messages} max messages")
    
    async def should_skip_autoresponse(self, recipient_email, sender_email, subject=None, email_body=None):
        """
        Determine if autoresponse should be skipped based on enhanced rules:
        1. Basic system message detection (from existing implementation)
        2. Time-based loop protection using SQL database check
        
        Args:
            recipient_email (str): Email address where the original email was sent to
            sender_email (str): Email address of the original sender
            subject (str): Email subject line (optional but recommended)
            email_body (str): Email body content (optional but recommended)
            
        Returns:
            tuple: (should_skip: bool, reason: str) - True if autoresponse should be skipped
        """
        timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
        
        # STEP 1: Run the existing system message detection first (fast and efficient first check)
        system_check_result, system_check_reason = await self._check_for_system_message(
            recipient_email, sender_email, subject, email_body
        )
        
        if system_check_result:
            print(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - "
                  f"SKIPPING (system check): {system_check_reason}")
            return True, system_check_reason
        
        # STEP 2: Time-based loop protection - check database for recent messages from same sender
        try:
            if not sender_email:
                return True, "No sender email found"
            
            # Clean up email address for database check
            sender_clean = sender_email.lower().strip()
            
            # Check if we've already sent an autoresponse to this sender within the time window
            recent_responses = await self._check_recent_responses(sender_clean)
            
            if recent_responses >= self.max_messages:
                reason = f"Already sent {recent_responses} autoresponses to {sender_email} within last {self.time_window_hours} hours"
                print(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - "
                      f"SKIPPING (time window): {reason}")
                return True, reason
            
            print(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - "
                  f"ALLOWING autoresponse: No recent responses to {sender_email} within time window")
            return False, "Autoresponse allowed - no recent responses within time window"
            
        except Exception as e:
            # If there's any error in the analysis, log it but don't skip the autoresponse
            # This ensures we don't accidentally block legitimate autoresponses due to errors
            error_msg = f"Error in time-based loop protection: {str(e)}"
            print(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - WARNING: {error_msg}")
            print(f">> {timestamp} Script: autoresponse.py - Function: should_skip_autoresponse - "
                  f"Allowing autoresponse despite error (fail open)")
            return False, "Autoresponse allowed despite error (fail open)"
    
    async def _check_for_system_message(self, recipient_email, sender_email, subject=None, email_body=None):
        """
        Check if the message is a system message or bounce notification.
        Reuses the existing system message detection logic with optimizations.
        
        Args:
            recipient_email (str): Email address where the original email was sent to
            sender_email (str): Email address of the original sender
            subject (str): Email subject line (optional)
            email_body (str): Email body content (optional)
            
        Returns:
            tuple: (is_system_message: bool, reason: str)
        """
        timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
        
        try:
            # 1. BASIC VALIDATION - Skip if sender email is empty
            if not sender_email:
                return True, "No sender email found"
            
            # 2. BASIC VALIDATION - Skip if no recipient email
            if not recipient_email:
                return True, "No recipient email found"
            
            # Clean up email addresses for comparison
            sender_clean = sender_email.lower().strip()
            recipient_clean = recipient_email.lower().strip()
            
            # 3. PRIMARY LOOP PREVENTION - Skip if email was sent TO any autoresponse account
            if EMAIL_ACCOUNTS:
                for account in EMAIL_ACCOUNTS:
                    if account:
                        account_clean = account.lower().strip()
                        if recipient_clean == account_clean:
                            return True, f"Email sent directly to autoresponse account: {recipient_email}"
            
            # 4. SECONDARY LOOP PREVENTION - Skip if sender is also an autoresponse account
            if EMAIL_ACCOUNTS:
                for account in EMAIL_ACCOUNTS:
                    if account:
                        account_clean = account.lower().strip()
                        if sender_clean == account_clean:
                            return True, f"Sender is also an autoresponse account: {sender_email}"
            
            # 5. MICROSOFT EXCHANGE SYSTEM DETECTION
            exchange_patterns = [
                r'microsoftexchange[a-f0-9]+@',
                r'exchange[a-f0-9]+@',
                r'[a-f0-9]{32}@'
            ]
            
            for pattern in exchange_patterns:
                if re.search(pattern, sender_clean):
                    return True, f"Microsoft Exchange system sender detected: {sender_email}"
            
            # 6. SYSTEM ADDRESS DETECTION - Enhanced list
            system_indicators = [
                'noreply', 'no-reply', 'donotreply', 'do-not-reply',
                'mailer-daemon', 'postmaster', 'daemon', 'mail-daemon',
                'microsoftexchange', 'exchange', 'outlook-com', 
                'auto-reply', 'autoreply', 'bounce', 'delivery',
                'system', 'administrator', 'admin', 'notification',
                'report', 'alert', 'info@', 'support@', 'service@'
            ]
            
            for indicator in system_indicators:
                if indicator in sender_clean:
                    return True, f"System/automated sender detected: {sender_email}"
            
            # 7. SUBJECT LINE ANALYSIS - Check for bounce/error indicators
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
                    'delivery incomplete', 'message rejected', 'smtp error',
                    'failure notice', 'away from my desk', 'vacation'
                ]
                
                for indicator in bounce_subject_indicators:
                    if indicator in subject_clean:
                        return True, f"Bounce/error message detected in subject: '{subject}'"
                
                # Special check for subjects that start with common bounce prefixes
                bounce_prefixes = ['undeliverable:', 'delivery failure:', 'returned mail:', 'ndr:', 're: auto:', 're: automated', 'auto:', 'automated:']
                for prefix in bounce_prefixes:
                    if subject_clean.startswith(prefix):
                        return True, f"Bounce message detected by subject prefix: '{subject}'"
            
            # 8. EMAIL BODY ANALYSIS - Check for common bounce message content
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
                    'mailbox does not exist', 'invalid recipient',
                    'out of office', 'automatic reply', 'auto-response', 
                    'vacation response', 'away message', 'while I am away',
                    'will be out of the office', 'thank you for your email',
                    'will not be checking email', 'message has been received'
                ]
                
                for indicator in bounce_body_indicators:
                    if indicator in body_clean:
                        return True, f"Bounce/error message detected in body content"
            
            # If none of the system message conditions match, it's not a system message
            return False, "Not a system message"
            
        except Exception as e:
            # If there's any error in the system message detection, log it but don't block
            error_msg = f"Error in system message detection: {str(e)}"
            print(f">> {timestamp} Script: autoresponse.py - Function: _check_for_system_message - ERROR: {error_msg}")
            return False, "Error in system message detection (fail open)"
    
    async def _check_recent_responses(self, sender_email):
        """
        Check if we've already sent an autoresponse to this sender within the time window.
        Queries the SQL database to count recent autoresponses.
        
        Args:
            sender_email (str): Clean sender email address to check
            
        Returns:
            int: Number of autoresponses sent to this sender in the time window
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
            
            # Query to count autoresponses to this sender within the time window
            query = """
            SELECT COUNT(*) 
            FROM [dbo].[logs] 
            WHERE eml_frm LIKE ? 
            AND auto_response_sent = 'success'
            AND dttm_proc >= ?
            """
            
            # Use LIKE with wildcards to handle various forms of the same email
            # e.g., "John Doe <john@example.com>" or just "john@example.com"
            search_pattern = f'%{sender_email}%'
            
            cursor.execute(query, (search_pattern, window_start_str))
            count = cursor.fetchone()[0]
            
            cursor.close()
            conn.close()
            
            print(f">> {timestamp} Script: autoresponse.py - Function: _check_recent_responses - "
                  f"Found {count} recent autoresponses to {sender_email} since {window_start_str}")
            
            return count
            
        except Exception as e:
            # If there's any error querying the database, log it and return 0
            error_msg = f"Error checking recent responses: {str(e)}"
            print(f">> {timestamp} Script: autoresponse.py - Function: _check_recent_responses - ERROR: {error_msg}")
            return 0


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
