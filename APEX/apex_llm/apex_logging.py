import uuid
import datetime
import time
import pyodbc
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

# SQL SERVER CONNECTION SETTINGS
from config import SQL_SERVER, SQL_DATABASE, SQL_USERNAME, SQL_PASSWORD

# Thread pool for database operations
db_pool = ThreadPoolExecutor(max_workers=5)

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
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: apex_logging.py - Function: create_log - Error processing date: {str(e)}")
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
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: apex_logging.py - Function: create_log - Error creating log: {str(e)}")
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
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: apex_logging.py - Function: add_to_log - Error adding {key} to log: {str(e)}")
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
        add_to_log("apex_class", message.get('classification', 'error'), log)
        add_to_log("apex_class_rsn", message.get('rsn_classification', 'error'), log)
        add_to_log("apex_action_req", message.get('action_required', 'error'), log)
        add_to_log("apex_sentiment", message.get('sentiment', 'error'), log)
        add_to_log("apex_cost_usd", message.get('apex_cost_usd', 0.0), log)
    except Exception as e:
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: apex_logging.py - Function: log_apex_success - Error logging APEX success: {str(e)}")
        # Set error values if exception occurs
        add_to_log("apex_class", "error", log)
        add_to_log("apex_class_rsn", f"error logging success: {str(e)}", log)
        add_to_log("apex_action_req", "error", log)
        add_to_log("apex_sentiment", "error", log)
        add_to_log("apex_cost_usd", 0.00, log)

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
    except Exception as e:
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: apex_logging.py - Function: log_apex_fail - Error logging APEX failure: {str(e)}")
        # Set generic error values if exception occurs
        add_to_log("apex_class", "error", log)
        add_to_log("apex_class_rsn", "severe error in logging", log)
        add_to_log("apex_action_req", "error", log)
        add_to_log("apex_sentiment", "error", log)
        add_to_log("apex_cost_usd", 0.00, log)

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
                print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: apex_logging.py - Function: insert_log_to_db - Successfully added to DB")
                
                cursor.close()
                conn.close()
                return True
                
            except pyodbc.Error as e:
                print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: apex_logging.py - Function: insert_log_to_db - Database error (attempt {attempt+1}/{max_retries}): {str(e)}")
                
                if attempt < max_retries - 1:
                    # Implement backoff strategy
                    time.sleep(2 ** attempt)
                else:
                    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: apex_logging.py - Function: insert_log_to_db - Failed to insert log after {max_retries} attempts")
                    
            except Exception as e:
                print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: apex_logging.py - Function: insert_log_to_db - Unexpected error: {str(e)}")
                
                if attempt < max_retries - 1:
                    # Implement backoff strategy
                    time.sleep(2 ** attempt)
                else:
                    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: apex_logging.py - Function: insert_log_to_db - Failed to insert log after {max_retries} attempts")
        
        return False
    
    try:
        return await asyncio.get_event_loop().run_in_executor(db_pool, db_operation)
    except Exception as e:
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: apex_logging.py - Function: insert_log_to_db - Error executing db_operation: {str(e)}")
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
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: apex_logging.py - Function: check_email_processed - No email ID provided")
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
                print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: apex_logging.py - Function: check_email_processed - Database error (attempt {attempt+1}/{max_retries}): {str(e)}")
                
                if attempt < max_retries - 1:
                    # Implement backoff strategy
                    time.sleep(2 ** attempt)
                else:
                    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: apex_logging.py - Function: check_email_processed - Failed to check email status after {max_retries} attempts")
                    # If we can't check, assume it hasn't been processed to avoid skipping emails
                    return False
                    
            except Exception as e:
                print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: apex_logging.py - Function: check_email_processed - Unexpected error: {str(e)}")
                
                if attempt < max_retries - 1:
                    # Implement backoff strategy
                    time.sleep(2 ** attempt)
                else:
                    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: apex_logging.py - Function: check_email_processed - Failed to check email status after {max_retries} attempts")
                    # If we can't check, assume it hasn't been processed to avoid skipping emails
                    return False
        
        # Default return if all retries fail
        return False
    
    try:
        return await asyncio.get_event_loop().run_in_executor(db_pool, db_check)
    except Exception as e:
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: apex_logging.py - Function: check_email_processed - Error executing db_check: {str(e)}")
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
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: apex_logging.py - Function: insert_log_to_db_sync - Error: {str(e)}")
        return False
