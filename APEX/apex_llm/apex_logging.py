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

    log = {"id": str(uuid.uuid4())}
    add_to_log("eml_id", email_data.get('email_id'), log)
    add_to_log("internet_message_id", email_data.get('internet_message_id'), log)
    date_received_str = email_data.get('date_received')
    date_received_dt = datetime.datetime.strptime(date_received_str, '%Y-%m-%dT%H:%M:%SZ')
    date_received_dt = date_received_dt + datetime.timedelta(hours=2)
    add_to_log("dttm_rec", date_received_dt, log)
    add_to_log("dttm_proc", datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S'), log)
    add_to_log("eml_to", email_data.get('to'), log)
    add_to_log("eml_frm", email_data.get('from'), log)
    add_to_log("eml_cc", email_data.get('cc'), log)
    add_to_log("eml_sub", email_data.get('subject'), log)
    add_to_log("eml_bdy", email_data.get('body_text'), log) 
    # Add default acknowledged value of 0
    add_to_log("acknowledged", 0, log)
    return log

def add_to_log(key, value, log):
    log[key] = value

def log_apex_success(apex_response, log):
    add_to_log("apex_class", apex_response['message']['classification'], log)
    add_to_log("apex_class_rsn", apex_response['message']['rsn_classification'], log)
    add_to_log("apex_action_req", apex_response['message']['action_required'], log)
    add_to_log("apex_sentiment", apex_response['message']['sentiment'], log)
    add_to_log("apex_cost_usd", apex_response['message']['apex_cost_usd'], log)

def log_apex_fail(log, classification_error_message):
    add_to_log("apex_class", f"error", log)
    add_to_log("apex_class_rsn", f"error : {classification_error_message}", log)
    add_to_log("apex_action_req", f"error", log)
    add_to_log("apex_sentiment", f"error", log)
    add_to_log("apex_cost_usd", 0.00, log)

async def insert_log_to_db(log):
    server = SQL_SERVER
    database = SQL_DATABASE
    username = SQL_USERNAME
    password = SQL_PASSWORD
    
    def db_operation():
        
        conn = pyodbc.connect(
            f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password}'
        )
        cursor = conn.cursor()
        
        columns = ', '.join(log.keys())
        placeholders = ', '.join(['?' for _ in log.values()])
        sql = f"INSERT INTO [{database}].[dbo].[logs] ({columns}) VALUES ({placeholders})"
        
        values = tuple(str(value).encode('utf-8').decode('utf-8') if isinstance(value, str) else value for value in log.values())
        
        cursor.execute(sql, values)
        conn.commit()
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: apex_logging.py - Function: insert_log_to_db - Successfully added to DB")
        
        cursor.close()
        conn.close()
    
    await asyncio.get_event_loop().run_in_executor(db_pool, db_operation)

async def check_email_processed(email_id):
    server = SQL_SERVER
    database = SQL_DATABASE
    username = SQL_USERNAME
    password = SQL_PASSWORD
    
    def db_check():
        try:
            conn = pyodbc.connect(
                f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password}'
            )
            cursor = conn.cursor()
            
            sql = f"SELECT COUNT(*) FROM [{database}].[dbo].[logs] WHERE internet_message_id = ?"
            cursor.execute(sql, (email_id,))
            count = cursor.fetchone()[0]
            
            cursor.close()
            conn.close()
            
            return count > 0
        except Exception as e:
            print(f"Error : {e}")
    
    return await asyncio.get_event_loop().run_in_executor(db_pool, db_check)

# Synchronous version for backward compatibility
def insert_log_to_db_sync(log):
    asyncio.run(insert_log_to_db(log))
