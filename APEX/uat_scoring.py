import os
import csv
import asyncio
import datetime
import json
import uuid
import traceback
from pathlib import Path
import email
from email import policy
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import html2text

# Import the APEX engine components - using same imports as production
from apex_llm.apex import apex_categorise
from config import *

class UATEmailProcessor:
    """UAT Email Processing class that mimics production flow"""
    
    def __init__(self, uat_folder_path, output_csv_path):
        self.uat_folder_path = Path(uat_folder_path)
        self.output_csv_path = Path(output_csv_path)
        self.results = []
        self.processed_count = 0
        self.failed_count = 0
        
    def extract_email_content(self, file_path):
        """
        Extract email content and metadata from various email file formats.
        Mimics the email parsing logic from production.
        """
        try:
            file_path = Path(file_path)
            filename = file_path.name
            
            # Handle different file extensions
            if file_path.suffix.lower() in ['.eml', '.msg', '.txt']:
                # Read the email file
                with open(file_path, 'rb') as f:
                    raw_email = f.read()
                
                try:
                    # Parse as email message
                    msg = email.message_from_bytes(raw_email, policy=policy.default)
                except Exception as e:
                    # If binary parsing fails, try text parsing
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        raw_text = f.read()
                    msg = email.message_from_string(raw_text, policy=policy.default)
                
                # Extract email components similar to production email_utils.py
                email_data = self._extract_email_details(msg, filename)
                return email_data
                
            else:
                # For other file types, treat as plain text
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # Create a basic email structure
                email_data = {
                    'filename': filename,
                    'email_id': str(uuid.uuid4()),
                    'internet_message_id': f"uat-{filename}-{uuid.uuid4()}",
                    'to': 'uat-test@example.com',
                    'from': 'customer@example.com',
                    'date_received': datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'cc': '',
                    'subject': f'UAT Test Email - {filename}',
                    'body_html': '',
                    'body_text': content
                }
                return email_data
                
        except Exception as e:
            print(f"Error extracting email content from {file_path}: {str(e)}")
            return None
    
    def _extract_email_details(self, msg, filename):
        """
        Extract email details from parsed message object.
        Replicates the logic from email_utils.py create_email_details()
        """
        try:
            # Extract body content
            body_content = self._get_email_body(msg)
            
            # Extract recipients - handle various formats
            to_recipients = []
            cc_recipients = []
            
            # Get TO recipients
            if msg.get('To'):
                to_recipients = [addr.strip() for addr in str(msg.get('To')).split(',')]
            
            # Get CC recipients  
            if msg.get('Cc'):
                cc_recipients = [addr.strip() for addr in str(msg.get('Cc')).split(',')]
            
            # Get sender
            from_addr = str(msg.get('From', 'unknown@example.com'))
            
            # Create email details structure matching production
            email_data = {
                'filename': filename,
                'email_id': str(uuid.uuid4()),
                'internet_message_id': str(msg.get('Message-ID', f'uat-{filename}-{uuid.uuid4()}')),
                'to': ', '.join(to_recipients) if to_recipients else 'uat-test@example.com',
                'from': from_addr,
                'date_received': str(msg.get('Date', datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'))),
                'cc': ', '.join(cc_recipients),
                'subject': str(msg.get('Subject', f'UAT Test Email - {filename}')),
                'body_html': body_content.get('html', ''),
                'body_text': body_content.get('text', '')
            }
            
            return email_data
            
        except Exception as e:
            print(f"Error parsing email details: {str(e)}")
            return None
    
    def _get_email_body(self, msg):
        """
        Extract body content from email message.
        Replicates the logic from email_utils.py get_email_body()
        """
        try:
            html_content = ""
            text_content = ""
            
            if msg.is_multipart():
                # Handle multipart messages
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition"))
                    
                    # Skip attachments
                    if "attachment" in content_disposition:
                        continue
                    
                    if content_type == "text/plain":
                        text_content = part.get_content()
                    elif content_type == "text/html":
                        html_content = part.get_content()
                        # Convert HTML to text for processing
                        if html_content and not text_content:
                            text_content = html2text.html2text(html_content)
            else:
                # Handle single part messages
                content_type = msg.get_content_type()
                if content_type == "text/html":
                    html_content = msg.get_content()
                    text_content = html2text.html2text(html_content)
                else:
                    text_content = msg.get_content()
            
            return {
                'html': html_content or '',
                'text': text_content or ''
            }
            
        except Exception as e:
            print(f"Error extracting email body: {str(e)}")
            return {'html': '', 'text': ''}
    
    async def process_single_email(self, file_path):
        """
        Process a single email file through the APEX engine.
        Mimics the production process_email function logic.
        """
        start_time = datetime.datetime.now()
        timestamp = start_time.strftime('%Y-%m-%d %H:%M:%S')
        
        result = {
            'filename': Path(file_path).name,
            'internet_message_id': '',
            'apex_classification': '',
            'apex_reason_classification': '',
            'apex_action_required': '',
            'apex_sentiment': '',
            'apex_cost_usd': 0.0,
            'apex_top_categories': '',
            'processing_status': '',
            'error_message': '',
            'processing_time_seconds': 0.0,
            'timestamp': timestamp,
            'region_used': '',
            'gpt_4o_prompt_tokens': 0,
            'gpt_4o_completion_tokens': 0, 
            'gpt_4o_total_tokens': 0,
            'gpt_4o_cached_tokens': 0,
            'gpt_4o_mini_prompt_tokens': 0,
            'gpt_4o_mini_completion_tokens': 0,
            'gpt_4o_mini_total_tokens': 0,
            'gpt_4o_mini_cached_tokens': 0
        }
        
        try:
            print(f">> {timestamp} Processing UAT email file: {Path(file_path).name}")
            
            # Extract email content - same as production
            email_data = self.extract_email_content(file_path)
            if not email_data:
                result['processing_status'] = 'FAILED'
                result['error_message'] = 'Failed to extract email content'
                return result
            
            result['internet_message_id'] = email_data.get('internet_message_id', '')
            
            # Concatenate email data for APEX processing - same as production main.py
            llm_text = " ".join([str(value) for key, value in email_data.items() if key not in ['filename', 'email_object']])
            
            subject = email_data.get('subject', 'No Subject')
            print(f">> {timestamp} Running APEX classification for: {subject}")
            
            # Run APEX classification - exact same call as production
            apex_response = await apex_categorise(str(llm_text), subject)
            
            if apex_response.get('response') == '200':
                # Successfully classified by APEX
                message = apex_response.get('message', {})
                
                result['apex_classification'] = str(message.get('classification', ''))
                result['apex_reason_classification'] = str(message.get('rsn_classification', ''))
                result['apex_action_required'] = str(message.get('action_required', ''))
                result['apex_sentiment'] = str(message.get('sentiment', ''))
                result['apex_cost_usd'] = float(message.get('apex_cost_usd', 0.0))
                result['processing_status'] = 'SUCCESS'
                result['region_used'] = str(message.get('region_used', ''))
                
                # Store top categories
                top_categories = message.get('top_categories', [])
                if isinstance(top_categories, list):
                    result['apex_top_categories'] = ', '.join(top_categories)
                else:
                    result['apex_top_categories'] = str(top_categories)
                
                # Token usage tracking
                result['gpt_4o_prompt_tokens'] = int(message.get('gpt_4o_prompt_tokens', 0))
                result['gpt_4o_completion_tokens'] = int(message.get('gpt_4o_completion_tokens', 0))
                result['gpt_4o_total_tokens'] = int(message.get('gpt_4o_total_tokens', 0))
                result['gpt_4o_cached_tokens'] = int(message.get('gpt_4o_cached_tokens', 0))
                result['gpt_4o_mini_prompt_tokens'] = int(message.get('gpt_4o_mini_prompt_tokens', 0))
                result['gpt_4o_mini_completion_tokens'] = int(message.get('gpt_4o_mini_completion_tokens', 0))
                result['gpt_4o_mini_total_tokens'] = int(message.get('gpt_4o_mini_total_tokens', 0))
                result['gpt_4o_mini_cached_tokens'] = int(message.get('gpt_4o_mini_cached_tokens', 0))
                
                print(f">> {timestamp} APEX classification successful: {result['apex_classification']}")
                self.processed_count += 1
                
            else:
                # Classification failed
                result['processing_status'] = 'FAILED'
                result['error_message'] = f"APEX classification failed: {apex_response.get('message', 'Unknown error')}"
                print(f">> {timestamp} APEX classification failed: {result['error_message']}")
                self.failed_count += 1
                
        except Exception as e:
            # Handle any unexpected errors
            result['processing_status'] = 'ERROR'
            result['error_message'] = f"Unexpected error: {str(e)}"
            print(f">> {timestamp} Error processing {Path(file_path).name}: {str(e)}")
            print(f">> {timestamp} Traceback: {traceback.format_exc()}")
            self.failed_count += 1
        
        # Calculate processing time
        end_time = datetime.datetime.now()
        result['processing_time_seconds'] = (end_time - start_time).total_seconds()
        
        return result
    
    async def process_all_emails(self):
        """
        Process all email files in the UAT folder.
        """
        if not self.uat_folder_path.exists():
            print(f"ERROR: UAT folder does not exist: {self.uat_folder_path}")
            return
        
        # Find all email files
        email_files = []
        for pattern in ['*.eml', '*.msg', '*.txt']:
            email_files.extend(self.uat_folder_path.glob(pattern))
        
        if not email_files:
            print(f"WARNING: No email files found in {self.uat_folder_path}")
            return
        
        print(f"Found {len(email_files)} email files to process")
        
        # Process each email file
        for file_path in email_files:
            try:
                result = await self.process_single_email(file_path)
                self.results.append(result)
            except Exception as e:
                print(f"Critical error processing {file_path}: {str(e)}")
                # Add failed result
                self.results.append({
                    'filename': file_path.name,
                    'internet_message_id': '',
                    'apex_classification': '',
                    'apex_reason_classification': '',
                    'apex_action_required': '',
                    'apex_sentiment': '',
                    'apex_cost_usd': 0.0,
                    'apex_top_categories': '',
                    'processing_status': 'CRITICAL_ERROR',
                    'error_message': f'Critical error: {str(e)}',
                    'processing_time_seconds': 0.0,
                    'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'region_used': '',
                    'gpt_4o_prompt_tokens': 0,
                    'gpt_4o_completion_tokens': 0,
                    'gpt_4o_total_tokens': 0,
                    'gpt_4o_cached_tokens': 0,
                    'gpt_4o_mini_prompt_tokens': 0,
                    'gpt_4o_mini_completion_tokens': 0,
                    'gpt_4o_mini_total_tokens': 0,
                    'gpt_4o_mini_cached_tokens': 0
                })
                self.failed_count += 1
    
    def generate_csv_report(self):
        """
        Generate CSV report with all processing results.
        """
        try:
            # Define CSV headers - comprehensive set including all details
            headers = [
                'filename',
                'internet_message_id', 
                'apex_classification',
                'apex_reason_classification',
                'apex_action_required',
                'apex_sentiment',
                'apex_cost_usd',
                'apex_top_categories',
                'processing_status',
                'error_message',
                'processing_time_seconds',
                'timestamp',
                'region_used',
                'gpt_4o_prompt_tokens',
                'gpt_4o_completion_tokens',
                'gpt_4o_total_tokens', 
                'gpt_4o_cached_tokens',
                'gpt_4o_mini_prompt_tokens',
                'gpt_4o_mini_completion_tokens',
                'gpt_4o_mini_total_tokens',
                'gpt_4o_mini_cached_tokens'
            ]
            
            # Write CSV file
            with open(self.output_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=headers)
                writer.writeheader()
                writer.writerows(self.results)
            
            print(f"\n=== UAT TEST SUMMARY ===")
            print(f"Total emails processed: {len(self.results)}")
            print(f"Successful classifications: {self.processed_count}")
            print(f"Failed classifications: {self.failed_count}")
            print(f"Success rate: {(self.processed_count/len(self.results)*100):.1f}%" if self.results else "0%")
            
            # Calculate total cost
            total_cost = sum(result.get('apex_cost_usd', 0) for result in self.results)
            print(f"Total APEX processing cost: ${total_cost:.4f}")
            
            print(f"Results saved to: {self.output_csv_path}")
            
        except Exception as e:
            print(f"Error generating CSV report: {str(e)}")

async def main():
    """
    Main UAT test execution function.
    """
    print("=== APEX UAT Email Processing Test ===")
    print(f"Started at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Configuration - modify these paths as needed
    UAT_FOLDER = r"W:\Tevin\APEX-UAT\Catgeorized mails\Claims"  # Folder containing email files for testing
    OUTPUT_CSV = f"apex_uat_results_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_Claims.csv"

    # Create UAT processor
    processor = UATEmailProcessor(UAT_FOLDER, OUTPUT_CSV)
    
    try:
        # Process all emails
        await processor.process_all_emails()
        
        # Generate CSV report
        processor.generate_csv_report()
        
    except Exception as e:
        print(f"Critical error in UAT test execution: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
    
    print(f"Completed at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    """
    Run the UAT test script.
    
    Usage:
    1. Create a folder called 'uat_emails' in the same directory as this script
    2. Add your test email files (.eml, .msg, .txt) to that folder
    3. Run: python apex_uat_test.py
    4. Check the generated CSV file for results
    """
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nUAT test interrupted by user.")
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
