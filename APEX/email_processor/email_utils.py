import html2text
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

# CREATE EMAIL OBJECT
def create_email_details(msg):
    """
    Enhanced version with debugging for bounce message analysis
    """
    import datetime
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    
    body_content = get_email_body(msg)

    # Get all the recipients and cc list
    to_recipients = [recipient.get('emailAddress', {}).get('address', '') for recipient in msg.get('toRecipients', [])]
    cc_recipients = [cc.get('emailAddress', {}).get('address', '') for cc in msg.get('ccRecipients', [])]
    
    to_recipients_str = ', '.join(to_recipients)
    cc_recipients_str = ', '.join(cc_recipients)
    
    # Extract sender
    from_address = msg.get('from', {}).get('emailAddress', {}).get('address', '')
    subject = msg.get('subject', '')
    
    # DEBUG LOGGING - Enhanced for bounce message analysis
    print(f">> {timestamp} Script: email_utils.py - Function: create_email_details - PARSING EMAIL:")
    print(f">> {timestamp} Subject: '{subject}'")
    print(f">> {timestamp} FROM: '{from_address}'")
    print(f">> {timestamp} TO: '{to_recipients_str}'")
    print(f">> {timestamp} CC: '{cc_recipients_str}'")
    
    # SPECIAL DEBUG: Check if this looks like a bounce message
    if ('undeliverable' in subject.lower() or 
        'delivery' in subject.lower() or 
        'microsoftexchange' in from_address.lower() or
        'bounce' in subject.lower()):
        print(f">> {timestamp} Script: email_utils.py - Function: create_email_details - BOUNCE MESSAGE DETECTED!")
        print(f">> {timestamp} Raw msg structure keys: {list(msg.keys())}")
        print(f">> {timestamp} Full FROM object: {msg.get('from', {})}")
        print(f">> {timestamp} Full TO object: {msg.get('toRecipients', [])}")
        
        # Log first 500 characters of body for analysis
        body_preview = body_content.get('text', '')[:500] if body_content.get('text') else 'No text body'
        print(f">> {timestamp} Body preview: {body_preview}")

    email_details = {
        'email_id': msg.get('id', ''),
        'internet_message_id': msg.get('internetMessageId', ''),
        'to': to_recipients_str,
        'from': from_address,
        'date_received': msg.get('receivedDateTime', ''),
        'cc': cc_recipients_str,
        'subject': subject,
        'body_html': body_content.get('html', ''),
        'body_text': body_content.get('text', '')
    }
    
    return email_details
