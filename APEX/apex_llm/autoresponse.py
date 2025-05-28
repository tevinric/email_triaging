import asyncio
import datetime
import os
import re
import uuid
import aiohttp
import json
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
    Enhanced with proper encoding handling to fix character display issues.
    
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
            # Download blob content with explicit encoding handling
            download_stream = await blob_client.download_blob()
            template_content_bytes = await download_stream.readall()
            
            # Enhanced encoding handling to fix character display issues
            template_content = await _decode_template_content(template_content_bytes, timestamp)
            return template_content, folder_name
        else:
            # Try fallback to html extension
            alt_template_path = f"{folder_name}/{mailbox_name}@{domain}.html"
            blob_client = container_client.get_blob_client(alt_template_path)
            
            if await blob_client.exists():
                download_stream = await blob_client.download_blob()
                template_content_bytes = await download_stream.readall()
                
                # Apply same encoding handling
                template_content = await _decode_template_content(template_content_bytes, timestamp)
                return template_content, folder_name
            else:
                # Try one more fallback to a simple named file
                simple_template_path = f"{folder_name}/{folder_name}.html"
                blob_client = container_client.get_blob_client(simple_template_path)
                
                if await blob_client.exists():
                    download_stream = await blob_client.download_blob()
                    template_content_bytes = await download_stream.readall()
                    
                    # Apply same encoding handling
                    template_content = await _decode_template_content(template_content_bytes, timestamp)
                    return template_content, folder_name
                else:
                    print(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Template not found in blob storage for folder: {folder_name}")
                    return None, None
            
    except Exception as e:
        print(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Error retrieving template from blob storage: {str(e)}")
        return None, None

async def _decode_template_content(template_content_bytes, timestamp):
    """
    Helper function to properly decode template content with encoding fallbacks.
    Fixes character encoding issues including smart quotes and special characters.
    
    Args:
        template_content_bytes (bytes): Raw template content bytes
        timestamp (str): Timestamp for logging
        
    Returns:
        str: Properly decoded and cleaned template content
    """
    template_content = None
    encoding_used = "unknown"
    
    # Try different encoding methods
    encoding_attempts = [
        ('utf-8', 'strict'),
        ('windows-1252', 'strict'),
        ('iso-8859-1', 'strict'),
        ('utf-8', 'replace'),
        ('cp1252', 'strict'),  # Another name for Windows-1252
        ('latin1', 'strict'),  # Another name for ISO-8859-1
    ]
    
    for encoding, error_handling in encoding_attempts:
        try:
            template_content = template_content_bytes.decode(encoding, errors=error_handling)
            encoding_used = f"{encoding} ({error_handling})"
            print(f">> {timestamp} Script: autoresponse.py - Function: _decode_template_content - Successfully decoded with {encoding_used}")
            break
        except (UnicodeDecodeError, LookupError) as e:
            print(f">> {timestamp} Script: autoresponse.py - Function: _decode_template_content - Failed with {encoding}: {str(e)}")
            continue
    
    # If all encoding attempts failed, use UTF-8 with ignore
    if template_content is None:
        template_content = template_content_bytes.decode('utf-8', errors='ignore')
        encoding_used = "utf-8 (ignore)"
        print(f">> {timestamp} Script: autoresponse.py - Function: _decode_template_content - Used final fallback: {encoding_used}")
    
    # Now fix common character encoding issues (smart quotes, em dashes, etc.)
    original_length = len(template_content)
    template_content = _fix_character_encoding_issues(template_content, timestamp)
    
    if len(template_content) != original_length:
        print(f">> {timestamp} Script: autoresponse.py - Function: _decode_template_content - Applied character fixes, length changed: {original_length} -> {len(template_content)}")
    
    return template_content

def _fix_character_encoding_issues(content, timestamp):
    """
    Fix common character encoding issues that occur with Word-generated HTML templates.
    Replaces problematic characters with their correct equivalents.
    
    Args:
        content (str): Template content with potential encoding issues
        timestamp (str): Timestamp for logging
        
    Returns:
        str: Content with fixed character encoding
    """
    if not content:
        return content
    
    # Log suspicious characters for debugging
    suspicious_chars = []
    for char in content:
        if ord(char) > 127 and char not in ['\n', '\r', '\t']:
            if char not in suspicious_chars:
                suspicious_chars.append(char)
    
    if suspicious_chars:
        print(f">> {timestamp} Script: autoresponse.py - Function: _fix_character_encoding_issues - Found suspicious characters: {suspicious_chars}")
        for char in suspicious_chars[:10]:  # Show first 10 to avoid spam
            print(f">> {timestamp} Script: autoresponse.py - Function: _fix_character_encoding_issues - Character '{char}' has Unicode code: {ord(char)}")
    
    # Dictionary of problematic characters and their replacements
    character_fixes = {
        # Smart quotes and apostrophes - most common issues
        '�': "'",           # Common replacement character for curly apostrophe
        ''': "'",           # Left single quotation mark (U+2018)
        ''': "'",           # Right single quotation mark (U+2019) 
        '"': '"',           # Left double quotation mark (U+201C)
        '"': '"',           # Right double quotation mark (U+201D)
        '„': '"',           # Double low-9 quotation mark
        '‚': "'",           # Single low-9 quotation mark
        
        # Dashes
        '–': '-',           # En dash (U+2013)
        '—': '-',           # Em dash (U+2014)
        '−': '-',           # Minus sign (U+2212)
        
        # Other common problematic characters
        '…': '...',         # Horizontal ellipsis (U+2026)
        '•': '*',           # Bullet point (U+2022)
        '™': '(TM)',        # Trademark symbol
        '®': '(R)',         # Registered trademark
        '©': '(C)',         # Copyright symbol
        '€': 'EUR',         # Euro symbol
        '£': 'GBP',         # Pound sterling
        '¢': 'c',           # Cent sign
        
        # Accented characters that might cause issues
        'á': 'a', 'à': 'a', 'â': 'a', 'ä': 'a', 'ã': 'a', 'å': 'a',
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
        'ó': 'o', 'ò': 'o', 'ô': 'o', 'ö': 'o', 'õ': 'o',
        'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
        'ñ': 'n', 'ç': 'c',
        
        # Capital versions
        'Á': 'A', 'À': 'A', 'Â': 'A', 'Ä': 'A', 'Ã': 'A', 'Å': 'A',
        'É': 'E', 'È': 'E', 'Ê': 'E', 'Ë': 'E',
        'Í': 'I', 'Ì': 'I', 'Î': 'I', 'Ï': 'I',
        'Ó': 'O', 'Ò': 'O', 'Ô': 'O', 'Ö': 'O', 'Õ': 'O',
        'Ú': 'U', 'Ù': 'U', 'Û': 'U', 'Ü': 'U',
        'Ñ': 'N', 'Ç': 'C',
        
        # Other problematic symbols that might appear as question marks
        '†': '+',           # Dagger
        '‡': '++',          # Double dagger
        '‰': '%',           # Per mille sign
        '‹': '<',           # Single left-pointing angle quotation mark
        '›': '>',           # Single right-pointing angle quotation mark
        '«': '<<',          # Left-pointing double angle quotation mark
        '»': '>>',          # Right-pointing double angle quotation mark
        
        # Non-breaking space and other whitespace issues
        '\xa0': ' ',        # Non-breaking space (U+00A0)
        '\u2000': ' ',      # En quad
        '\u2001': ' ',      # Em quad
        '\u2002': ' ',      # En space
        '\u2003': ' ',      # Em space
        '\u2009': ' ',      # Thin space
        '\u200a': ' ',      # Hair space
        '\u202f': ' ',      # Narrow no-break space
        '\u205f': ' ',      # Medium mathematical space
    }
    
    fixes_applied = 0
    original_content = content
    
    # Apply character fixes
    for bad_char, replacement in character_fixes.items():
        if bad_char in content:
            content = content.replace(bad_char, replacement)
            fixes_applied += 1
            print(f">> {timestamp} Script: autoresponse.py - Function: _fix_character_encoding_issues - Replaced '{bad_char}' (U+{ord(bad_char):04X}) with '{replacement}'")
    
    # Special handling for the specific issue mentioned by user
    # Handle various forms of "don't" that might be corrupted
    problematic_dont_patterns = [
        'don�t',           # The specific issue reported (Unicode replacement character)
        'don´t',           # Acute accent instead of apostrophe
        'don`t',           # Grave accent instead of apostrophe
        'don't',           # Curly apostrophe (U+2019)
        'don't',           # Another form of curly apostrophe (U+2018)
        'don�t',          # Another common corruption
        'donâ€™t',        # UTF-8 encoding issue
        'don\u2019t',     # Unicode escape for right single quotation mark
        'don\u2018t',     # Unicode escape for left single quotation mark
    ]
    
    for pattern in problematic_dont_patterns:
        if pattern in content:
            content = content.replace(pattern, "don't")
            fixes_applied += 1
            print(f">> {timestamp} Script: autoresponse.py - Function: _fix_character_encoding_issues - Fixed 'don't' pattern: '{pattern}'")
    
    # Handle other common contractions that might be corrupted
    contraction_fixes = {
        'can�t': "can't",      'can't': "can't",      'canâ€™t': "can't",
        'won�t': "won't",      'won't': "won't",      'wonâ€™t': "won't", 
        'isn�t': "isn't",      'isn't': "isn't",      'isnâ€™t': "isn't",
        'aren�t': "aren't",    'aren't': "aren't",    'arenâ€™t': "aren't",
        'wasn�t': "wasn't",    'wasn't': "wasn't",    'wasnâ€™t': "wasn't",
        'weren�t': "weren't",  'weren't': "weren't",  'werenâ€™t': "weren't",
        'hasn�t': "hasn't",    'hasn't': "hasn't",    'hasnâ€™t': "hasn't",
        'haven�t': "haven't",  'haven't': "haven't",  'havenâ€™t': "haven't",
        'hadn�t': "hadn't",    'hadn't': "hadn't",    'hadnâ€™t': "hadn't",
        'shouldn�t': "shouldn't", 'shouldn't': "shouldn't", 'shouldnâ€™t': "shouldn't",
        'wouldn�t': "wouldn't", 'wouldn't': "wouldn't", 'wouldnâ€™t': "wouldn't",
        'couldn�t': "couldn't", 'couldn't': "couldn't", 'couldnâ€™t': "couldn't",
        'didn�t': "didn't",    'didn't': "didn't",    'didnâ€™t': "didn't",
        'doesn�t': "doesn't",  'doesn't': "doesn't",  'doesnâ€™t': "doesn't",
        'it�s': "it's",        'it's': "it's",        'itâ€™s': "it's",
        'that�s': "that's",    'that's': "that's",    'thatâ€™s': "that's",
        'there�s': "there's",  'there's': "there's",  'thereâ€™s': "there's",
        'here�s': "here's",    'here's': "here's",    'hereâ€™s': "here's",
        'what�s': "what's",    'what's': "what's",    'whatâ€™s': "what's",
        'where�s': "where's",  'where's': "where's",  'whereâ€™s': "where's",
        'who�s': "who's",      'who's': "who's",      'whoâ€™s': "who's",
        'how�s': "how's",      'how's': "how's",      'howâ€™s': "how's",
        'let�s': "let's",      'let's': "let's",      'letâ€™s': "let's",
        'I�m': "I'm",          'I'm': "I'm",          'Iâ€™m': "I'm",
        'you�re': "you're",    'you're': "you're",    'youâ€™re': "you're",
        'we�re': "we're",      'we're': "we're",      'weâ€™re': "we're",
        'they�re': "they're",  'they're': "they're",  'theyâ€™re': "they're",
        'I�ve': "I've",        'I've': "I've",        'Iâ€™ve': "I've",
        'you�ve': "you've",    'you've': "you've",    'youâ€™ve': "you've",
        'we�ve': "we've",      'we've': "we've",      'weâ€™ve': "we've",
        'they�ve': "they've",  'they've': "they've",  'theyâ€™ve': "they've",
        'I�ll': "I'll",        'I'll': "I'll",        'Iâ€™ll': "I'll",
        'you�ll': "you'll",    'you'll': "you'll",    'youâ€™ll': "you'll",
        'we�ll': "we'll",      'we'll': "we'll",      'weâ€™ll': "we'll",
        'they�ll': "they'll",  'they'll': "they'll",  'theyâ€™ll': "they'll",
        'I�d': "I'd",          'I'd': "I'd",          'Iâ€™d': "I'd",
        'you�d': "you'd",      'you'd': "you'd",      'youâ€™d': "you'd",
        'we�d': "we'd",        'we'd': "we'd",        'weâ€™d': "we'd",
        'they�d': "they'd",    'they'd': "they'd",    'theyâ€™d': "they'd",
    }
    
    for bad_contraction, good_contraction in contraction_fixes.items():
        if bad_contraction in content:
            content = content.replace(bad_contraction, good_contraction)
            fixes_applied += 1
            print(f">> {timestamp} Script: autoresponse.py - Function: _fix_character_encoding_issues - Fixed contraction: '{bad_contraction}' -> '{good_contraction}'")
    
    if fixes_applied > 0:
        print(f">> {timestamp} Script: autoresponse.py - Function: _fix_character_encoding_issues - Applied {fixes_applied} character fixes total")
    else:
        print(f">> {timestamp} Script: autoresponse.py - Function: _fix_character_encoding_issues - No character fixes needed")
    
    return content

async def process_template_images(template_content, template_folder):
    """
    Process the template to update image references to point to blob storage.
    Enhanced with detailed logging for troubleshooting image display issues.
    
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
    
    try:
        # Parse HTML using BeautifulSoup with proper HTML parser
        soup = BeautifulSoup(template_content, 'html.parser')
        
        # Find all image tags
        img_tags = soup.find_all('img')
        
        # Base URL for images in blob storage - images are in the same folder as the template
        base_url = f"{AZURE_STORAGE_PUBLIC_URL}/{BLOB_CONTAINER_NAME}/{template_folder}"
        
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Processing {len(img_tags)} images with base URL: {base_url}")
        
        images_processed = 0
        
        # Update image src attributes
        for img in img_tags:
            if img.get('src'):
                src = img['src']
                original_src = src
                
                # Check if already an absolute URL
                if src.startswith('http://') or src.startswith('https://'):
                    print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Skipping absolute URL: {src}")
                    continue
                
                # Replace backslashes with forward slashes
                src = src.replace('\\', '/')
                
                # Remove leading ./ if present
                if src.startswith('./'):
                    src = src[2:]
                
                # Process different image path formats
                if '_files/' in src:
                    # Handle Word HTML exports with references like "onlinesupport@brand.co.za_files/image001.png"
                    img_filename = src.split('_files/')[-1]
                    absolute_url = f"{base_url}/{img_filename}"
                    img['src'] = absolute_url
                    print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Updated _files/ image: '{original_src}' -> '{absolute_url}'")
                elif '/' in src:
                    # For any other path with folders
                    img_filename = src.split('/')[-1]
                    absolute_url = f"{base_url}/{img_filename}"
                    img['src'] = absolute_url
                    print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Updated path image: '{original_src}' -> '{absolute_url}'")
                else:
                    # For simple filename references
                    absolute_url = f"{base_url}/{src}"
                    img['src'] = absolute_url
                    print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Updated simple image: '{original_src}' -> '{absolute_url}'")
                
                images_processed += 1
                
        # Find all VML image references (used in Outlook HTML)
        vml_shapes = soup.find_all('v:shape')
        vml_images = soup.find_all('v:imagedata')
        
        for vml_img in vml_images:
            if vml_img.get('src'):
                src = vml_img['src']
                original_src = src
                
                if not (src.startswith('http://') or src.startswith('https://')):
                    src = src.replace('\\', '/')
                    if src.startswith('./'):
                        src = src[2:]
                    
                    if '_files/' in src:
                        img_filename = src.split('_files/')[-1]
                        absolute_url = f"{base_url}/{img_filename}"
                        vml_img['src'] = absolute_url
                        print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Updated VML image: '{original_src}' -> '{absolute_url}'")
                        images_processed += 1
        
        # Find all background image references in inline styles
        elements_with_style = soup.find_all(lambda tag: tag.has_attr('style') and 'background-image' in tag['style'])
        
        for elem in elements_with_style:
            style = elem['style']
            original_style = style
            
            # Use regex to find and replace URL references
            url_pattern = r'url\([\'"]?([^\'"()]+)[\'"]?\)'
            url_matches = re.findall(url_pattern, style)
            
            for url in url_matches:
                if url.startswith('http://') or url.startswith('https://'):
                    continue
                    
                # Clean up the URL
                clean_url = url.replace('\\', '/')
                if clean_url.startswith('./'):
                    clean_url = clean_url[2:]
                
                # Extract filename and create absolute URL
                if '_files/' in clean_url:
                    img_filename = clean_url.split('_files/')[-1]
                    absolute_url = f"{base_url}/{img_filename}"
                elif '/' in clean_url:
                    img_filename = clean_url.split('/')[-1]
                    absolute_url = f"{base_url}/{img_filename}"
                else:
                    absolute_url = f"{base_url}/{clean_url}"
                
                # Replace in style
                style = style.replace(f"url({url})", f"url({absolute_url})")
                style = style.replace(f"url('{url}')", f"url('{absolute_url}')")
                style = style.replace(f'url("{url}")', f'url("{absolute_url}")')
            
            if style != original_style:
                elem['style'] = style
                print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Updated background image style")
                images_processed += 1
        
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Total images processed: {images_processed}")
        
        # Convert back to string - preserve original formatting as much as possible
        return str(soup)
        
    except Exception as e:
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template_images - Error processing template images: {str(e)}")
        # Return original content if processing fails
        return template_content

async def process_template(template_content, template_folder, email_data):
    """
    Process the template by replacing ONLY the reference ID and updating image references.
    IMPORTANT: Template is taken as-is with NO name manipulation per user requirements.
    Applies character encoding fixes to ensure proper display.
    
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
            print(f">> {timestamp} Script: autoresponse.py - Function: process_template - No template content provided")
            return template_content
        
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template - Processing template (length: {len(template_content)} chars)")
        
        # First, apply character encoding fixes to the template content
        processed_content = _fix_character_encoding_issues(template_content, timestamp)
        
        # Process image references to use absolute URLs for blob storage
        if template_folder:
            processed_content = await process_template_images(processed_content, template_folder)
            print(f">> {timestamp} Script: autoresponse.py - Function: process_template - Image processing completed")
        else:
            print(f">> {timestamp} Script: autoresponse.py - Function: process_template - No template folder, skipping image processing")
        
        # Generate a reference ID (could be based on the email ID or a UUID)
        reference_id = email_data.get('internet_message_id', '')
        if not reference_id:
            reference_id = str(uuid.uuid4())
        
        # Truncate if too long - take last 10 characters
        if len(reference_id) > 10:
            reference_id = reference_id[-10:]
        
        # ONLY replace the {{REFERENCE_ID}} placeholder - leave everything else completely as-is
        if '{{REFERENCE_ID}}' in processed_content:
            processed_content = processed_content.replace('{{REFERENCE_ID}}', reference_id)
            print(f">> {timestamp} Script: autoresponse.py - Function: process_template - Replaced reference ID placeholder with: {reference_id}")
        else:
            print(f">> {timestamp} Script: autoresponse.py - Function: process_template - No {{REFERENCE_ID}} placeholder found in template")
        
        # REMOVED: ALL name manipulation per user requirement
        # The template should be taken exactly as-is without ANY text changes
        # This ensures "Dear brand Customer" and all other text remains unchanged
        
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template - Template processing completed (final length: {len(processed_content)} chars)")
        
        return processed_content
        
    except Exception as e:
        print(f">> {timestamp} Script: autoresponse.py - Function: process_template - Error processing template: {str(e)}")
        return template_content  # Return original content if processing fails

async def send_email(access_token, account, to_email, subject, body_html, body_text):
    """
    Send a new email using Microsoft Graph API with proper encoding to fix character issues.
    
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
    
    # Clean the subject line of any encoding issues
    if subject:
        subject = _fix_character_encoding_issues(subject, timestamp)
    
    # Clean the HTML body content of any encoding issues
    if body_html:
        body_html = _fix_character_encoding_issues(body_html, timestamp)
        print(f">> {timestamp} Script: autoresponse.py - Function: send_email - Applied character fixes to HTML content")
    
    # Clean the text body content of any encoding issues  
    if body_text:
        body_text = _fix_character_encoding_issues(body_text, timestamp)
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json; charset=utf-8',  # Explicitly specify UTF-8
        'Accept': 'application/json',
        'Accept-Charset': 'utf-8'
    }
    
    # Ensure the HTML content has proper charset declaration and encoding
    if body_html:
        # Check if it already has a DOCTYPE and HTML structure
        if not '<!DOCTYPE html>' in body_html.upper():
            # Add proper HTML structure with charset if missing
            body_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Email Response</title>
</head>
<body>
{body_html}
</body>
</html>'''
            print(f">> {timestamp} Script: autoresponse.py - Function: send_email - Added HTML wrapper with charset declaration")
        
        # If it already has HTML structure but missing charset, add it
        elif '<meta charset=' not in body_html.lower() and '<meta http-equiv="content-type"' not in body_html.lower():
            # Try to add charset to existing head section
            if '<head>' in body_html.lower():
                head_pos = body_html.lower().find('<head>') + 6
                charset_meta = '\n    <meta charset="UTF-8">\n    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">'
                body_html = body_html[:head_pos] + charset_meta + body_html[head_pos:]
                print(f">> {timestamp} Script: autoresponse.py - Function: send_email - Added charset meta tags to existing HTML")
    
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
            ],
            # Add importance and other headers that might help with encoding
            'importance': 'normal',
            'internetMessageHeaders': [
                {
                    'name': 'Content-Type',
                    'value': 'text/html; charset=utf-8'
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
            # Create a new session with proper encoding settings
            connector = aiohttp.TCPConnector(force_close=True, enable_cleanup_closed=True)
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                # Ensure JSON is properly encoded with UTF-8, preserving all characters
                json_data = json.dumps(message_body, ensure_ascii=False, indent=None, separators=(',', ':'))
                
                print(f">> {timestamp} Script: autoresponse.py - Function: send_email - Sending email (attempt {attempt + 1}/{max_retries}) to {to_email}")
                print(f">> {timestamp} Script: autoresponse.py - Function: send_email - JSON payload size: {len(json_data)} characters")
                
                async with session.post(endpoint, headers=headers, data=json_data.encode('utf-8')) as response:
                    response_text = await response.text()
                    
                    if response.status == 202:  # 202 Accepted indicates success for sendMail
                        print(f">> {timestamp} Script: autoresponse.py - Function: send_email - Email sent successfully to {to_email}")
                        return True
                    else:
                        print(f">> {timestamp} Script: autoresponse.py - Function: send_email - Failed to send email: {response.status}")
                        print(f">> {timestamp} Script: autoresponse.py - Function: send_email - Response: {response_text}")
                        
                        # Don't retry for certain status codes
                        if response.status in [401, 403]:
                            print(f">> {timestamp} Script: autoresponse.py - Function: send_email - Authentication error. Not retrying.")
                            return False
                        
                        # Don't retry for bad request either
                        if response.status == 400:
                            print(f">> {timestamp} Script: autoresponse.py - Function: send_email - Bad request. Not retrying.")
                            # Log the request for debugging
                            print(f">> {timestamp} Script: autoresponse.py - Function: send_email - Request headers: {headers}")
                            return False
                            
        except Exception as e:
            print(f">> {timestamp} Script: autoresponse.py - Function: send_email - Error sending email (attempt {attempt + 1}): {str(e)}")
            import traceback
            print(f">> {timestamp} Script: autoresponse.py - Function: send_email - Traceback: {traceback.format_exc()}")
        
        # Implement exponential backoff
        if attempt < max_retries - 1:
            backoff_time = 2 ** attempt
            print(f">> {timestamp} Script: autoresponse.py - Function: send_email - Retrying in {backoff_time} seconds (attempt {attempt + 1}/{max_retries})...")
            await asyncio.sleep(backoff_time)
    
    print(f">> {timestamp} Script: autoresponse.py - Function: send_email - Failed to send email after {max_retries} attempts")
    return False

async def send_autoresponse(account, sender_email, email_subject, email_data):
    """
    Send an autoresponse email to the sender with proper encoding and template handling.
    
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
        system_addresses = ['noreply', 'no-reply', 'donotreply', 'mailer-daemon', 'postmaster', 'daemon']
        if not sender_email or any(system_domain in sender_email.lower() for system_domain in system_addresses):
            print(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Skipping autoresponse to system address: {sender_email}")
            return False
            
        print(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Starting autoresponse process for: {sender_email}")
        
        # Get access token for Microsoft Graph API
        access_token = await get_access_token()
        if not access_token:
            print(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Failed to obtain access token for autoresponse")
            return False
        
        # Get the recipient email (where the original email was sent to)
        recipient_email = email_data.get('to', '').split(',')[0].strip()
        print(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Original recipient: {recipient_email}")
        
        # Get template from Azure Blob Storage
        template_content, template_folder = await get_template_from_blob(recipient_email)
        
        # If no template found, use a default template with proper encoding
        if not template_content:
            print(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - No template found, using default template")
            template_content = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
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
</html>"""
        else:
            print(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Template loaded successfully (length: {len(template_content)} chars)")
        
        # Process the template to replace ONLY reference ID and update image references
        # NO name manipulation per user requirements
        processed_template = await process_template(template_content, template_folder, email_data)
        
        # Create subject line for autoresponse
        subject = f"Re: {email_subject}"
        
        # Extract plain text version from HTML (basic conversion)
        plain_text = "Thank you for your email. We have received your message and will respond as soon as possible. Reference number: " + email_data.get('internet_message_id', '')[-10:] + ". This is an automated response. Please do not reply to this email."
        
        # Send the email
        print(f">> {timestamp} Script: autoresponse.py - Function: send_autoresponse - Sending autoresponse to {sender_email} with subject: {subject}")
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
