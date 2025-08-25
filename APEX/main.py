import sys
import time
import asyncio
import re  # Added import for regex patterns
from email_processor.email_client import get_access_token, fetch_unread_emails, forward_email, mark_email_as_read, force_mark_emails_as_read
from apex_llm.apex import apex_categorise, apex_action_check
from config import EMAIL_ACCOUNTS, EMAIL_FETCH_INTERVAL, POLICY_SERVICES
from apex_llm.apex_logging import (
    create_log, add_to_log, log_apex_success, log_apex_fail, 
    insert_log_to_db, check_email_processed, log_apex_intervention,
    email_log_capture, email_log, insert_system_log_to_db,
    log_skipped_email  # Added import for skipped email logging
)
import datetime
from apex_llm.apex_routing import ang_routings
from apex_llm.autoresponse import send_autoresponse 


# Set to track emails that have been processed but not marked as read yet
processed_but_unread = set()

# Number of emails to process in parallel
BATCH_SIZE = 3  # Process 3 emails at a time - Cap for MS Graph

async def process_email(access_token, account, email_data, message_id):
    """
    Process a single email: categorize it, forward it, mark as read, and log it.
    Ensures single logging per email processed and implements robust error handling
    to guarantee email delivery despite potential failures.
    Enhanced with comprehensive autoresponse logging and Exchange pattern detection.
    
    Args:
        access_token: Valid Microsoft Graph API token
        account: Email account being processed
        email_data: Dictionary containing the email data
        message_id: Unique ID of the email message
        
    Returns:
        None
    """
    start_time = datetime.datetime.now()
    
    # Default sender and destination for fallback forwarding in case of errors
    original_sender = email_data.get('from', '')
    original_destination = email_data.get('to', '')
    subject = email_data.get('subject', 'No Subject')
    email_id = email_data.get('email_id', '')
    internet_message_id = email_data.get('internet_message_id', '')
      
    # Enhanced: Use system log capture context for this email
    with email_log_capture.capture_for_email(email_id, internet_message_id, subject):
        log = create_log(email_data)
        processed = False
        system_log_inserted = False  # Track if system log has been inserted
        autoresponse_attempted = False
        autoresponse_successful = False
        autoresponse_skip_reason = ''
        autoresponse_error = ''
        
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        email_log(f">> {timestamp} Processing email [Subject: {subject}] from {original_sender}")
        
        try:
            # First check if this email has already been processed to avoid duplicates
            email_log(f">> {timestamp} Checking if email already processed [Subject: {subject}]")
            if await check_email_processed(email_data['internet_message_id']):
                email_log(f">> {timestamp} Email already processed [Subject: {subject}]. Marking as read and logging as skipped.")
                
                # Calculate processing time before skipping
                processing_time = (datetime.datetime.now() - start_time).total_seconds()
                
                # Log the skipped email with detailed reason
                skip_reason = f"Email already processed - found in database with internet_message_id: {email_data['internet_message_id']}"
                try:
                    await log_skipped_email(
                        email_data=email_data,
                        reason_skipped=skip_reason,
                        account_processed=account,
                        skip_type="DUPLICATE",
                        processing_time=processing_time
                    )
                    email_log(f">> {timestamp} Successfully logged skipped email to skipped_mails table [Subject: {subject}]")
                except Exception as log_err:
                    email_log(f">> {timestamp} Failed to log skipped email: {str(log_err)} [Subject: {subject}]")
                
                # Mark the email as read if it was already found in the database
                try:
                    email_log(f">> {timestamp} Attempting to mark already processed email as read [Subject: {subject}]")
                    await mark_email_as_read(access_token, account, message_id)
                    email_log(f">> {timestamp} Successfully marked already processed email as read [Subject: {subject}]")
                except Exception as e:
                    email_log(f">> {timestamp} Failed to mark already processed email as read: {str(e)}")
                
                # Enhanced: Log autoresponse details for already processed emails
                email_log_capture.log_autoresponse_attempt(
                    email_id,
                    attempted=False,
                    successful=False,
                    skip_reason="Email already processed",
                    recipient=original_sender
                )
                
                # Insert system logs for skipped emails too
                try:
                    await insert_system_log_to_db(email_id)
                    system_log_inserted = True
                    email_log(f">> {timestamp} System log inserted for already processed email [Subject: {subject}]")
                except Exception as e:
                    email_log(f">> {timestamp} Failed to insert system log for already processed email: {str(e)}")
                
                return
            
            email_log(f">> {timestamp} Email not found in database, proceeding with additional checks [Subject: {subject}]")
            
            # NEW: Check for Microsoft Exchange system patterns (autoresponse.py checks 5 & 6)
            email_log(f">> {timestamp} Checking for Microsoft Exchange system patterns [Subject: {subject}]")
            sender_clean = original_sender.lower().strip() if original_sender else ""
            
            # Check 5: MICROSOFT EXCHANGE SYSTEM DETECTION - Primary defense against bounce loops
            exchange_patterns = [
                r'microsoftexchange[a-f0-9]+@',  # Standard Exchange pattern
                r'exchange[a-f0-9]+@',          # Alternative Exchange pattern
                r'[a-f0-9]{32}@'                # Generic 32-character hex @ domain
            ]
            
            exchange_pattern_detected = False
            detected_pattern = ""
            
            for pattern in exchange_patterns:
                if re.search(pattern, sender_clean):
                    exchange_pattern_detected = True
                    detected_pattern = pattern
                    break
            
            # Check 6: Domain-specific substring detection for telesure.co.za
            telesure_exchange_detected = "microsoftexchange" in sender_clean and "telesure.co.za" in sender_clean
            
            # If either Exchange pattern is detected, skip the email
            if exchange_pattern_detected or telesure_exchange_detected:
                # Calculate processing time before skipping
                processing_time = (datetime.datetime.now() - start_time).total_seconds()
                
                # Determine the specific reason
                if exchange_pattern_detected:
                    skip_reason = f"Microsoft Exchange system sender detected: {original_sender} (matches pattern '{detected_pattern}')"
                    skip_type = "EXCHANGE_SYSTEM"
                    email_log(f">> {timestamp} Exchange pattern detected [Subject: {subject}]: {skip_reason}")
                else:
                    skip_reason = f"Sender is Microsoft Exchange system at telesure.co.za: {original_sender}"
                    skip_type = "TELESURE_EXCHANGE"
                    email_log(f">> {timestamp} Telesure Exchange system detected [Subject: {subject}]: {skip_reason}")
                
                # Log the skipped email
                try:
                    await log_skipped_email(
                        email_data=email_data,
                        reason_skipped=skip_reason,
                        account_processed=account,
                        skip_type=skip_type,
                        processing_time=processing_time
                    )
                    email_log(f">> {timestamp} Successfully logged Exchange system skipped email to skipped_mails table [Subject: {subject}]")
                except Exception as log_err:
                    email_log(f">> {timestamp} Failed to log Exchange system skipped email: {str(log_err)} [Subject: {subject}]")
                
                # Mark the email as read
                try:
                    email_log(f">> {timestamp} Attempting to mark Exchange system email as read [Subject: {subject}]")
                    await mark_email_as_read(access_token, account, message_id)
                    email_log(f">> {timestamp} Successfully marked Exchange system email as read [Subject: {subject}]")
                except Exception as e:
                    email_log(f">> {timestamp} Failed to mark Exchange system email as read: {str(e)} [Subject: {subject}]")
                
                # Log autoresponse details for Exchange system emails
                email_log_capture.log_autoresponse_attempt(
                    email_id,
                    attempted=False,
                    successful=False,
                    skip_reason=f"Exchange system sender detected - {skip_type}",
                    recipient=original_sender
                )
                
                # Insert system logs for Exchange system skipped emails
                try:
                    await insert_system_log_to_db(email_id)
                    system_log_inserted = True
                    email_log(f">> {timestamp} System log inserted for Exchange system skipped email [Subject: {subject}]")
                except Exception as e:
                    email_log(f">> {timestamp} Failed to insert system log for Exchange system skipped email: {str(e)} [Subject: {subject}]")
                
                return
            
            email_log(f">> {timestamp} No Exchange system patterns detected, proceeding with normal processing [Subject: {subject}]")
            
            # Start autoresponse process concurrently with detailed logging
            # This will run in the background while the rest of the processing continues
            email_log(f">> {timestamp} Starting autoresponse task concurrently [Subject: {subject}]")
            autoresponse_attempted = True
            
            # Create autoresponse task and track it
            async def tracked_autoresponse():
                """Wrapper for autoresponse with enhanced tracking"""
                nonlocal autoresponse_successful, autoresponse_skip_reason, autoresponse_error
                try:
                    email_log(f">> {timestamp} AUTORESPONSE: Starting autoresponse analysis for {original_sender}")
                    result = await send_autoresponse(
                        account,
                        original_sender,
                        subject,
                        email_data
                    )
                    
                    if result:
                        autoresponse_successful = True
                        email_log(f">> {timestamp} AUTORESPONSE: Successfully sent autoresponse to {original_sender}")
                        # Log successful autoresponse details
                        email_log_capture.log_autoresponse_attempt(
                            email_id,
                            attempted=True,
                            successful=True,
                            recipient=original_sender,
                            subject_line="Auto-generated response"  # Will be updated by autoresponse module if needed
                        )
                    else:
                        autoresponse_successful = False
                        autoresponse_skip_reason = "Autoresponse was skipped or failed"
                        email_log(f">> {timestamp} AUTORESPONSE: Autoresponse was not sent to {original_sender} (skipped or failed)")
                        # Log skipped/failed autoresponse
                        email_log_capture.log_autoresponse_attempt(
                            email_id,
                            attempted=True,
                            successful=False,
                            skip_reason=autoresponse_skip_reason,
                            recipient=original_sender
                        )
                    
                    return result
                    
                except Exception as e:
                    autoresponse_successful = False
                    autoresponse_error = str(e)
                    email_log(f">> {timestamp} AUTORESPONSE: Error in autoresponse process: {str(e)}")
                    # Log autoresponse error
                    email_log_capture.log_autoresponse_attempt(
                        email_id,
                        attempted=True,
                        successful=False,
                        error_message=autoresponse_error,
                        recipient=original_sender
                    )
                    return False
            
            autoresponse_task = asyncio.create_task(tracked_autoresponse())
            
            # Concatenate email data for APEX processing
            email_log(f">> {timestamp} Preparing email data for APEX classification [Subject: {subject}]")
            llm_text = " ".join([str(value) for key, value in email_data.items() if key != 'email_object'])
            
            # 10/07/2025 - BUGFIX 481012
            # CHANGE 1
            # TRUNCATE THE LLM TEXT TO FIT WITHIN LLM CONTEXT WINDOW
            if len(llm_text) >= 300000:
                llm_text = llm_text[:300000]  # Truncate to 300,000 characters to prevent context window limitations. Main message should be concluded in the first 300K characters ~100K tokens of the mail.
            else:
                llm_text = llm_text

            # END OF CHANGE 1 - BUGFIX 481012


            # Get APEX classification - attempt to categorize the email
            email_log(f">> {timestamp} Starting APEX classification [Subject: {subject}]")
            try:
                apex_response = await apex_categorise(str(llm_text), subject)
                email_log(f">> {timestamp} APEX classification completed [Subject: {subject}]")
            except Exception as e:
                email_log(f">> {timestamp} Error in APEX categorization [Subject: {subject}]: {str(e)}")
                # If categorization fails, prepare for fallback routing
                apex_response = {'response': '500', 'message': str(e)}
            
            if apex_response['response'] == '200':
                # Successfully classified by APEX
                email_log(f">> {timestamp} APEX classification successful [Subject: {subject}]")
                email_log(f">> {timestamp} Classification result: {apex_response['message']['classification']} [Subject: {subject}]")
                email_log(f">> {timestamp} Action required: {apex_response['message']['action_required']} [Subject: {subject}]")
                email_log(f">> {timestamp} Sentiment: {apex_response['message']['sentiment']} [Subject: {subject}]")
                sts_class = "success"
                
                try:
                    # Determine forwarding address based on classification
                    email_log(f">> {timestamp} Determining forwarding address for classification: {apex_response['message']['classification']} [Subject: {subject}]")
                    if str(apex_response['message']['classification']).lower() in ang_routings.keys():
                        FORWARD_TO = ang_routings[str(apex_response['message']['classification']).lower()]
                        email_log(f">> {timestamp} Found routing for classification '{apex_response['message']['classification']}' -> {FORWARD_TO} [Subject: {subject}]")
                    else:
                        email_log(f">> {timestamp} APEX classification '{apex_response['message']['classification']}' not found in routing table [Subject: {subject}]. Forwarding to original recipient.")
                        
                        # 10/07/2025 - BUGFIX 481012
                        # CHANGE 2
                        # OVERRIDE ORIGINAL DESTINATION TO POLICYSERVICE IF ORIGINAL DESTINATION IS SAME AS APEX CONSOLIDATION BIN
                        if original_destination.lower() == EMAIL_ACCOUNTS[0].lower():
                            FORWARD_TO = POLICY_SERVICES
                        else: 
                            FORWARD_TO = original_destination
                        # END OF CHANGE - BUGFIX 481012
                    
                    # Log whether AI intervention occurred (changed the destination)
                    log_apex_intervention(log, original_destination, FORWARD_TO)
                    if original_destination.lower() != FORWARD_TO.lower():
                        email_log(f">> {timestamp} AI intervention: Routing changed from {original_destination} to {FORWARD_TO} [Subject: {subject}]")
                    else:
                        email_log(f">> {timestamp} No AI intervention: Email stays with original destination {original_destination} [Subject: {subject}]")
                    
                    email_log(f">> {timestamp} Forwarding to {FORWARD_TO} based on classification '{apex_response['message']['classification']}' [Subject: {subject}]")
                    
                    # Forward email to the determined address
                    email_log(f">> {timestamp} Starting email forwarding process [Subject: {subject}]")
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
                        email_log(f">> {timestamp} Email forwarding successful to {FORWARD_TO} [Subject: {subject}]")
                        # Mark as read only if forwarding was successful
                        email_log(f">> {timestamp} Attempting to mark email as read [Subject: {subject}]")
                        marked_as_read = await mark_email_as_read(access_token, account, message_id)
                        
                        if marked_as_read:
                            email_log(f">> {timestamp} Email marked as read successfully [Subject: {subject}]")
                            # Only log if both forwarding and marking as read were successful
                            if not processed:  # Extra check to prevent duplicate logging
                                email_log(f">> {timestamp} Starting database logging process [Subject: {subject}]")
                                log_apex_success(apex_response, log)
                                add_to_log("apex_routed_to", FORWARD_TO, log)
                                add_to_log("sts_read_eml", "success", log)
                                add_to_log("sts_class", sts_class, log)
                                add_to_log("sts_routing", "success", log)
                                
                                end_time = datetime.datetime.now()
                                tat = (end_time - start_time).total_seconds()
                                add_to_log("tat", tat, log)
                                add_to_log("end_time", end_time, log)
                                email_log(f">> {timestamp} Processing time: {tat:.2f} seconds [Subject: {subject}]")
                                
                                # Enhanced: Capture autoresponse result with timeout handling
                                email_log(f">> {timestamp} Checking autoresponse task status [Subject: {subject}]")
                                try:
                                    # Wait for autoresponse task with a timeout (e.g., 10 seconds)
                                    autoresponse_success = await asyncio.wait_for(autoresponse_task, timeout=10.0)
                                    add_to_log("auto_response_sent", "success" if autoresponse_success else "failed", log)
                                    email_log(f">> {timestamp} Autoresponse task completed: {'success' if autoresponse_success else 'failed'} [Subject: {subject}]")
                                except asyncio.TimeoutError:
                                    # If autoresponse is taking too long, assume it's still running in background
                                    # and mark as "pending" in the log
                                    email_log(f">> {timestamp} Autoresponse task taking longer than expected [Subject: {subject}]")
                                    add_to_log("auto_response_sent", "pending", log)
                                except Exception as e:
                                    # If autoresponse task raised an exception
                                    email_log(f">> {timestamp} Error in autoresponse task [Subject: {subject}]: {str(e)}")
                                    add_to_log("auto_response_sent", "failed", log)
                                
                                email_log(f">> {timestamp} Inserting main log record to database [Subject: {subject}]")
                                await insert_log_to_db(log)
                                
                                # Enhanced: Insert system logs to database with autoresponse details
                                try:
                                    email_log(f">> {timestamp} Inserting enhanced system log record to database [Subject: {subject}]")
                                    await insert_system_log_to_db(email_id)
                                    system_log_inserted = True
                                    email_log(f">> {timestamp} Enhanced system log inserted successfully [Subject: {subject}]")
                                except Exception as e:
                                    email_log(f">> {timestamp} Failed to insert enhanced system log: {str(e)}")
                                
                                processed = True
                                email_log(f">> {timestamp} Successfully processed and marked as read [Subject: {subject}]")
                        else:
                            email_log(f">> {timestamp} Failed to mark email as read [Subject: {subject}]. Adding to retry queue.")
                            processed_but_unread.add((account, message_id))
                            
                            # Log even if we couldn't mark as read
                            if not processed:
                                email_log(f">> {timestamp} Logging to database despite read failure [Subject: {subject}]")
                                log_apex_success(apex_response, log)
                                add_to_log("apex_routed_to", FORWARD_TO, log)
                                add_to_log("sts_read_eml", "error", log)
                                add_to_log("sts_class", sts_class, log)
                                add_to_log("sts_routing", "success", log)
                                
                                end_time = datetime.datetime.now()
                                tat = (end_time - start_time).total_seconds()
                                add_to_log("tat", tat, log)
                                add_to_log("end_time", end_time, log)
                                email_log(f">> {timestamp} Processing time: {tat:.2f} seconds [Subject: {subject}]")
                                
                                # Enhanced: Capture autoresponse result with timeout handling
                                email_log(f">> {timestamp} Checking autoresponse task status [Subject: {subject}]")
                                try:
                                    # Wait for autoresponse task with a timeout (e.g., 10 seconds)
                                    autoresponse_success = await asyncio.wait_for(autoresponse_task, timeout=10.0)
                                    add_to_log("auto_response_sent", "success" if autoresponse_success else "failed", log)
                                    email_log(f">> {timestamp} Autoresponse task completed: {'success' if autoresponse_success else 'failed'} [Subject: {subject}]")
                                except asyncio.TimeoutError:
                                    # If autoresponse is taking too long, assume it's still running in background
                                    # and mark as "pending" in the log
                                    email_log(f">> {timestamp} Autoresponse task taking longer than expected [Subject: {subject}]")
                                    add_to_log("auto_response_sent", "pending", log)
                                except Exception as e:
                                    # If autoresponse task raised an exception
                                    email_log(f">> {timestamp} Error in autoresponse task [Subject: {subject}]: {str(e)}")
                                    add_to_log("auto_response_sent", "failed", log)
                                
                                email_log(f">> {timestamp} Inserting main log record to database [Subject: {subject}]")
                                await insert_log_to_db(log)
                                
                                # Enhanced: Insert system logs to database with autoresponse details
                                try:
                                    email_log(f">> {timestamp} Inserting enhanced system log record to database [Subject: {subject}]")
                                    await insert_system_log_to_db(email_id)
                                    system_log_inserted = True
                                    email_log(f">> {timestamp} Enhanced system log inserted successfully [Subject: {subject}]")
                                except Exception as e:
                                    email_log(f">> {timestamp} Failed to insert enhanced system log: {str(e)}")
                                
                                processed = True
                    else:
                        # If forwarding to classified destination failed, try sending to original destination
                        email_log(f">> {timestamp} Failed to forward to classified destination {FORWARD_TO} [Subject: {subject}]. Attempting fallback routing.")
                        
                        # Reset intervention flag for fallback routing
                        add_to_log("apex_intervention", "false", log)
                        email_log(f">> {timestamp} Starting fallback forwarding to original destination: {original_destination} [Subject: {subject}]")
                        
                        # 10/07/2025 - BUGFIX 481012
                        # CHANGE 2
                        # OVERRIDE ORIGINAL DESTINATION TO POLICYSERVICE IF ORIGINAL DESTINATION IS SAME AS APEX CONSOLIDATION BIN
                        if original_destination.lower() == EMAIL_ACCOUNTS[0].lower():
                            FORWARD_TO = POLICY_SERVICES
                        else: 
                            FORWARD_TO = original_destination
                        # END OF CHANGE - BUGFIX 481012
                        
                        fallback_success = await forward_email(
                            access_token,
                            account,
                            message_id,
                            original_sender,
                            FORWARD_TO,
                            email_data,
                            "AI Forwarded message (fallback routing)"
                        )
                        
                        if fallback_success:
                            email_log(f">> {timestamp} Fallback forwarding successful [Subject: {subject}]")
                            email_log(f">> {timestamp} Attempting to mark email as read after fallback [Subject: {subject}]")
                            marked_as_read = await mark_email_as_read(access_token, account, message_id)
                            
                            if not processed:
                                email_log(f">> {timestamp} Logging fallback routing success to database [Subject: {subject}]")
                                log_apex_success(apex_response, log)
                                add_to_log("apex_routed_to", FORWARD_TO + " (fallback routing)", log)
                                add_to_log("sts_read_eml", "success" if marked_as_read else "error", log)
                                add_to_log("sts_class", sts_class, log)
                                add_to_log("sts_routing", "error", log)
                                
                                end_time = datetime.datetime.now()
                                tat = (end_time - start_time).total_seconds()
                                add_to_log("tat", tat, log)
                                add_to_log("end_time", end_time, log)
                                email_log(f">> {timestamp} Processing time: {tat:.2f} seconds [Subject: {subject}]")
                                
                                # Enhanced: Capture autoresponse result with timeout handling
                                email_log(f">> {timestamp} Checking autoresponse task status [Subject: {subject}]")
                                try:
                                    # Wait for autoresponse task with a timeout (e.g., 10 seconds)
                                    autoresponse_success = await asyncio.wait_for(autoresponse_task, timeout=10.0)
                                    add_to_log("auto_response_sent", "success" if autoresponse_success else "failed", log)
                                    email_log(f">> {timestamp} Autoresponse task completed: {'success' if autoresponse_success else 'failed'} [Subject: {subject}]")
                                except asyncio.TimeoutError:
                                    # If autoresponse is taking too long, assume it's still running in background
                                    # and mark as "pending" in the log
                                    email_log(f">> {timestamp} Autoresponse task taking longer than expected [Subject: {subject}]")
                                    add_to_log("auto_response_sent", "pending", log)
                                except Exception as e:
                                    # If autoresponse task raised an exception
                                    email_log(f">> {timestamp} Error in autoresponse task [Subject: {subject}]: {str(e)}")
                                    add_to_log("auto_response_sent", "failed", log)
                                
                                email_log(f">> {timestamp} Inserting main log record to database [Subject: {subject}]")
                                await insert_log_to_db(log)
                                
                                # Enhanced: Insert system logs to database with autoresponse details
                                try:
                                    email_log(f">> {timestamp} Inserting enhanced system log record to database [Subject: {subject}]")
                                    await insert_system_log_to_db(email_id)
                                    system_log_inserted = True
                                    email_log(f">> {timestamp} Enhanced system log inserted successfully [Subject: {subject}]")
                                except Exception as e:
                                    email_log(f">> {timestamp} Failed to insert enhanced system log: {str(e)}")
                                
                                processed = True
                                
                                email_log(f">> {timestamp} Fallback routing successful [Subject: {subject}]")
                        else:
                            # Both primary and fallback forwarding failed
                            if not processed:
                                system_log_inserted = await handle_error_logging(
                                    log,
                                    f"Failed to forward to both {FORWARD_TO} and fallback {original_destination}",
                                    "Multiple forwarding failures",
                                    start_time,
                                    subject,
                                    autoresponse_task,
                                    email_id  # Pass email_id for system logging
                                )
                                processed = True
                    
                except Exception as e:
                    email_log(f">> {timestamp} Error in forwarding/marking as read [Subject: {subject}]: {str(e)}")
                    
                    # Attempt fallback forwarding to original destination
                    try:
                        email_log(f">> {timestamp} Starting error recovery process [Subject: {subject}]")
                        # No intervention in fallback case
                        add_to_log("apex_intervention", "false", log)
                        
                        # 10/07/2025 - BUGFIX 481012
                        # CHANGE 2
                        # OVERRIDE ORIGINAL DESTINATION TO POLICYSERVICE IF ORIGINAL DESTINATION IS SAME AS APEX CONSOLIDATION BIN
                        if original_destination.lower() == EMAIL_ACCOUNTS[0].lower():
                            FORWARD_TO = POLICY_SERVICES
                        else: 
                            FORWARD_TO = original_destination
                        # END OF CHANGE - BUGFIX 481012
                        
                        
                        email_log(f">> {timestamp} Attempting fallback forwarding for error recovery [Subject: {subject}]")
                        fallback_success = await forward_email(
                            access_token,
                            account,
                            message_id,
                            original_sender,
                            FORWARD_TO,
                            email_data,
                            f"AI Forwarded message (error recovery: {str(e)[:50]}...)"
                        )
                        
                        if fallback_success:
                            email_log(f">> {timestamp} Error recovery forwarding successful [Subject: {subject}]")
                            email_log(f">> {timestamp} Attempting to mark email as read after error recovery [Subject: {subject}]")
                            marked_as_read = await mark_email_as_read(access_token, account, message_id)
                            
                            if not processed:
                                email_log(f">> {timestamp} Logging error recovery to database [Subject: {subject}]")
                                log_apex_success(apex_response, log) if apex_response['response'] == '200' else log_apex_fail(log, str(e))
                                add_to_log("apex_routed_to", FORWARD_TO + " (error recovery)", log)
                                add_to_log("sts_read_eml", "success" if marked_as_read else "error", log)
                                add_to_log("sts_class", sts_class if apex_response['response'] == '200' else "error", log)
                                add_to_log("sts_routing", "error", log)
                                
                                end_time = datetime.datetime.now()
                                tat = (end_time - start_time).total_seconds()
                                add_to_log("tat", tat, log)
                                add_to_log("end_time", end_time, log)
                                email_log(f">> {timestamp} Processing time: {tat:.2f} seconds [Subject: {subject}]")
                                
                                # Enhanced: Capture autoresponse result with timeout handling
                                email_log(f">> {timestamp} Checking autoresponse task status [Subject: {subject}]")
                                try:
                                    # Wait for autoresponse task with a timeout (e.g., 10 seconds)
                                    autoresponse_success = await asyncio.wait_for(autoresponse_task, timeout=10.0)
                                    add_to_log("auto_response_sent", "success" if autoresponse_success else "failed", log)
                                    email_log(f">> {timestamp} Autoresponse task completed: {'success' if autoresponse_success else 'failed'} [Subject: {subject}]")
                                except asyncio.TimeoutError:
                                    # If autoresponse is taking too long, assume it's still running in background
                                    # and mark as "pending" in the log
                                    email_log(f">> {timestamp} Autoresponse task taking longer than expected [Subject: {subject}]")
                                    add_to_log("auto_response_sent", "pending", log)
                                except Exception as e:
                                    # If autoresponse task raised an exception
                                    email_log(f">> {timestamp} Error in autoresponse task [Subject: {subject}]: {str(e)}")
                                    add_to_log("auto_response_sent", "failed", log)
                                
                                email_log(f">> {timestamp} Inserting main log record to database [Subject: {subject}]")
                                await insert_log_to_db(log)
                                
                                # Enhanced: Insert system logs to database with autoresponse details
                                try:
                                    email_log(f">> {timestamp} Inserting enhanced system log record to database [Subject: {subject}]")
                                    await insert_system_log_to_db(email_id)
                                    system_log_inserted = True
                                    email_log(f">> {timestamp} Enhanced system log inserted successfully [Subject: {subject}]")
                                except Exception as e:
                                    email_log(f">> {timestamp} Failed to insert enhanced system log: {str(e)}")
                                
                                processed = True
                                
                                email_log(f">> {timestamp} Error recovery successful [Subject: {subject}]")
                        else:
                            if not processed:
                                system_log_inserted = await handle_error_logging(log, original_destination, f"Failed in both primary processing and fallback forwarding: {str(e)}", start_time, subject, autoresponse_task, email_id)
                                processed = True
                    except Exception as fallback_err:
                        email_log(f">> {timestamp} Error in fallback forwarding [Subject: {subject}]: {str(fallback_err)}")
                        if not processed:
                            system_log_inserted = await handle_error_logging(log, original_destination, f"Complete failure - Primary error: {str(e)}, Fallback error: {str(fallback_err)}", start_time, subject, autoresponse_task, email_id)
                            processed = True
                    
            else:
                # APEX classification failed - implement fallback routing
                email_log(f">> {timestamp} APEX classification failed [Subject: {subject}]. Implementing fallback routing.")
                email_log(f">> {timestamp} APEX failure reason: {apex_response.get('message', 'Unknown error')} [Subject: {subject}]")
                # No intervention when falling back to original destination
                add_to_log("apex_intervention", "false", log)
                
                if not processed:
                    email_log(f">> {timestamp} Starting APEX failure logging and fallback process [Subject: {subject}]")
                    system_log_inserted = await handle_apex_failure_logging(
                        log, 
                        email_data, 
                        apex_response, 
                        access_token, 
                        account, 
                        message_id, 
                        start_time,
                        subject,
                        autoresponse_task,
                        email_id  # Pass email_id for system logging
                    )
                    processed = True
                    
        except Exception as e:
            email_log(f">> {timestamp} General error processing email [Subject: {subject}]: {str(e)}")
            
            # Final attempt at fallback routing if nothing else worked
            try:
                # Only attempt if we haven't processed yet
                if not processed:
                    email_log(f">> {timestamp} Starting critical error recovery [Subject: {subject}]")
                    # No intervention in critical error recovery
                    add_to_log("apex_intervention", "false", log)
                    
                    # 10/07/2025 - BUGFIX 481012
                    # CHANGE 2
                    # OVERRIDE ORIGINAL DESTINATION TO POLICYSERVICE IF ORIGINAL DESTINATION IS SAME AS APEX CONSOLIDATION BIN
                    if original_destination.lower() == EMAIL_ACCOUNTS[0].lower():
                        FORWARD_TO = POLICY_SERVICES
                    else: 
                        FORWARD_TO = original_destination
                    # END OF CHANGE - BUGFIX 481012

                    email_log(f">> {timestamp} Attempting critical error recovery forwarding [Subject: {subject}]")
                    fallback_success = await forward_email(
                        access_token,
                        account,
                        message_id,
                        original_sender,
                        FORWARD_TO,
                        email_data,
                        f"AI Forwarded message (critical error recovery)"
                    )
                    
                    if fallback_success:
                        email_log(f">> {timestamp} Critical error recovery forwarding successful [Subject: {subject}]")
                        try:
                            email_log(f">> {timestamp} Attempting to mark email as read after critical recovery [Subject: {subject}]")
                            marked_as_read = await mark_email_as_read(access_token, account, message_id)
                        except Exception as mark_err:
                            email_log(f">> {timestamp} Failed to mark as read in critical error recovery [Subject: {subject}]: {str(mark_err)}")
                            marked_as_read = False
                        
                        system_log_inserted = await handle_error_logging(log, original_destination + " (critical recovery)", f"Critical error recovery successful: {str(e)}", start_time, subject, autoresponse_task, email_id)
                        processed = True
                        
                        email_log(f">> {timestamp} Critical error recovery successful [Subject: {subject}]")
                    else:
                        email_log(f">> {timestamp} Critical error recovery forwarding failed [Subject: {subject}]")
                        system_log_inserted = await handle_error_logging(log, "DELIVERY FAILED", f"CRITICAL: All delivery attempts failed. Original error: {str(e)}", start_time, subject, autoresponse_task, email_id)
                        processed = True
                        
                        email_log(f">> {timestamp} CRITICAL: All delivery attempts failed [Subject: {subject}]")
            except Exception as final_err:
                email_log(f">> {timestamp} Final error recovery attempt failed [Subject: {subject}]: {str(final_err)}")
                if not processed:
                    try:
                        system_log_inserted = await handle_error_logging(log, "DELIVERY FAILED", f"CRITICAL: Email could not be processed or forwarded. Original error: {str(e)}, Final error: {str(final_err)}", start_time, subject, autoresponse_task, email_id)
                        processed = True
                    except Exception as log_err:
                        email_log(f">> {timestamp} Even logging failed [Subject: {subject}]: {str(log_err)}")
        
        # Enhanced: Clean up email log capture after processing
        finally:
            # Ensure system logs are always inserted, even if there were critical errors
            if not system_log_inserted:
                try:
                    await insert_system_log_to_db(email_id)
                    email_log(f">> {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Enhanced system log inserted in finally block [Subject: {subject}]")
                except Exception as cleanup_err:
                    email_log(f">> {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Failed to insert enhanced system log in finally block [Subject: {subject}]: {str(cleanup_err)}")
            
            # Clean up email log capture memory
            try:
                email_log_capture.clear_email_logs(email_id)
            except Exception as cleanup_err:
                # Don't fail the whole process for cleanup errors
                email_log(f">> {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Error cleaning up email logs [Subject: {subject}]: {str(cleanup_err)}")

async def handle_error_logging(log, forward_to, error_message, start_time, subject=None, autoresponse_task=None, email_id=None):
    """
    Helper function to handle error logging consistently with enhanced autoresponse tracking
    
    Args:
        log: The log object to update
        forward_to: The address the email was forwarded to (or attempted to)
        error_message: The error message to log
        start_time: When the processing started, for calculating TAT
        subject: Optional email subject for better logging
        autoresponse_task: Optional autoresponse task to wait for
        email_id: Email ID for enhanced system logging
        
    Returns:
        bool: True if system log was inserted successfully
    """
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    subject_info = f"[Subject: {subject}] " if subject else ""
    system_log_inserted = False
    
    try:
        log_apex_fail(log, error_message)
        add_to_log("apex_routed_to", forward_to, log)
        add_to_log("sts_read_eml", "error", log)
        add_to_log("sts_class", "error", log)
        add_to_log("sts_routing", "error", log)
        
        # Default to no intervention for error cases if not already set
        if "apex_intervention" not in log:
            add_to_log("apex_intervention", "false", log)
        
        end_time = datetime.datetime.now()
        tat = (end_time - start_time).total_seconds()
        add_to_log("tat", tat, log)
        add_to_log("end_time", end_time, log)
        
        # Enhanced: Capture autoresponse result with proper error handling
        if autoresponse_task:
            try:
                # Wait for autoresponse task with a timeout (e.g., 10 seconds)
                autoresponse_success = await asyncio.wait_for(autoresponse_task, timeout=10.0)
                add_to_log("auto_response_sent", "success" if autoresponse_success else "failed", log)
                email_log(f">> {timestamp} Autoresponse task completed in error handler: {'success' if autoresponse_success else 'failed'} {subject_info}")
            except asyncio.TimeoutError:
                # If autoresponse is taking too long, assume it's still running in background
                # and mark as "pending" in the log
                email_log(f">> {timestamp} Autoresponse task taking longer than expected in error handler {subject_info}")
                add_to_log("auto_response_sent", "pending", log)
            except Exception as e:
                # If autoresponse task raised an exception
                email_log(f">> {timestamp} Error in autoresponse task in error handler {subject_info}: {str(e)}")
                add_to_log("auto_response_sent", "failed", log)
        else:
            # No autoresponse task was created
            add_to_log("auto_response_sent", "not_attempted", log)
        
        await insert_log_to_db(log)
        
        # Enhanced: Insert system logs to database with comprehensive error details
        if email_id:
            try:
                await insert_system_log_to_db(email_id)
                system_log_inserted = True
                email_log(f">> {timestamp} Enhanced system log inserted successfully in error logging {subject_info}")
            except Exception as e:
                email_log(f">> {timestamp} Failed to insert enhanced system log in error logging {subject_info}: {str(e)}")
        
        email_log(f">> {timestamp} Error logged with enhanced details {subject_info}")
        return system_log_inserted
    except Exception as e:
        email_log(f">> {timestamp} Failed to log error with enhanced details {subject_info}: {str(e)}")
        return system_log_inserted

async def handle_apex_failure_logging(log, email_data, apex_response, access_token, account, message_id, start_time, subject=None, autoresponse_task=None, email_id=None):
    """
    Helper function to handle APEX failure logging consistently with fallback routing and enhanced autoresponse tracking
    
    Args:
        log: The log object to update
        email_data: Dictionary containing email data
        apex_response: The failed response from APEX classification
        access_token: Valid Microsoft Graph API token
        account: Email account being processed
        message_id: Unique ID of the email message
        start_time: When processing started, for calculating TAT
        subject: Optional email subject for better logging
        autoresponse_task: Optional autoresponse task to wait for
        email_id: Email ID for enhanced system logging
        
    Returns:
        bool: True if system log was inserted successfully
    """
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    subject_info = f"[Subject: {subject}] " if subject else ""
    system_log_inserted = False
    
    original_sender = email_data.get('from', '')
    original_destination = email_data.get('to', '')
    
    try:
        # Always try to forward to original destination when APEX fails
        email_log(f">> {timestamp} Attempting to forward to original destination due to APEX failure {subject_info}")
        
        # No intervention when falling back to original destination on APEX failure
        add_to_log("apex_intervention", "false", log)
        
        # 10/07/2025 - BUGFIX 481012
        # CHANGE 2
        # OVERRIDE ORIGINAL DESTINATION TO POLICYSERVICE IF ORIGINAL DESTINATION IS SAME AS APEX CONSOLIDATION BIN
        if original_destination.lower() == EMAIL_ACCOUNTS[0].lower():
            FORWARD_TO = POLICY_SERVICES
        else: 
            FORWARD_TO = original_destination
        # END OF CHANGE - BUGFIX 481012
             
        forward_success = await forward_email(
            access_token,
            account,
            message_id,
            original_sender,
            FORWARD_TO,
            email_data,
            "AI Forwarded message by default due to APEX LLM error"
        )
        
        if forward_success:
            # Try to mark the email as read
            try:
                marked_as_read = await mark_email_as_read(access_token, account, message_id)
            except Exception as mark_err:
                email_log(f">> {timestamp} Failed to mark as read {subject_info}: {str(mark_err)}")
                marked_as_read = False
                
            # Log the outcome
            log_apex_fail(log, apex_response['message'])
            add_to_log("apex_routed_to", FORWARD_TO, log)
            add_to_log("sts_read_eml", "success" if marked_as_read else "error", log)
            add_to_log("sts_class", "error", log)
            add_to_log("sts_routing", "success", log)
            
            end_time = datetime.datetime.now()
            tat = (end_time - start_time).total_seconds()
            add_to_log("tat", tat, log)
            add_to_log("end_time", end_time, log)
            
            # Enhanced: Capture autoresponse result with proper error handling
            if autoresponse_task:
                try:
                    # Wait for autoresponse task with a timeout (e.g., 10 seconds)
                    autoresponse_success = await asyncio.wait_for(autoresponse_task, timeout=10.0)
                    add_to_log("auto_response_sent", "success" if autoresponse_success else "failed", log)
                    email_log(f">> {timestamp} Autoresponse task completed in APEX failure handler: {'success' if autoresponse_success else 'failed'} {subject_info}")
                except asyncio.TimeoutError:
                    # If autoresponse is taking too long, assume it's still running in background
                    # and mark as "pending" in the log
                    email_log(f">> {timestamp} Autoresponse task taking longer than expected in APEX failure handler {subject_info}")
                    add_to_log("auto_response_sent", "pending", log)
                except Exception as e:
                    # If autoresponse task raised an exception
                    email_log(f">> {timestamp} Error in autoresponse task in APEX failure handler {subject_info}: {str(e)}")
                    add_to_log("auto_response_sent", "failed", log)
            else:
                # No autoresponse task was created
                add_to_log("auto_response_sent", "not_attempted", log)
            
            await insert_log_to_db(log)
            
            # Enhanced: Insert system logs to database with APEX failure details
            if email_id:
                try:
                    await insert_system_log_to_db(email_id)
                    system_log_inserted = True
                    email_log(f">> {timestamp} Enhanced system log inserted successfully in APEX failure logging {subject_info}")
                except Exception as e:
                    email_log(f">> {timestamp} Failed to insert enhanced system log in APEX failure logging {subject_info}: {str(e)}")
            
            email_log(f">> {timestamp} Successfully forwarded to original destination despite APEX failure {subject_info}")
        else:
            # If even the fallback forwarding failed, log the error
            system_log_inserted = await handle_error_logging(log, original_destination, f"Failed to forward to original destination after APEX failure: {apex_response['message']}", start_time, subject, autoresponse_task, email_id)
        
        return system_log_inserted
            
    except Exception as e:
        email_log(f">> {timestamp} Error in handling APEX failure {subject_info}: {str(e)}")
        system_log_inserted = await handle_error_logging(log, "DELIVERY FAILED", f"Failed to recover from APEX failure: {str(e)}", start_time, subject, autoresponse_task, email_id)
        return system_log_inserted

async def process_batch():
    """
    Process a batch of unread emails from all configured accounts.
    Fetches unread emails and processes them in small batches to avoid
    overwhelming the API.
    
    Returns:
        None
    """
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        # Get fresh access token for Microsoft Graph API
        access_token = await get_access_token()
        if not access_token:
            print(f">> {timestamp} Failed to obtain access token. Skipping batch.")
            return
        
        # Process each configured email account
        for account in EMAIL_ACCOUNTS:
            try:
                all_unread_emails = await fetch_unread_emails(access_token, account)
                
            except Exception as e:
                print(f">> {timestamp} Error fetching unread emails for {account}: {str(e)}")
                continue  # Skip to the next account if there's an error fetching emails

            if all_unread_emails:
                print(f">> {timestamp} Processing {len(all_unread_emails)} unread emails in batch")
            
                # Process emails in small batches to avoid API rate limits
                for i in range(0, len(all_unread_emails), BATCH_SIZE):
                    batch = all_unread_emails[i:i+BATCH_SIZE]
                    tasks = [asyncio.create_task(process_email(access_token, account, email_data, message_id)) 
                            for email_data, message_id in batch]
                    
                    # gather with return_exceptions=True ensures the loop continues even if some tasks fail
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Enhanced: Check for exceptions in the results and create comprehensive emergency logs
                    for idx, result in enumerate(results):
                        if isinstance(result, Exception):
                            try:
                                email_subject = batch[idx][0].get('subject', 'Unknown subject') if idx < len(batch) else 'Unknown'
                                email_id = batch[idx][0].get('email_id', '') if idx < len(batch) else ''
                                internet_message_id = batch[idx][0].get('internet_message_id', '') if idx < len(batch) else ''
                                
                                print(f">> {timestamp} Task for email [Subject: {email_subject}] raised exception: {str(result)}")
                                
                                # Enhanced: Try to create a comprehensive system log for the failed email
                                if email_id and internet_message_id:
                                    try:
                                        with email_log_capture.capture_for_email(email_id, internet_message_id, email_subject):
                                            email_log(f">> {timestamp} CRITICAL ERROR: Email processing task failed with exception: {str(result)}")
                                            email_log(f">> {timestamp} Email ID: {email_id}")
                                            email_log(f">> {timestamp} Internet Message ID: {internet_message_id}")
                                            email_log(f">> {timestamp} Subject: {email_subject}")
                                            email_log(f">> {timestamp} From: {batch[idx][0].get('from', 'Unknown sender') if idx < len(batch) else 'Unknown'}")
                                            email_log(f">> {timestamp} To: {batch[idx][0].get('to', 'Unknown recipient') if idx < len(batch) else 'Unknown'}")
                                            email_log(f">> {timestamp} Task exception type: {type(result).__name__}")
                                            email_log(f">> {timestamp} Emergency system log created due to task failure")
                                            
                                            # Enhanced: Log autoresponse details for failed emails
                                            email_log_capture.log_autoresponse_attempt(
                                                email_id,
                                                attempted=False,
                                                successful=False,
                                                skip_reason="Email processing task failed before autoresponse attempt",
                                                error_message=f"Task exception: {str(result)}"
                                            )
                                            
                                            await insert_system_log_to_db(email_id)
                                            print(f">> {timestamp} System log created for failed email [Subject: {email_subject}]")
                                    except Exception as emergency_log_err:
                                        print(f">> {timestamp} Failed to create system log for failed email: {str(emergency_log_err)}")
                            except Exception as exception_handling_err:
                                print(f">> {timestamp} Error handling task exception: {str(exception_handling_err)}")
                    
                    # Add a small delay between batches to avoid overwhelming the API
                    await asyncio.sleep(1)
            else:
                print(f">> {timestamp} No unread emails found for: {account}")
                
    except Exception as e:
        print(f">> {timestamp} Unexpected error in batch processing: {str(e)}")

async def retry_unread_emails():
    """
    Periodically attempt to mark emails as read that were processed
    but couldn't be marked as read previously.
    
    Returns:
        None
    """
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    
    if not processed_but_unread:
        return
    
    print(f">> {timestamp} Retrying to mark {len(processed_but_unread)} processed emails as read")
    
    try:
        # Get fresh access token
        access_token = await get_access_token()
        if not access_token:
            print(f">> {timestamp} Failed to obtain access token for retry operation.")
            return
        
        # Create a copy of the set to avoid modification during iteration
        retry_set = processed_but_unread.copy()
        success_count = 0
        
        for account, message_id in retry_set:
            try:
                success = await mark_email_as_read(access_token, account, message_id)
                if success:
                    processed_but_unread.remove((account, message_id))
                    success_count += 1
            except Exception as e:
                print(f">> {timestamp} Failed to mark message {message_id} as read on retry: {str(e)}")
        
        if success_count > 0:
            print(f">> {timestamp} Successfully marked {success_count} emails as read on retry")
    
    except Exception as e:
        print(f">> {timestamp} Error in retry operation: {str(e)}")

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

    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    print(f">> {timestamp} APEX Email Processing Service starting")

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
            timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
            print(f">> {timestamp} Error processing batch: {str(e)}")
            # Continue the loop despite errors to maintain service continuity

        # Calculate remaining time in the interval and sleep accordingly
        elapsed_time = time.time() - start_time
        if elapsed_time < EMAIL_FETCH_INTERVAL:
            sleep_time = EMAIL_FETCH_INTERVAL - elapsed_time
            timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
            print(f">> {timestamp} Batch processing completed in {elapsed_time:.2f}s. Sleeping for {sleep_time:.2f}s.")
            await asyncio.sleep(sleep_time)
        else:
            timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
            print(f">> {timestamp} Batch processing took {elapsed_time:.2f}s (longer than interval). Processing next batch immediately.")

def trigger_email_triage():
    """
    Entry point for the application. Runs the main async loop
    if the 'start' argument is provided.
    
    Returns:
        None
    """
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    
    if len(sys.argv) > 1 and sys.argv[1] == 'start':
        print(f">> {timestamp} Starting APEX email processing service")
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print(f">> {timestamp} Service stopped by user.")
        except Exception as e:
            print(f">> {timestamp} Fatal error: {str(e)}")
            # In a production environment, you might want to restart the service here
    else:
        print("To start the email processing, run with 'start' argument")
        print("Run Command: python main.py start")

if __name__ == '__main__':
    trigger_email_triage()
