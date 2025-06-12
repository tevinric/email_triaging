import os
import sys
import asyncio
import argparse
import datetime
import pyodbc
import json
import traceback
import aiohttp
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from io import BytesIO
import base64
from collections import Counter, defaultdict

# Import APEX components for email sending and token acquisition
from email_processor.email_client import get_access_token
from config import (CLIENT_ID, TENANT_ID, CLIENT_SECRET, AUTHORITY, SCOPE,
    SQL_SERVER, SQL_DATABASE, SQL_USERNAME, SQL_PASSWORD,
    EMAIL_ACCOUNTS, DAILY_REPORT_RECIPIENTS)

# Load configuration from environment variables
def get_env_var(var_name, default=None, required=False):
    """Get environment variable with optional default and required check"""
    value = os.environ.get(var_name, default)
    if required and value is None:
        raise ValueError(f"Required environment variable {var_name} is not set")
    return value

# Constants from environment variables
REPORT_RECIPIENTS = DAILY_REPORT_RECIPIENTS
TEST_EMAIL_PREFIX = "APEX Daily Performance Report"

# NEW: Mail bin to monitor for unread emails and daily volume
MONITORED_MAIL_BIN = get_env_var('MONITORED_MAIL_BIN', EMAIL_ACCOUNTS[0] if EMAIL_ACCOUNTS and len(EMAIL_ACCOUNTS) > 0 else None)

# Set up argument parsing
parser = argparse.ArgumentParser(description='APEX Daily Performance Report Script')
parser.add_argument('--recipients', type=str, help='Comma-separated list of email addresses to send the report to (overrides env var)')
parser.add_argument('--date', type=str, help='Date to run the report for (format: YYYY-MM-DD, default: today)')
parser.add_argument('--mailbin', type=str, help='Email address of the mail bin to monitor (overrides env var)')
args = parser.parse_args()

class DailyReport:
    """Class to handle daily report generation and analysis"""
    
    def __init__(self, report_date=None, mail_bin=None):
        """
        Initialize the report with the specified date or today
        
        Args:
            report_date: Date to generate report for (str in YYYY-MM-DD format or datetime object)
            mail_bin: Email address of the mail bin to monitor
        """
        if report_date is None:
            self.report_date = datetime.datetime.now().date()
        elif isinstance(report_date, str):
            self.report_date = datetime.datetime.strptime(report_date, '%Y-%m-%d').date()
        else:
            self.report_date = report_date
            
        self.report_start = datetime.datetime.combine(self.report_date, datetime.time.min)
        self.report_end = datetime.datetime.combine(self.report_date, datetime.time.max)
        
        # Mail bin to monitor
        self.mail_bin = mail_bin or MONITORED_MAIL_BIN
        
        # Initialize data structures
        self.all_emails = []
        self.prod_emails = []  # Excluding test emails
        
        # Statistics
        self.total_emails = 0
        self.test_emails = 0
        self.prod_email_count = 0
        self.successful_emails = 0
        self.failed_emails = 0
        self.category_counts = Counter()
        self.hourly_counts = defaultdict(int)
        self.error_counts = Counter()
        self.autoresponse_stats = {'success': 0, 'failed': 0, 'not_attempted': 0, 'unknown': 0}
        
        # NEW: Email bin monitoring statistics
        self.unread_emails_count = 0
        self.daily_received_count = 0
        self.email_variance = 0
        self.mail_bin_check_success = False
        self.mail_bin_error_message = None
        
        # Performance metrics
        self.avg_processing_time = 0
        self.avg_processing_by_category = {}
        self.token_usage = {'total': 0, 'avg_per_email': 0}
        self.cost_analysis = {'total_usd': 0, 'avg_per_email': 0}
        
        # Failures and issues
        self.classification_failures = []
        self.routing_failures = []
        self.read_status_failures = []
        self.autoresponse_failures = []
        
        # Report components
        self.charts = {}
        self.alerts = []
        self.recommendations = []

    async def check_mail_bin_status(self):
        """Check unread emails and daily received count in the specified mail bin"""
        if not self.mail_bin:
            self.mail_bin_error_message = "No mail bin specified for monitoring"
            print(f"Warning: {self.mail_bin_error_message}")
            return False
            
        try:
            print(f"Checking mail bin status for: {self.mail_bin}")
            
            # Get access token for MS Graph API
            access_token = await get_access_token_with_mail_scope()
            if not access_token:
                raise Exception("Failed to obtain access token for mail bin check")
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
            }
            
            async with aiohttp.ClientSession() as session:
                # Check unread emails count
                unread_url = f'https://graph.microsoft.com/v1.0/users/{self.mail_bin}/mailFolders/inbox/messages?$filter=isRead eq false&$count=true'
                
                async with session.get(unread_url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.unread_emails_count = data.get('@odata.count', len(data.get('value', [])))
                        print(f"Found {self.unread_emails_count} unread emails in mail bin")
                    else:
                        response_text = await response.text()
                        raise Exception(f"Failed to get unread emails: {response.status} - {response_text}")
                
                # Check daily received emails count
                # Format dates for OData filter
                start_date = self.report_start.isoformat() + 'Z'
                end_date = self.report_end.isoformat() + 'Z'
                
                daily_url = f'https://graph.microsoft.com/v1.0/users/{self.mail_bin}/mailFolders/inbox/messages?$filter=receivedDateTime ge {start_date} and receivedDateTime le {end_date}&$count=true'
                
                async with session.get(daily_url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.daily_received_count = data.get('@odata.count', len(data.get('value', [])))
                        print(f"Found {self.daily_received_count} emails received in mail bin for {self.report_date}")
                    else:
                        response_text = await response.text()
                        raise Exception(f"Failed to get daily emails: {response.status} - {response_text}")
            
            self.mail_bin_check_success = True
            print(f"Mail bin check completed successfully")
            print(f"MS Graph API - Emails received today: {self.daily_received_count}")
            print(f"Note: Variance will be calculated after email processing count is determined")
            
            return True
            
        except Exception as e:
            self.mail_bin_error_message = f"Error checking mail bin: {str(e)}"
            print(f"Error checking mail bin status: {str(e)}")
            print(traceback.format_exc())
            return False
        
    async def fetch_data(self):
        """Fetch email processing data from the database, including model costs"""
        try:
            # Connect to the database
            conn = await self.get_db_connection()
            cursor = conn.cursor()

            # Fetch model costs for gpt-4o and gpt-4o-mini
            cursor.execute("""
                SELECT model, prompt_cost, completion_cost, cache_cost
                FROM [dbo].[model_costs]
                WHERE model IN ('gpt-4o', 'gpt-4o-mini')
            """)
            model_costs = {row[0]: {'prompt': row[1], 'completion': row[2], 'cache': row[3]} for row in cursor.fetchall()}
            self.model_costs = model_costs  # Save for later use

            # Query for all emails processed during the report date
            query = """
            SELECT * FROM [dbo].[logs]
            WHERE dttm_proc >= ? AND dttm_proc <= ?
            ORDER BY dttm_proc ASC
            """
            cursor.execute(query, (self.report_start, self.report_end))

            # Fetch all rows
            columns = [column[0] for column in cursor.description]
            self.all_emails = []

            for row in cursor.fetchall():
                email_data = {columns[i]: row[i] for i in range(len(columns))}
                self.all_emails.append(email_data)

            # Close connection
            cursor.close()
            conn.close()

            print(f"Fetched {len(self.all_emails)} emails from database for {self.report_date}")

            # Filter out test emails
            self.prod_emails = [email for email in self.all_emails
                               if not (email.get('eml_sub') and
                                      TEST_EMAIL_PREFIX in str(email.get('eml_sub', '')))]

            self.test_emails = len(self.all_emails) - len(self.prod_emails)
            print(f"Identified {self.test_emails} test emails, {len(self.prod_emails)} production emails")

            return True

        except Exception as e:
            print(f"Error fetching data: {str(e)}")
            print(traceback.format_exc())
            return False

    async def get_db_connection(self):
        """Create and return a database connection"""
        try:
            conn = pyodbc.connect(
                f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SQL_SERVER};DATABASE={SQL_DATABASE};UID={SQL_USERNAME};PWD={SQL_PASSWORD}'
            )
            return conn
        except Exception as e:
            print(f"Database connection error: {str(e)}")
            raise
    
    async def analyze_data(self):
        """Analyze the email data and calculate statistics, including accurate cost calculation"""
        # Check mail bin status first
        await self.check_mail_bin_status()
        
        # Remove the early return if no production emails
        if not self.prod_emails:
            print("No production emails to analyze")
            # Do not return False; allow report to be generated
            self.prod_email_count = 0
            self.successful_emails = 0
            self.failed_emails = 0
            return True
        
        # Basic counts
        self.prod_email_count = len(self.prod_emails)
        
        # Process each email
        for email in self.prod_emails:
            # Count by category
            category = email.get('apex_class', 'unknown').lower()
            self.category_counts[category] += 1
            
            # Count by hour
            proc_time = email.get('dttm_proc')
            if proc_time:
                hour = proc_time.hour
                self.hourly_counts[hour] += 1
            
            # Success/failure counts
            routing_status = str(email.get('sts_routing', '')).lower()
            class_status = str(email.get('sts_class', '')).lower()
            read_status = str(email.get('sts_read_eml', '')).lower()
            
            if routing_status == 'success' and class_status == 'success' and read_status == 'success':
                self.successful_emails += 1
            else:
                self.failed_emails += 1
                
                # Track specific failures
                if class_status != 'success':
                    self.classification_failures.append(email)
                if routing_status != 'success':
                    self.routing_failures.append(email)
                if read_status != 'success':
                    self.read_status_failures.append(email)
            
            # Track autoresponse status
            auto_response = str(email.get('auto_response_sent', '')).lower()
            if auto_response == 'success':
                self.autoresponse_stats['success'] += 1
            elif auto_response == 'failed':
                self.autoresponse_stats['failed'] += 1
                self.autoresponse_failures.append(email)
            elif auto_response == 'not_attempted':
                self.autoresponse_stats['not_attempted'] += 1
            else:
                self.autoresponse_stats['unknown'] += 1
            
            # Error tracking
            if 'error' in email and email['error']:
                error_type = self._categorize_error(email['error'])
                self.error_counts[error_type] += 1
        
        # Calculate performance metrics
        tat_values = [email.get('tat', 0) for email in self.prod_emails if email.get('tat') is not None]
        if tat_values:
            self.avg_processing_time = sum(tat_values) / len(tat_values)
        
        # Calculate average processing time by category
        category_times = defaultdict(list)
        for email in self.prod_emails:
            category = email.get('apex_class', 'unknown').lower()
            tat = email.get('tat')
            if tat is not None:
                category_times[category].append(tat)
        
        self.avg_processing_by_category = {
            category: sum(times) / len(times) if times else 0
            for category, times in category_times.items()
        }
        
        # Token usage and cost analysis
        total_tokens = sum(
            (email.get('gpt_4o_prompt_tokens', 0) or 0) +
            (email.get('gpt_4o_completion_tokens', 0) or 0) +
            (email.get('gpt_4o_cached_tokens', 0) or 0) +
            (email.get('gpt_4o_mini_prompt_tokens', 0) or 0) +
            (email.get('gpt_4o_mini_completion_tokens', 0) or 0) +
            (email.get('gpt_4o_mini_cached_tokens', 0) or 0)
            for email in self.prod_emails
        )

        # --- Accurate cost calculation using model_costs ---
        cost_gpt4o = self.model_costs.get('gpt-4o', {'prompt': 0, 'completion': 0, 'cache': 0})
        cost_gpt4o_mini = self.model_costs.get('gpt-4o-mini', {'prompt': 0, 'completion': 0, 'cache': 0})

        total_cost = 0.0
        for email in self.prod_emails:
            # gpt-4o
            gpt4o_prompt = (email.get('gpt_4o_prompt_tokens', 0) or 0) * cost_gpt4o['prompt']/1000000
            gpt4o_completion = (email.get('gpt_4o_completion_tokens', 0) or 0) * cost_gpt4o['completion']/1000000
            gpt4o_cache = (email.get('gpt_4o_cached_tokens', 0) or 0) * cost_gpt4o['cache']/1000000
            # gpt-4o-mini
            gpt4o_mini_prompt = (email.get('gpt_4o_mini_prompt_tokens', 0) or 0) * cost_gpt4o_mini['prompt']/1000000
            gpt4o_mini_completion = (email.get('gpt_4o_mini_completion_tokens', 0) or 0) * cost_gpt4o_mini['completion']/1000000
            gpt4o_mini_cache = (email.get('gpt_4o_mini_cached_tokens', 0) or 0) * cost_gpt4o_mini['cache']/1000000

            email_cost = (
                gpt4o_prompt + gpt4o_completion + gpt4o_cache +
                gpt4o_mini_prompt + gpt4o_mini_completion + gpt4o_mini_cache
            )
            total_cost += email_cost

        self.token_usage = {
            'total': total_tokens,
            'avg_per_email': total_tokens / self.prod_email_count if self.prod_email_count else 0
        }

        self.cost_analysis = {
            'total_usd': total_cost,
            'avg_per_email': total_cost / self.prod_email_count if self.prod_email_count else 0
        }
        
        # Generate insights and alerts
        self._generate_insights()
        
        return True
    
    def _categorize_error(self, error_text):
        """Categorize error messages into common types"""
        error_text = str(error_text).lower()
        
        if 'token' in error_text or 'auth' in error_text:
            return 'Authentication Error'
        elif 'timeout' in error_text:
            return 'Timeout Error'
        elif 'connection' in error_text:
            return 'Connection Error'
        elif 'database' in error_text or 'sql' in error_text:
            return 'Database Error'
        elif 'graph api' in error_text:
            return 'Graph API Error'
        elif 'openai' in error_text or 'model' in error_text:
            return 'AI Model Error'
        else:
            return 'Other Error'
    
    def _generate_insights(self):
        """Generate insights, alerts, and recommendations based on the analysis"""
        # NEW: Check for email variance alerts
        if self.mail_bin_check_success and self.email_variance != 0:
            if self.email_variance > 5:  # More than 5 emails received but not processed
                self.alerts.append({
                    'level': 'CRITICAL',
                    'message': f"Critical email processing gap: {self.email_variance} emails received but not processed",
                    'details': f"MS Graph shows {self.daily_received_count} emails received today, but only {self.prod_email_count} were processed. This indicates {self.email_variance} emails may have been missed by the APEX system."
                })
            elif self.email_variance > 0:  # 1-5 emails received but not processed
                self.alerts.append({
                    'level': 'WARNING',
                    'message': f"Email processing gap detected: {self.email_variance} emails received but not processed",
                    'details': f"MS Graph shows {self.daily_received_count} emails received today, but only {self.prod_email_count} were processed. Monitor for processing issues."
                })
            elif self.email_variance < -5:  # Significantly more processed than received (unusual)
                self.alerts.append({
                    'level': 'WARNING',
                    'message': f"Unexpected processing count: {abs(self.email_variance)} more emails processed than received today",
                    'details': f"Processed {self.prod_email_count} emails but MS Graph shows only {self.daily_received_count} received today. This may indicate processing of emails from previous days or other sources."
                })
        
        # NEW: Check for unread emails alert
        if self.mail_bin_check_success and self.unread_emails_count > 0:
            if self.unread_emails_count > 10:
                self.alerts.append({
                    'level': 'CRITICAL',
                    'message': f"High number of unread emails in mail bin: {self.unread_emails_count} unread emails",
                    'details': f"There are {self.unread_emails_count} unread emails in {self.mail_bin} that may require immediate attention."
                })
            elif self.unread_emails_count > 5:
                self.alerts.append({
                    'level': 'WARNING',
                    'message': f"Unread emails in mail bin: {self.unread_emails_count} unread emails",
                    'details': f"There are {self.unread_emails_count} unread emails in {self.mail_bin} that may need attention."
                })
        
        # Check for critical alerts (high failure rates)
        if self.prod_email_count > 0:
            failure_rate = (self.failed_emails / self.prod_email_count) * 100
            
            if failure_rate > 10:  # More than 10% failures
                self.alerts.append({
                    'level': 'CRITICAL',
                    'message': f"High email processing failure rate: {failure_rate:.1f}% ({self.failed_emails} of {self.prod_email_count})",
                    'details': "Processing failures indicate systemic issues that need immediate attention."
                })
            elif failure_rate > 5:  # 5-10% failures
                self.alerts.append({
                    'level': 'WARNING',
                    'message': f"Elevated email processing failure rate: {failure_rate:.1f}% ({self.failed_emails} of {self.prod_email_count})",
                    'details': "Failure rate is above acceptable threshold."
                })
            
            # Check autoresponse failures
            if self.autoresponse_stats['failed'] > 0:
                autoresponse_failure_rate = (self.autoresponse_stats['failed'] / self.prod_email_count) * 100
                if autoresponse_failure_rate > 10:
                    self.alerts.append({
                        'level': 'CRITICAL',
                        'message': f"High autoresponse failure rate: {autoresponse_failure_rate:.1f}% ({self.autoresponse_stats['failed']} failures)",
                        'details': "Customers are not receiving expected automated responses."
                    })
                elif autoresponse_failure_rate > 5:
                    self.alerts.append({
                        'level': 'WARNING',
                        'message': f"Elevated autoresponse failure rate: {autoresponse_failure_rate:.1f}% ({self.autoresponse_stats['failed']} failures)",
                        'details': "Some customers are not receiving expected automated responses."
                    })
            
            # Check for specific error types
            for error_type, count in self.error_counts.items():
                error_rate = (count / self.prod_email_count) * 100
                if error_rate > 5:
                    self.alerts.append({
                        'level': 'WARNING',
                        'message': f"High rate of {error_type}: {error_rate:.1f}% ({count} occurrences)",
                        'details': f"Investigate the cause of {error_type} errors."
                    })
            
            # Generate recommendations based on findings
            if self.classification_failures:
                self.recommendations.append({
                    'category': 'Classification',
                    'message': f"Review {len(self.classification_failures)} classification failures to improve accuracy",
                    'details': "Consider updating the AI model or adjusting prompts to handle these cases better."
                })
            
            if self.routing_failures:
                self.recommendations.append({
                    'category': 'Routing',
                    'message': f"Investigate {len(self.routing_failures)} routing failures",
                    'details': "Check email forwarding configuration and permissions."
                })
            
            if self.read_status_failures:
                self.recommendations.append({
                    'category': 'Email Handling',
                    'message': f"Address {len(self.read_status_failures)} failures to mark emails as read",
                    'details': "This may indicate permission issues with the Microsoft Graph API."
                })
            
            if self.autoresponse_failures:
                self.recommendations.append({
                    'category': 'Autoresponse',
                    'message': f"Fix {len(self.autoresponse_failures)} autoresponse failures",
                    'details': "Customers expect immediate acknowledgment of their emails."
                })
            
            # NEW: Recommendations for email variance and unread emails
            if self.mail_bin_check_success:
                if self.email_variance > 2:
                    self.recommendations.append({
                        'category': 'Email Processing Gap',
                        'message': f"Investigate {self.email_variance} emails that were received but not processed",
                        'details': f"MS Graph API shows {self.daily_received_count} emails received today, but only {self.prod_email_count} were processed. Check for system issues, email filtering problems, or connectivity issues with the mail bin."
                    })
                elif self.email_variance < -2:
                    self.recommendations.append({
                        'category': 'Processing Analysis',
                        'message': f"Review why {abs(self.email_variance)} more emails were processed than received today",
                        'details': f"This may indicate processing of backlogged emails from previous days or emails from other sources. Verify if this is expected behavior."
                    })
                
                if self.unread_emails_count > 3:
                    self.recommendations.append({
                        'category': 'Mail Bin Management',
                        'message': f"Review {self.unread_emails_count} unread emails in the monitored mail bin",
                        'details': "Check if these emails require manual attention or if there are issues with the automated processing."
                    })
            
            # Performance optimization recommendations
            slowest_categories = sorted(
                self.avg_processing_by_category.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:3]  # Top 3 slowest categories
            
            if slowest_categories and slowest_categories[0][1] > 10:  # More than 10 seconds
                self.recommendations.append({
                    'category': 'Performance',
                    'message': f"Optimize processing for slow categories: {', '.join([c[0] for c in slowest_categories])}",
                    'details': f"The slowest category ({slowest_categories[0][0]}) takes {slowest_categories[0][1]:.1f} seconds on average."
                })
            
            # Cost optimization if applicable
            if self.cost_analysis['avg_per_email'] > 0.05:  # More than 5 cents per email
                self.recommendations.append({
                    'category': 'Cost',
                    'message': f"Consider cost optimization strategies (current avg: ${self.cost_analysis['avg_per_email']:.3f} per email)",
                    'details': "Using the smaller AI model for more emails could reduce costs."
                })
    
    def generate_charts(self):
        """Generate charts for the report"""
        # 1. Email volume by hour
        plt.figure(figsize=(10, 6))
        hours = list(range(24))
        counts = [self.hourly_counts.get(hour, 0) for hour in hours]
        
        plt.bar(hours, counts, color='#2176ae')
        plt.xlabel('Hour of Day')
        plt.ylabel('Number of Emails')
        plt.title('Email Processing Volume by Hour')
        plt.xticks(hours)
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        plt.tight_layout(pad=2.0)
        
        buffer = BytesIO()
        plt.savefig(buffer, format='png')
        buffer.seek(0)
        self.charts['hourly_volume'] = buffer.getvalue()
        plt.close()
        
        # 2. Category distribution
        plt.figure(figsize=(12, 6))
        categories = list(self.category_counts.keys())
        counts = list(self.category_counts.values())
        
        sorted_data = sorted(zip(categories, counts), key=lambda x: x[1], reverse=True)
        categories = [x[0] for x in sorted_data]
        counts = [x[1] for x in sorted_data]
        
        plt.bar(categories, counts, color='#2176ae')
        plt.xlabel('Category')
        plt.ylabel('Number of Emails')
        plt.title('Email Distribution by Category')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout(pad=2.0)
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        
        buffer = BytesIO()
        plt.savefig(buffer, format='png')
        buffer.seek(0)
        self.charts['category_distribution'] = buffer.getvalue()
        plt.close()
        
        # 3. Success/Failure pie chart
        labels = ['Successful', 'Failed']
        sizes = [self.successful_emails, self.failed_emails]
        if sum(sizes) > 0:
            plt.figure(figsize=(8, 6))  # Increased size for better visibility
            colors = ['#4CAF50', '#F44336']
            explode = (0, 0.1)  # Explode the failure slice

            wedges, texts, autotexts = plt.pie(
                sizes, explode=explode, labels=None, colors=colors, autopct='%1.1f%%',
                shadow=True, startangle=90
            )
            plt.title('Email Processing Success Rate')
            plt.axis('equal')
            plt.legend(wedges, labels, loc='lower center', bbox_to_anchor=(0.5, -0.15), ncol=2)
            plt.tight_layout(pad=3.0)

            buffer = BytesIO()
            plt.savefig(buffer, format='png', bbox_inches='tight')
            buffer.seek(0)
            self.charts['success_rate'] = buffer.getvalue()
            plt.close()
        # else: do not add 'success_rate' chart if no data

        # 4. Autoresponse status
        # Only include 'Success' and 'Failed' in the pie chart
        ar_labels = []
        ar_sizes = []
        ar_colors = []
        if self.autoresponse_stats['success'] > 0:
            ar_labels.append('Success')
            ar_sizes.append(self.autoresponse_stats['success'])
            ar_colors.append('#4CAF50')
        if self.autoresponse_stats['failed'] > 0:
            ar_labels.append('Failed')
            ar_sizes.append(self.autoresponse_stats['failed'])
            ar_colors.append('#F44336')

        if sum(ar_sizes) > 0:
            plt.figure(figsize=(8, 6))  # Increased size for better visibility
            wedges, texts, autotexts = plt.pie(
                ar_sizes, labels=None, colors=ar_colors, autopct='%1.1f%%', shadow=True, startangle=90
            )
            plt.title('Autoresponse Status')
            plt.axis('equal')
            plt.legend(wedges, ar_labels, loc='lower center', bbox_to_anchor=(0.5, -0.15), ncol=len(ar_labels))
            plt.tight_layout(pad=3.0)

            buffer = BytesIO()
            plt.savefig(buffer, format='png', bbox_inches='tight')
            buffer.seek(0)
            self.charts['autoresponse_status'] = buffer.getvalue()
            plt.close()
        # else: do not add 'autoresponse_status' chart if no data
        
        # 5. Error distribution if there are errors
        if sum(self.error_counts.values()) > 0:
            plt.figure(figsize=(10, 6))
            error_types = list(self.error_counts.keys())
            error_counts = list(self.error_counts.values())
            
            # Sort by count
            sorted_data = sorted(zip(error_types, error_counts), key=lambda x: x[1], reverse=True)
            error_types = [x[0] for x in sorted_data]
            error_counts = [x[1] for x in sorted_data]
            
            plt.bar(error_types, error_counts, color='#F44336')
            plt.xlabel('Error Type')
            plt.ylabel('Number of Occurrences')
            plt.title('Error Distribution')
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout(pad=2.0)
            plt.grid(axis='y', linestyle='--', alpha=0.7)
            
            buffer = BytesIO()
            plt.savefig(buffer, format='png')
            buffer.seek(0)
            self.charts['error_distribution'] = buffer.getvalue()
            plt.close()
        
        # 6. Processing time by category
        if self.avg_processing_by_category:
            plt.figure(figsize=(12, 6))
            categories = list(self.avg_processing_by_category.keys())
            times = list(self.avg_processing_by_category.values())
            
            # Sort by time
            sorted_data = sorted(zip(categories, times), key=lambda x: x[1], reverse=True)
            categories = [x[0] for x in sorted_data]
            times = [x[1] for x in sorted_data]
            
            plt.bar(categories, times, color='#2176ae')
            plt.xlabel('Category')
            plt.ylabel('Average Processing Time (seconds)')
            plt.title('Average Processing Time by Category')
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout(pad=2.0)
            plt.grid(axis='y', linestyle='--', alpha=0.7)
            
            buffer = BytesIO()
            plt.savefig(buffer, format='png')
            buffer.seek(0)
            self.charts['processing_time'] = buffer.getvalue()
            plt.close()
    
    def generate_html_report(self):
        """Generate an HTML report with the analysis results"""
        # Generate charts first
        self.generate_charts()
        
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        date_str = self.report_date.strftime('%Y-%m-%d')
        
        # Create HTML report with enhanced styling
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>APEX Daily Performance Report - {date_str}</title>
            <style>
                body {{
                    background: linear-gradient(135deg, #e3e9f7 0%, #f7fafc 100%);
                    min-height: 100vh;
                    margin: 0;
                    padding: 0;
                    width: 100%;
                    font-family: 'Segoe UI', Arial, sans-serif;
                    color: #333;
                    line-height: 1.6;
                }}
                .container {{
                    max-width: 1200px;
                    margin: 48px auto 48px auto;
                    background: #fff;
                    border-radius: 18px;
                    box-shadow: 0 8px 32px rgba(44,62,80,0.13), 0 2px 8px rgba(44,62,80,0.09);
                    padding: 0;
                    overflow: hidden;
                }}
                .header {{
                    background: #1a253b;
                    color: white;
                    padding: 36px 48px 24px 48px;
                    border-radius: 18px 18px 0 0;
                    margin-bottom: 0;
                    box-shadow: 0 2px 8px rgba(44,62,80,0.13);
                }}
                .header h1 {{
                    margin-top: 0;
                    font-weight: 600;
                    font-size: 2.2em;
                    margin-bottom: 16px;
                }}
                .header p {{
                    margin: 8px 0;
                    opacity: 0.9;
                    font-size: 1.1em;
                }}
                .content-wrapper {{
                    padding: 0 48px 48px 48px;
                }}
                .summary {{
                    background: linear-gradient(90deg, #f8fafc 60%, #e3f0fa 100%);
                    padding: 28px 32px;
                    border-radius: 12px;
                    margin: 32px 0;
                    box-shadow: 0 1px 4px rgba(44,62,80,0.04);
                    border-left: 5px solid #3498db;
                }}
                .summary h2 {{
                    margin-top: 0;
                    color: #2c3e50;
                    font-size: 1.6em;
                    margin-bottom: 20px;
                }}
                .metric {{
                    margin-bottom: 16px;
                    display: flex;
                    align-items: center;
                    font-size: 1.08em;
                }}
                .metric-label {{
                    min-width: 230px;
                    color: #3a3a3a;
                    font-weight: 500;
                }}
                .metric-value {{
                    font-weight: 600;
                    font-size: 1.13em;
                    margin-left: 12px;
                    margin-right: 12px;
                }}
                .success {{ color: #2ecc71; }}
                .warning {{ color: #f39c12; }}
                .error {{ color: #e74c3c; }}
                .mail-bin-section {{
                    background: linear-gradient(90deg, #f0f8ff 60%, #e6f3ff 100%);
                    padding: 28px 32px;
                    border-radius: 12px;
                    margin: 32px 0;
                    box-shadow: 0 1px 4px rgba(52,152,219,0.07);
                    border-left: 5px solid #3498db;
                }}
                .mail-bin-section h2 {{
                    margin-top: 0;
                    color: #2980b9;
                    font-size: 1.6em;
                    margin-bottom: 20px;
                }}
                .alerts {{
                    background: linear-gradient(90deg, #fffbe6 60%, #fbeee6 100%);
                    padding: 28px 32px;
                    border-radius: 12px;
                    margin: 32px 0;
                    border-left: 5px solid #f39c12;
                    box-shadow: 0 1px 4px rgba(241,196,15,0.07);
                }}
                .alerts h2 {{
                    margin-top: 0;
                    color: #d35400;
                    font-size: 1.6em;
                    margin-bottom: 20px;
                }}
                .alert-critical, .alert-warning, .alert-info {{
                    padding: 16px;
                    border-radius: 8px;
                    margin-bottom: 16px;
                }}
                .alert-critical {{
                    background-color: rgba(231, 76, 60, 0.1);
                    border-left: 4px solid #e74c3c;
                }}
                .alert-warning {{
                    background-color: rgba(243, 156, 18, 0.1);
                    border-left: 4px solid #f39c12;
                }}
                .alert-info {{
                    background-color: rgba(52, 152, 219, 0.1);
                    border-left: 4px solid #3498db;
                }}
                .alert-critical h3, .alert-warning h3, .alert-info h3 {{
                    margin-top: 0;
                    margin-bottom: 8px;
                }}
                .recommendations {{
                    background: linear-gradient(90deg, #eafaf1 60%, #e3f6f7 100%);
                    padding: 28px 32px;
                    border-radius: 12px;
                    margin: 32px 0;
                    border-left: 5px solid #2ecc71;
                    box-shadow: 0 1px 4px rgba(46,204,113,0.07);
                }}
                .recommendations h2 {{
                    margin-top: 0;
                    color: #27ae60;
                    font-size: 1.6em;
                    margin-bottom: 20px;
                }}
                .recommendation-item {{
                    margin-bottom: 16px;
                    padding-bottom: 16px;
                    border-bottom: 1px solid rgba(46,204,113,0.15);
                }}
                .recommendation-item:last-child {{
                    border-bottom: none;
                    padding-bottom: 0;
                }}
                .charts-section {{
                    margin: 32px 0;
                }}
                .charts-section h2 {{
                    color: #2c3e50;
                    font-size: 1.6em;
                    margin-bottom: 24px;
                }}
                .charts-grid {{
                    display: flex;
                    flex-direction: column;
                    gap: 32px;
                }}
                .charts-row {{
                    display: flex;
                    flex-wrap: nowrap;
                    gap: 32px;
                    margin-bottom: 8px;
                }}
                .chart {{
                    flex: 1;
                    min-width: 0;
                    background-color: white;
                    padding: 20px;
                    border-radius: 12px;
                    box-shadow: 0 0 15px rgba(0,0,0,0.06);
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                }}
                .chart h3 {{
                    margin-top: 0;
                    margin-bottom: 16px;
                    color: #2c3e50;
                    text-align: center;
                    font-size: 1.25em;
                }}
                .chart img {{
                    max-width: 100%;
                    height: auto;
                    border-radius: 8px;
                    box-shadow: 0 0 5px rgba(0,0,0,0.05);
                }}
                .stats-section {{
                    margin: 32px 0;
                }}
                .stats-section h2, .stats-section h3 {{
                    color: #2c3e50;
                }}
                .stats-section h2 {{
                    font-size: 1.6em;
                    margin-bottom: 24px;
                }}
                .stats-section h3 {{
                    font-size: 1.4em;
                    margin: 28px 0 16px 0;
                }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin-bottom: 32px;
                    background: #fafbfc;
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 0 10px rgba(0,0,0,0.03);
                }}
                th, td {{
                    border: 1px solid #e1e4e8;
                    padding: 12px 16px;
                    text-align: left;
                }}
                th {{
                    background-color: #f2f5f9;
                    font-weight: 600;
                    color: #2c3e50;
                }}
                tr:nth-child(even) {{ background-color: #f9f9f9; }}
                tr:hover {{ background-color: #f5f5f5; }}
                .failure-section {{
                    margin: 32px 0;
                }}
                .failure-section h2 {{
                    color: #e74c3c;
                    font-size: 1.6em;
                    margin-bottom: 20px;
                }}
                .failure-details {{
                    max-height: 500px;
                    overflow-y: auto;
                    border-radius: 8px;
                    border: 1px solid #eee;
                    background: #fcfcfc;
                    padding: 16px;
                }}
                .no-emails-alert {{
                    background: linear-gradient(90deg, #e8f4fc 60%, #daeeff 100%);
                    padding: 28px 32px;
                    border-radius: 12px;
                    margin: 32px 0;
                    border-left: 5px solid #3498db;
                    box-shadow: 0 1px 4px rgba(52,152,219,0.07);
                }}
                .support-info {{
                    background: #f9f9f9;
                    border-radius: 8px;
                    padding: 24px 32px;
                    margin: 32px 0;
                    border-top: 1px solid #eee;
                }}
                .support-info h3 {{
                    color: #2c3e50;
                    margin-top: 0;
                }}
                .support-info ol {{
                    padding-left: 24px;
                }}
                .support-info li {{
                    margin-bottom: 12px;
                }}
                .footer {{
                    margin-top: 40px;
                    padding-top: 20px;
                    border-top: 1px solid #eee;
                    color: #777;
                    font-size: 0.9em;
                    text-align: center;
                }}
                @media (max-width: 1200px) {{
                    .container {{ max-width: 98vw; }}
                    .content-wrapper {{ padding: 0 24px 24px 24px; }}
                }}
                @media (max-width: 992px) {{
                    .charts-row {{ flex-direction: column; gap: 24px; }}
                    .chart {{ width: 100%; }}
                }}
                @media (max-width: 768px) {{
                    .header {{ padding: 24px; }}
                    .metric {{ flex-direction: column; align-items: flex-start; }}
                    .metric-label {{ min-width: auto; margin-bottom: 4px; }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>APEX Email Triaging System - Daily Performance Report</h1>
                    <p>Report Date: {date_str}</p>
                    <p>Generated at: {timestamp}</p>
                </div>
                
                <div class="content-wrapper">
                    <div class="summary">
                        <h2>Summary</h2>
                        <div class="metric">
                            <span class="metric-label">Total Emails Processed:</span>
                            <span class="metric-value">{self.prod_email_count}</span>
                            <span style="color:#888;">(excluding {self.test_emails} test emails)</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Success Rate:</span>
                            <span class="metric-value {'success' if (self.prod_email_count > 0 and (self.successful_emails / self.prod_email_count) * 100 >= 95) else 'warning' if (self.prod_email_count > 0 and (self.successful_emails / self.prod_email_count) * 100 >= 90) else 'error'}">
                                {((self.successful_emails / self.prod_email_count) * 100 if self.prod_email_count else 0.0):.1f}%
                            </span>
                            <span style="color:#888;">({self.successful_emails} successful, {self.failed_emails} failed)</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Autoresponse Success Rate:</span>
                            <span class="metric-value {'success' if (self.prod_email_count > 0 and (self.autoresponse_stats['success'] / self.prod_email_count) * 100 >= 95) else 'warning' if (self.prod_email_count > 0 and (self.autoresponse_stats['success'] / self.prod_email_count) * 100 >= 90) else 'error'}">
                                {((self.autoresponse_stats['success'] / self.prod_email_count) * 100 if self.prod_email_count else 0.0):.1f}%
                            </span>
                            <span style="color:#888;">({self.autoresponse_stats['success']} successful, {self.autoresponse_stats['failed']} failed)</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Average Processing Time:</span>
                            <span class="metric-value">{self.avg_processing_time:.2f} seconds</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Total AI Tokens Used:</span>
                            <span class="metric-value">{self.token_usage['total']:,}</span>
                            <span style="color:#888;">(avg: {self.token_usage['avg_per_email']:.1f} per email)</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Approximate AI Cost:</span>
                            <span class="metric-value">${self.cost_analysis['total_usd']:.2f}</span>
                            <span style="color:#888;">(avg: ${self.cost_analysis['avg_per_email']:.3f} per email)</span>
                        </div>
                    </div>
        """
        
        # NEW: Add mail bin monitoring section
        html += f"""
                    <div class="mail-bin-section">
                        <h2>📧 Mail Bin Monitoring</h2>
                        <div class="metric">
                            <span class="metric-label">Monitored Mail Bin:</span>
                            <span class="metric-value">{self.mail_bin or 'Not configured'}</span>
                        </div>
        """
        
        if self.mail_bin_check_success:
            html += f"""
                        <div class="metric">
                            <span class="metric-label">Unread Emails in Mail Bin:</span>
                            <span class="metric-value {'error' if self.unread_emails_count > 10 else 'warning' if self.unread_emails_count > 5 else 'success'}">{self.unread_emails_count}</span>
                            <span style="color:#888;">emails requiring attention</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Emails Received Today (Mail Bin):</span>
                            <span class="metric-value">{self.daily_received_count}</span>
                            <span style="color:#888;">via MS Graph API</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Email Processing Variance:</span>
                            <span class="metric-value {'error' if abs(self.email_variance) > 5 else 'warning' if abs(self.email_variance) > 0 else 'success'}">
                                {'+' if self.email_variance > 0 else ''}{self.email_variance}
                            </span>
                            <span style="color:#888;">(MS Graph received - DB processed){' - Potential missed emails!' if self.email_variance > 0 else ''}</span>
                        </div>
            """
        else:
            html += f"""
                        <div class="metric">
                            <span class="metric-label">Mail Bin Check Status:</span>
                            <span class="metric-value error">Failed</span>
                            <span style="color:#888;">{self.mail_bin_error_message or 'Unknown error'}</span>
                        </div>
            """
        
        html += """
                    </div>
        """
        
        # Add alerts if any
        if self.alerts:
            html += """
                    <div class="alerts">
                        <h2>⚠️ Alerts Requiring Attention</h2>
            """
            
            for alert in self.alerts:
                if alert['level'] == 'CRITICAL':
                    html += f"""
                        <div class="alert-critical">
                            <h3>CRITICAL: {alert['message']}</h3>
                            <p>{alert['details']}</p>
                        </div>
                    """
                elif alert['level'] == 'WARNING':
                    html += f"""
                        <div class="alert-warning">
                            <h3>WARNING: {alert['message']}</h3>
                            <p>{alert['details']}</p>
                        </div>
                    """
                else:
                    html += f"""
                        <div class="alert-info">
                            <h3>INFO: {alert['message']}</h3>
                            <p>{alert['details']}</p>
                        </div>
                    """
            
            html += """
                    </div>
            """
        
        # Add recommendations if any
        if self.recommendations:
            html += """
                    <div class="recommendations">
                        <h2>📋 Recommendations</h2>
            """
            
            for rec in self.recommendations:
                html += f"""
                        <div class="recommendation-item">
                            <b>{rec['category']}:</b> {rec['message']}
                            <div style="color:#3a3a3a; font-weight:400; margin-top:8px;">{rec['details']}</div>
                        </div>
                """
            
            html += """
                    </div>
            """
        
        # Add charts in a grid layout
        html += """
                    <div class="charts-section">
                        <h2>📊 Performance Charts</h2>
                        <div class="charts-grid">
        """

        # First row: Email Volume by Hour and Email Distribution by Category
        html += '<div class="charts-row">'
        if 'hourly_volume' in self.charts:
            chart_base64 = base64.b64encode(self.charts['hourly_volume']).decode('utf-8')
            html += f"""
                            <div class="chart">
                                <h3>Email Volume by Hour</h3>
                                <img src="data:image/png;base64,{chart_base64}" alt="Email Volume by Hour">
                            </div>
            """
        if 'category_distribution' in self.charts:
            chart_base64 = base64.b64encode(self.charts['category_distribution']).decode('utf-8')
            html += f"""
                            <div class="chart">
                                <h3>Email Distribution by Category</h3>
                                <img src="data:image/png;base64,{chart_base64}" alt="Email Distribution by Category">
                            </div>
            """
        html += '</div>'

        # Second row: Success Rate Pie and Autoresponse Pie
        html += '<div class="charts-row">'
        if 'success_rate' in self.charts:
            chart_base64 = base64.b64encode(self.charts['success_rate']).decode('utf-8')
            html += f"""
                            <div class="chart">
                                <h3>Email Processing Success Rate</h3>
                                <img src="data:image/png;base64,{chart_base64}" alt="Email Processing Success Rate">
                            </div>
            """
        if 'autoresponse_status' in self.charts:
            chart_base64 = base64.b64encode(self.charts['autoresponse_status']).decode('utf-8')
            html += f"""
                            <div class="chart">
                                <h3>Autoresponse Status</h3>
                                <img src="data:image/png;base64,{chart_base64}" alt="Autoresponse Status">
                            </div>
            """
        html += '</div>'

        # Third row: Average Processing Time by Category (alone, but same structure)
        if 'processing_time' in self.charts:
            html += '<div class="charts-row">'
            chart_base64 = base64.b64encode(self.charts['processing_time']).decode('utf-8')
            html += f"""
                            <div class="chart">
                                <h3>Average Processing Time by Category</h3>
                                <img src="data:image/png;base64,{chart_base64}" alt="Average Processing Time by Category">
                            </div>
            """
            html += '</div>'

        # Error distribution (optional)
        if 'error_distribution' in self.charts:
            html += '<div class="charts-row">'
            chart_base64 = base64.b64encode(self.charts['error_distribution']).decode('utf-8')
            html += f"""
                            <div class="chart">
                                <h3>Error Distribution</h3>
                                <img src="data:image/png;base64,{chart_base64}" alt="Error Distribution">
                            </div>
            """
            html += '</div>'

        html += """
                        </div>
                    </div>
        """
        
        # Add detailed stats
        html += """
                    <div class="stats-section">
                        <h2>📈 Detailed Statistics</h2>
                        
                        <h3>Category Statistics</h3>
                        <table>
                            <tr>
                                <th>Category</th>
                                <th>Count</th>
                                <th>Percentage</th>
                                <th>Avg. Processing Time (s)</th>
                            </tr>
        """
        
        # Add category statistics
        for category, count in sorted(self.category_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / self.prod_email_count) * 100 if self.prod_email_count else 0
            avg_time = self.avg_processing_by_category.get(category, 0)
            
            html += f"""
                            <tr>
                                <td>{category}</td>
                                <td>{count}</td>
                                <td>{percentage:.1f}%</td>
                                <td>{avg_time:.2f}s</td>
                            </tr>
            """
        
        html += """
                        </table>
                        
                        <h3>Hourly Volume</h3>
                        <table>
                            <tr>
                                <th>Hour</th>
                                <th>Number of Emails</th>
                                <th>Percentage</th>
                            </tr>
        """
        
        # Add hourly statistics
        for hour in range(24):
            count = self.hourly_counts.get(hour, 0)
            percentage = (count / self.prod_email_count) * 100 if self.prod_email_count else 0
            
            html += f"""
                            <tr>
                                <td>{hour:02d}:00 - {hour:02d}:59</td>
                                <td>{count}</td>
                                <td>{percentage:.1f}%</td>
                            </tr>
            """
        
        html += """
                        </table>
                    </div>
        """
        
        # Add failures section if there are any
        if self.failed_emails > 0:
            html += """
                    <div class="failure-section">
                        <h2>❌ Failures</h2>
                        <div class="failure-details">
            """
            
            # Classification failures
            if self.classification_failures:
                html += f"""
                            <h3>Classification Failures ({len(self.classification_failures)})</h3>
                            <table>
                                <tr>
                                    <th>Subject</th>
                                    <th>Time</th>
                                    <th>Status</th>
                                    <th>Error</th>
                                </tr>
                """
                
                for failure in self.classification_failures[:10]:  # Show first 10
                    subject = failure.get('eml_sub', 'N/A')
                    time = failure.get('dttm_proc', 'N/A')
                    status = failure.get('sts_class', 'N/A')
                    error = failure.get('apex_class_rsn', 'N/A')
                    
                    if isinstance(time, datetime.datetime):
                        time = time.strftime('%Y-%m-%d %H:%M:%S')
                    
                    # Truncate long texts
                    if len(str(subject)) > 50:
                        subject = str(subject)[:50] + "..."
                    if len(str(error)) > 100:
                        error = str(error)[:100] + "..."
                    
                    html += f"""
                                <tr>
                                    <td>{subject}</td>
                                    <td>{time}</td>
                                    <td>{status}</td>
                                    <td>{error}</td>
                                </tr>
                    """
                
                if len(self.classification_failures) > 10:
                    html += f"""
                                <tr>
                                    <td colspan="4">... and {len(self.classification_failures) - 10} more failures</td>
                                </tr>
                    """
                
                html += """
                            </table>
                """
            
            # Routing failures
            if self.routing_failures:
                html += f"""
                            <h3>Routing Failures ({len(self.routing_failures)})</h3>
                            <table>
                                <tr>
                                    <th>Subject</th>
                                    <th>Time</th>
                                    <th>Status</th>
                                    <th>Destination</th>
                                </tr>
                """
                
                for failure in self.routing_failures[:10]:  # Show first 10
                    subject = failure.get('eml_sub', 'N/A')
                    time = failure.get('dttm_proc', 'N/A')
                    status = failure.get('sts_routing', 'N/A')
                    destination = failure.get('apex_routed_to', 'N/A')
                    
                    if isinstance(time, datetime.datetime):
                        time = time.strftime('%Y-%m-%d %H:%M:%S')
                    
                    # Truncate long texts
                    if len(str(subject)) > 50:
                        subject = str(subject)[:50] + "..."
                    
                    html += f"""
                                <tr>
                                    <td>{subject}</td>
                                    <td>{time}</td>
                                    <td>{status}</td>
                                    <td>{destination}</td>
                                </tr>
                    """
                
                if len(self.routing_failures) > 10:
                    html += f"""
                                <tr>
                                    <td colspan="4">... and {len(self.routing_failures) - 10} more failures</td>
                                </tr>
                    """
                
                html += """
                            </table>
                """
            
            # Autoresponse failures
            if self.autoresponse_failures:
                html += f"""
                            <h3>Autoresponse Failures ({len(self.autoresponse_failures)})</h3>
                            <table>
                                <tr>
                                    <th>Subject</th>
                                    <th>Time</th>
                                    <th>Sender</th>
                                </tr>
                """
                
                for failure in self.autoresponse_failures[:10]:  # Show first 10
                    subject = failure.get('eml_sub', 'N/A')
                    time = failure.get('dttm_proc', 'N/A')
                    sender = failure.get('eml_frm', 'N/A')
                    
                    if isinstance(time, datetime.datetime):
                        time = time.strftime('%Y-%m-%d %H:%M:%S')
                    
                    # Truncate long texts
                    if len(str(subject)) > 50:
                        subject = str(subject)[:50] + "..."
                    
                    html += f"""
                                <tr>
                                    <td>{subject}</td>
                                    <td>{time}</td>
                                    <td>{sender}</td>
                                </tr>
                    """
                
                if len(self.autoresponse_failures) > 10:
                    html += f"""
                                <tr>
                                    <td colspan="3">... and {len(self.autoresponse_failures) - 10} more failures</td>
                                </tr>
                    """
                
                html += """
                            </table>
                """
            
            html += """
                        </div>
                    </div>
            """
        
        # Add a message if there were no production emails processed
        if self.prod_email_count == 0:
            html += """
                    <div class="no-emails-alert">
                        <h2>ℹ️ No Emails Processed</h2>
                        <div class="alert-info">
                            <h3>No production emails were processed for this date.</h3>
                            <p>The system did not process any emails on this day. This could be due to no incoming emails or a possible upstream issue.</p>
                        </div>
                    </div>
            """
        
        # Add detailed failures section (sender, recipient, subject, routed_to) - REMOVED BODY FIELD
        html += """
                    <div class="failure-section">
                        <h2>❌ Detailed Failure Information</h2>
                        <div class="failure-details">
        """

        # Gather all failures (classification, routing, read status, autoresponse)
        all_failures = (
            self.classification_failures +
            self.routing_failures +
            self.read_status_failures +
            self.autoresponse_failures
        )

        # Remove duplicates (in case an email failed multiple steps)
        seen_ids = set()
        unique_failures = []
        for email in all_failures:
            key = (
                str(email.get('eml_sub', '')),
                str(email.get('eml_frm', '')),
                str(email.get('eml_to', '')),
                str(email.get('dttm_proc', ''))
            )
            if key not in seen_ids:
                seen_ids.add(key)
                unique_failures.append(email)

        if unique_failures:
            html += """
                            <table>
                                <tr>
                                    <th>Sender</th>
                                    <th>Recipient</th>
                                    <th>Subject</th>
                                    <th>Routed To</th>
                                </tr>
            """
            for failure in unique_failures:
                sender = failure.get('eml_frm', 'N/A')
                recipient = failure.get('eml_to', 'N/A')
                subject = failure.get('eml_sub', 'N/A')
                routed_to = failure.get('apex_routed_to', 'N/A')

                # Truncate long fields for readability
                if len(str(subject)) > 80:
                    subject = str(subject)[:80] + "..."
                if len(str(routed_to)) > 80:
                    routed_to = str(routed_to)[:80] + "..."

                html += f"""
                                <tr>
                                    <td>{sender}</td>
                                    <td>{recipient}</td>
                                    <td>{subject}</td>
                                    <td>{routed_to}</td>
                                </tr>
                """
            html += """
                            </table>
            """
        else:
            html += """
                            <p>No failures to display.</p>
            """

        html += """
                        </div>
                    </div>
        """
        
        # Support information section
        html += """
                    <div class="support-info">
                        <h3>Need Support?</h3>
                        <p>Should you have any concerns related to the performance of the APEX Email Triaging System as per the performance stats above, please log a SysAid Incident immediately so that the AI Center of Excellence can investigate further.</p>
                        
                        <p>Use the following link to log a SysAid Incident: <a href="{os.environ.get('incident_link')}">SysAid Portal</a></p>
                        
                        <p>Follow these steps to log a SysAid Incident:</p>
                        <ol>
                            <li>Click on the "Submit an Incident" button</li>
                            <li>Select the category -> <b>AI Centre of Excellence</b></li>
                            <li>Select the sub-category -> <b>Email Triaging (APEX)</b></li>
                            <li>Select third level category -> <b>Report an issue</b></li>
                            <li>Provide a description of the incident/issue.</li>
                            <li>Click on the "Submit" button to log the incident.</li>
                        </ol>
                        <p>Thank you for your cooperation.</p>
                    </div>
                    
                    <div class="footer">
                        <p>This is an automated report from the APEX Email Triaging System.</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def generate_csv_report(self):
        """Generate a CSV report with key statistics"""
        import csv
        from io import StringIO
        
        # Create CSV file in memory
        output = StringIO()
        
        # Write summary statistics
        writer = csv.writer(output)
        writer.writerow(['APEX Daily Performance Report'])
        writer.writerow(['Report Date', self.report_date.strftime('%Y-%m-%d')])
        writer.writerow(['Generated At', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow([])
        
        writer.writerow(['Summary Statistics'])
        writer.writerow(['Total Emails Processed', self.prod_email_count])
        writer.writerow(['Test Emails Excluded', self.test_emails])
        writer.writerow(['Successful Emails', self.successful_emails])
        writer.writerow(['Failed Emails', self.failed_emails])
        writer.writerow(['Success Rate (%)', f"{(self.successful_emails / self.prod_email_count) * 100:.1f}" if self.prod_email_count else "0.0"])
        writer.writerow(['Average Processing Time (s)', f"{self.avg_processing_time:.2f}"])
        writer.writerow(['Total AI Tokens Used', self.token_usage['total']])
        writer.writerow(['Avg. Tokens per Email', f"{self.token_usage['avg_per_email']:.1f}"])
        writer.writerow(['Total AI Cost (USD)', f"${self.cost_analysis['total_usd']:.2f}"])
        writer.writerow(['Avg. Cost per Email (USD)', f"${self.cost_analysis['avg_per_email']:.3f}"])
        writer.writerow([])
        
        # NEW: Mail bin monitoring statistics
        writer.writerow(['Mail Bin Monitoring'])
        writer.writerow(['Monitored Mail Bin', self.mail_bin or 'Not configured'])
        writer.writerow(['Mail Bin Check Success', 'Yes' if self.mail_bin_check_success else 'No'])
        if self.mail_bin_check_success:
            writer.writerow(['Unread Emails in Mail Bin', self.unread_emails_count])
            writer.writerow(['Emails Received Today (MS Graph)', self.daily_received_count])
            writer.writerow(['Total Emails Processed (Database)', self.prod_email_count])
            writer.writerow(['Variance (MS Graph - Database)', self.email_variance])
            writer.writerow(['Variance Explanation', f"{'Potential missed emails' if self.email_variance > 0 else 'More processed than received today' if self.email_variance < 0 else 'Perfect match'}"])
        else:
            writer.writerow(['Mail Bin Check Error', self.mail_bin_error_message or 'Unknown error'])
        writer.writerow([])
        
        writer.writerow(['Autoresponse Statistics'])
        writer.writerow(['Successful Autoresponses', self.autoresponse_stats['success']])
        writer.writerow(['Failed Autoresponses', self.autoresponse_stats['failed']])
        writer.writerow(['Not Attempted', self.autoresponse_stats['not_attempted']])
        writer.writerow(['Unknown Status', self.autoresponse_stats['unknown']])
        writer.writerow(['Autoresponse Success Rate (%)', f"{(self.autoresponse_stats['success'] / self.prod_email_count) * 100:.1f}" if self.prod_email_count else "0.0"])
        writer.writerow([])
        
        writer.writerow(['Category Statistics'])
        writer.writerow(['Category', 'Count', 'Percentage (%)', 'Avg. Processing Time (s)'])
        for category, count in sorted(self.category_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / self.prod_email_count) * 100 if self.prod_email_count else 0
            avg_time = self.avg_processing_by_category.get(category, 0)
            writer.writerow([category, count, f"{percentage:.1f}", f"{avg_time:.2f}"])
        writer.writerow([])
        
        writer.writerow(['Hourly Volume'])
        writer.writerow(['Hour', 'Count', 'Percentage (%)'])
        for hour in range(24):
            count = self.hourly_counts.get(hour, 0)
            percentage = (count / self.prod_email_count) * 100 if self.prod_email_count else 0
            writer.writerow([f"{hour:02d}:00 - {hour:02d}:59", count, f"{percentage:.1f}"])
        writer.writerow([])
        
        if self.error_counts:
            writer.writerow(['Error Distribution'])
            writer.writerow(['Error Type', 'Count'])
            for error_type, count in sorted(self.error_counts.items(), key=lambda x: x[1], reverse=True):
                writer.writerow([error_type, count])
            writer.writerow([])
        
        if self.alerts:
            writer.writerow(['Alerts'])
            writer.writerow(['Level', 'Message'])
            for alert in self.alerts:
                writer.writerow([alert['level'], alert['message']])
            writer.writerow([])
        
        if self.recommendations:
            writer.writerow(['Recommendations'])
            writer.writerow(['Category', 'Message'])
            for rec in self.recommendations:
                writer.writerow([rec['category'], rec['message']])
        
        return output.getvalue().encode('utf-8')

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

async def send_report_email(html_report, csv_report, report_recipients, report_date):
    """
    Send the report via email
    
    Args:
        html_report: HTML report content
        csv_report: CSV report content
        report_recipients: List of email addresses to send the report to
        report_date: Date of the report
        
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
        
        # Format date for email subject
        date_str = report_date.strftime('%Y-%m-%d')
        
        # Set up email subject with a professional title
        base_subject = f"[APEX Email Triaging] Daily Performance Report - {date_str}"
        subject = base_subject
        
        # Check if there are any critical alerts
        has_critical_alerts = any(alert['level'] == 'CRITICAL' for alert in report.alerts)
        has_warnings = any(alert['level'] == 'WARNING' for alert in report.alerts)
        
        # Add alerts to the subject
        if report.prod_email_count == 0:
            subject = f"ℹ️ {base_subject} - No Emails Processed"
        elif has_critical_alerts:
            subject = f"🚨 {base_subject} - CRITICAL ISSUES DETECTED"
        elif has_warnings:
            subject = f"⚠️ {base_subject} - Warnings Present"
        elif report.successful_emails == report.prod_email_count and report.prod_email_count > 0:
            subject = f"✅ {base_subject} - All Systems Normal"
        
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
                "internetMessageId": f"<APEX_DAILY_REPORT_{date_str}@apex.report>"
            },
            "saveToSentItems": "true"
        }
        
        # Encode CSV report for attachment
        csv_base64 = base64.b64encode(csv_report).decode('utf-8')
        
        # Add CSV attachment if supported by your Graph API permissions
        # Note: This requires specific permissions and might not work with all setups
        # If it fails, you can embed a download link in the HTML as an alternative
        try:
            message["message"]["attachments"] = [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": f"APEX_Daily_Report_{date_str}.csv",
                    "contentType": "text/csv",
                    "contentBytes": csv_base64
                }
            ]
        except Exception as attach_err:
            print(f"Warning: Could not add attachment, embedding download link instead: {str(attach_err)}")
            # Add a CSV download link to the HTML
            download_link = f'<p><a href="data:text/csv;base64,{csv_base64}" download="APEX_Daily_Report_{date_str}.csv">Download CSV Report</a></p>'
            message["message"]["body"]["content"] = message["message"]["body"]["content"].replace('</body>', f'{download_link}</body>')
        
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
                if response_status != 202:  # 202 Accepted is success for sendMail
                    print(f"Graph API response text: {response_text}")
                
                if response_status == 202:  # 202 Accepted is success for sendMail
                    print(f"Successfully sent report to: {', '.join(report_recipients)}")
                    return True
                else:
                    error_msg = f"Failed to send report: {response_status} - {response_text}"
                    print(error_msg)
                    return False
            
    except Exception as e:
        error_msg = f"Error sending report: {str(e)}"
        print(error_msg)
        print(f"Traceback: {traceback.format_exc()}")
        return False

async def main():
    """Main execution function"""
    print(f"=== APEX Daily Performance Report Started at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    
    try:
        # Parse command line arguments
        report_date = None
        if args.date:
            try:
                report_date = datetime.datetime.strptime(args.date, '%Y-%m-%d').date()
            except ValueError:
                print(f"Error: Invalid date format. Please use YYYY-MM-DD. Using today's date instead.")
                report_date = datetime.datetime.now().date()
        else:
            report_date = datetime.datetime.now().date()
        
        # Get report recipients
        report_recipients = REPORT_RECIPIENTS
        if args.recipients:
            report_recipients = [email.strip() for email in args.recipients.split(',') if email.strip()]
        
        # Get mail bin to monitor
        mail_bin = args.mailbin or MONITORED_MAIL_BIN
        
        # Create and initialize report
        global report
        report = DailyReport(report_date, mail_bin)
        
        # Fetch data from the database
        print(f"Fetching data for {report_date}...")
        success = await report.fetch_data()
        if not success:
            raise Exception("Failed to fetch data from the database")
        
        # Analyze the data (this will also check mail bin status)
        print("Analyzing data...")
        success = await report.analyze_data()
        if not success:
            raise Exception("Failed to analyze data")
        
        # Generate reports
        print("Generating reports...")
        html_report = report.generate_html_report()
        csv_report = report.generate_csv_report()
        
        # Save reports locally if needed
        date_str = report_date.strftime('%Y-%m-%d')
        # Remove or comment out the following lines to avoid saving files locally
        # with open(f"APEX_Daily_Report_{date_str}.html", "w", encoding="utf-8") as f:
        #     f.write(html_report)
        # 
        # with open(f"APEX_Daily_Report_{date_str}.csv", "wb") as f:
        #     f.write(csv_report)
        #
        # print(f"Reports saved to APEX_Daily_Report_{date_str}.html and APEX_Daily_Report_{date_str}.csv")
        
        # Send the report via email if recipients are specified
        if report_recipients:
            print(f"Sending report to: {', '.join(report_recipients)}")
            success = await send_report_email(html_report, csv_report, report_recipients, report_date)
            if success:
                print("Report sent successfully")
            else:
                print("Failed to send report")
        else:
            print("No report recipients specified. Report was not sent.")
        
        print(f"=== APEX Daily Performance Report Completed at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
        
    except Exception as e:
        error_msg = f"Error in daily report execution: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        
        # Try to send error notification if recipients are specified
        if 'report_recipients' in locals() and report_recipients:
            try:
                error_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <title>APEX Daily Report Error</title>
                    <style>
                        body {{
                            font-family: 'Segoe UI', Arial, sans-serif;
                            line-height: 1.6;
                            color: #333;
                            max-width: 800px;
                            margin: 20px auto;
                            padding: 20px;
                        }}
                        h1 {{
                            color: #e74c3c;
                            border-bottom: 1px solid #eee;
                            padding-bottom: 10px;
                        }}
                        pre {{
                            white-space: pre-wrap;
                            word-wrap: break-word;
                            padding: 15px;
                            border-radius: 5px;
                            margin: 15px 0;
                        }}
                        .error-message {{
                            background-color: #f8d7da;
                            padding: 15px;
                            border-radius: 5px;
                            margin-bottom: 20px;
                        }}
                        .error-trace {{
                            background-color: #f8f9fa;
                            padding: 15px;
                            border-radius: 5px;
                            max-height: 400px;
                            overflow-y: auto;
                            font-size: 14px;
                            border: 1px solid #eee;
                        }}
                    </style>
                </head>
                <body>
                    <h1>❌ APEX Daily Performance Report Failed</h1>
                    <p>The daily performance report script encountered an error:</p>
                    <div class="error-message">{error_msg}</div>
                    <h2>Error Details</h2>
                    <div class="error-trace">{traceback.format_exc()}</div>
                </body>
                </html>
                """
                
                await send_report_email(
                    error_html, 
                    f"Error: {error_msg}".encode('utf-8'), 
                    report_recipients,
                    datetime.datetime.now().date()
                )
            except Exception as email_err:
                print(f"Failed to send error notification: {str(email_err)}")

if __name__ == "__main__":
    # Run the main async function
    asyncio.run(main())
