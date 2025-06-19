import uuid
import datetime
import time
import pyodbc
import os
import asyncio
import threading
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor

# SQL SERVER CONNECTION SETTINGS
from config import SQL_SERVER, SQL_DATABASE, SQL_USERNAME, SQL_PASSWORD

# Thread pool for database operations
db_pool = ThreadPoolExecutor(max_workers=5)

class EmailLogCapture:
    """
    Thread-safe email log capture system that collects terminal output 
    for each email being processed individually.
    Enhanced with comprehensive error tracking and autoresponse logging.
    """
    
    def __init__(self):
        self._current_email = threading.local()
        self._email_logs = {}  # {email_id: {'logs': [], 'metadata': {}, 'stats': {}}}
        self._lock = threading.Lock()
    
    @contextmanager
    def capture_for_email(self, email_id, internet_message_id, email_subject=""):
        """
        Context manager to capture logs for a specific email processing session.
        
        Args:
            email_id (str): Unique email ID
            internet_message_id (str): Internet message ID for linking
            email_subject (str): Email subject for easier identification
        """
        # Set thread-local context
        self._current_email.email_id = email_id
        self._current_email.internet_message_id = internet_message_id
        self._current_email.start_time = datetime.datetime.now()
        
        # Initialize log storage for this email with enhanced structure
        with self._lock:
            self._email_logs[email_id] = {
                'logs': [],
                'metadata': {
                    'email_id': email_id,
                    'internet_message_id': internet_message_id,
                    'email_subject': email_subject[:500] if email_subject else "",  # Limit subject length
                    'start_time': self._current_email.start_time,
                    'end_time': None
                },
                'stats': {
                    'total_log_entries': 0,
                    'error_count': 0,
                    'warning_count': 0,
                    'autoresponse_logs': 0,
                    'apex_logs': 0,
                    'email_client_logs': 0,
                    'system_logs': 0
                },
                'errors': [],  # Separate error tracking
                'autoresponse_details': {
                    'attempted': False,
                    'successful': False,
                    'skip_reason': '',
                    'template_used': '',
                    'template_folder': '',
                    'subject_line': '',
                    'recipient': '',
                    'error_message': ''
                }
            }
        
        try:
            yield
        finally:
            # Mark end time and finalize stats
            end_time = datetime.datetime.now()
            with self._lock:
                if email_id in self._email_logs:
                    self._email_logs[email_id]['metadata']['end_time'] = end_time
                    # Calculate final processing time
                    processing_time = (end_time - self._current_email.start_time).total_seconds()
                    self._email_logs[email_id]['metadata']['processing_time_seconds'] = processing_time
    
    def email_log(self, message):
        """
        Log a message for the current email context and print to console.
        Enhanced with automatic categorization and error detection.
        
        Args:
            message (str): Log message to capture and print
        """
        # Always print to console (preserves existing behavior)
        print(message)
        
        # Capture for current email if context exists
        if hasattr(self._current_email, 'email_id'):
            email_id = self._current_email.email_id
            log_entry = {
                'timestamp': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S'),
                'message': str(message),
                'level': self._determine_log_level(message),
                'category': self._categorize_message(message)
            }
            
            with self._lock:
                if email_id in self._email_logs:
                    self._email_logs[email_id]['logs'].append(log_entry)
                    self._update_stats(email_id, log_entry)
                    
                    # If it's an error, add to separate error tracking
                    if log_entry['level'] in ['ERROR', 'CRITICAL']:
                        self._email_logs[email_id]['errors'].append({
                            'timestamp': log_entry['timestamp'],
                            'message': log_entry['message'],
                            'category': log_entry['category'],
                            'level': log_entry['level']
                        })
    
    def _determine_log_level(self, message):
        """
        Determine the log level based on message content.
        
        Args:
            message (str): Log message
            
        Returns:
            str: Log level (INFO, WARNING, ERROR, CRITICAL)
        """
        message_lower = message.lower()
        
        if any(keyword in message_lower for keyword in ['critical', 'fatal', 'severe']):
            return 'CRITICAL'
        elif any(keyword in message_lower for keyword in ['error', 'failed', 'failure', 'exception']):
            return 'ERROR'
        elif any(keyword in message_lower for keyword in ['warning', 'warn', 'skipping', 'retrying']):
            return 'WARNING'
        else:
            return 'INFO'
    
    def _categorize_message(self, message):
        """
        Categorize the log message based on its content.
        
        Args:
            message (str): Log message
            
        Returns:
            str: Category of the message
        """
        message_lower = message.lower()
        
        if 'autoresponse' in message_lower:
            return 'AUTORESPONSE'
        elif 'apex' in message_lower:
            return 'APEX'
        elif 'email_client' in message_lower:
            return 'EMAIL_CLIENT'
        elif 'forward' in message_lower:
            return 'FORWARDING'
        elif 'database' in message_lower or 'sql' in message_lower:
            return 'DATABASE'
        elif 'template' in message_lower or 'blob' in message_lower:
            return 'TEMPLATE'
        elif 'classification' in message_lower:
            return 'CLASSIFICATION'
        else:
            return 'SYSTEM'
    
    def _update_stats(self, email_id, log_entry):
        """
        Update statistics for the email processing session.
        
        Args:
            email_id (str): Email ID
            log_entry (dict): Log entry details
        """
        if email_id in self._email_logs:
            stats = self._email_logs[email_id]['stats']
            stats['total_log_entries'] += 1
            
            # Update level counters
            if log_entry['level'] == 'ERROR':
                stats['error_count'] += 1
            elif log_entry['level'] == 'WARNING':
                stats['warning_count'] += 1
            
            # Update category counters
            category = log_entry['category']
            if category == 'AUTORESPONSE':
                stats['autoresponse_logs'] += 1
            elif category == 'APEX':
                stats['apex_logs'] += 1
            elif category == 'EMAIL_CLIENT':
                stats['email_client_logs'] += 1
            else:
                stats['system_logs'] += 1
    
    def log_autoresponse_attempt(self, email_id, attempted=True, successful=False, skip_reason='', 
                                template_folder='', subject_line='', recipient='', error_message=''):
        """
        Log autoresponse attempt details.
        
        Args:
            email_id (str): Email ID
            attempted (bool): Whether autoresponse was attempted
            successful (bool): Whether autoresponse was successful
            skip_reason (str): Reason for skipping autoresponse
            template_folder (str): Template folder used
            subject_line (str): Subject line used
            recipient (str): Recipient email
            error_message (str): Error message if any
        """
        with self._lock:
            if email_id in self._email_logs:
                autoresponse_details = self._email_logs[email_id]['autoresponse_details']
                autoresponse_details.update({
                    'attempted': attempted,
                    'successful': successful,
                    'skip_reason': skip_reason,
                    'template_folder': template_folder,
                    'subject_line': subject_line,
                    'recipient': recipient,
                    'error_message': error_message
                })
    
    def get_email_logs(self, email_id):
        """
        Get all captured logs for a specific email.
        
        Args:
            email_id (str): Email ID to get logs for
            
        Returns:
            dict: Log data and metadata for the email
        """
        with self._lock:
            return self._email_logs.get(email_id, {'logs': [], 'metadata': {}, 'stats': {}, 'errors': [], 'autoresponse_details': {}})
    
    def clear_email_logs(self, email_id):
        """
        Clear logs for a specific email (cleanup after processing).
        
        Args:
            email_id (str): Email ID to clear logs for
        """
        with self._lock:
            if email_id in self._email_logs:
                del self._email_logs[email_id]
    
    def format_logs_for_storage(self, email_id):
        """
        Format captured logs into a comprehensive JSON structure for database storage.
        Enhanced with detailed statistics and error information.
        
        Args:
            email_id (str): Email ID to format logs for
            
        Returns:
            str: Formatted log text ready for database storage
        """
        email_log_data = self.get_email_logs(email_id)
        logs = email_log_data.get('logs', [])
        metadata = email_log_data.get('metadata', {})
        stats = email_log_data.get('stats', {})
        errors = email_log_data.get('errors', [])
        autoresponse_details = email_log_data.get('autoresponse_details', {})
        
        if not logs:
            return "No logs captured for this email."
        
        # Create comprehensive log structure
        log_structure = {
            'session_info': {
                'email_id': metadata.get('email_id', ''),
                'internet_message_id': metadata.get('internet_message_id', ''),
                'email_subject': metadata.get('email_subject', ''),
                'processing_start': metadata.get('start_time', '').isoformat() if metadata.get('start_time') else '',
                'processing_end': metadata.get('end_time', '').isoformat() if metadata.get('end_time') else '',
                'processing_duration_seconds': metadata.get('processing_time_seconds', 0),
                'log_capture_version': '2.0'
            },
            'statistics': {
                'total_log_entries': stats.get('total_log_entries', 0),
                'error_count': stats.get('error_count', 0),
                'warning_count': stats.get('warning_count', 0),
                'autoresponse_logs': stats.get('autoresponse_logs', 0),
                'apex_logs': stats.get('apex_logs', 0),
                'email_client_logs': stats.get('email_client_logs', 0),
                'system_logs': stats.get('system_logs', 0)
            },
            'autoresponse_summary': autoresponse_details,
            'error_summary': {
                'total_errors': len(errors),
                'error_details': errors[:10] if errors else []  # Limit to first 10 errors
            },
            'detailed_logs': []
        }
        
        # Add all log entries with enhanced structure
        for log_entry in logs:
            log_structure['detailed_logs'].append({
                'timestamp': log_entry.get('timestamp', ''),
                'level': log_entry.get('level', 'INFO'),
                'category': log_entry.get('category', 'SYSTEM'),
                'message': log_entry.get('message', '')
            })
        
        # Convert to JSON string for storage
        import json
        try:
            formatted_json = json.dumps(log_structure, indent=2, ensure_ascii=False, default=str)
            return formatted_json
        except Exception as e:
            # Fallback to simple text format if JSON serialization fails
            fallback_lines = [
                "=== EMAIL PROCESSING LOG START ===",
                f"Email ID: {metadata.get('email_id', '')}",
                f"Subject: {metadata.get('email_subject', '')}",
                f"Processing Time: {metadata.get('processing_time_seconds', 0):.2f} seconds",
                f"Total Log Entries: {stats.get('total_log_entries', 0)}",
                f"Errors: {stats.get('error_count', 0)}",
                f"Warnings: {stats.get('warning_count', 0)}",
                "",
                "=== AUTORESPONSE DETAILS ===",
                f"Attempted: {autoresponse_details.get('attempted', False)}",
                f"Successful: {autoresponse_details.get('successful', False)}",
                f"Skip Reason: {autoresponse_details.get('skip_reason', '')}",
                "",
                "=== DETAILED LOGS ===",
            ]
            
            for log_entry in logs:
                fallback_lines.append(f"[{log_entry.get('level', 'INFO')}] {log_entry.get('timestamp', '')}: {log_entry.get('message', '')}")
            
            fallback_lines.append("=== EMAIL PROCESSING LOG END ===")
            
            return "\n".join(fallback_lines)

# Global instance for email log capture
email_log_capture = EmailLogCapture()

def email_log(message):
    """
    Convenience function for email-specific logging.
    Use this instead of print() for log messages you want captured per email.
    
    Args:
        message (str): Log message to capture and print
    """
    email_log_capture.email_log(message)

def create_log(email_data):
    """
    Create a new log entry for an email being processed.
    
    Args:
        email_data (dict): Dictionary containing email data
        
    Returns:
        dict: Initial log entry with basic email information
    """
    log = {"id": str(uuid.uuid4())}
    
    try:
        # Add email ID
        add_to_log("eml_id", email_data.get('email_id'), log)
        add_to_log("internet_message_id", email_data.get('internet_message_id'), log)
        
        # Process date received with error handling
        try:
            date_received_str = email_data.get('date_received')
            if date_received_str:
                date_received_dt = datetime.datetime.strptime(date_received_str, '%Y-%m-%dT%H:%M:%SZ')
                date_received_dt = date_received_dt + datetime.timedelta(hours=2)
                add_to_log("dttm_rec", date_received_dt, log)
            else:
                add_to_log("dttm_rec", datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S'), log)
        except Exception as e:
            email_log(f"Script: apex_logging.py - Function: create_log - Error processing date: {str(e)}")
            add_to_log("dttm_rec", datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S'), log)
        
        # Add processing time and email details
        add_to_log("dttm_proc", datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S'), log)
        add_to_log("eml_to", email_data.get('to'), log)
        add_to_log("eml_frm", email_data.get('from'), log)
        add_to_log("eml_cc", email_data.get('cc'), log)
        add_to_log("eml_sub", email_data.get('subject'), log)
        
        # Handle potentially large body text
        body_text = email_data.get('body_text', '')
        if body_text and len(body_text) > 8000:  # SQL Server VARCHAR(MAX) has practical limits
            body_text = body_text[:8000] + "... [truncated]"
        add_to_log("eml_bdy", body_text, log) 
    except Exception as e:
        email_log(f"Script: apex_logging.py - Function: create_log - Error creating log: {str(e)}")
        # Ensure we have at least a valid ID
        if "id" not in log:
            log["id"] = str(uuid.uuid4())
    
    return log

def add_to_log(key, value, log):
    """
    Add a key-value pair to the log, with error handling.
    
    Args:
        key (str): Log field name
        value: Value to add to the log
        log (dict): Log dictionary to update
        
    Returns:
        None
    """
    try:
        # Handle None values
        if value is None:
            log[key] = ""
        else:
            log[key] = value
    except Exception as e:
        email_log(f"Script: apex_logging.py - Function: add_to_log - Error adding {key} to log: {str(e)}")
        # Set to empty string if error occurs
        log[key] = ""

def log_apex_success(apex_response, log):
    """
    Add successful APEX classification results to the log.
    
    Args:
        apex_response (dict): Response from APEX classification
        log (dict): Log dictionary to update
        
    Returns:
        None
    """
    try:
        message = apex_response.get('message', {})
        
        # Store the final classification
        add_to_log("apex_class", message.get('classification', 'error'), log)
        add_to_log("apex_class_rsn", message.get('rsn_classification', 'error'), log)
        add_to_log("apex_action_req", message.get('action_required', 'error'), log)
        add_to_log("apex_sentiment", message.get('sentiment', 'error'), log)
        add_to_log("apex_cost_usd", message.get('apex_cost_usd', 0.0), log)
        
        # Store the top 3 categories
        top_categories = message.get('top_categories', [])
        
        # Handle different possible formats of top_categories
        if isinstance(top_categories, list):
            # Convert list to string representation for storage
            top_categories_str = ', '.join(top_categories)
            add_to_log("apex_top_categories", top_categories_str, log)
        elif isinstance(top_categories, str):
            # If it's already a string, store directly
            add_to_log("apex_top_categories", top_categories, log)
        else:
            # If format is unexpected, try to convert to string
            try:
                top_categories_str = str(top_categories)
                add_to_log("apex_top_categories", top_categories_str, log)
            except:
                # If even that fails, set empty
                add_to_log("apex_top_categories", "", log)
            
        # Add new fields for region and token tracking
        add_to_log("region_used", message.get('region_used', 'main'), log)
        
        # GPT-4o token usage
        add_to_log("gpt_4o_prompt_tokens", message.get('gpt_4o_prompt_tokens', 0), log)
        add_to_log("gpt_4o_completion_tokens", message.get('gpt_4o_completion_tokens', 0), log)
        add_to_log("gpt_4o_total_tokens", message.get('gpt_4o_total_tokens', 0), log)
        add_to_log("gpt_4o_cached_tokens", message.get('gpt_4o_cached_tokens', 0), log)
        
        # GPT-4o-mini token usage
        add_to_log("gpt_4o_mini_prompt_tokens", message.get('gpt_4o_mini_prompt_tokens', 0), log)
        add_to_log("gpt_4o_mini_completion_tokens", message.get('gpt_4o_mini_completion_tokens', 0), log)
        add_to_log("gpt_4o_mini_total_tokens", message.get('gpt_4o_mini_total_tokens', 0), log)
        add_to_log("gpt_4o_mini_cached_tokens", message.get('gpt_4o_mini_cached_tokens', 0), log)
            
    except Exception as e:
        email_log(f"Script: apex_logging.py - Function: log_apex_success - Error logging APEX success: {str(e)}")
        # Set error values if exception occurs
        add_to_log("apex_class", "error", log)
        add_to_log("apex_class_rsn", f"error logging success: {str(e)}", log)
        add_to_log("apex_action_req", "error", log)
        add_to_log("apex_sentiment", "error", log)
        add_to_log("apex_cost_usd", 0.00, log)
        add_to_log("apex_top_categories", "", log)
        add_to_log("region_used", "error", log)
        add_to_log("gpt_4o_prompt_tokens", 0, log)
        add_to_log("gpt_4o_completion_tokens", 0, log)
        add_to_log("gpt_4o_total_tokens", 0, log)
        add_to_log("gpt_4o_cached_tokens", 0, log)
        add_to_log("gpt_4o_mini_prompt_tokens", 0, log)
        add_to_log("gpt_4o_mini_completion_tokens", 0, log)
        add_to_log("gpt_4o_mini_total_tokens", 0, log)
        add_to_log("gpt_4o_mini_cached_tokens", 0, log)


def log_apex_fail(log, classification_error_message):
    """
    Add failed APEX classification details to the log.
    
    Args:
        log (dict): Log dictionary to update
        classification_error_message: Error message from APEX classification
        
    Returns:
        None
    """
    try:
        error_msg = str(classification_error_message)
        if len(error_msg) > 8000:  # Limit error message length for SQL
            error_msg = error_msg[:8000] + "... [truncated]"
            
        add_to_log("apex_class", "error", log)
        add_to_log("apex_class_rsn", f"error : {error_msg}", log)
        add_to_log("apex_action_req", "error", log)
        add_to_log("apex_sentiment", "error", log)
        add_to_log("apex_cost_usd", 0.00, log)
        add_to_log("apex_top_categories", "", log)
        add_to_log("apex_intervention", "false", log)
        
        # Add defaults for new fields
        add_to_log("region_used", "error", log)
        add_to_log("gpt_4o_prompt_tokens", 0, log)
        add_to_log("gpt_4o_completion_tokens", 0, log)
        add_to_log("gpt_4o_total_tokens", 0, log)
        add_to_log("gpt_4o_cached_tokens", 0, log)
        add_to_log("gpt_4o_mini_prompt_tokens", 0, log)
        add_to_log("gpt_4o_mini_completion_tokens", 0, log)
        add_to_log("gpt_4o_mini_total_tokens", 0, log)
        add_to_log("gpt_4o_mini_cached_tokens", 0, log)
    except Exception as e:
        email_log(f"Script: apex_logging.py - Function: log_apex_fail - Error logging APEX failure: {str(e)}")
        # Set generic error values if exception occurs
        add_to_log("apex_class", "error", log)
        add_to_log("apex_class_rsn", "severe error in logging", log)
        add_to_log("apex_action_req", "error", log)
        add_to_log("apex_sentiment", "error", log)
        add_to_log("apex_cost_usd", 0.00, log)
        add_to_log("apex_top_categories", "", log)
        add_to_log("apex_intervention", "false", log)
        add_to_log("region_used", "error", log)
        add_to_log("gpt_4o_prompt_tokens", 0, log)
        add_to_log("gpt_4o_completion_tokens", 0, log)
        add_to_log("gpt_4o_total_tokens", 0, log)
        add_to_log("gpt_4o_cached_tokens", 0, log)
        add_to_log("gpt_4o_mini_prompt_tokens", 0, log)
        add_to_log("gpt_4o_mini_completion_tokens", 0, log)
        add_to_log("gpt_4o_mini_total_tokens", 0, log)
        add_to_log("gpt_4o_mini_cached_tokens", 0, log)

def log_apex_intervention(log, original_destination, routed_destination):
    """
    Determine and log if AI intervention occurred (changed destination).
    
    Args:
        log (dict): Log dictionary to update
        original_destination (str): Original destination email address
        routed_destination (str): Final destination email address after AI classification
        
    Returns:
        None
    """
    try:
        # Compare original and routed destinations - case insensitive comparison
        if original_destination.lower() != routed_destination.lower():
            add_to_log("apex_intervention", "true", log)
        else:
            add_to_log("apex_intervention", "false", log)
    except Exception as e:
        email_log(f"Script: apex_logging.py - Function: log_apex_intervention - Error logging intervention: {str(e)}")
        # Default to false if error occurs
        add_to_log("apex_intervention", "false", log)

# =======================================================================================
# NEW SKIPPED EMAIL LOGGING FUNCTIONS
# =======================================================================================

def create_skipped_email_log(email_data, reason_skipped, account_processed=None, skip_type="DUPLICATE", processing_time=0.0):
    """
    Create a new log entry for a skipped email.
    
    Args:
        email_data (dict): Dictionary containing email data
        reason_skipped (str): Reason why the email was skipped
        account_processed (str): Which email account was being processed (optional)
        skip_type (str): Type of skip (DUPLICATE, ERROR, etc.)
        processing_time (float): Time spent before skipping (optional)
        
    Returns:
        dict: Log entry for the skipped email
    """
    log = {"id": str(uuid.uuid4())}
    
    try:
        # Add email ID
        add_to_skipped_log("eml_id", email_data.get('email_id'), log)
        add_to_skipped_log("internet_message_id", email_data.get('internet_message_id'), log)
        
        # Process date received with error handling
        try:
            date_received_str = email_data.get('date_received')
            if date_received_str:
                # Handle different date formats
                if 'T' in date_received_str and 'Z' in date_received_str:
                    # ISO format: '2025-06-17T08:18:36Z'
                    date_received_dt = datetime.datetime.strptime(date_received_str, '%Y-%m-%dT%H:%M:%SZ')
                    date_received_dt = date_received_dt + datetime.timedelta(hours=2)  # Adjust timezone
                elif 'T' in date_received_str:
                    # ISO format without Z: '2025-06-17T08:18:36'
                    date_received_dt = datetime.datetime.strptime(date_received_str, '%Y-%m-%dT%H:%M:%S')
                    date_received_dt = date_received_dt + datetime.timedelta(hours=2)  # Adjust timezone
                else:
                    # Try parsing as standard datetime string
                    date_received_dt = datetime.datetime.strptime(date_received_str, '%Y-%m-%d %H:%M:%S.%f')
                
                add_to_skipped_log("dttm_rec", date_received_dt, log)
            else:
                add_to_skipped_log("dttm_rec", datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))), log)
        except Exception as e:
            email_log(f"Script: apex_logging.py - Function: create_skipped_email_log - Error processing date: {str(e)}")
            add_to_skipped_log("dttm_rec", datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))), log)
        
        # Add processing time (when the skip occurred)
        add_to_skipped_log("dttm_proc", datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))), log)
        
        # Add email header details
        add_to_skipped_log("eml_frm", email_data.get('from'), log)
        add_to_skipped_log("eml_to", email_data.get('to'), log)
        add_to_skipped_log("eml_cc", email_data.get('cc'), log)
        add_to_skipped_log("eml_subject", email_data.get('subject'), log)
        
        # Handle potentially large body text
        body_text = email_data.get('body_text', '')
        if body_text and len(body_text) > 8000:  # SQL Server VARCHAR(MAX) has practical limits
            body_text = body_text[:8000] + "... [truncated]"
        add_to_skipped_log("eml_body", body_text, log)
        
        # Add skip-specific information
        add_to_skipped_log("rsn_skipped", reason_skipped, log)
        add_to_skipped_log("skip_type", skip_type, log)
        add_to_skipped_log("account_processed", account_processed, log)
        add_to_skipped_log("processing_time_seconds", processing_time, log)
        add_to_skipped_log("created_timestamp", datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))), log)
        
    except Exception as e:
        email_log(f"Script: apex_logging.py - Function: create_skipped_email_log - Error creating skipped email log: {str(e)}")
        # Ensure we have at least a valid ID and reason
        if "id" not in log:
            log["id"] = str(uuid.uuid4())
        if "rsn_skipped" not in log:
            log["rsn_skipped"] = f"Error creating log: {str(e)}"
    
    return log

def add_to_skipped_log(key, value, log):
    """
    Add a key-value pair to the skipped email log, with error handling.
    
    Args:
        key (str): Log field name
        value: Value to add to the log
        log (dict): Log dictionary to update
        
    Returns:
        None
    """
    try:
        # Handle None values
        if value is None:
            log[key] = "" if key != "processing_time_seconds" else 0.0
        else:
            log[key] = value
    except Exception as e:
        email_log(f"Script: apex_logging.py - Function: add_to_skipped_log - Error adding {key} to skipped log: {str(e)}")
        # Set appropriate default based on field type
        if key == "processing_time_seconds":
            log[key] = 0.0
        elif key in ["dttm_rec", "dttm_proc", "created_timestamp"]:
            log[key] = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2)))
        else:
            log[key] = ""

async def insert_skipped_email_to_db(skipped_log, max_retries=3):
    """
    Insert a skipped email log entry into the SQL database with retry logic.
    
    Args:
        skipped_log (dict): Skipped email log dictionary to insert
        max_retries (int): Maximum number of retry attempts
        
    Returns:
        bool: True if successful, False otherwise
    """
    server = SQL_SERVER
    database = SQL_DATABASE
    username = SQL_USERNAME
    password = SQL_PASSWORD
    
    def db_operation():
        """Database insertion operation to be executed in a separate thread"""
        for attempt in range(max_retries):
            try:
                # Connect to the database
                conn = pyodbc.connect(
                    f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password}'
                )
                cursor = conn.cursor()
                
                # Prepare SQL statement for skipped_mails table
                columns = ', '.join(skipped_log.keys())
                placeholders = ', '.join(['?' for _ in skipped_log.values()])
                sql = f"INSERT INTO [{database}].[dbo].[skipped_mails] ({columns}) VALUES ({placeholders})"
                
                # Sanitize values for SQL insertion
                values = []
                for value in skipped_log.values():
                    if isinstance(value, str):
                        # Handle string encoding and truncation if necessary
                        try:
                            sanitized = value.encode('utf-8').decode('utf-8')
                            values.append(sanitized)
                        except UnicodeError:
                            # If encoding fails, use a placeholder
                            values.append("[encoding error]")
                    else:
                        values.append(value)
                
                # Execute SQL
                cursor.execute(sql, tuple(values))
                conn.commit()
                email_log(f"Script: apex_logging.py - Function: insert_skipped_email_to_db - Successfully added skipped email to DB")
                
                cursor.close()
                conn.close()
                return True
                
            except pyodbc.Error as e:
                email_log(f"Script: apex_logging.py - Function: insert_skipped_email_to_db - Database error (attempt {attempt+1}/{max_retries}): {str(e)}")
                
                if attempt < max_retries - 1:
                    # Implement backoff strategy
                    time.sleep(2 ** attempt)
                else:
                    email_log(f"Script: apex_logging.py - Function: insert_skipped_email_to_db - Failed to insert skipped email log after {max_retries} attempts")
                    
            except Exception as e:
                email_log(f"Script: apex_logging.py - Function: insert_skipped_email_to_db - Unexpected error: {str(e)}")
                
                if attempt < max_retries - 1:
                    # Implement backoff strategy
                    time.sleep(2 ** attempt)
                else:
                    email_log(f"Script: apex_logging.py - Function: insert_skipped_email_to_db - Failed to insert skipped email log after {max_retries} attempts")
        
        return False
    
    try:
        return await asyncio.get_event_loop().run_in_executor(db_pool, db_operation)
    except Exception as e:
        email_log(f"Script: apex_logging.py - Function: insert_skipped_email_to_db - Error executing db_operation: {str(e)}")
        return False

async def log_skipped_email(email_data, reason_skipped, account_processed=None, skip_type="DUPLICATE", processing_time=0.0):
    """
    Complete function to log a skipped email - creates log and inserts to database.
    
    Args:
        email_data (dict): Dictionary containing email data
        reason_skipped (str): Reason why the email was skipped
        account_processed (str): Which email account was being processed (optional)
        skip_type (str): Type of skip (DUPLICATE, ERROR, etc.)
        processing_time (float): Time spent before skipping (optional)
        
    Returns:
        bool: True if successfully logged, False otherwise
    """
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        email_log(f">> {timestamp} Script: apex_logging.py - Function: log_skipped_email - Creating skipped email log entry")
        
        # Create the skipped email log
        skipped_log = create_skipped_email_log(
            email_data, 
            reason_skipped, 
            account_processed, 
            skip_type, 
            processing_time
        )
        
        # Insert to database
        success = await insert_skipped_email_to_db(skipped_log)
        
        if success:
            email_log(f">> {timestamp} Script: apex_logging.py - Function: log_skipped_email - Successfully logged skipped email: {email_data.get('subject', 'No Subject')}")
        else:
            email_log(f">> {timestamp} Script: apex_logging.py - Function: log_skipped_email - Failed to log skipped email: {email_data.get('subject', 'No Subject')}")
        
        return success
        
    except Exception as e:
        email_log(f">> {timestamp} Script: apex_logging.py - Function: log_skipped_email - Error logging skipped email: {str(e)}")
        return False

# Synchronous version for backward compatibility
def log_skipped_email_sync(email_data, reason_skipped, account_processed=None, skip_type="DUPLICATE", processing_time=0.0):
    """
    Synchronous wrapper for log_skipped_email
    
    Args:
        email_data (dict): Dictionary containing email data
        reason_skipped (str): Reason why the email was skipped
        account_processed (str): Which email account was being processed (optional)
        skip_type (str): Type of skip (DUPLICATE, ERROR, etc.)
        processing_time (float): Time spent before skipping (optional)
        
    Returns:
        bool: True if successfully logged, False otherwise
    """
    try:
        return asyncio.run(log_skipped_email(email_data, reason_skipped, account_processed, skip_type, processing_time))
    except Exception as e:
        email_log(f"Script: apex_logging.py - Function: log_skipped_email_sync - Error: {str(e)}")
        return False

# =======================================================================================
# END OF SKIPPED EMAIL LOGGING FUNCTIONS
# =======================================================================================

async def insert_log_to_db(log, max_retries=3):
    """
    Insert a log entry into the SQL database with retry logic.
    
    Args:
        log (dict): Log dictionary to insert
        max_retries (int): Maximum number of retry attempts
        
    Returns:
        bool: True if successful, False otherwise
    """
    server = SQL_SERVER
    database = SQL_DATABASE
    username = SQL_USERNAME
    password = SQL_PASSWORD
    
    def db_operation():
        """Database insertion operation to be executed in a separate thread"""
        for attempt in range(max_retries):
            try:
                # Connect to the database
                conn = pyodbc.connect(
                    f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password}'
                )
                cursor = conn.cursor()
                
                # Prepare SQL statement
                columns = ', '.join(log.keys())
                placeholders = ', '.join(['?' for _ in log.values()])
                sql = f"INSERT INTO [{database}].[dbo].[logs] ({columns}) VALUES ({placeholders})"
                
                # Sanitize values for SQL insertion
                values = []
                for value in log.values():
                    if isinstance(value, str):
                        # Handle string encoding and truncation if necessary
                        try:
                            sanitized = value.encode('utf-8').decode('utf-8')
                            values.append(sanitized)
                        except UnicodeError:
                            # If encoding fails, use a placeholder
                            values.append("[encoding error]")
                    else:
                        values.append(value)
                
                # Execute SQL
                cursor.execute(sql, tuple(values))
                conn.commit()
                email_log(f"Script: apex_logging.py - Function: insert_log_to_db - Successfully added to DB")
                
                cursor.close()
                conn.close()
                return True
                
            except pyodbc.Error as e:
                email_log(f"Script: apex_logging.py - Function: insert_log_to_db - Database error (attempt {attempt+1}/{max_retries}): {str(e)}")
                
                if attempt < max_retries - 1:
                    # Implement backoff strategy
                    time.sleep(2 ** attempt)
                else:
                    email_log(f"Script: apex_logging.py - Function: insert_log_to_db - Failed to insert log after {max_retries} attempts")
                    
            except Exception as e:
                email_log(f"Script: apex_logging.py - Function: insert_log_to_db - Unexpected error: {str(e)}")
                
                if attempt < max_retries - 1:
                    # Implement backoff strategy
                    time.sleep(2 ** attempt)
                else:
                    email_log(f"Script: apex_logging.py - Function: insert_log_to_db - Failed to insert log after {max_retries} attempts")
        
        return False
    
    try:
        return await asyncio.get_event_loop().run_in_executor(db_pool, db_operation)
    except Exception as e:
        email_log(f"Script: apex_logging.py - Function: insert_log_to_db - Error executing db_operation: {str(e)}")
        return False

async def insert_system_log_to_db(email_id, max_retries=3):
    """
    Insert enhanced system logs for a specific email into the system_logs table.
    Now includes comprehensive autoresponse and error details.
    
    Args:
        email_id (str): Email ID to get logs for
        max_retries (int): Maximum number of retry attempts
        
    Returns:
        bool: True if successful, False otherwise
    """
    server = SQL_SERVER
    database = SQL_DATABASE
    username = SQL_USERNAME
    password = SQL_PASSWORD
    
    def db_operation():
        """Database insertion operation for enhanced system logs"""
        for attempt in range(max_retries):
            try:
                # Get email log data
                email_log_data = email_log_capture.get_email_logs(email_id)
                metadata = email_log_data.get('metadata', {})
                stats = email_log_data.get('stats', {})
                autoresponse_details = email_log_data.get('autoresponse_details', {})
                errors = email_log_data.get('errors', [])
                
                if not email_log_data.get('logs'):
                    email_log(f"Script: apex_logging.py - Function: insert_system_log_to_db - No logs found for email {email_id}")
                    return False
                
                # Format logs for database storage with enhanced structure
                log_details = email_log_capture.format_logs_for_storage(email_id)
                
                # Create enhanced system log entry
                system_log = {
                    'id': str(uuid.uuid4()),
                    'eml_id': metadata.get('email_id', ''),
                    'internet_message_id': metadata.get('internet_message_id', ''),
                    'log_details': log_details,
                    'log_entry_count': len(email_log_data.get('logs', [])),
                    'created_timestamp': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))),
                    'processing_start_time': metadata.get('start_time'),
                    'processing_end_time': metadata.get('end_time'),
                    'processing_duration_seconds': metadata.get('processing_time_seconds', 0),
                    'email_subject': metadata.get('email_subject', ''),
                    'total_errors': stats.get('error_count', 0),
                    'total_warnings': stats.get('warning_count', 0),
                    'autoresponse_attempted': autoresponse_details.get('attempted', False),
                    'autoresponse_successful': autoresponse_details.get('successful', False),
                    'autoresponse_skip_reason': autoresponse_details.get('skip_reason', ''),
                    'template_folder_used': autoresponse_details.get('template_folder', ''),
                    'autoresponse_subject': autoresponse_details.get('subject_line', ''),
                    'autoresponse_recipient': autoresponse_details.get('recipient', ''),
                    'autoresponse_error': autoresponse_details.get('error_message', ''),
                    'log_stats_json': str({
                        'total_log_entries': stats.get('total_log_entries', 0),
                        'autoresponse_logs': stats.get('autoresponse_logs', 0),
                        'apex_logs': stats.get('apex_logs', 0),
                        'email_client_logs': stats.get('email_client_logs', 0),
                        'system_logs': stats.get('system_logs', 0)
                    })
                }
                
                # Connect to database
                conn = pyodbc.connect(
                    f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password}'
                )
                cursor = conn.cursor()
                
                # Prepare SQL statement for enhanced system_logs table
                columns = ', '.join(system_log.keys())
                placeholders = ', '.join(['?' for _ in system_log.values()])
                sql = f"INSERT INTO [{database}].[dbo].[system_logs] ({columns}) VALUES ({placeholders})"
                
                # Sanitize values
                values = []
                for value in system_log.values():
                    if isinstance(value, str):
                        try:
                            sanitized = value.encode('utf-8').decode('utf-8')
                            values.append(sanitized)
                        except UnicodeError:
                            values.append("[encoding error]")
                    else:
                        values.append(value)
                
                # Execute SQL
                cursor.execute(sql, tuple(values))
                conn.commit()
                
                email_log(f"Script: apex_logging.py - Function: insert_system_log_to_db - Enhanced system log inserted successfully for email {email_id}")
                
                cursor.close()
                conn.close()
                return True
                
            except pyodbc.Error as e:
                email_log(f"Script: apex_logging.py - Function: insert_system_log_to_db - Database error (attempt {attempt+1}/{max_retries}): {str(e)}")
                
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    email_log(f"Script: apex_logging.py - Function: insert_system_log_to_db - Failed to insert system log after {max_retries} attempts")
                    
            except Exception as e:
                email_log(f"Script: apex_logging.py - Function: insert_system_log_to_db - Unexpected error: {str(e)}")
                
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    email_log(f"Script: apex_logging.py - Function: insert_system_log_to_db - Failed to insert system log after {max_retries} attempts")
        
        return False
    
    try:
        return await asyncio.get_event_loop().run_in_executor(db_pool, db_operation)
    except Exception as e:
        email_log(f"Script: apex_logging.py - Function: insert_system_log_to_db - Error executing db_operation: {str(e)}")
        return False

async def check_email_processed(email_id, max_retries=3):
    """
    Check if an email has already been processed by looking up its ID in the database.
    
    Args:
        email_id (str): Internet message ID to check
        max_retries (int): Maximum number of retry attempts
        
    Returns:
        bool: True if email has been processed, False otherwise
    """
    if not email_id:
        email_log(f"Script: apex_logging.py - Function: check_email_processed - No email ID provided")
        return False
        
    server = SQL_SERVER
    database = SQL_DATABASE
    username = SQL_USERNAME
    password = SQL_PASSWORD
    
    def db_check():
        """Database check operation to be executed in a separate thread"""
        for attempt in range(max_retries):
            try:
                conn = pyodbc.connect(
                    f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password}'
                )
                cursor = conn.cursor()
                
                # Use parameterized query to prevent SQL injection
                sql = f"SELECT COUNT(*) FROM [{database}].[dbo].[logs] WHERE internet_message_id = ?"
                cursor.execute(sql, (email_id,))
                count = cursor.fetchone()[0]
                
                cursor.close()
                conn.close()
                
                return count > 0
                
            except pyodbc.Error as e:
                email_log(f"Script: apex_logging.py - Function: check_email_processed - Database error (attempt {attempt+1}/{max_retries}): {str(e)}")
                
                if attempt < max_retries - 1:
                    # Implement backoff strategy
                    time.sleep(2 ** attempt)
                else:
                    email_log(f"Script: apex_logging.py - Function: check_email_processed - Failed to check email status after {max_retries} attempts")
                    # If we can't check, assume it hasn't been processed to avoid skipping emails
                    return False
                    
            except Exception as e:
                email_log(f"Script: apex_logging.py - Function: check_email_processed - Unexpected error: {str(e)}")
                
                if attempt < max_retries - 1:
                    # Implement backoff strategy
                    time.sleep(2 ** attempt)
                else:
                    email_log(f"Script: apex_logging.py - Function: check_email_processed - Failed to check email status after {max_retries} attempts")
                    # If we can't check, assume it hasn't been processed to avoid skipping emails
                    return False
        
        # Default return if all retries fail
        return False
    
    try:
        return await asyncio.get_event_loop().run_in_executor(db_pool, db_check)
    except Exception as e:
        email_log(f"Script: apex_logging.py - Function: check_email_processed - Error executing db_check: {str(e)}")
        # If we can't check, assume it hasn't been processed to avoid skipping emails
        return False

# Synchronous version for backward compatibility
def insert_log_to_db_sync(log):
    """
    Synchronous wrapper for insert_log_to_db
    
    Args:
        log (dict): Log dictionary to insert
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        return asyncio.run(insert_log_to_db(log))
    except Exception as e:
        email_log(f"Script: apex_logging.py - Function: insert_log_to_db_sync - Error: {str(e)}")
        return False
