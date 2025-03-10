import sys
import time
import asyncio
from email_processor.email_client import get_access_token, fetch_unread_emails, forward_email, mark_email_as_read, force_mark_emails_as_read
#from apex_llm.apex import apex_categorise, apex_action_check
from config import EMAIL_ACCOUNTS, EMAIL_FETCH_INTERVAL, DEFAULT_EMAIL_ACCOUNT
#from apex_llm.apex_logging import create_log, add_to_log, log_apex_success, log_apex_fail, insert_log_to_db, check_email_processed
import datetime
#from apex_llm.apex_routing import ang_routings


processed_but_unread = set()

BATCH_SIZE =3  # Process 3 emails at a time - Cap for MS Graph

async def process_email(access_token, account, email_data, message_id):
    """
    Process a single email: categorize it, forward it, mark as read, and log it.
    Ensures single logging per email processed.
    """
    start_time = datetime.datetime.now()
    #log = create_log(email_data)
    processed = False

    # try:
        
        # if await check_email_processed(email_data['internet_message_id']):
        #     print(f"Email {email_data['internet_message_id']} has already been processed. Skipping.")
        #     # Mark the email as read if it was already found in the database
        #     await mark_email_as_read(access_token, account, message_id)
        #     return
        
        # Concatenate email data for APEX processing
    llm_text = " ".join([str(value) for key, value in email_data.items() if key != 'email_object'])
    print(email_data)
    
    await mark_email_as_read(access_token, account, message_id)
        
    try:
        FORWARD_TO = 'tevinri@tihsa.co.za'
        original_sender = email_data['from']
                
        # Forward email
    await forward_email(
            access_token, 
            account, 
            message_id, 
            original_sender, 
            FORWARD_TO, 
            email_data, 
            "AI Forwarded message"
        )
                
        #         if forward_success:
        #             # Mark as read only if forwarding was successful
        #             marked_as_read = await mark_email_as_read(access_token, account, message_id)
                    
        #             if marked_as_read:
        #                 # Only log if both forwarding and marking as read were successful
        #                 if not processed:  # Extra check to prevent duplicate logging
        #                     log_apex_success(apex_response, log)
        #                     add_to_log("apex_routed_to", FORWARD_TO, log)
        #                     add_to_log("sts_read_eml", "success", log)
        #                     add_to_log("sts_class", sts_class, log)
        #                     add_to_log("sts_routing", "success", log)
                            
        #                     end_time = datetime.datetime.now()
        #                     tat = (end_time - start_time).total_seconds()
        #                     add_to_log("tat", tat, log)
        #                     add_to_log("end_time", end_time, log)
                            
        #                     await insert_log_to_db(log)
        #                     processed = True
        #             else:
        #                 print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - Failed to mark email {message_id} as read. Adding to processed_but_unread set.")
        #                 processed_but_unread.add((account, message_id))
                
        #     except Exception as e:
        #         print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - Error in forwarding/marking as read: {str(e)}")
        #         if not processed:
        #             await handle_error_logging(log, FORWARD_TO, str(e), start_time)
        #             processed = True
                
        # else:
        #     # APEX classification failed
        #     if not processed:
        #         await handle_apex_failure_logging(
        #             log, 
        #             email_data, 
        #             apex_response, 
        #             access_token, 
        #             account, 
        #             message_id, 
        #             start_time
        #         )
        #         processed = True
                
    # except Exception as e:
    #     print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - General error: {str(e)}")
    #     if not processed:
    #         await handle_error_logging(log, email_data['to'], str(e), start_time)
    #         processed = True

# async def handle_error_logging(log, forward_to, error_message, start_time):
#     """Helper function to handle error logging consistently"""
#     log_apex_fail(log, error_message)
#     add_to_log("apex_routed_to", forward_to, log)
#     add_to_log("sts_read_eml", "error", log)
#     add_to_log("sts_class", "error", log)
#     add_to_log("sts_routing", "error", log)
    
#     end_time = datetime.datetime.now()
#     tat = (end_time - start_time).total_seconds()
#     add_to_log("tat", tat, log)
#     add_to_log("end_time", end_time, log)
    
#     await insert_log_to_db(log)

# async def handle_apex_failure_logging(log, email_data, apex_response, access_token, account, message_id, start_time):
#     """Helper function to handle APEX failure logging consistently"""
#     try:
#         # Try to forward to default address
#         forward_success = await forward_email(
#             access_token,
#             account,
#             message_id,
#             email_data['from'],
#             email_data['to'],
#             email_data,
#             "AI Forwarded message by default due to APEX LLM error"
#         )
        
#         if forward_success:
#             marked_as_read = await mark_email_as_read(access_token, account, message_id)
#             if marked_as_read:
#                 log_apex_fail(log, apex_response['message'])
#                 add_to_log("apex_routed_to", email_data['to'], log)
#                 add_to_log("sts_read_eml", "error", log)
#                 add_to_log("sts_class", "error", log)
#                 add_to_log("sts_routing", "success", log)
                
#                 end_time = datetime.datetime.now()
#                 tat = (end_time - start_time).total_seconds()
#                 add_to_log("tat", tat, log)
#                 add_to_log("end_time", end_time, log)
                
#                 await insert_log_to_db(log)
            
#     except Exception as e:
#         await handle_error_logging(log, email_data['to'], str(e), start_time)

async def process_batch():
    
    access_token = await get_access_token()
    
    for account in EMAIL_ACCOUNTS:
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Fetching unread emails for: {account}")
        try:
            all_unread_emails = await fetch_unread_emails(access_token, account)
            
        except Exception as e:
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_batch - Error fetching unread emails for {account}: {str(e)}")
            continue  # Skip to the next account if there's an error fetching emails

        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_batch - Processing {len(all_unread_emails)} unread emails in batch")
        for i in range(0, len(all_unread_emails), BATCH_SIZE):
            batch = all_unread_emails[i:i+BATCH_SIZE]
            tasks = [asyncio.create_task(process_email(access_token, account, email_data, message_id)) 
                     for email_data, message_id in batch]
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Add a small delay between batches to avoid overwhelming the API
            await asyncio.sleep(1)


async def main():
    while True:
        start_time = time.time()
        
        try:
            await process_batch()
        except Exception as e: 
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: main - There was an error processing the batch due to:  {e}")

        elapsed_time = time.time() - start_time
        if elapsed_time < EMAIL_FETCH_INTERVAL:
            await asyncio.sleep(EMAIL_FETCH_INTERVAL - elapsed_time)

def trigger_email_triage():
    if len(sys.argv) > 1 and sys.argv[1] == 'start':
        asyncio.run(main())
    else:
        print("To start the email processing, run with 'start' argument")
        print("Run Command: python main.py start")

if __name__ == '__main__':
    trigger_email_triage()
    
