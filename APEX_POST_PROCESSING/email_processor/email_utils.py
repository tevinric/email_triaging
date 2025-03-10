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
    body_content = get_email_body(msg)

    # Get all the recipeints and cc list
    to_recipients = [recipient.get('emailAddress', {}).get('address', '') for recipient in msg.get('toRecipients', [])]
    cc_recipients = [cc.get('emailAddress', {}).get('address', '') for cc in msg.get('ccRecipients', [])]
    
    to_recipients_str = ', '.join(to_recipients)
    cc_recipients_str = ', '.join(cc_recipients)

    email_details = {
        'email_id': msg.get('id', ''),
        'internet_message_id': msg.get('internetMessageId', ''),
        'to': to_recipients_str,
        'from': msg.get('from', {}).get('emailAddress', {}).get('address', ''),
        'date_received': msg.get('receivedDateTime', ''),
        'cc': cc_recipients_str,
        'subject': msg.get('subject', ''),
        'body_html': body_content.get('html', ''),
        'body_text': body_content.get('text', '')
    }
    
    return email_details
