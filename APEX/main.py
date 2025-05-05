import sys
import time
import asyncio
from email_processor.email_client import get_access_token, fetch_unread_emails, forward_email, mark_email_as_read, force_mark_emails_as_read
from apex_llm.apex import apex_categorise, apex_action_check
from config import EMAIL_ACCOUNTS, EMAIL_FETCH_INTERVAL, DEFAULT_EMAIL_ACCOUNT
from apex_llm.apex_logging import create_log, add_to_log, log_apex_success, log_apex_fail, insert_log_to_db, check_email_processed
import datetime
from apex_llm.apex_routing import ang_routings


# Set to track emails that have been processed but not marked as read yet
processed_but_unread = set()

# Number of emails to process in parallel
BATCH_SIZE = 3  # Process 3 emails at a time - Cap for MS Graph

async def process_email(access_token, account, email_data, message_id):
    """
    Process a single email: categorize it, forward it, mark as read, and log it.
    Ensures single logging per email processed and implements robust error handling
    to guarantee email delivery despite potential failures.
    
    Args:
        access_token: Valid Microsoft Graph API token
        account: Email account being processed
        email_data: Dictionary containing the email data
        message_id: Unique ID of the email message
        
    Returns:
        None
    """
    start_time = datetime.datetime.now()
    log = create_log(email_data)
    processed = False
    
    # Default sender and destination for fallback forwarding in case of errors
    original_sender = email_data.get('from', '')
    original_destination = email_data.get('to', '')
    
    try:
        # First check if this email has already been processed to avoid duplicates
        if await check_email_processed(email_data['internet_message_id']):
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - Email {email_data['internet_message_id']} has already been processed. Skipping.")
            # Mark the email as read if it was already found in the database
            try:
                await mark_email_as_read(access_token, account, message_id)
            except Exception as e:
                print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - Failed to mark already processed email as read: {str(e)}")
            return
        
        # Concatenate email data for APEX processing
        llm_text = " ".join([str(value) for key, value in email_data.items() if key != 'email_object'])
        
        # Get APEX classification - attempt to categorize the email
        try:
            apex_response = await apex_categorise(str(llm_text))
        except Exception as e:
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - Error in APEX categorization: {str(e)}")
            # If categorization fails, prepare for fallback routing
            apex_response = {'response': '500', 'message': str(e)}
        
        if apex_response['response'] == '200':
            # Successfully classified by APEX
            sts_class = "success"
            
            try:
                # Determine forwarding address based on classification
                if str(apex_response['message']['classification']).lower() in ang_routings.keys():
                    FORWARD_TO = ang_routings[str(apex_response['message']['classification']).lower()]
                else:
                    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - APEX classification '{apex_response['message']['classification']}' not found in routing table. Forwarding to the original recipient.")
                    FORWARD_TO = original_destination
                
                # Forward email to the determined address
                forward_success = await forward_email(
                    access_token, 
                    account, 
                    message_id, 
                    original_sender, 
                    FORWARD_TO, 
                    email_data, 
                    "AI Forwarded message"
                )
                
                if forward_success:
                    # Mark as read only if forwarding was successful
                    marked_as_read = await mark_email_as_read(access_token, account, message_id)
                    
                    if marked_as_read:
                        # Only log if both forwarding and marking as read were successful
                        if not processed:  # Extra check to prevent duplicate logging
                            log_apex_success(apex_response, log)
                            add_to_log("apex_routed_to", FORWARD_TO, log)
                            add_to_log("sts_read_eml", "success", log)
                            add_to_log("sts_class", sts_class, log)
                            add_to_log("sts_routing", "success", log)
                            
                            end_time = datetime.datetime.now()
                            tat = (end_time - start_time).total_seconds()
                            add_to_log("tat", tat, log)
                            add_to_log("end_time", end_time, log)
                            
                            await insert_log_to_db(log)
                            processed = True
                            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - Successfully processed email {message_id}, forwarded to {FORWARD_TO}")
                    else:
                        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - Failed to mark email {message_id} as read. Adding to processed_but_unread set.")
                        processed_but_unread.add((account, message_id))
                        
                        # Log even if we couldn't mark as read
                        if not processed:
                            log_apex_success(apex_response, log)
                            add_to_log("apex_routed_to", FORWARD_TO, log)
                            add_to_log("sts_read_eml", "error", log)
                            add_to_log("sts_class", sts_class, log)
                            add_to_log("sts_routing", "success", log)
                            
                            end_time = datetime.datetime.now()
                            tat = (end_time - start_time).total_seconds()
                            add_to_log("tat", tat, log)
                            add_to_log("end_time", end_time, log)
                            
                            await insert_log_to_db(log)
                            processed = True
                else:
                    # If forwarding to classified destination failed, try sending to original destination
                    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - Failed to forward to classified destination {FORWARD_TO}. Attempting to forward to original destination {original_destination}")
                    
                    fallback_success = await forward_email(
                        access_token,
                        account,
                        message_id,
                        original_sender,
                        original_destination,
                        email_data,
                        "AI Forwarded message (fallback routing)"
                    )
                    
                    if fallback_success:
                        marked_as_read = await mark_email_as_read(access_token, account, message_id)
                        
                        if not processed:
                            log_apex_success(apex_response, log)
                            add_to_log("apex_routed_to", original_destination + " (fallback routing)", log)
                            add_to_log("sts_read_eml", "success" if marked_as_read else "error", log)
                            add_to_log("sts_class", sts_class, log)
                            add_to_log("sts_routing", "error", log)
                            
                            end_time = datetime.datetime.now()
                            tat = (end_time - start_time).total_seconds()
                            add_to_log("tat", tat, log)
                            add_to_log("end_time", end_time, log)
                            
                            await insert_log_to_db(log)
                            processed = True
                            
                            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - Successfully forwarded email {message_id} to original destination {original_destination} after primary routing failed")
                    else:
                        # Both primary and fallback forwarding failed
                        if not processed:
                            await handle_error_logging(
                                log,
                                f"Failed to forward to both {FORWARD_TO} and fallback {original_destination}",
                                "Multiple forwarding failures",
                                start_time
                            )
                            processed = True
                
            except Exception as e:
                print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - Error in forwarding/marking as read: {str(e)}")
                
                # Attempt fallback forwarding to original destination
                try:
                    fallback_success = await forward_email(
                        access_token,
                        account,
                        message_id,
                        original_sender,
                        original_destination,
                        email_data,
                        f"AI Forwarded message (error recovery: {str(e)[:50]}...)"
                    )
                    
                    if fallback_success:
                        marked_as_read = await mark_email_as_read(access_token, account, message_id)
                        
                        if not processed:
                            log_apex_success(apex_response, log) if apex_response['response'] == '200' else log_apex_fail(log, str(e))
                            add_to_log("apex_routed_to", original_destination + " (error recovery)", log)
                            add_to_log("sts_read_eml", "success" if marked_as_read else "error", log)
                            add_to_log("sts_class", sts_class if apex_response['response'] == '200' else "error", log)
                            add_to_log("sts_routing", "error", log)
                            
                            end_time = datetime.datetime.now()
                            tat = (end_time - start_time).total_seconds()
                            add_to_log("tat", tat, log)
                            add_to_log("end_time", end_time, log)
                            
                            await insert_log_to_db(log)
                            processed = True
                            
                            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - Successfully recovered from error by forwarding to {original_destination}")
                    else:
                        if not processed:
                            await handle_error_logging(log, original_destination, f"Failed in both primary processing and fallback forwarding: {str(e)}", start_time)
                            processed = True
                except Exception as fallback_err:
                    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - Error in fallback forwarding: {str(fallback_err)}")
                    if not processed:
                        await handle_error_logging(log, original_destination, f"Complete failure - Primary error: {str(e)}, Fallback error: {str(fallback_err)}", start_time)
                        processed = True
                
        else:
            # APEX classification failed - implement fallback routing
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - APEX classification failed: {apex_response['message']}. Implementing fallback routing.")
            if not processed:
                await handle_apex_failure_logging(
                    log, 
                    email_data, 
                    apex_response, 
                    access_token, 
                    account, 
                    message_id, 
                    start_time
                )
                processed = True
                
    except Exception as e:
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - General error: {str(e)}")
        
        # Final attempt at fallback routing if nothing else worked
        try:
            # Only attempt if we haven't processed yet
            if not processed:
                fallback_success = await forward_email(
                    access_token,
                    account,
                    message_id,
                    original_sender,
                    original_destination,
                    email_data,
                    f"AI Forwarded message (critical error recovery)"
                )
                
                if fallback_success:
                    try:
                        marked_as_read = await mark_email_as_read(access_token, account, message_id)
                    except Exception as mark_err:
                        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - Failed to mark as read in critical error recovery: {str(mark_err)}")
                        marked_as_read = False
                    
                    await handle_error_logging(log, original_destination + " (critical recovery)", f"Critical error recovery successful: {str(e)}", start_time)
                    processed = True
                    
                    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - Critical error recovery successful for email {message_id}")
                else:
                    await handle_error_logging(log, "DELIVERY FAILED", f"CRITICAL: All delivery attempts failed. Original error: {str(e)}", start_time)
                    processed = True
                    
                    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - CRITICAL: All delivery attempts failed for email {message_id}")
        except Exception as final_err:
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - Final error recovery attempt failed: {str(final_err)}")
            if not processed:
                try:
                    await handle_error_logging(log, "DELIVERY FAILED", f"CRITICAL: Email could not be processed or forwarded. Original error: {str(e)}, Final error: {str(final_err)}", start_time)
                    processed = True
                except Exception as log_err:
                    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - Even logging failed: {str(log_err)}")

async def handle_error_logging(log, forward_to, error_message, start_time):
    """
    Helper function to handle error logging consistently
    
    Args:
        log: The log object to update
        forward_to: The address the email was forwarded to (or attempted to)
        error_message: The error message to log
        start_time: When the processing started, for calculating TAT
        
    Returns:
        None
    """
    try:
        log_apex_fail(log, error_message)
        add_to_log("apex_routed_to", forward_to, log)
        add_to_log("sts_read_eml", "error", log)
        add_to_log("sts_class", "error", log)
        add_to_log("sts_routing", "error", log)
        
        end_time = datetime.datetime.now()
        tat = (end_time - start_time).total_seconds()
        add_to_log("tat", tat, log)
        add_to_log("end_time", end_time, log)
        
        await insert_log_to_db(log)
    except Exception as e:
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: handle_error_logging - Failed to log error: {str(e)}")

async def handle_apex_failure_logging(log, email_data, apex_response, access_token, account, message_id, start_time):
    """
    Helper function to handle APEX failure logging consistently with fallback routing
    
    Args:
        log: The log object to update
        email_data: Dictionary containing email data
        apex_response: The failed response from APEX classification
        access_token: Valid Microsoft Graph API token
        account: Email account being processed
        message_id: Unique ID of the email message
        start_time: When processing started, for calculating TAT
        
    Returns:
        None
    """
    original_sender = email_data.get('from', '')
    original_destination = email_data.get('to', '')
    
    try:
        # Always try to forward to original destination when APEX fails
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: handle_apex_failure_logging - Attempting to forward to original destination {original_destination} due to APEX failure")
        
        forward_success = await forward_email(
            access_token,
            account,
            message_id,
            original_sender,
            original_destination,
            email_data,
            "AI Forwarded message by default due to APEX LLM error"
        )
        
        if forward_success:
            # Try to mark the email as read
            try:
                marked_as_read = await mark_email_as_read(access_token, account, message_id)
            except Exception as mark_err:
                print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: handle_apex_failure_logging - Failed to mark as read: {str(mark_err)}")
                marked_as_read = False
                
            # Log the outcome
            log_apex_fail(log, apex_response['message'])
            add_to_log("apex_routed_to", original_destination, log)
            add_to_log("sts_read_eml", "success" if marked_as_read else "error", log)
            add_to_log("sts_class", "error", log)
            add_to_log("sts_routing", "success", log)
            
            end_time = datetime.datetime.now()
            tat = (end_time - start_time).total_seconds()
            add_to_log("tat", tat, log)
            add_to_log("end_time", end_time, log)
            
            await insert_log_to_db(log)
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: handle_apex_failure_logging - Successfully forwarded to original destination despite APEX failure")
        else:
            # If even the fallback forwarding failed, log the error
            await handle_error_logging(log, original_destination, f"Failed to forward to original destination after APEX failure: {apex_response['message']}", start_time)
            
    except Exception as e:
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: handle_apex_failure_logging - Error in handling APEX failure: {str(e)}")
        await handle_error_logging(log, "DELIVERY FAILED", f"Failed to recover from APEX failure: {str(e)}", start_time)

async def process_batch():
    """
    Process a batch of unread emails from all configured accounts.
    Fetches unread emails and processes them in small batches to avoid
    overwhelming the API.
    
    Returns:
        None
    """
    try:
        # Get fresh access token for Microsoft Graph API
        access_token = await get_access_token()
        if not access_token:
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_batch - Failed to obtain access token. Skipping batch.")
            return
        
        # Process each configured email account
        for account in EMAIL_ACCOUNTS:
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_batch - Fetching unread emails for: {account}")
            try:
                all_unread_emails = await fetch_unread_emails(access_token, account)
                
            except Exception as e:
                print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_batch - Error fetching unread emails for {account}: {str(e)}")
                continue  # Skip to the next account if there's an error fetching emails

            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_batch - Processing {len(all_unread_emails)} unread emails in batch")
            
            # Process emails in small batches to avoid API rate limits
            for i in range(0, len(all_unread_emails), BATCH_SIZE):
                batch = all_unread_emails[i:i+BATCH_SIZE]
                tasks = [asyncio.create_task(process_email(access_token, account, email_data, message_id)) 
                         for email_data, message_id in batch]
                
                # gather with return_exceptions=True ensures the loop continues even if some tasks fail
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Check for exceptions in the results
                for idx, result in enumerate(results):
                    if isinstance(result, Exception):
                        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_batch - Task for email {idx+i} raised exception: {str(result)}")
                
                # Add a small delay between batches to avoid overwhelming the API
                await asyncio.sleep(1)
                
    except Exception as e:
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_batch - Unexpected error in batch processing: {str(e)}")

async def retry_unread_emails():
    """
    Periodically attempt to mark emails as read that were processed
    but couldn't be marked as read previously.
    
    Returns:
        None
    """
    if not processed_but_unread:
        return
    
    try:
        # Get fresh access token
        access_token = await get_access_token()
        if not access_token:
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: retry_unread_emails - Failed to obtain access token for retry operation.")
            return
        
        # Create a copy of the set to avoid modification during iteration
        retry_set = processed_but_unread.copy()
        
        for account, message_id in retry_set:
            try:
                success = await mark_email_as_read(access_token, account, message_id)
                if success:
                    processed_but_unread.remove((account, message_id))
                    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: retry_unread_emails - Successfully marked message {message_id} as read on retry.")
            except Exception as e:
                print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: retry_unread_emails - Failed to mark message {message_id} as read on retry: {str(e)}")
    
    except Exception as e:
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: retry_unread_emails - Error in retry operation: {str(e)}")

async def main():
    """
    Main application loop that continuously processes email batches
    at the configured interval.
    
    Returns:
        None
    """
    # How often to retry marking emails as read (in main loop cycles)
    retry_interval = 5
    loop_count = 0

    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - APEX Email Processing Service starting...")

    while True:
        start_time = time.time()
        
        try:
            # Process a batch of emails
            await process_batch()
            
            # Periodically retry marking emails as read
            loop_count += 1
            if loop_count >= retry_interval:
                await retry_unread_emails()
                loop_count = 0
                
        except Exception as e: 
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: main - There was an error processing the batch: {str(e)}")
            # Continue the loop despite errors to maintain service continuity

        # Calculate remaining time in the interval and sleep accordingly
        elapsed_time = time.time() - start_time
        if elapsed_time < EMAIL_FETCH_INTERVAL:
            sleep_time = EMAIL_FETCH_INTERVAL - elapsed_time
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: main - Batch processing completed in {elapsed_time:.2f} seconds. Sleeping for {sleep_time:.2f} seconds.")
            await asyncio.sleep(sleep_time)
        else:
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: main - Batch processing took {elapsed_time:.2f} seconds, which is longer than the interval ({EMAIL_FETCH_INTERVAL} seconds). Processing next batch immediately.")

def trigger_email_triage():
    """
    Entry point for the application. Runs the main async loop
    if the 'start' argument is provided.
    
    Returns:
        None
    """
    if len(sys.argv) > 1 and sys.argv[1] == 'start':
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: trigger_email_triage - Starting APEX email processing service...")
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: trigger_email_triage - Service stopped by user.")
        except Exception as e:
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: trigger_email_triage - Fatal error: {str(e)}")
            # In a production environment, you might want to restart the service here
    else:
        print("To start the email processing, run with 'start' argument")
        print("Run Command: python main.py start")

if __name__ == '__main__':
    trigger_email_triage()
