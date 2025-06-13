import html2text
import re
import datetime
from email import message_from_bytes

# EXTRACT BODY FROM EMAIL
def get_email_body(msg):
    """Extract the body from the raw email message."""
    if 'body' in msg:
        body_content = msg['body']
        content_type = body_content.get('contentType', 'text')
        content = body_content.get('content', '')

        if content_type == 'html':
            plain_text_content = html2text.html2text(content)
            return {'html': content, 'text': plain_text_content}
        elif content_type == 'text':
            return {'html': '', 'text': content}
        else:
            return {'html': '', 'text': ''}
        
    return {'html': '', 'text': ''}

def extract_bounce_original_addresses(body_text, subject):
    """
    Extract original sender and recipient from bounce message body.
    Microsoft Exchange bounce messages contain the original message details in the body.
    
    Args:
        body_text (str): The email body text
        subject (str): The email subject
        
    Returns:
        dict: {'original_sender': str, 'original_recipient': str} or None if not found
    """
    if not body_text:
        return None
        
    try:
        # Common patterns in Microsoft Exchange bounce messages
        patterns = {
            'original_sender': [
                r'Sender Address:\s*([^\s\n\r]+)',
                r'From:\s*([^\s\n\r]+)',
                r'Original sender:\s*([^\s\n\r]+)',
                r'The sender was:\s*([^\s\n\r]+)'
            ],
            'original_recipient': [
                r'Recipient Address:\s*([^\s\n\r]+)', 
                r'To:\s*([^\s\n\r]+)',
                r'Original recipient:\s*([^\s\n\r]+)',
                r'The recipient was:\s*([^\s\n\r]+)',
                r'rejected your message to the following email addresses:\s*([^\s\n\r(]+)',
                r'couldn\'t be delivered to:\s*([^\s\n\r]+)'
            ]
        }
        
        result = {}
        
        # Extract original sender
        for pattern in patterns['original_sender']:
            match = re.search(pattern, body_text, re.IGNORECASE | re.MULTILINE)
            if match:
                email = match.group(1).strip()
                # Clean up common suffixes and validate email format
                email = re.sub(r'\s*\([^)]*\)$', '', email)  # Remove (name) suffix
                if '@' in email and '.' in email:
                    result['original_sender'] = email
                    break
        
        # Extract original recipient
        for pattern in patterns['original_recipient']:
            match = re.search(pattern, body_text, re.IGNORECASE | re.MULTILINE)
            if match:
                email = match.group(1).strip()
                # Clean up common suffixes and validate email format
                email = re.sub(r'\s*\([^)]*\)$', '', email)  # Remove (name) suffix
                if '@' in email and '.' in email:
                    result['original_recipient'] = email
                    break
        
        # Additional pattern: Extract from "Your message to X couldn't be delivered" 
        if not result.get('original_recipient'):
            pattern = r'Your message to\s+([^\s]+)\s+couldn\'t be delivered'
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                email = match.group(1).strip()
                if '@' in email and '.' in email:
                    result['original_recipient'] = email
        
        return result if result else None
        
    except Exception as e:
        print(f"Error extracting bounce addresses: {str(e)}")
        return None

def is_bounce_or_system_message(sender_email, subject, body_text):
    """
    Determine if this is a bounce/system message based on various indicators.
    
    Args:
        sender_email (str): Sender email address
        subject (str): Email subject
        body_text (str): Email body text
        
    Returns:
        bool: True if this appears to be a bounce/system message
    """
    if not sender_email:
        return False
        
    sender_lower = sender_email.lower()
    subject_lower = subject.lower() if subject else ''
    body_lower = body_text.lower() if body_text else ''
    
    # Check sender patterns
    system_sender_patterns = [
        r'microsoftexchange[a-f0-9]+@',
        r'mailer-daemon@',
        r'postmaster@',
        r'noreply@',
        r'no-reply@',
        r'donotreply@'
    ]
    
    for pattern in system_sender_patterns:
        if re.search(pattern, sender_lower):
            return True
    
    # Check subject patterns
    bounce_subject_indicators = [
        'undeliverable', 'delivery status notification', 'delivery failure',
        'mail delivery failed', 'returned mail', 'bounce notification',
        'message not delivered', 'delivery report', 'non-delivery report'
    ]
    
    for indicator in bounce_subject_indicators:
        if indicator in subject_lower:
            return True
    
    # Check body patterns
    bounce_body_indicators = [
        'rejected your message', 'message could not be delivered',
        'delivery failed', 'mailbox is full', 'user is over quota',
        'address not found', 'user unknown'
    ]
    
    for indicator in bounce_body_indicators:
        if indicator in body_lower:
            return True
    
    return False

# CREATE EMAIL OBJECT - ENHANCED VERSION
def create_email_details(msg):
    """
    Enhanced version that properly handles bounce messages and extracts correct recipient information.
    """
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    
    body_content = get_email_body(msg)

    # Get all the recipients and cc list from Graph API response
    to_recipients = [recipient.get('emailAddress', {}).get('address', '') for recipient in msg.get('toRecipients', [])]
    cc_recipients = [cc.get('emailAddress', {}).get('address', '') for cc in msg.get('ccRecipients', [])]
    
    to_recipients_str = ', '.join(to_recipients)
    cc_recipients_str = ', '.join(cc_recipients)

    # Extract basic details from Graph API
    from_address = msg.get('from', {}).get('emailAddress', {}).get('address', '')
    subject = msg.get('subject', '')
    body_text = body_content.get('text', '')
    
    # DEBUG LOGGING - Show what Graph API returned
    print(f">> {timestamp} Script: email_utils.py - Function: create_email_details - GRAPH API PARSING:")
    print(f">> {timestamp} Subject: '{subject}'")
    print(f">> {timestamp} Graph API FROM: '{from_address}'")
    print(f">> {timestamp} Graph API TO: '{to_recipients_str}'")
    
    # ENHANCED LOGIC: Check if this is a bounce/system message
    is_bounce = is_bounce_or_system_message(from_address, subject, body_text)
    
    if is_bounce:
        print(f">> {timestamp} Script: email_utils.py - Function: create_email_details - BOUNCE MESSAGE DETECTED!")
        print(f">> {timestamp} Attempting to extract original addresses from message body...")
        
        # Try to extract the REAL original addresses from the bounce message body
        bounce_info = extract_bounce_original_addresses(body_text, subject)
        
        if bounce_info:
            print(f">> {timestamp} Script: email_utils.py - Function: create_email_details - BOUNCE ANALYSIS SUCCESS:")
            print(f">> {timestamp} Original sender found: '{bounce_info.get('original_sender', 'Not found')}'")
            print(f">> {timestamp} Original recipient found: '{bounce_info.get('original_recipient', 'Not found')}'")
            
            # For bounce messages, we want to use:
            # - FROM: The system sender (as Graph API shows it)
            # - TO: The ACTUAL original recipient (extracted from body)
            # This way, our loop prevention will see the correct "TO" address
            
            if bounce_info.get('original_recipient'):
                # Override the TO address with the real original recipient
                to_recipients_str = bounce_info['original_recipient']
                print(f">> {timestamp} Script: email_utils.py - Function: create_email_details - CORRECTED TO address: '{to_recipients_str}'")
        else:
            print(f">> {timestamp} Script: email_utils.py - Function: create_email_details - Could not extract original addresses from bounce message")
            # Log the body content for manual analysis
            print(f">> {timestamp} Body preview (first 1000 chars): {body_text[:1000]}")
    
    email_details = {
        'email_id': msg.get('id', ''),
        'internet_message_id': msg.get('internetMessageId', ''),
        'to': to_recipients_str,  # This now contains the corrected TO address for bounces
        'from': from_address,
        'date_received': msg.get('receivedDateTime', ''),
        'cc': cc_recipients_str,
        'subject': subject,
        'body_html': body_content.get('html', ''),
        'body_text': body_text,
        'is_bounce_message': is_bounce  # Add flag to indicate if this is a bounce
    }
    
    # Final debug log
    print(f">> {timestamp} Script: email_utils.py - Function: create_email_details - FINAL DETAILS:")
    print(f">> {timestamp} Final FROM: '{email_details['from']}'")
    print(f">> {timestamp} Final TO: '{email_details['to']}'")
    print(f">> {timestamp} Is bounce message: {is_bounce}")
    
    return email_details
