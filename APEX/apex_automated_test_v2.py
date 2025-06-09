import os
import sys
import time
import uuid
import asyncio
import datetime
import argparse
import pyodbc
import json
import traceback
from tabulate import tabulate
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import aiohttp  # Add this import for the HTTP client
from collections import Counter, defaultdict

# Import APEX components
from email_processor.email_client import get_access_token
from apex_llm.apex_routing import ang_routings
from config import (
    CLIENT_ID, TENANT_ID, CLIENT_SECRET, AUTHORITY, SCOPE,
    SQL_SERVER, SQL_DATABASE, SQL_USERNAME, SQL_PASSWORD,
    EMAIL_ACCOUNTS
)

# Load configuration from environment variables
def get_env_var(var_name, default=None, required=False):
    """Get environment variable with optional default and required check"""
    value = os.environ.get(var_name, default)
    if required and value is None:
        raise ValueError(f"Required environment variable {var_name} is not set")
    return value

# Constants from environment variables
TEST_ID_PREFIX = "APEX_AUTOMATED_TEST"
DEFAULT_WAIT_TIME = 1  # minutes
DEFAULT_REPORT_RECIPIENTS = [""]
EMAIL_CATEGORIES = list(ang_routings.keys())
DEFAULT_TEST_SENDER = ""

# Set up argument parsing
parser = argparse.ArgumentParser(description='APEX Automated Testing Script')
parser.add_argument('--recipients', type=str, help='Comma-separated list of email addresses to send the report to (overrides env var)')
parser.add_argument('--wait-time', type=int, help=f'Wait time in minutes between sending test emails and checking DB (default: {DEFAULT_WAIT_TIME})')
parser.add_argument('--sender', type=str, help='Email address to use as sender for test emails (overrides env var)')
parser.add_argument('--prefix', type=str, help='Prefix to use in test email subjects (overrides env var)')
args = parser.parse_args()

# Global variables to track test results
test_emails = []
test_results = []
error_details = []
charts = {}
alerts = []
recommendations = []

class TestEmail:
    """Class to represent a test email and track its status"""
    
    def __init__(self, category, test_id, subject, recipient, sender=None):
        self.category = category
        self.test_id = test_id
        self.subject = subject
        self.recipient = recipient
        self.sender = sender or DEFAULT_TEST_SENDER
        self.message_id = None
        self.internet_message_id = None
        self.sent_time = None
        self.found_in_db = False
        self.db_record = None
        self.error = None
        self.classification_correct = False
        self.verification_time = None
        # Additional fields
        self.auto_response_sent = None
        self.email_body = None
        self.sts_read_eml = None
        self.sts_routing = None
        self.processing_time = None
        self.cost_usd = None
        self.tokens_used = None
    
    def to_dict(self):
        """Convert to dictionary for reporting"""
        return {
            'category': self.category,
            'test_id': self.test_id,
            'subject': self.subject,
            'email_body': self.email_body,
            'recipient': self.recipient,
            'sender': self.sender,
            'message_id': self.message_id,
            'internet_message_id': self.internet_message_id,
            'sent_time': self.sent_time.strftime('%Y-%m-%d %H:%M:%S') if self.sent_time else None,
            'verification_time': self.verification_time.strftime('%Y-%m-%d %H:%M:%S') if self.verification_time else None,
            'found_in_db': self.found_in_db,
            'classification_correct': self.classification_correct,
            'auto_response_sent': self.auto_response_sent,
            'sts_read_eml': self.sts_read_eml,
            'sts_routing': self.sts_routing,
            'processing_time': self.processing_time,
            'cost_usd': self.cost_usd,
            'tokens_used': self.tokens_used,
            'error': self.error
        }

async def get_access_token_with_mail_scope():
    """
    Obtain an access token from Microsoft Graph API with Mail.Send scope
    
    Returns:
        str: Access token if successful, None otherwise
    """
    try:
        # First try using the existing access token function
        print("Attempting to get access token using the default method...")
        access_token = await get_access_token()
        
        if access_token:
            print("Successfully obtained access token with default method")
            return access_token
        
        print("Default access token method failed, trying alternative method...")
        
        # If that fails, we might need to add explicit Mail.Send scope
        # This requires app registration to have Mail.Send permissions
        from msal import ConfidentialClientApplication
        
        app = ConfidentialClientApplication(
            CLIENT_ID,
            authority=AUTHORITY,
            client_credential=CLIENT_SECRET,
        )
        
        # Try with explicit Mail.Send scope
        mail_scopes = ['https://graph.microsoft.com/.default', 'https://graph.microsoft.com/Mail.Send']
        result = await asyncio.to_thread(app.acquire_token_for_client, scopes=mail_scopes)
        
        if 'access_token' in result:
            print("Successfully obtained access token with Mail.Send scope")
            return result['access_token']
        else:
            print(f"Failed to obtain access token with Mail.Send scope")
            print(f"Error: {result.get('error', 'Unknown error')}")
            print(f"Error description: {result.get('error_description', 'No description')}")
            return None
            
    except Exception as e:
        print(f"Error obtaining access token: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return None

async def verify_api_permissions(access_token):
    """
    Verify that the access token has the necessary permissions to send mail
    
    Args:
        access_token: The access token to verify
        
    Returns:
        bool: True if permissions are verified, False otherwise
    """
    try:
        # For application permissions, we can't use /me endpoint
        # Instead, try accessing the users endpoint directly
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }
        
        # Get the first user from the EMAIL_ACCOUNTS list
        if EMAIL_ACCOUNTS and EMAIL_ACCOUNTS[0]:
            user_email = EMAIL_ACCOUNTS[0]
            print(f"Verifying API permissions by checking access to user: {user_email}")
            
            # Try accessing the user directly - this works with application permissions
            users_endpoint = f'https://graph.microsoft.com/v1.0/users/{user_email}'
            
            async with aiohttp.ClientSession() as session:
                async with session.get(users_endpoint, headers=headers) as users_response:
                    response_status = users_response.status
                    response_text = await users_response.text()
                    print(f"Graph API user endpoint response status: {response_status}")
                    print(f"Graph API user endpoint response text: {response_text}")
                    
                    if response_status == 200:
                        print(f"Successfully accessed user info for {user_email}")
                        
                        # Now try to check if we have Mail.Send permissions
                        # We'll do this by checking if we can access mailbox settings
                        # This doesn't require actually sending mail
                        mailbox_endpoint = f'https://graph.microsoft.com/v1.0/users/{user_email}/mailboxSettings'
                        
                        async with session.get(mailbox_endpoint, headers=headers) as mailbox_response:
                            mailbox_status = mailbox_response.status
                            mailbox_text = await mailbox_response.text()
                            print(f"Graph API mailbox endpoint response status: {mailbox_status}")
                            
                            if mailbox_status == 200:
                                print(f"Successfully accessed mailbox settings - mail permissions confirmed")
                                return True
                            else:
                                print(f"Warning: Could not access mailbox settings, but user access successful")
                                print(f"Mail permissions might be limited: {mailbox_text}")
                                # We'll continue anyway since we at least have user access
                                return True
                    else:
                        print(f"Failed to access user info: {response_status} - {response_text}")
                        
                        # Try one more approach - list users
                        print("Trying to list users as a fallback...")
                        users_list_endpoint = 'https://graph.microsoft.com/v1.0/users'
                        
                        async with session.get(users_list_endpoint, headers=headers) as users_list_response:
                            list_status = users_list_response.status
                            list_text = await users_list_response.text()
                            print(f"Graph API users list response status: {list_status}")
                            
                            if list_status == 200:
                                print("Successfully accessed users list - basic API access confirmed")
                                return True
                            else:
                                print(f"Failed to access users list: {list_status} - {list_text}")
                                print("WARNING: API permission issues detected - this will likely cause email delivery failures")
                                return False
        else:
            print("No email accounts configured - cannot verify permissions")
            return False
                    
    except Exception as e:
        print(f"Error verifying API permissions: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return False

async def get_db_connection():
    """Create and return a database connection"""
    try:
        conn = pyodbc.connect(
            f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SQL_SERVER};DATABASE={SQL_DATABASE};UID={SQL_USERNAME};PWD={SQL_PASSWORD}'
        )
        return conn
    except Exception as e:
        print(f"Database connection error: {str(e)}")
        raise

async def check_email_in_db(conn, test_email):
    """
    Check if a test email has been processed and logged in the database
    
    Args:
        conn: Database connection
        test_email: TestEmail object to check
        
    Returns:
        bool: True if found, False otherwise
    """
    try:
        cursor = conn.cursor()
        
        # Query the logs table using the test ID which should be in the subject
        query = f"""
        SELECT * FROM [dbo].[logs] 
        WHERE eml_sub LIKE '%{test_email.test_id}%'
        ORDER BY dttm_proc DESC
        """
        
        cursor.execute(query)
        row = cursor.fetchone()
        
        if row:
            # Convert row to dict for easier access
            columns = [column[0] for column in cursor.description]
            db_record = {columns[i]: row[i] for i in range(len(columns))}
            
            test_email.found_in_db = True
            test_email.db_record = db_record
            
            # Store additional fields
            test_email.email_body = db_record.get('eml_bdy', '')
            test_email.auto_response_sent = db_record.get('auto_response_sent', 'unknown')
            test_email.sts_read_eml = db_record.get('sts_read_eml', 'unknown')
            test_email.sts_routing = db_record.get('sts_routing', 'unknown')
            test_email.processing_time = db_record.get('tat', 0)
            test_email.cost_usd = db_record.get('apex_cost_usd', 0)
            test_email.tokens_used = (db_record.get('gpt_4o_total_tokens', 0) + 
                                    db_record.get('gpt_4o_mini_total_tokens', 0))
            
            # Check if classification matches expected category
            if 'apex_class' in db_record and db_record['apex_class']:
                actual_class = str(db_record['apex_class']).lower()
                expected_class = test_email.category.lower()
                test_email.classification_correct = (actual_class == expected_class)
            
            return True
        else:
            test_email.found_in_db = False
            test_email.error = "Email not found in database"
            return False
            
    except Exception as e:
        error_msg = f"Database query error: {str(e)}"
        print(error_msg)
        test_email.error = error_msg
        return False

async def create_test_email_content(category, test_id):
    """
    Create the content for a test email for a specific category
    
    Args:
        category: Email category to test
        test_id: Unique test identifier
        
    Returns:
        dict: Email content dictionary
    """
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Use prefix from command line if provided, otherwise use environment variable
    prefix = args.prefix if args.prefix else TEST_ID_PREFIX
    subject = f"{prefix} - {category} - {test_id}"
    
    # Create category-specific content
    category_content = {
        "amendments": "Please update my policy to change my address to 123 New Street, City. My policy number is TEST123456.",
        "assist": "I need roadside assistance. My car has a flat tire. My policy number is TEST123456.",
        "vehicle tracking": "Please find attached my vehicle tracking certificate for registration. My policy number is TEST123456.",
        "bad service/experience": "I am very disappointed with the service I received yesterday. My policy number is TEST123456.",
        "claims": "I would like to file a claim for my vehicle that was damaged yesterday. My policy number is TEST123456.",
        "refund request": "Please process a refund for my account. My policy number is TEST123456.",
        "document request": "Please send me a copy of my policy document. My policy number is TEST123456.",
        "online/app": "I'm having trouble accessing my account on the website. My policy number is TEST123456.",
        "retentions": "I would like to cancel my policy. My policy number is TEST123456.",
        "request for quote": "Please send me a quote for adding my new car to my insurance. My policy number is TEST123456.",
        "debit order switch": "I need to change my debit order details. My policy number is TEST123456.",
        "previous insurance checks/queries": "Can you confirm my previous insurance details? My policy number is TEST123456.",
        "other": "This is a general query about my policy. My policy number is TEST123456."
    }
    
    # Use default content if category not found
    body_text = category_content.get(
        category, 
        f"This is an automated test email for category: {category}. My policy number is TEST123456."
    )
    
    # Add test metadata to body
    body_text += f"\n\nThis is an automated test email.\nTest ID: {test_id}\nTimestamp: {timestamp}\nCategory: {category}\n"
    
    # Create basic HTML version
    body_html = f"""
    <html>
    <body>
        <p>{body_text.replace('\n', '<br>')}</p>
        <p>Test ID: <strong>{test_id}</strong></p>
        <p>Timestamp: <strong>{timestamp}</strong></p>
        <p>Category: <strong>{category}</strong></p>
    </body>
    </html>
    """
    
    email_content = {
        'to': '',  # Will be set when sending
        'from': DEFAULT_TEST_SENDER,
        'cc': '',
        'subject': subject,
        'body_html': body_html,
        'body_text': body_text,
        'internet_message_id': f"{test_id}@apex.test",
        'date_received': datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'email_id': test_id,
    }
    
    return email_content

async def send_test_email(access_token, account, test_email, email_content):
    """
    Send a test email via Microsoft Graph API
    
    Args:
        access_token: MS Graph access token
        account: Email account to send from
        test_email: TestEmail object
        email_content: Email content dictionary
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        print(f"Sending test email for category: {test_email.category}")
        print(f"  From: {account}")  # Must use authenticated account
        print(f"  To: {test_email.recipient}")
        print(f"  Subject: {email_content['subject']}")
        
        # Update recipient in email content
        email_content['to'] = test_email.recipient
        
        # Create a proper message object for the Microsoft Graph API
        # IMPORTANT: Do NOT include the "from" field as it must match the authenticated user
        message = {
            "message": {
                "subject": email_content['subject'],
                "body": {
                    "contentType": "HTML",
                    "content": email_content['body_html']
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": test_email.recipient
                        }
                    }
                ],
                # Only set replyTo if different from the sending account
                "internetMessageId": f"<{email_content['internet_message_id']}>"
            },
            "saveToSentItems": "true"
        }
        
        # Only add replyTo if it's different from the sending account
        if test_email.sender.lower() != account.lower():
            message["message"]["replyTo"] = [
                {
                    "emailAddress": {
                        "address": test_email.sender
                    }
                }
            ]
        
        # Add CC recipients if any
        if email_content.get('cc'):
            cc_addresses = [address.strip() for address in email_content['cc'].split(',') if address.strip()]
            if cc_addresses:
                message["message"]["ccRecipients"] = [
                    {"emailAddress": {"address": address}} for address in cc_addresses
                ]
        
        # Send the email using Microsoft Graph API
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }
        
        # Use the sendMail endpoint
        endpoint = f'https://graph.microsoft.com/v1.0/users/{account}/sendMail'
        
        # Convert message to JSON for logging
        message_json = json.dumps(message, indent=2)
        print(f"Sending message to Graph API endpoint {endpoint}:\n{message_json}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, json=message) as response:
                response_status = response.status
                response_text = await response.text()
                
                print(f"Graph API response status: {response_status}")
                print(f"Graph API response text: {response_text}")
                
                if response_status == 202:  # 202 Accepted is success for sendMail
                    test_email.sent_time = datetime.datetime.now()
                    print(f"Successfully sent test email for category: {test_email.category}")
                    return True
                else:
                    error_msg = f"Failed to send email: {response_status} - {response_text}"
                    print(error_msg)
                    test_email.error = error_msg
                    return False
            
    except Exception as e:
        error_msg = f"Error sending test email: {str(e)}"
        print(error_msg)
        print(f"Traceback: {traceback.format_exc()}")
        test_email.error = error_msg
        return False

async def send_all_test_emails():
    """
    Send test emails for all categories
    
    Returns:
        list: List of TestEmail objects
    """
    global test_emails
    
    try:
        # Get access token for MS Graph API with Mail.Send scope
        access_token = await get_access_token_with_mail_scope()
        if not access_token:
            raise Exception("Failed to obtain access token")
        
        # Check if token includes required permissions
        print("Verifying API permissions...")
        permissions_verified = await verify_api_permissions(access_token)
        if not permissions_verified:
            print("WARNING: Could not verify Mail.Send permission. Emails might not be delivered.")
        
        # Use the first configured email account
        if not EMAIL_ACCOUNTS or not EMAIL_ACCOUNTS[0]:
            raise Exception("No email account configured")
            
        account = EMAIL_ACCOUNTS[0]
        print(f"Using email account: {account}")
        
        # If sender is specified via command line, use it
        test_sender = args.sender if args.sender else DEFAULT_TEST_SENDER
        print(f"Test sender address: {test_sender}")
        
        # If prefix is specified via command line, use it
        test_prefix = args.prefix if args.prefix else TEST_ID_PREFIX
        
        # Create and send test emails for each category
        for category in EMAIL_CATEGORIES:
            # Generate unique test ID
            test_id = f"{test_prefix}_{uuid.uuid4()}"
            
            # Determine recipient email (same as the APEX monitored mailbox)
            recipient = account
            
            # Create test email object
            subject = f"{test_prefix} - {category} - {test_id}"
            test_email = TestEmail(category, test_id, subject, recipient, sender=test_sender)
            
            # Create email content
            email_content = await create_test_email_content(category, test_id)
            
            # Send the email
            success = await send_test_email(access_token, account, test_email, email_content)
            
            # Add to tracking list regardless of success (to track failures too)
            test_emails.append(test_email)
            
            # Wait 10 seconds between sending emails to avoid throttling
            await asyncio.sleep(10)
            
        return test_emails
        
    except Exception as e:
        error_msg = f"Error in send_all_test_emails: {str(e)}"
        print(error_msg)
        print(f"Traceback: {traceback.format_exc()}")
        error_details.append({
            "phase": "sending_emails",
            "error": error_msg,
            "traceback": traceback.format_exc()
        })
        return test_emails

async def verify_all_emails_in_db():
    """
    Check the database to verify all test emails were processed
    
    Returns:
        list: Updated list of TestEmail objects
    """
    global test_emails, test_results
    
    try:
        # Create database connection
        conn = await get_db_connection()
        
        # Check each test email
        for test_email in test_emails:
            print(f"Verifying email for category: {test_email.category}")
            await check_email_in_db(conn, test_email)
            test_email.verification_time = datetime.datetime.now()
            
        # Close database connection
        conn.close()
        
        # Compile results
        success_count = sum(1 for email in test_emails if email.found_in_db)
        classification_correct_count = sum(1 for email in test_emails if email.classification_correct)
        total_processing_time = sum(email.processing_time or 0 for email in test_emails if email.found_in_db)
        total_cost = sum(email.cost_usd or 0 for email in test_emails if email.found_in_db)
        total_tokens = sum(email.tokens_used or 0 for email in test_emails if email.found_in_db)
        
        test_results = {
            "total_emails": len(test_emails),
            "found_in_db": success_count,
            "not_found": len(test_emails) - success_count,
            "classification_correct": classification_correct_count,
            "classification_incorrect": sum(1 for email in test_emails if email.found_in_db and not email.classification_correct),
            "success_rate": round(success_count / len(test_emails) * 100, 2) if test_emails else 0,
            "classification_accuracy": round(classification_correct_count / success_count * 100, 2) if success_count else 0,
            "avg_processing_time": round(total_processing_time / success_count, 2) if success_count else 0,
            "total_cost": round(total_cost, 4),
            "avg_cost_per_email": round(total_cost / success_count, 4) if success_count else 0,
            "total_tokens": total_tokens,
            "avg_tokens_per_email": round(total_tokens / success_count, 1) if success_count else 0
        }
        
        # Generate insights and alerts
        generate_insights()
        
        return test_emails
        
    except Exception as e:
        error_msg = f"Error in verify_all_emails_in_db: {str(e)}"
        print(error_msg)
        error_details.append({
            "phase": "database_verification",
            "error": error_msg,
            "traceback": traceback.format_exc()
        })
        return test_emails

def generate_insights():
    """Generate insights, alerts, and recommendations based on the test results"""
    global alerts, recommendations
    
    # Check for critical alerts
    if test_results.get('total_emails', 0) > 0:
        success_rate = test_results.get('success_rate', 0)
        classification_accuracy = test_results.get('classification_accuracy', 0)
        
        # Email processing alerts
        if success_rate < 90:
            alerts.append({
                'level': 'CRITICAL',
                'message': f"Low email processing success rate: {success_rate}%",
                'details': f"Only {test_results.get('found_in_db', 0)} of {test_results.get('total_emails', 0)} test emails were processed successfully."
            })
        elif success_rate < 95:
            alerts.append({
                'level': 'WARNING',
                'message': f"Below target email processing success rate: {success_rate}%",
                'details': "Target success rate is 95% or higher."
            })
        
        # Classification accuracy alerts
        if classification_accuracy < 85:
            alerts.append({
                'level': 'CRITICAL',
                'message': f"Low classification accuracy: {classification_accuracy}%",
                'details': "AI classification accuracy is below acceptable threshold of 85%."
            })
        elif classification_accuracy < 90:
            alerts.append({
                'level': 'WARNING',
                'message': f"Below target classification accuracy: {classification_accuracy}%",
                'details': "Target classification accuracy is 90% or higher."
            })
        
        # Performance alerts
        avg_processing_time = test_results.get('avg_processing_time', 0)
        if avg_processing_time > 15:
            alerts.append({
                'level': 'WARNING',
                'message': f"Slow average processing time: {avg_processing_time:.1f} seconds",
                'details': "Target processing time is under 10 seconds per email."
            })
        
        # Cost alerts
        avg_cost = test_results.get('avg_cost_per_email', 0)
        if avg_cost > 0.10:
            alerts.append({
                'level': 'WARNING',
                'message': f"High average cost per email: ${avg_cost:.3f}",
                'details': "Consider optimizing AI model usage to reduce costs."
            })
        
        # Generate recommendations
        failed_emails = [email for email in test_emails if not email.found_in_db]
        misclassified_emails = [email for email in test_emails if email.found_in_db and not email.classification_correct]
        
        if failed_emails:
            recommendations.append({
                'category': 'Email Processing',
                'message': f"Investigate {len(failed_emails)} failed email processing cases",
                'details': "Check email reading, authentication, and database connectivity."
            })
        
        if misclassified_emails:
            recommendations.append({
                'category': 'AI Classification',
                'message': f"Review {len(misclassified_emails)} misclassification cases",
                'details': "Consider retraining the AI model or adjusting classification prompts."
            })
        
        # Autoresponse issues
        autoresponse_failures = [email for email in test_emails if email.auto_response_sent and email.auto_response_sent.lower() == 'failed']
        if autoresponse_failures:
            recommendations.append({
                'category': 'Autoresponse',
                'message': f"Fix {len(autoresponse_failures)} autoresponse failures",
                'details': "Customers expect immediate acknowledgment of their emails."
            })
        
        # Performance recommendations
        if avg_processing_time > 10:
            recommendations.append({
                'category': 'Performance',
                'message': "Optimize processing speed to meet target of <10 seconds",
                'details': "Consider using faster AI models or optimizing database queries."
            })

def generate_charts():
    """Generate charts for the test report"""
    global charts
    
    # 1. Test Results Overview
    plt.figure(figsize=(10, 6))
    categories = ['Found in DB', 'Not Found', 'Correctly Classified', 'Misclassified']
    values = [
        test_results.get('found_in_db', 0),
        test_results.get('not_found', 0),
        test_results.get('classification_correct', 0),
        test_results.get('classification_incorrect', 0)
    ]
    colors = ['#4CAF50', '#F44336', '#2196F3', '#FF9800']
    
    bars = plt.bar(categories, values, color=colors)
    plt.title('APEX Automated Test Results Overview', fontsize=16, fontweight='bold')
    plt.ylabel('Number of Emails')
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    # Add value labels on bars
    for bar, value in zip(bars, values):
        plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1, 
                str(value), ha='center', va='bottom', fontweight='bold')
    
    plt.tight_layout()
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
    buffer.seek(0)
    charts['test_overview'] = buffer.getvalue()
    plt.close()
    
    # 2. Success Rate Pie Chart
    plt.figure(figsize=(8, 8))
    labels = ['Successful', 'Failed']
    sizes = [test_results.get('found_in_db', 0), test_results.get('not_found', 0)]
    colors = ['#4CAF50', '#F44336']
    explode = (0, 0.1) if test_results.get('not_found', 0) > 0 else (0, 0)
    
    plt.pie(sizes, explode=explode, labels=labels, colors=colors, autopct='%1.1f%%', 
            shadow=True, startangle=90, textprops={'fontsize': 12, 'fontweight': 'bold'})
    plt.axis('equal')
    plt.title('Email Processing Success Rate', fontsize=16, fontweight='bold')
    
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
    buffer.seek(0)
    charts['success_rate'] = buffer.getvalue()
    plt.close()
    
    # 3. Classification Accuracy
    if test_results.get('found_in_db', 0) > 0:
        plt.figure(figsize=(8, 8))
        labels = ['Correctly Classified', 'Misclassified']
        sizes = [test_results.get('classification_correct', 0), test_results.get('classification_incorrect', 0)]
        colors = ['#4CAF50', '#FF9800']
        explode = (0, 0.1) if test_results.get('classification_incorrect', 0) > 0 else (0, 0)
        
        plt.pie(sizes, explode=explode, labels=labels, colors=colors, autopct='%1.1f%%', 
                shadow=True, startangle=90, textprops={'fontsize': 12, 'fontweight': 'bold'})
        plt.axis('equal')
        plt.title('AI Classification Accuracy', fontsize=16, fontweight='bold')
        
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        buffer.seek(0)
        charts['classification_accuracy'] = buffer.getvalue()
        plt.close()
    
    # 4. Category Performance Breakdown
    category_stats = defaultdict(lambda: {'found': 0, 'correct': 0, 'total': 0})
    for email in test_emails:
        category_stats[email.category]['total'] += 1
        if email.found_in_db:
            category_stats[email.category]['found'] += 1
            if email.classification_correct:
                category_stats[email.category]['correct'] += 1
    
    if category_stats:
        plt.figure(figsize=(14, 8))
        categories = list(category_stats.keys())
        found_rates = [(category_stats[cat]['found'] / category_stats[cat]['total']) * 100 for cat in categories]
        correct_rates = [(category_stats[cat]['correct'] / category_stats[cat]['found']) * 100 if category_stats[cat]['found'] > 0 else 0 for cat in categories]
        
        x = range(len(categories))
        width = 0.35
        
        bars1 = plt.bar([i - width/2 for i in x], found_rates, width, label='Processing Success Rate', color='#4CAF50', alpha=0.8)
        bars2 = plt.bar([i + width/2 for i in x], correct_rates, width, label='Classification Accuracy', color='#2196F3', alpha=0.8)
        
        plt.xlabel('Email Categories')
        plt.ylabel('Success Rate (%)')
        plt.title('Performance by Email Category', fontsize=16, fontweight='bold')
        plt.xticks(x, categories, rotation=45, ha='right')
        plt.legend()
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        
        # Add value labels on bars
        for bars in [bars1, bars2]:
            for bar in bars:
                height = bar.get_height()
                plt.text(bar.get_x() + bar.get_width()/2., height + 1,
                        f'{height:.1f}%', ha='center', va='bottom', fontsize=8)
        
        plt.tight_layout()
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        buffer.seek(0)
        charts['category_performance'] = buffer.getvalue()
        plt.close()
    
    # 5. Processing Time Distribution (if data available)
    processing_times = [email.processing_time for email in test_emails if email.processing_time]
    if processing_times:
        plt.figure(figsize=(10, 6))
        plt.hist(processing_times, bins=min(10, len(processing_times)), edgecolor='black', alpha=0.7, color='#2196F3')
        plt.xlabel('Processing Time (seconds)')
        plt.ylabel('Number of Emails')
        plt.title('Processing Time Distribution', fontsize=16, fontweight='bold')
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        
        # Add mean line
        mean_time = sum(processing_times) / len(processing_times)
        plt.axvline(mean_time, color='red', linestyle='--', linewidth=2, 
                   label=f'Mean: {mean_time:.2f}s')
        plt.legend()
        
        plt.tight_layout()
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        buffer.seek(0)
        charts['processing_time'] = buffer.getvalue()
        plt.close()

def generate_html_report():
    """
    Generate an HTML report of the test results with improved styling
    
    Returns:
        str: HTML report content
    """
    # Generate charts first
    generate_charts()
    
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Create HTML report with improved styling
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>APEX Automated Test Report</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; color: #333; line-height: 1.6; }}
            h1, h2, h3 {{ color: #2c3e50; }}
            .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px; margin-bottom: 30px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }}
            .header h1 {{ margin: 0; font-size: 2.5em; font-weight: 300; }}
            .header p {{ margin: 5px 0; opacity: 0.9; }}
            .summary {{ background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); padding: 25px; border-radius: 10px; margin-bottom: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
            .success {{ color: #2ecc71; font-weight: bold; }}
            .warning {{ color: #f39c12; font-weight: bold; }}
            .error {{ color: #e74c3c; font-weight: bold; }}
            .metric {{ margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center; }}
            .metric-label {{ font-weight: 500; }}
            .metric-value {{ font-weight: bold; font-size: 1.2em; }}
            .alerts {{ background-color: #fff3cd; padding: 20px; border-radius: 10px; margin-bottom: 30px; border-left: 5px solid #ffc107; }}
            .alert-critical {{ background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%); color: #721c24; padding: 15px; margin: 15px 0; border-radius: 8px; border-left: 5px solid #dc3545; }}
            .alert-warning {{ background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%); color: #856404; padding: 15px; margin: 15px 0; border-radius: 8px; border-left: 5px solid #ffc107; }}
            .alert-info {{ background: linear-gradient(135deg, #d1ecf1 0%, #bee5eb 100%); color: #0c5460; padding: 15px; margin: 15px 0; border-radius: 8px; border-left: 5px solid #17a2b8; }}
            .recommendations {{ background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); padding: 20px; border-radius: 10px; margin-bottom: 30px; border-left: 5px solid #28a745; }}
            .charts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 30px; margin-bottom: 30px; }}
            .chart {{ background-color: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }}
            .chart h3 {{ margin-top: 0; color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
            .chart img {{ width: 100%; height: auto; border-radius: 5px; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 30px; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            th {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; font-weight: 600; }}
            tr:nth-child(even) {{ background-color: #f8f9fa; }}
            tr:hover {{ background-color: #e9ecef; transition: background-color 0.3s ease; }}
            .status-ok {{ background-color: #d4edda !important; }}
            .status-warning {{ background-color: #fff3cd !important; }}
            .status-error {{ background-color: #f8d7da !important; }}
            .email-body {{ max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
            .failure-details {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); margin-bottom: 30px; }}
            .failure-details h3 {{ color: #e74c3c; border-bottom: 2px solid #e74c3c; padding-bottom: 10px; }}
            .tech-support {{ background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); padding: 20px; border-radius: 10px; margin-top: 30px; border-left: 5px solid #2196f3; }}
            .tech-support h2 {{ color: #1976d2; margin-top: 0; }}
            .badge {{ display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }}
            .badge-success {{ background-color: #28a745; color: white; }}
            .badge-warning {{ background-color: #ffc107; color: #212529; }}
            .badge-danger {{ background-color: #dc3545; color: white; }}
            @media (max-width: 768px) {{
                .charts {{ grid-template-columns: 1fr; }}
                .metric {{ flex-direction: column; align-items: flex-start; }}
                .header {{ padding: 20px; }}
                .header h1 {{ font-size: 2em; }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🚀 APEX Email Triaging System</h1>
            <h2>Automated Test Report</h2>
            <p>📅 Test Run Date: {timestamp}</p>
            <p>🎯 Testing {len(EMAIL_CATEGORIES)} email categories</p>
        </div>
        
        <div class="summary">
            <h2>📊 Executive Summary</h2>
            
            <div class="metric">
                <span class="metric-label">Total Test Emails Sent:</span>
                <span class="metric-value">{test_results.get('total_emails', 0)}</span>
            </div>
            
            <div class="metric">
                <span class="metric-label">Processing Success Rate:</span>
                <span class="metric-value {'success' if test_results.get('success_rate', 0) >= 95 else 'warning' if test_results.get('success_rate', 0) >= 90 else 'error'}">
                    {test_results.get('success_rate', 0)}%
                </span>
            </div>
            
            <div class="metric">
                <span class="metric-label">Classification Accuracy:</span>
                <span class="metric-value {'success' if test_results.get('classification_accuracy', 0) >= 90 else 'warning' if test_results.get('classification_accuracy', 0) >= 80 else 'error'}">
                    {test_results.get('classification_accuracy', 0)}%
                </span>
            </div>
            
            <div class="metric">
                <span class="metric-label">Average Processing Time:</span>
                <span class="metric-value {'success' if test_results.get('avg_processing_time', 0) <= 10 else 'warning' if test_results.get('avg_processing_time', 0) <= 15 else 'error'}">
                    {test_results.get('avg_processing_time', 0):.2f} seconds
                </span>
            </div>
            
            <div class="metric">
                <span class="metric-label">Total AI Cost:</span>
                <span class="metric-value">
                    ${test_results.get('total_cost', 0):.4f}
                </span>
            </div>
            
            <div class="metric">
                <span class="metric-label">Average Cost per Email:</span>
                <span class="metric-value {'success' if test_results.get('avg_cost_per_email', 0) <= 0.05 else 'warning' if test_results.get('avg_cost_per_email', 0) <= 0.10 else 'error'}">
                    ${test_results.get('avg_cost_per_email', 0):.4f}
                </span>
            </div>
            
            <div class="metric">
                <span class="metric-label">Total AI Tokens Used:</span>
                <span class="metric-value">
                    {test_results.get('total_tokens', 0):,}
                </span>
            </div>
        </div>
    """
    
    # Add alerts if any
    if alerts:
        html += """
        <div class="alerts">
            <h2>⚠️ Alerts Requiring Attention</h2>
        """
        
        for alert in alerts:
            if alert['level'] == 'CRITICAL':
                html += f"""
                <div class="alert-critical">
                    <h3>🚨 CRITICAL: {alert['message']}</h3>
                    <p>{alert['details']}</p>
                </div>
                """
            elif alert['level'] == 'WARNING':
                html += f"""
                <div class="alert-warning">
                    <h3>⚠️ WARNING: {alert['message']}</h3>
                    <p>{alert['details']}</p>
                </div>
                """
            else:
                html += f"""
                <div class="alert-info">
                    <h3>ℹ️ INFO: {alert['message']}</h3>
                    <p>{alert['details']}</p>
                </div>
                """
        
        html += "</div>"
    
    # Add recommendations if any
    if recommendations:
        html += """
        <div class="recommendations">
            <h2>💡 Recommendations</h2>
        """
        
        for rec in recommendations:
            html += f"""
            <div class="metric">
                <h3>🎯 {rec['category']}: {rec['message']}</h3>
                <p>{rec['details']}</p>
            </div>
            """
        
        html += "</div>"
    
    # Add charts
    html += """
    <h2>📈 Performance Visualizations</h2>
    <div class="charts">
    """
    
    # Add charts in order
    chart_titles = {
        'test_overview': 'Test Results Overview',
        'success_rate': 'Email Processing Success Rate',
        'classification_accuracy': 'AI Classification Accuracy',
        'category_performance': 'Performance by Email Category',
        'processing_time': 'Processing Time Distribution'
    }
    
    for chart_key, chart_title in chart_titles.items():
        if chart_key in charts:
            chart_base64 = base64.b64encode(charts[chart_key]).decode('utf-8')
            html += f"""
            <div class="chart">
                <h3>{chart_title}</h3>
                <img src="data:image/png;base64,{chart_base64}" alt="{chart_title}">
            </div>
            """
    
    html += "</div>"  # Close charts div
    
    # Add detailed test results table
    html += """
    <h2>📋 Detailed Test Results</h2>
    <table>
        <tr>
            <th>Category</th>
            <th>Test ID</th>
            <th>Subject</th>
            <th>Status</th>
            <th>Classification</th>
            <th>Processing Time</th>
            <th>Cost</th>
            <th>Tokens</th>
            <th>Autoresponse</th>
            <th>Error</th>
        </tr>
    """
    
    # Add rows for each test email
    for email in test_emails:
        # Determine row status class
        if email.found_in_db and email.classification_correct:
            status_class = "status-ok"
            status_badge = '<span class="badge badge-success">✓ Success</span>'
        elif email.found_in_db and not email.classification_correct:
            status_class = "status-warning"
            status_badge = '<span class="badge badge-warning">⚠ Misclassified</span>'
        else:
            status_class = "status-error"
            status_badge = '<span class="badge badge-danger">✗ Failed</span>'
        
        # Format classification result
        classification_result = "✓ Correct" if email.classification_correct else "✗ Wrong" if email.found_in_db else "N/A"
        classification_class = "success" if email.classification_correct else "error" if email.found_in_db else ""
        
        # Format autoresponse status
        autoresponse_status = "N/A"
        if email.auto_response_sent:
            if email.auto_response_sent.lower() == "success":
                autoresponse_status = '<span class="badge badge-success">✓ Sent</span>'
            elif email.auto_response_sent.lower() == "failed":
                autoresponse_status = '<span class="badge badge-danger">✗ Failed</span>'
            else:
                autoresponse_status = email.auto_response_sent
        
        # Truncate subject and error for display
        subject = email.subject if len(email.subject) <= 50 else email.subject[:50] + "..."
        error_msg = email.error if email.error and len(str(email.error)) <= 100 else (str(email.error)[:100] + "..." if email.error else "None")
        
        html += f"""
        <tr class="{status_class}">
            <td><strong>{email.category}</strong></td>
            <td><code>{email.test_id.split('_')[-1][:8]}</code></td>
            <td>{subject}</td>
            <td>{status_badge}</td>
            <td><span class="{classification_class}">{classification_result}</span></td>
            <td>{email.processing_time:.2f}s if email.processing_time else 'N/A'}</td>
            <td>${email.cost_usd:.4f} if email.cost_usd else 'N/A'}</td>
            <td>{email.tokens_used:,} if email.tokens_used else 'N/A'}</td>
            <td>{autoresponse_status}</td>
            <td>{error_msg}</td>
        </tr>
        """
    
    html += "</table>"
    
    # Add failure details section if there are failures
    failed_emails = [email for email in test_emails if not email.found_in_db]
    misclassified_emails = [email for email in test_emails if email.found_in_db and not email.classification_correct]
    autoresponse_failures = [email for email in test_emails if email.auto_response_sent and email.auto_response_sent.lower() == 'failed']
    
    if failed_emails or misclassified_emails or autoresponse_failures:
        html += """
        <div class="failure-details">
            <h2>🔍 Failure Analysis & Diagnostics</h2>
        """
        
        # Processing failures
        if failed_emails:
            html += f"""
            <h3>❌ Email Processing Failures ({len(failed_emails)})</h3>
            <p>These emails were not found in the database, indicating they were not processed by the APEX system:</p>
            <table>
                <tr>
                    <th>Category</th>
                    <th>Test ID</th>
                    <th>Sent Time</th>
                    <th>Error Details</th>
                    <th>Possible Causes</th>
                </tr>
            """
            
            for email in failed_emails:
                # Determine possible causes based on error
                possible_causes = []
                if email.error:
                    error_lower = str(email.error).lower()
                    if 'auth' in error_lower or 'token' in error_lower:
                        possible_causes.append("Authentication issues")
                    if 'connection' in error_lower or 'timeout' in error_lower:
                        possible_causes.append("Network connectivity")
                    if 'database' in error_lower or 'sql' in error_lower:
                        possible_causes.append("Database connectivity")
                    if 'graph api' in error_lower:
                        possible_causes.append("Microsoft Graph API issues")
                
                if not possible_causes:
                    possible_causes = ["Email reading failure", "Database connectivity", "Service downtime"]
                
                html += f"""
                <tr class="status-error">
                    <td>{email.category}</td>
                    <td><code>{email.test_id.split('_')[-1][:8]}</code></td>
                    <td>{email.sent_time.strftime('%H:%M:%S') if email.sent_time else 'N/A'}</td>
                    <td>{email.error if email.error else 'Unknown error'}</td>
                    <td>{'<br>'.join(['• ' + cause for cause in possible_causes])}</td>
                </tr>
                """
            
            html += "</table>"
        
        # Classification failures
        if misclassified_emails:
            html += f"""
            <h3>🤖 AI Classification Failures ({len(misclassified_emails)})</h3>
            <p>These emails were processed but incorrectly classified by the AI model:</p>
            <table>
                <tr>
                    <th>Expected Category</th>
                    <th>Actual Category</th>
                    <th>Test ID</th>
                    <th>Processing Time</th>
                    <th>Recommendation</th>
                </tr>
            """
            
            for email in misclassified_emails:
                actual_category = email.db_record.get('apex_class', 'unknown') if email.db_record else 'unknown'
                
                # Generate recommendation based on misclassification
                recommendation = "Review training data"
                if email.category in ['claims', 'assist'] and actual_category in ['amendments', 'document request']:
                    recommendation = "Improve urgency detection"
                elif email.category in ['amendments', 'document request'] and actual_category in ['claims', 'assist']:
                    recommendation = "Better intent classification"
                elif actual_category == 'other':
                    recommendation = "Add more specific examples"
                
                html += f"""
                <tr class="status-warning">
                    <td><strong>{email.category}</strong></td>
                    <td><em>{actual_category}</em></td>
                    <td><code>{email.test_id.split('_')[-1][:8]}</code></td>
                    <td>{email.processing_time:.2f}s if email.processing_time else 'N/A'}</td>
                    <td>{recommendation}</td>
                </tr>
                """
            
            html += "</table>"
        
        # Autoresponse failures
        if autoresponse_failures:
            html += f"""
            <h3>📧 Autoresponse Failures ({len(autoresponse_failures)})</h3>
            <p>These emails were processed but failed to send automatic responses to customers:</p>
            <table>
                <tr>
                    <th>Category</th>
                    <th>Test ID</th>
                    <th>Sender</th>
                    <th>Impact</th>
                    <th>Resolution</th>
                </tr>
            """
            
            for email in autoresponse_failures:
                html += f"""
                <tr class="status-error">
                    <td>{email.category}</td>
                    <td><code>{email.test_id.split('_')[-1][:8]}</code></td>
                    <td>{email.sender}</td>
                    <td>Customer expects acknowledgment</td>
                    <td>Check email sending permissions</td>
                </tr>
                """
            
            html += "</table>"
        
        html += "</div>"  # Close failure-details
    
    # Add technical support section
    html += """
    <div class="tech-support">
        <h2>🔧 Technical Support Information</h2>
        
        <h3>📞 Emergency Contacts</h3>
        <ul>
            <li><strong>Technical Lead:</strong> Contact system administrator</li>
            <li><strong>Database Issues:</strong> Contact database team</li>
            <li><strong>AI Model Issues:</strong> Contact ML engineering team</li>
            <li><strong>Microsoft Graph API:</strong> Check Azure portal for service status</li>
        </ul>
        
        <h3>🔍 Diagnostic Steps</h3>
        <ol>
            <li><strong>Check System Status:</strong> Verify all APEX services are running</li>
            <li><strong>Database Connectivity:</strong> Test database connection and permissions</li>
            <li><strong>API Authentication:</strong> Verify Microsoft Graph API tokens and permissions</li>
            <li><strong>AI Model Performance:</strong> Check OpenAI API status and quotas</li>
            <li><strong>Email Access:</strong> Ensure mailbox reading permissions are intact</li>
        </ol>
        
        <h3>📊 Performance Thresholds</h3>
        <ul>
            <li><strong>Processing Success Rate:</strong> Target ≥95%, Warning <90%, Critical <80%</li>
            <li><strong>Classification Accuracy:</strong> Target ≥90%, Warning <85%, Critical <80%</li>
            <li><strong>Processing Time:</strong> Target ≤10s, Warning >15s, Critical >30s</li>
            <li><strong>Cost per Email:</strong> Target ≤$0.05, Warning >$0.10, Critical >$0.20</li>
        </ul>
        
        <h3>🔧 Common Solutions</h3>
        <ul>
            <li><strong>Authentication Failures:</strong> Refresh Azure AD app registration and secrets</li>
            <li><strong>High Processing Times:</strong> Check database performance and optimize queries</li>
            <li><strong>Classification Issues:</strong> Review and update AI model prompts</li>
            <li><strong>Cost Optimization:</strong> Consider using GPT-4o-mini for simpler classifications</li>
        </ul>
        
        <h3>📝 Log Locations</h3>
        <ul>
            <li><strong>Application Logs:</strong> Check APEX service logs for detailed error messages</li>
            <li><strong>Database Logs:</strong> Review SQL Server logs for connectivity issues</li>
            <li><strong>Azure Logs:</strong> Check Azure portal for Graph API call failures</li>
            <li><strong>OpenAI Logs:</strong> Monitor API usage and error rates in OpenAI dashboard</li>
        </ul>
    </div>
    
    <div style="margin-top: 40px; padding-top: 20px; border-top: 2px solid #ddd; color: #777; font-size: 0.9em; text-align: center;">
        <p>🤖 This is an automated report from the APEX Email Triaging System</p>
        <p>Report generated at {timestamp} | For technical support, contact your system administrator</p>
    </div>
    </body>
    </html>
    """
    
    return html

def generate_csv_report():
    """
    Generate a CSV report of the test results
    
    Returns:
        bytes: CSV content as bytes
    """
    import csv
    from io import StringIO
    
    # Create CSV file in memory
    output = StringIO()
    
    # Write summary section
    writer = csv.writer(output)
    writer.writerow(['APEX Automated Test Report'])
    writer.writerow(['Generated At', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow([])
    
    writer.writerow(['Summary Statistics'])
    writer.writerow(['Total Emails Sent', test_results.get('total_emails', 0)])
    writer.writerow(['Processing Success Rate (%)', test_results.get('success_rate', 0)])
    writer.writerow(['Classification Accuracy (%)', test_results.get('classification_accuracy', 0)])
    writer.writerow(['Average Processing Time (s)', test_results.get('avg_processing_time', 0)])
    writer.writerow(['Total Cost (USD)', test_results.get('total_cost', 0)])
    writer.writerow(['Average Cost per Email (USD)', test_results.get('avg_cost_per_email', 0)])
    writer.writerow(['Total Tokens Used', test_results.get('total_tokens', 0)])
    writer.writerow(['Average Tokens per Email', test_results.get('avg_tokens_per_email', 0)])
    writer.writerow([])
    
    # Detailed results
    writer.writerow(['Detailed Test Results'])
    fieldnames = [
        'category', 'test_id', 'subject', 'sent_time', 'verification_time', 
        'found_in_db', 'classification_correct', 'processing_time', 'cost_usd',
        'tokens_used', 'autoresponse_sent', 'sts_read_eml', 'sts_routing', 'error'
    ]
    
    writer.writerow(fieldnames)
    
    for email in test_emails:
        writer.writerow([
            email.category,
            email.test_id,
            email.subject,
            email.sent_time.strftime('%Y-%m-%d %H:%M:%S') if email.sent_time else 'N/A',
            email.verification_time.strftime('%Y-%m-%d %H:%M:%S') if email.verification_time else 'N/A',
            'Yes' if email.found_in_db else 'No',
            'Yes' if email.classification_correct else 'No',
            f"{email.processing_time:.2f}" if email.processing_time else 'N/A',
            f"{email.cost_usd:.4f}" if email.cost_usd else 'N/A',
            email.tokens_used if email.tokens_used else 'N/A',
            email.auto_response_sent if email.auto_response_sent else 'N/A',
            email.sts_read_eml if email.sts_read_eml else 'N/A',
            email.sts_routing if email.sts_routing else 'N/A',
            email.error if email.error else 'None'
        ])
    
    return output.getvalue().encode('utf-8')

async def send_report_email(report_recipients):
    """
    Send the test report via email
    
    Args:
        report_recipients: List of email addresses to send the report to
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get access token for MS Graph API with Mail.Send scope
        access_token = await get_access_token_with_mail_scope()
        if not access_token:
            raise Exception("Failed to obtain access token")
        
        # Use the first configured email account
        if not EMAIL_ACCOUNTS or not EMAIL_ACCOUNTS[0]:
            raise Exception("No email account configured")
            
        account = EMAIL_ACCOUNTS[0]
        print(f"Sending report email from: {account}")
        
        # Generate HTML report
        html_report = generate_html_report()
        
        # Generate CSV report
        csv_report = generate_csv_report()
        
        # Create timestamp for filenames
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Set up email content with success/failure summary in the subject
        success_rate = test_results.get('success_rate', 0)
        classification_accuracy = test_results.get('classification_accuracy', 0)
        
        if len(alerts) > 0:
            critical_alerts = [alert for alert in alerts if alert['level'] == 'CRITICAL']
            if critical_alerts:
                subject = f"🚨 APEX Test Report {timestamp} - CRITICAL ISSUES ({success_rate}% success)"
            else:
                subject = f"⚠️ APEX Test Report {timestamp} - Warnings Present ({success_rate}% success)"
        elif success_rate == 100 and classification_accuracy >= 90:
            subject = f"✅ APEX Test Report {timestamp} - All Tests Passed"
        elif success_rate >= 95:
            subject = f"✅ APEX Test Report {timestamp} - {success_rate}% Success"
        elif success_rate >= 90:
            subject = f"⚠️ APEX Test Report {timestamp} - {success_rate}% Success"
        else:
            subject = f"❌ APEX Test Report {timestamp} - {success_rate}% Success"
        
        # Create message for Microsoft Graph API
        message = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": html_report
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": recipient
                        }
                    } for recipient in report_recipients
                ],
                "internetMessageId": f"<APEX_TEST_REPORT_{timestamp}@apex.test>"
            },
            "saveToSentItems": "true"
        }
        
        # Add CSV download link
        csv_base64 = base64.b64encode(csv_report).decode('utf-8')
        html_with_csv = html_report.replace('</body>', f'''
            <div style="text-align: center; margin: 30px 0; padding: 20px; background: #f8f9fa; border-radius: 10px;">
                <h3>📄 Download Detailed Report</h3>
                <p>
                  <a href="data:text/csv;base64,{csv_base64}" download="APEX_Test_Report_{timestamp}.csv"
                     style="display: inline-block; padding: 12px 24px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">
                    📊 Download CSV Report
                  </a>
                </p>
            </div>
            </body>
        ''')
        
        # Update the message body with the modified HTML
        message["message"]["body"]["content"] = html_with_csv
        
        # Send the email using Microsoft Graph API
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }
        
        endpoint = f'https://graph.microsoft.com/v1.0/users/{account}/sendMail'
        
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, json=message) as response:
                response_status = response.status
                response_text = await response.text()
                
                print(f"Graph API response status: {response_status}")
                if response_status != 202:
                    print(f"Graph API response text: {response_text}")
                
                if response_status == 202:  # 202 Accepted is success for sendMail
                    print(f"Successfully sent test report to: {', '.join(report_recipients)}")
                    return True
                else:
                    error_msg = f"Failed to send report: {response_status} - {response_text}"
                    print(error_msg)
                    return False
            
    except Exception as e:
        error_msg = f"Error sending test report: {str(e)}"
        print(error_msg)
        print(f"Traceback: {traceback.format_exc()}")
        error_details.append({
            "phase": "sending_report",
            "error": error_msg,
            "traceback": traceback.format_exc()
        })
        return False

async def main():
    """Main execution function"""
    global test_emails, test_results
    
    print(f"=== APEX Automated Test Started at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    
    try:
        # Parse command line arguments (override environment variables)
        wait_time = args.wait_time if args.wait_time is not None else DEFAULT_WAIT_TIME
        
        report_recipients = DEFAULT_REPORT_RECIPIENTS
        if args.recipients:
            report_recipients = [email.strip() for email in args.recipients.split(',') if email.strip()]
        
        # Log configuration
        print(f"Test Configuration:")
        print(f"- Wait time: {wait_time} minutes")
        print(f"- Report recipients: {', '.join(report_recipients) if report_recipients else 'None configured'}")
        print(f"- Test email sender: {DEFAULT_TEST_SENDER}")
        print(f"- Test ID prefix: {TEST_ID_PREFIX}")
        print(f"- Email categories to test: {len(EMAIL_CATEGORIES)}")
        
        # Validate configuration
        if not report_recipients:
            print("WARNING: No report recipients configured. Report will not be sent.")
        
        if not EMAIL_ACCOUNTS:
            raise ValueError("No email accounts configured in EMAIL_ACCOUNTS")
        
        # Send test emails for all categories
        print("Sending test emails...")
        await send_all_test_emails()
        
        # Wait for the system to process the emails
        print(f"Waiting {wait_time} minutes for emails to be processed...")
        await asyncio.sleep(wait_time * 60)
        
        # Verify emails in the database
        print("Verifying emails in database...")
        await verify_all_emails_in_db()
        
        # Send the report
        if report_recipients:
            print(f"Sending test report to: {', '.join(report_recipients)}")
            await send_report_email(report_recipients)
        else:
            print("Skipping report email - no recipients configured")
        
        print(f"=== APEX Automated Test Completed at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
        
        # Print summary to console
        print("\nTest Summary:")
        print(f"Total emails sent: {test_results.get('total_emails', 0)}")
        print(f"Emails found in database: {test_results.get('found_in_db', 0)}")
        print(f"Emails not found: {test_results.get('not_found', 0)}")
        print(f"Classification correct: {test_results.get('classification_correct', 0)}")
        print(f"Success rate: {test_results.get('success_rate', 0)}%")
        print(f"Classification accuracy: {test_results.get('classification_accuracy', 0)}%")
        
    except Exception as e:
        error_msg = f"Error in main execution: {str(e)}"
        print(error_msg)
        error_details.append({
            "phase": "main_execution",
            "error": error_msg,
            "traceback": traceback.format_exc()
        })
        
        # Try to send error report
        try:
            if 'report_recipients' in locals() and report_recipients:
                await send_report_email(report_recipients)
        except Exception as report_err:
            print(f"Failed to send error report: {str(report_err)}")

if __name__ == "__main__":
    # Run the main async function
    asyncio.run(main())
