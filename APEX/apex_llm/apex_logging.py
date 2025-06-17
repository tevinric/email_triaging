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
    """
    
    def __init__(self):
        self._current_email = threading.local()
        self._email_logs = {}  # {email_id: {'logs': [], 'metadata': {}}}
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
        
        # Initialize log storage for this email
        with self._lock:
            self._email_logs[email_id] = {
                'logs': [],
                'metadata': {
                    'email_id': email_id,
                    'internet_message_id': internet_message_id,
                    'email_subject': email_subject[:500] if email_subject else "",  # Limit subject length
                    'start_time': self._current_email.start_time,
                    'end_time': None
                }
            }
        
        try:
            yield
        finally:
            # Mark end time
            end_time = datetime.datetime.now()
            with self._lock:
                if email_id in self._email_logs:
                    self._email_logs[email_id]['metadata']['end_time'] = end_time
    
    def email_log(self, message):
        """
        Log a message for the current email context and print to console.
        This function should be used instead of print() for email-specific logging.
        
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
                'message': str(message)
            }
            
            with self._lock:
                if email_id in self._email_logs:
                    self._email_logs[email_id]['logs'].append(log_entry)
    
    def get_email_logs(self, email_id):
        """
        Get all captured logs for a specific email.
        
        Args:
            email_id (str): Email ID to get logs for
            
        Returns:
            dict: Log data and metadata for the email
        """
        with self._lock:
            return self._email_logs.get(email_id, {'logs': [], 'metadata': {}})
    
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
        Format captured logs into a single text block for database storage.
        
        Args:
            email_id (str): Email ID to format logs for
            
        Returns:
            str: Formatted log text ready for database storage
        """
        email_log_data = self.get_email_logs(email_id)
        logs = email_log_data.get('logs', [])
        
        if not logs:
            return "No logs captured for this email."
        
        # Format logs into a single text block
        formatted_lines = []
        formatted_lines.append("=== EMAIL PROCESSING LOG START ===")
        
        for log_entry in logs:
            formatted_lines.append(f"{log_entry['timestamp']}: {log_entry['message']}")
        
        formatted_lines.append("=== EMAIL PROCESSING LOG END ===")
        
        return "\n".join(formatted_lines)

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
    Insert system logs for a specific email into the system_logs table.
    
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
        """Database insertion operation for system logs"""
        for attempt in range(max_retries):
            try:
                # Get email log data
                email_log_data = email_log_capture.get_email_logs(email_id)
                metadata = email_log_data.get('metadata', {})
                
                if not email_log_data.get('logs'):
                    email_log(f"Script: apex_logging.py - Function: insert_system_log_to_db - No logs found for email {email_id}")
                    return False
                
                # Format logs for database storage
                log_details = email_log_capture.format_logs_for_storage(email_id)
                
                # Create system log entry
                system_log = {
                    'id': str(uuid.uuid4()),
                    'eml_id': metadata.get('email_id', ''),
                    'internet_message_id': metadata.get('internet_message_id', ''),
                    'log_details': log_details,
                    'log_entry_count': len(email_log_data.get('logs', [])),
                    'created_timestamp': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))),
                    'processing_start_time': metadata.get('start_time'),
                    'processing_end_time': metadata.get('end_time'),
                    'email_subject': metadata.get('email_subject', '')
                }
                
                # Connect to database
                conn = pyodbc.connect(
                    f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password}'
                )
                cursor = conn.cursor()
                
                # Prepare SQL statement
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
                
                email_log(f"Script: apex_logging.py - Function: insert_system_log_to_db - System log inserted successfully for email {email_id}")
                
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
