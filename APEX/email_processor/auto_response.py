import os
import aiohttp
import asyncio
import datetime
from pathlib import Path
from config import EMAIL_ACCOUNTS

# Directory where HTML templates are stored - will create if it doesn't exist
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
os.makedirs(TEMPLATES_DIR, exist_ok=True)

async def send_auto_response(access_token, recipient_email, original_to_address, subject, sender_account=None):
    """
    Send an auto-response email to the original sender based on which address they sent to.
    
    Args:
        access_token (str): Valid access token for Microsoft Graph API
        recipient_email (str): Email address of the customer who sent the original email
        original_to_address (str): The address the customer sent their email to
        subject (str): The subject of the original email
        sender_account (str, optional): Email account to send from. If None, uses the first 
                                        account from EMAIL_ACCOUNTS config.
        
    Returns:
        bool: True if auto-response was sent successfully, False otherwise
    """
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        # Get template based on original_to_address
        template_html = get_template_for_address(original_to_address)
        
        if not template_html:
            print(f">> {timestamp} No template found for address: {original_to_address}. Skipping auto-response.")
            return False
        
        # Use the same email account that's receiving emails
        if sender_account is None:
            if EMAIL_ACCOUNTS and len(EMAIL_ACCOUNTS) > 0:
                sender_account = EMAIL_ACCOUNTS[0]  # Use the first configured email account
            else:
                print(f">> {timestamp} No email account configured. Cannot send auto-response.")
                return False
        
        # Create auto-response subject
        auto_response_subject = f"Re: {subject}"
        
        # Send the email using MS Graph API
        return await send_email_via_graph(
            access_token,
            sender_account,
            recipient_email,
            auto_response_subject,
            template_html
        )
        
    except Exception as e:
        print(f">> {timestamp} Error sending auto-response: {str(e)}")
        return False

def get_template_for_address(email_address):
    """
    Get the appropriate HTML template based on the email address.
    
    Args:
        email_address (str): The email address the customer sent to
        
    Returns:
        str: HTML template content, or None if no template is found
    """
    # Extract domain part for matching
    if not email_address:
        return None
    
    # Default template
    template_name = "default.html"
    
    # Map of email addresses to template names
    template_map = {
        "tracking@": "tracking.html",
        "claims@": "claims.html",
        "policy@": "policy.html",
        "online@": "online.html",
        "insurance@": "insurance.html",
        # Add more mappings as needed
    }
    
    # Try to find a match in the email address
    for addr_part, template in template_map.items():
        if addr_part.lower() in email_address.lower():
            template_name = template
            break
    
    # Load the template file
    template_path = os.path.join(TEMPLATES_DIR, template_name)
    
    # Create default templates if they don't exist
    create_default_templates()
    
    try:
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as file:
                return file.read()
        else:
            print(f"Template file not found: {template_path}")
            # Fall back to default template
            default_path = os.path.join(TEMPLATES_DIR, "default.html")
            if os.path.exists(default_path):
                with open(default_path, 'r', encoding='utf-8') as file:
                    return file.read()
            return None
    except Exception as e:
        print(f"Error loading template: {str(e)}")
        return None

def create_default_templates():
    """Create default templates if they don't exist"""
    
    # Default template
    default_template = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Email Receipt Confirmation</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
        }
        .header {
            background-color: #003366;
            color: white;
            padding: 20px;
            text-align: center;
        }
        .content {
            padding: 20px;
            border: 1px solid #ddd;
        }
        .footer {
            margin-top: 20px;
            font-size: 12px;
            color: #777;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Your Email Has Been Received</h1>
    </div>
    <div class="content">
        <p>Dear Valued Customer,</p>
        
        <p>Thank you for contacting us. This automated message confirms that we have received your email and it has been forwarded to the appropriate department for handling.</p>
        
        <p>A customer service representative will review your message and respond as soon as possible. Please note that our standard response time is within 24-48 business hours.</p>
        
        <p>For urgent matters, please contact our customer service line at 0800-123-4567.</p>
        
        <p>Thank you for your patience.</p>
        
        <p>Best regards,<br>
        Customer Service Team</p>
    </div>
    <div class="footer">
        <p>This is an automated message, please do not reply to this email.</p>
        <p>&copy; 2025 Insurance Company. All rights reserved.</p>
    </div>
</body>
</html>"""

    # Tracking template
    tracking_template = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Tracking Department Receipt Confirmation</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
        }
        .header {
            background-color: #005500;
            color: white;
            padding: 20px;
            text-align: center;
        }
        .content {
            padding: 20px;
            border: 1px solid #ddd;
        }
        .footer {
            margin-top: 20px;
            font-size: 12px;
            color: #777;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Vehicle Tracking Department</h1>
    </div>
    <div class="content">
        <p>Dear Valued Customer,</p>
        
        <p>Thank you for contacting our Vehicle Tracking Department. This automated message confirms that we have received your email regarding tracking services.</p>
        
        <p>Your message has been forwarded to our tracking specialists who will process your request. Vehicle tracking certificate processing typically takes 24-72 business hours.</p>
        
        <p>For urgent tracking assistance, please contact our tracking helpline at 0800-555-7890.</p>
        
        <p>Thank you for your patience.</p>
        
        <p>Best regards,<br>
        Vehicle Tracking Department</p>
    </div>
    <div class="footer">
        <p>This is an automated message, please do not reply to this email.</p>
        <p>&copy; 2025 Insurance Company. All rights reserved.</p>
    </div>
</body>
</html>"""

    # Create the templates directory if it doesn't exist
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    
    # Create default template if it doesn't exist
    default_path = os.path.join(TEMPLATES_DIR, "default.html")
    if not os.path.exists(default_path):
        with open(default_path, 'w', encoding='utf-8') as file:
            file.write(default_template)
    
    # Create tracking template if it doesn't exist
    tracking_path = os.path.join(TEMPLATES_DIR, "tracking.html")
    if not os.path.exists(tracking_path):
        with open(tracking_path, 'w', encoding='utf-8') as file:
            file.write(tracking_template)

async def send_email_via_graph(access_token, sender_account, recipient_email, subject, html_body):
    """
    Send an email using Microsoft Graph API.
    
    Args:
        access_token (str): Valid access token for Microsoft Graph API
        sender_account (str): Email address to send from
        recipient_email (str): Email address to send to
        subject (str): Email subject
        html_body (str): HTML content for the email body
        
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }
    
    # Endpoint for sending mail
    endpoint = f'https://graph.microsoft.com/v1.0/users/{sender_account}/sendMail'
    
    # Prepare the email message
    email_data = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": html_body
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": recipient_email
                    }
                }
            ]
        },
        "saveToSentItems": "true"
    }
    
    # Maximum retry attempts
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, headers=headers, json=email_data) as response:
                    if response.status == 202:  # Accepted
                        print(f">> {timestamp} Auto-response sent successfully to {recipient_email} from {sender_account}")
                        return True
                    else:
                        response_text = await response.text()
                        print(f">> {timestamp} Failed to send auto-response: {response.status}")
                        print(f"Response: {response_text}")
                        
                        # If authentication failed, don't retry
                        if response.status in [401, 403]:
                            return False
        except aiohttp.ClientError as e:
            print(f">> {timestamp} HTTP client error: {str(e)}")
        except Exception as e:
            print(f">> {timestamp} Error sending email: {str(e)}")
        
        # Implement exponential backoff for retries
        if attempt < max_retries - 1:
            backoff_time = 2 ** attempt
            print(f">> {timestamp} Retrying in {backoff_time} seconds (attempt {attempt + 1}/{max_retries})...")
            await asyncio.sleep(backoff_time)
    
    return False
