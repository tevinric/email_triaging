#!/usr/bin/env python3
"""
APEX Automated Testing Script

This script performs daily automated testing of the APEX email triaging solution by:
1. Sending test emails for each APEX category
2. Waiting for the system to process them
3. Verifying in the database that they were properly processed
4. Generating and sending a report email with results

Usage:
    python apex_automated_test.py [--recipients EMAIL1,EMAIL2] [--wait-time MINUTES]

Options:
    --recipients     Comma-separated list of email addresses to send the report to
    --wait-time      Wait time in minutes between sending test emails and checking DB (default: 3)
"""

import os
import sys
import time
import uuid
import asyncio
import datetime
import argparse
import pyodbc
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import json
import traceback
from tabulate import tabulate
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
import base64

# Import APEX components
from email_processor.email_client import get_access_token, forward_email
from apex_llm.apex_routing import ang_routings
from config import (
    CLIENT_ID, TENANT_ID, CLIENT_SECRET, AUTHORITY, SCOPE,
    SQL_SERVER, SQL_DATABASE, SQL_USERNAME, SQL_PASSWORD,
    EMAIL_ACCOUNTS
)

# Constants
TEST_ID_PREFIX = "APEX_AUTOMATED_TEST"
DEFAULT_WAIT_TIME = 3  # minutes
DEFAULT_REPORT_RECIPIENTS = ["your-email@example.com"]
EMAIL_CATEGORIES = list(ang_routings.keys())
DEFAULT_TEST_SENDER = "apex-test@example.com"

# Set up argument parsing
parser = argparse.ArgumentParser(description='APEX Automated Testing Script')
parser.add_argument('--recipients', type=str, help='Comma-separated list of email addresses to send the report to')
parser.add_argument('--wait-time', type=int, default=DEFAULT_WAIT_TIME, 
                    help=f'Wait time in minutes between sending test emails and checking DB (default: {DEFAULT_WAIT_TIME})')
args = parser.parse_args()

# Global variables to track test results
test_emails = []
test_results = []
error_details = []

class TestEmail:
    """Class to represent a test email and track its status"""
    
    def __init__(self, category, test_id, subject, recipient, sender=DEFAULT_TEST_SENDER):
        self.category = category
        self.test_id = test_id
        self.subject = subject
        self.recipient = recipient
        self.sender = sender
        self.message_id = None
        self.internet_message_id = None
        self.sent_time = None
        self.found_in_db = False
        self.db_record = None
        self.error = None
        self.classification_correct = False
        self.verification_time = None
    
    def to_dict(self):
        """Convert to dictionary for reporting"""
        return {
            'category': self.category,
            'test_id': self.test_id,
            'subject': self.subject,
            'recipient': self.recipient,
            'sender': self.sender,
            'message_id': self.message_id,
            'internet_message_id': self.internet_message_id,
            'sent_time': self.sent_time.strftime('%Y-%m-%d %H:%M:%S') if self.sent_time else None,
            'verification_time': self.verification_time.strftime('%Y-%m-%d %H:%M:%S') if self.verification_time else None,
            'found_in_db': self.found_in_db,
            'classification_correct': self.classification_correct,
            'error': self.error
        }

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
    subject = f"{TEST_ID_PREFIX} - {category} - {test_id}"
    
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
        
        # Update recipient in email content
        email_content['to'] = test_email.recipient
        
        # Use email_client.py's forward_email function to send the test email
        # In this case, we're not really forwarding, but using the function to create a new email
        result = await forward_email(
            access_token=access_token,
            user_id=account,
            message_id='draft',  # This won't be used since we're creating a new message
            original_sender=test_email.sender,
            forward_to=test_email.recipient,
            email_data=email_content,
            forwardMsg=f"APEX AUTOMATED TEST - {test_email.category}"
        )
        
        if result:
            test_email.sent_time = datetime.datetime.now()
            print(f"Successfully sent test email for category: {test_email.category}")
            return True
        else:
            test_email.error = "Failed to send email"
            print(f"Failed to send test email for category: {test_email.category}")
            return False
            
    except Exception as e:
        error_msg = f"Error sending test email: {str(e)}"
        print(error_msg)
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
        # Get access token for MS Graph API
        access_token = await get_access_token()
        if not access_token:
            raise Exception("Failed to obtain access token")
        
        # Use the first configured email account
        if not EMAIL_ACCOUNTS or not EMAIL_ACCOUNTS[0]:
            raise Exception("No email account configured")
            
        account = EMAIL_ACCOUNTS[0]
        
        # Create and send test emails for each category
        for category in EMAIL_CATEGORIES:
            # Generate unique test ID
            test_id = f"{TEST_ID_PREFIX}_{uuid.uuid4()}"
            
            # Determine recipient email (same as the APEX monitored mailbox)
            recipient = account
            
            # Create test email object
            subject = f"{TEST_ID_PREFIX} - {category} - {test_id}"
            test_email = TestEmail(category, test_id, subject, recipient)
            
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
        
        test_results = {
            "total_emails": len(test_emails),
            "found_in_db": success_count,
            "not_found": len(test_emails) - success_count,
            "classification_correct": classification_correct_count,
            "classification_incorrect": sum(1 for email in test_emails if email.found_in_db and not email.classification_correct),
            "success_rate": round(success_count / len(test_emails) * 100, 2) if test_emails else 0,
            "classification_accuracy": round(classification_correct_count / success_count * 100, 2) if success_count else 0
        }
        
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

def generate_html_report():
    """
    Generate an HTML report of the test results
    
    Returns:
        str: HTML report content
    """
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Create HTML report
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>APEX Automated Test Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            h1, h2 {{ color: #333366; }}
            .summary {{ background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
            .success {{ color: green; }}
            .warning {{ color: orange; }}
            .error {{ color: red; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
            tr:hover {{ background-color: #f5f5f5; }}
            .status-ok {{ background-color: #d4edda; }}
            .status-warning {{ background-color: #fff3cd; }}
            .status-error {{ background-color: #f8d7da; }}
        </style>
    </head>
    <body>
        <h1>APEX Automated Test Report</h1>
        <p>Report generated at: {timestamp}</p>
        
        <div class="summary">
            <h2>Summary</h2>
            <p>Total emails sent: <strong>{test_results.get('total_emails', 0)}</strong></p>
            <p>Emails found in database: <strong class="{'success' if test_results.get('found_in_db', 0) == test_results.get('total_emails', 0) else 'error'}">{test_results.get('found_in_db', 0)}</strong></p>
            <p>Emails not found: <strong class="{'success' if test_results.get('not_found', 0) == 0 else 'error'}">{test_results.get('not_found', 0)}</strong></p>
            <p>Classification correct: <strong class="{'success' if test_results.get('classification_correct', 0) == test_results.get('found_in_db', 0) else 'warning'}">{test_results.get('classification_correct', 0)}</strong></p>
            <p>Success rate: <strong class="{'success' if test_results.get('success_rate', 0) >= 90 else 'warning' if test_results.get('success_rate', 0) >= 75 else 'error'}">{test_results.get('success_rate', 0)}%</strong></p>
            <p>Classification accuracy: <strong class="{'success' if test_results.get('classification_accuracy', 0) >= 90 else 'warning' if test_results.get('classification_accuracy', 0) >= 75 else 'error'}">{test_results.get('classification_accuracy', 0)}%</strong></p>
        </div>
        
        <h2>Detailed Results</h2>
        <table>
            <tr>
                <th>Category</th>
                <th>Subject</th>
                <th>Sent Time</th>
                <th>Verification Time</th>
                <th>Found in DB</th>
                <th>Classification Correct</th>
                <th>Error</th>
            </tr>
    """
    
    # Add rows for each test email
    for email in test_emails:
        status_class = "status-ok" if email.found_in_db and email.classification_correct else \
                      "status-warning" if email.found_in_db and not email.classification_correct else \
                      "status-error"
        
        html += f"""
            <tr class="{status_class}">
                <td>{email.category}</td>
                <td>{email.subject}</td>
                <td>{email.sent_time.strftime('%Y-%m-%d %H:%M:%S') if email.sent_time else 'N/A'}</td>
                <td>{email.verification_time.strftime('%Y-%m-%d %H:%M:%S') if email.verification_time else 'N/A'}</td>
                <td>{'Yes' if email.found_in_db else 'No'}</td>
                <td>{'Yes' if email.classification_correct else 'No'}</td>
                <td>{email.error if email.error else 'None'}</td>
            </tr>
        """
    
    # Add error details if any
    if error_details:
        html += """
        <h2>Error Details</h2>
        <table>
            <tr>
                <th>Phase</th>
                <th>Error</th>
            </tr>
        """
        
        for error in error_details:
            html += f"""
            <tr class="status-error">
                <td>{error.get('phase', 'unknown')}</td>
                <td>{error.get('error', 'unknown error')}</td>
            </tr>
            """
        
        html += "</table>"
    
    # Close HTML
    html += """
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
    fieldnames = [
        'category', 'subject', 'sent_time', 'verification_time', 
        'found_in_db', 'classification_correct', 'error'
    ]
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    for email in test_emails:
        writer.writerow({
            'category': email.category,
            'subject': email.subject,
            'sent_time': email.sent_time.strftime('%Y-%m-%d %H:%M:%S') if email.sent_time else 'N/A',
            'verification_time': email.verification_time.strftime('%Y-%m-%d %H:%M:%S') if email.verification_time else 'N/A',
            'found_in_db': 'Yes' if email.found_in_db else 'No',
            'classification_correct': 'Yes' if email.classification_correct else 'No',
            'error': email.error if email.error else 'None'
        })
    
    return output.getvalue().encode('utf-8')

def generate_chart():
    """
    Generate a chart of test results
    
    Returns:
        bytes: PNG image data
    """
    # Create a pie chart for found vs not found
    plt.figure(figsize=(10, 8))
    
    # Create subplots
    plt.subplot(1, 2, 1)
    labels = ['Found in DB', 'Not Found']
    sizes = [test_results.get('found_in_db', 0), test_results.get('not_found', 0)]
    colors = ['#66b3ff', '#ff9999']
    plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
    plt.axis('equal')
    plt.title('Email Processing Results')
    
    # Create pie chart for classification accuracy
    plt.subplot(1, 2, 2)
    labels = ['Correct Classification', 'Incorrect Classification']
    sizes = [
        test_results.get('classification_correct', 0), 
        test_results.get('classification_incorrect', 0)
    ]
    colors = ['#99ff99', '#ffcc99']
    plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
    plt.axis('equal')
    plt.title('Classification Accuracy')
    
    plt.tight_layout()
    
    # Save chart to BytesIO
    buffer = BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    
    return buffer.getvalue()

async def send_report_email(report_recipients):
    """
    Send the test report via email
    
    Args:
        report_recipients: List of email addresses to send the report to
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get access token for MS Graph API
        access_token = await get_access_token()
        if not access_token:
            raise Exception("Failed to obtain access token")
        
        # Use the first configured email account
        if not EMAIL_ACCOUNTS or not EMAIL_ACCOUNTS[0]:
            raise Exception("No email account configured")
            
        account = EMAIL_ACCOUNTS[0]
        
        # Generate HTML report
        html_report = generate_html_report()
        
        # Generate CSV report
        csv_report = generate_csv_report()
        
        # Generate chart
        chart_data = generate_chart()
        
        # Create timestamp for filenames
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Set up email content
        subject = f"APEX Automated Test Report - {timestamp}"
        
        # Create email content with success/failure summary in the subject
        success_rate = test_results.get('success_rate', 0)
        if success_rate == 100:
            subject = f"✅ {subject} - All Tests Passed"
        elif success_rate >= 75:
            subject = f"⚠️ {subject} - {success_rate}% Success"
        else:
            subject = f"❌ {subject} - {success_rate}% Success"
        
        # Encode chart as base64 for embedding in HTML
        chart_base64 = base64.b64encode(chart_data).decode('utf-8')
        
        # Create HTML email with embedded chart
        html_with_chart = html_report.replace('</body>', f'''
            <h2>Results Chart</h2>
            <img src="data:image/png;base64,{chart_base64}" alt="Test Results Chart" style="max-width:100%;">
            </body>
        ''')
        
        # Basic text version for non-HTML clients
        text_content = f"""
        APEX Automated Test Report - {timestamp}
        
        Summary:
        - Total emails sent: {test_results.get('total_emails', 0)}
        - Emails found in database: {test_results.get('found_in_db', 0)}
        - Emails not found: {test_results.get('not_found', 0)}
        - Classification correct: {test_results.get('classification_correct', 0)}
        - Success rate: {test_results.get('success_rate', 0)}%
        - Classification accuracy: {test_results.get('classification_accuracy', 0)}%
        
        Please see the attached CSV file for detailed results.
        """
        
        # Create email message
        email_content = {
            'to': ', '.join(report_recipients),
            'from': account,
            'cc': '',
            'subject': subject,
            'body_html': html_with_chart,
            'body_text': text_content,
            'internet_message_id': f"APEX_TEST_REPORT_{timestamp}@apex.test",
            'date_received': datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'email_id': f"APEX_TEST_REPORT_{timestamp}",
            'attachments': [
                {
                    'name': f'apex_test_report_{timestamp}.csv',
                    'content_type': 'text/csv',
                    'content': base64.b64encode(csv_report).decode('utf-8')
                },
                {
                    'name': f'apex_test_results_{timestamp}.png',
                    'content_type': 'image/png',
                    'content': base64.b64encode(chart_data).decode('utf-8')
                }
            ]
        }
        
        # Use email_client.py's forward_email function to send the report
        # In this case, we're not really forwarding, but using the function to create a new email
        result = await forward_email(
            access_token=access_token,
            user_id=account,
            message_id='draft',  # This won't be used since we're creating a new message
            original_sender=account,
            forward_to=', '.join(report_recipients),
            email_data=email_content,
            forwardMsg="APEX AUTOMATED TEST REPORT"
        )
        
        if result:
            print(f"Successfully sent test report to: {', '.join(report_recipients)}")
            return True
        else:
            print(f"Failed to send test report")
            return False
            
    except Exception as e:
        error_msg = f"Error sending test report: {str(e)}"
        print(error_msg)
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
        # Parse command line arguments
        wait_time = args.wait_time or DEFAULT_WAIT_TIME
        
        report_recipients = DEFAULT_REPORT_RECIPIENTS
        if args.recipients:
            report_recipients = [email.strip() for email in args.recipients.split(',')]
        
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
        print("Sending test report...")
        await send_report_email(report_recipients)
        
        print(f"=== APEX Automated Test Completed at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
        
        # Print summary to console
        print("\nTest Summary:")
        print(f"Total emails sent: {test_results.get('total_emails', 0)}")
        print(f"Emails found in database: {test_results.get('found_in_db', 0)}")
        print(f"Emails not found: {test_results.get('not_found', 0)}")
        print(f"Classification correct: {test_results.get('classification_correct', 0)}")
        print(f"Success rate: {test_results.get('success_rate', 0)}%")
        
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
            if report_recipients:
                await send_report_email(report_recipients)
        except:
            print("Failed to send error report")

if __name__ == "__main__":
    # Run the main async function
    asyncio.run(main())
