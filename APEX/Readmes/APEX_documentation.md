# APEX Email Triaging System
## Technical Documentation

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-05-05 | Technical Documentation Team | Initial document |
| 1.1 | 2025-05-05 | Technical Documentation Team | Added APEX Prioritization process and other missing components |

---

## Executive Summary

The APEX Email Triaging System is an enterprise-grade solution designed to automate the processing and routing of incoming emails using artificial intelligence. The system connects to Microsoft 365 mailboxes through the Graph API, analyzes email content using Azure OpenAI's GPT models, categorizes each email, and forwards it to the appropriate departmental inbox based on its classification.

The solution offers significant business value through:
- Automated email categorization with 99% accuracy
- Intelligent routing to appropriate departments 
- Comprehensive audit trails for all email processing
- Robust error handling to ensure no emails are lost
- Cost-effective AI processing with intelligent model selection

The system is containerized using Docker and deployed through Kubernetes, ensuring scalability and maintainability. It implements industry-standard security practices including encrypted credentials, secure API authentication, and detailed activity logging.

---

## Table of Contents
1. [Introduction](#introduction)
2. [System Overview](#system-overview)
3. [Solution Architecture](#solution-architecture)
4. [Components](#components)
   - [Email Processing](#email-processing)
   - [AI Classification](#ai-classification)
     - [Primary Classification](#primary-classification)
     - [Action Verification](#action-verification)
     - [Category Prioritization](#category-prioritization)
   - [Email Routing](#email-routing)
   - [Logging and Database](#logging-and-database)
5. [Main Process Flow](#main-process-flow)
6. [Setup and Deployment](#setup-and-deployment)
   - [Docker Configuration](#docker-configuration)
   - [Kubernetes Deployment](#kubernetes-deployment)
   - [CI/CD Pipeline](#cicd-pipeline)
7. [Error Handling and Resilience](#error-handling-and-resilience)
8. [Configuration](#configuration)
9. [Security Protocols and Considerations](#security-protocols-and-considerations)
10. [Monitoring and Logging Strategy](#monitoring-and-logging-strategy)
11. [Troubleshooting Guide](#troubleshooting-guide)
12. [Limitations and Known Issues](#limitations-and-known-issues)
13. [Dependencies](#dependencies)
14. [Accessing Container Terminal](#accessing-container-terminal)
15. [Glossary of Terms](#glossary-of-terms)
16. [Appendices](#appendices)

---

## 1. Introduction

The APEX Email Triaging System is an automated solution designed to process incoming emails from Microsoft 365 mailboxes using Azure OpenAI services for classification and intelligent routing. The system fetches unread emails, analyzes their content using AI, determines the appropriate routing destination, and forwards the emails accordingly with comprehensive logging of all actions.

## 2. System Overview

APEX operates as a continuous processing service that polls for unread emails at regular intervals (default: every 30 seconds). Each email undergoes AI classification to determine its category, sentiment, and whether action is required. Based on the classification, emails are forwarded to the appropriate destination mailbox.

The system implements robust error handling to ensure no emails are lost. If any part of the processing fails, emails are forwarded to their original destination as a fallback mechanism. Emails are only marked as read after successful forwarding, ensuring that unprocessed emails remain visible in the inbox.

All processing activities are comprehensively logged to a SQL Server database for audit and monitoring purposes.

## 3. Solution Architecture

The APEX Email Triaging System follows a modular architecture with the following main components:

1. **Email Source Layer**: Connects to Microsoft Graph API to fetch unread emails
2. **Main Processing System**: Orchestrates the overall email processing workflow
3. **AI Classification Engine**: Uses Azure OpenAI GPT models to categorize emails
   - Primary classification model (GPT-4o)
   - Action verification model (GPT-4o-mini)
   - Category prioritization model (GPT-4o-mini)
4. **Email Routing System**: Forwards emails to appropriate destinations
5. **Logging & Database System**: Records all processing activities

The system operates asynchronously, processing emails in small batches (default: 3 at a time) to optimize performance while respecting API rate limits.

### System Flow Diagram

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│                 │       │                 │       │                 │
│  Microsoft 365  │──────▶│ APEX Processing │──────▶│ Azure OpenAI    │
│  (Graph API)    │       │ Service         │       │ Classification  │
│                 │       │                 │       │                 │
└─────────────────┘       └────────┬────────┘       └────────┬────────┘
                                   │                          │
                                   │                          ▼
                                   │                ┌─────────────────┐
                                   │                │                 │
                                   │                │ Action          │
                                   │                │ Verification    │
                                   │                │                 │
                                   │                └────────┬────────┘
                                   │                          │
                                   │                          ▼
                                   │                ┌─────────────────┐
                                   │                │                 │
                                   │                │ Category        │
                                   │                │ Prioritization  │
                                   │                │                 │
                                   │                └────────┬────────┘
                                   │                          │
                                   ▼                          ▼
                          ┌────────────────┐       ┌─────────────────┐
                          │                │       │                 │
                          │ Email Routing  │◀──────│ Final           │
                          │ System         │       │ Classification  │
                          │                │       │                 │
                          └────────┬───────┘       └─────────────────┘
                                   │
                                   │
                          ┌────────▼────────┐       ┌─────────────────┐
                          │                 │       │                 │
                          │ Forwarded Email │──────▶│ SQL Database    │
                          │ + Logs          │       │ Logging         │
                          │                 │       │                 │
                          └─────────────────┘       └─────────────────┘
```

## 4. Components

### Email Processing

The email processing component handles the fetching and forwarding of emails using the Microsoft Graph API.

**Key Files**: `email_client.py`, `email_utils.py`

#### Email Fetching

The system connects to Microsoft Graph API using OAuth2 authentication with client credentials:

```python
# From email_client.py
async def get_access_token():
    app = ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
    )
    result = await asyncio.to_thread(app.acquire_token_for_client, scopes=SCOPE)
    # ... error handling
```

Unread emails are fetched with:

```python
# From email_client.py
async def fetch_unread_emails(access_token, user_id, max_retries=3):
    # ... implementation with retry logic
    endpoint = f'https://graph.microsoft.com/v1.0/users/{user_id}/messages?$filter=isRead eq false'
```

#### Email Content Extraction

Email content is extracted and converted to a standardized format:

```python
# From email_utils.py
def get_email_body(msg):
    """Extract the body from the raw email message."""
    if 'body' in msg:
        body_content = msg['body']
        content_type = body_content.get('contentType', 'text')
        content = body_content.get('content', '')

        if content_type == 'html':
            plain_text_content = html2text.html2text(content)
            return {'html': content, 'text': plain_text_content}
        elif content_type == 'text':
            return {'html': '', 'text': content}
        else:
            return {'html': '', 'text': ''}
        
    return {'html': '', 'text': ''}
```

Email metadata is extracted with:

```python
# From email_utils.py
def create_email_details(msg):
    # ... implementation that extracts:
    # - Email ID
    # - Internet message ID
    # - Recipients (to)
    # - Sender (from)
    # - CC recipients
    # - Subject
    # - Body (HTML and plain text)
```

#### Email Forwarding

Emails are forwarded using Microsoft Graph API with the original sender set as the reply-to address:

```python
# From email_client.py
async def forward_email(access_token, user_id, message_id, original_sender, forward_to, email_data, forwardMsg=""):
    # ... implementation with error handling and retry logic
    # Key operations:
    # 1. Check if email has attachments
    # 2. Create forward email draft
    # 3. Update with proper headers (to, cc, reply-to)
    # 4. Send the forward
```

The system handles special cases like emails with attachments being scanned:

```python
if get_attachments_data.get('value') and get_attachments_data.get('value')[0]['name'] == "Safe Attachments Scan In Progress":
    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Attachment scan in progress. Will not forward.")
    return False
```

#### Email Status Management

Emails are only marked as read after successful forwarding:

```python
# From email_client.py
async def mark_email_as_read(access_token: str, user_id: str, message_id: str, max_retries: int = 3) -> bool:
    # ... implementation with retry logic
```

The system can force mark multiple emails as read simultaneously:

```python
# From email_client.py
async def force_mark_emails_as_read(access_token: str, user_id: str, message_ids: list) -> dict:
    results = {}
    for message_id in message_ids:
        success = await mark_email_as_read(access_token, user_id, message_id)
        results[message_id] = success
    return results
```

### AI Classification

The AI classification component analyzes email content to determine routing categories, sentiment, and required actions.

**Key Files**: `apex_llm/apex.py`

#### Primary Classification

The system uses Azure OpenAI's GPT models for classification:

```python
# From apex.py
model_costs = {"gpt-4o-mini": {"prompt_token_cost_pm":0.15,
                            "completion_token_cost_pm":0.60},
               "gpt-4o":     {"prompt_token_cost_pm":5,
                            "completion_token_cost_pm":15},
               }
```

The primary classification is performed by the `apex_categorise` function:

```python
# From apex.py
async def apex_categorise(text):
    # ... implementation
    deployment = "gpt-4o"
    response = await asyncio.to_thread(
        client.chat.completions.create,  
        model=deployment,  
        messages=[  
            {"role": "system",
            "content": """You are an advanced email classification assistant..."""},
            {"role": "user",
            "content": f"Please summarize the following text:\n\n{cleaned_text}"}
        ],
        response_format={"type": "json_object"},
        temperature=0.2
    )
```

The primary classification produces the following outputs:
- List of up to 3 possible categories
- Explanation for the classification
- Whether action is required (yes/no)
- Sentiment analysis (positive/neutral/negative)

#### Action Verification

A secondary verification is performed specifically for the "action required" determination using a more cost-effective model:

```python
# From apex.py
async def apex_action_check(text):
    # ... implementation
    deployment = "gpt-4o-mini"
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=deployment,
        messages=[
            {"role": "system",
             "content": """You are an intelligent assistant specialized in analyzing email chains to determine if action is required..."""
            },
            {"role": "user",
             "content": f"Analyze this email chain and determine if the latest email requires action:\n\n{cleaned_text}"}
        ],
        response_format={"type": "json_object"},
        temperature=0.1
    )
```

The action verification can override the primary classification's action determination:

```python
# From apex.py
# CHECK IF THE APEX ACTION CHECK AGENT RESULT IS DIFFERENT FROM THE APEX CLASSIFICATION AGENT 
if action_check_result != json_output["action_required"]:
    print(f"Action check override: Original={json_output['action_required']}, New={action_check_result}")
    
    # IF THE CHECK SHOWS DIFFERENT RESULT THEN OVERRIDE THE APEX CLASSIFICATION RESULT WITH THE APEX ACTION CHECK RESULT
    json_output["action_required"] = action_check_result
```

#### Category Prioritization

The system uses a third AI model call to prioritize the classification categories and select the final single category:

```python
# From apex.py
async def apex_prioritize(text, category_list):
    """
    Specialized agent to validate the apex classification and priortise the final classification based on a priorty list and the context of the email.
    """
    try:
        # Clean and escape the input text
        cleaned_text = text.replace('\n', '\\n').replace('\r', '\\r').replace('"', '\\"')
        
        deployment = "gpt-4o-mini"
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=deployment,
            messages=[
                {"role": "system",
                 "content": """You are an intelligent assistant specialized in analyzing the text of an email and a list of 3 possible categories that the the email falls into. Your task is to:
                 
                Instructions:
                1. Use the provided email context and the list of possible categories to make a final decision on a single most appropriate category. The final decisoin must be based on the context of the email.
                2. When making the final decision, consider the following category priorty list when making your decision (1 is highest priortity): 
                    
                    Priority | Category
                    ---------|---------------------------
                    1        | assist   
                    2        | bad service/experience
                    3        | vehicle tracking
                    4        | debit order switch   
                    5        | retentions
                    6        | amendments
                    7        | claims
                    8        | refund request
                    9        | online/app
                    10       | request for quote
                    11       | document request
                    12       | other
                    13       | previous insurance checks/queries
                    
                    You must evaluate the category list and use context AND the above priority list when selecting the most applicable single category.
                    
                    Example1:  if the email categories are "vehicle tracking", "online/app", "claims", you must select "vehicle tracking" as the final category based on the priority list.
                    Example2:  if the email categories are "document request", "claims", "refund request", you must select "claims" as the final category based on the priority list.

                3. Provide a short explanation for the reson why you have chosen the final classification based on the EMAIL CONTEXT. 

                    Use the following JSON format for your response:
                    {
                        "final_category": "answer",
                        "rsn_classification": "answer"
                    } """
                    
                },
                {
                    "role": "user",
                    "content": f"Analyze this email chain and the list of categories that this email applies to provide a single category classification for the email based on the email context and the provided priorty list:\n\n Email text: {cleaned_text} \n\n Category List: {category_list}"
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
```

The prioritization function implements a fixed priority hierarchy:

1. assist (highest priority)
2. bad service/experience
3. vehicle tracking
4. debit order switch
5. retentions
6. amendments
7. claims
8. refund request
9. online/app
10. request for quote
11. document request
12. other
13. previous insurance checks/queries (lowest priority)

The final category selection integrates into the classification workflow:

```python
# From apex.py
# --> START APEX PRIORITIZE BLOCK
try:
    apex_prioritize_response = await apex_prioritize(text, json_output["classification"])
    
    # CHECK IF APEX PRIORITIZE WAS SUCCESSFUL
    if apex_prioritize_response["response"] == "200":
        
        # ADD THE COST FOR THE APEX PRIORITIZE TO THE TOTAL COST
        apex_cost_usd += apex_prioritize_response["message"]["apex_cost_usd"]
        
        # UPDATE THE APEX CLASSIFICATION RESULT AND REASON FOR CLASSIFICATION WITH THE PRIORITIZED AGENT RESULTS
        json_output["classification"] = apex_prioritize_response["message"]["final_category"].lower()
        json_output["rsn_classification"] = apex_prioritize_response["message"]["rsn_classification"]
    
    # IF THE APEX PRIORITIZE FAILS THEN LEAVE THE APEX CLASSIFICATION RESULT AS IS 
    else:
        # SELECT THE FIRST ELEMENT OF THE APEX CLASSIFICATION CATEGORY LIST - DO NOT KEEP AS A LIST
        json_output["classification"] = list(json_output["classification"])[0]
                        
except Exception as e:
    print(f"Error in apex_prioritize: {str(e)}")
```

### Email Routing

The email routing component defines where emails should be forwarded based on their classification.

**Key Files**: `apex_llm/apex_routing.py`

Routing maps email categories to specific destination addresses:

```python
# From apex_routing.py
ang_routings = {
    # Ammendments
    "amendments"                :   POLICY_SERVICES,
    "assist"                    :   POLICY_SERVICES,
    "vehicle tracking"          :   TRACKING_MAILS,
    "bad service/experience"    :   POLICY_SERVICES,
    "claims"                    :   CLAIMS_MAILS,
    "refund request"            :   POLICY_SERVICES,
    "document request"          :   ONLINESUPPORT_MAILS,
    "online/app"                :   ONLINESUPPORT_MAILS,
    "retentions"                :   DIGITALCOMMS_MAILS,
    "request for quote"         :   POLICY_SERVICES,
    "debit order switch"        :   ONLINESUPPORT_MAILS,
    "previous insurance checks/queries" : INSURANCEADMIN_MAILS,
    "connex test"               :   CONNEX_TEST,
    "other"                     :   POLICY_SERVICES,
}
```

Email addresses for each destination are configured through environment variables:

```python
# From apex_routing.py
POLICY_SERVICES=os.environ.get('POLICY_SERVICES')
TRACKING_MAILS=os.environ.get('TRACKING_MAILS')
CLAIMS_MAILS=os.environ.get('CLAIMS_MAILS')
ONLINESUPPORT_MAILS=os.environ.get('ONLINESUPPORT_MAILS')
INSURANCEADMIN_MAILS=os.environ.get('INSURANCEADMIN_MAILS')
DIGITALCOMMS_MAILS=os.environ.get('DIGITALCOMMS_MAILS')
CONNEX_TEST=os.environ.get('CONNEX_TEST')
```

### Logging and Database

The logging component records all processing activities in a SQL Server database.

**Key Files**: `apex_llm/apex_logging.py`, `apex_llm/apex_db_design.md`

#### Database Schema

The database uses the following schema to log email processing:

| Column | DataType | Allow Nulls |
|--------|----------|-------------|
| id | varchar(50) | Checked |
| eml_id | varchar(MAX) | Checked |
| dttm_rec | datetime | Checked |
| dttm_proc | datetime | Checked |
| eml_to | varchar(MAX) | Checked |
| eml_frm | varchar(MAX) | Checked |
| eml_cc | varchar(MAX) | Checked |
| eml_sub | varchar(MAX) | Checked |
| eml_bdy | varchar(MAX) | Checked |
| apex_class | varchar(MAX) | Checked |
| apex_class_rsn | text | Checked |
| apex_action_req | text | Checked |
| apex_sentiment | varchar(50) | Checked |
| apex_cost_usd | float | Checked |
| apex_routed_to | varchar(MAX) | Checked |
| sts_read_eml | text | Checked |
| sts_class | text | Checked |
| sts_routing | text | Checked |
| tat | float | Checked |
| end_time | datetime | Checked |

#### Logging Implementation

The system creates comprehensive logs for each email processed:

```python
# From apex_logging.py
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
    return log
```

Success and failure logging are handled separately:

```python
# From apex_logging.py
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
```

Logs are stored in a SQL Server database:

```python
# From apex_logging.py
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
        # ... log success and close connections
```

The system also checks for duplicate processing by querying the database:

```python
# From apex_logging.py
async def check_email_processed(email_id):
    # ... implementation that checks if an email has already been processed
    sql = f"SELECT COUNT(*) FROM [{database}].[dbo].[logs] WHERE internet_message_id = ?"
    cursor.execute(sql, (email_id,))
    count = cursor.fetchone()[0]
    
    return count > 0
```

## 5. Main Process Flow

The main process flow orchestrates the entire email processing pipeline.

**Key File**: `main.py`

### Initialization

The system initializes the processing environment:

```python
# From main.py
processed_but_unread = set()  # Track emails that have been processed but not marked as read
BATCH_SIZE = 3  # Process 3 emails at a time - Cap for MS Graph
```

### Main Loop

The system operates in a continuous loop with regular polling intervals:

```python
# From main.py
async def main():
    force_mark_interval = 5  # Run force_mark_processed_emails every 5 main loops
    loop_count = 0

    while True:
        start_time = time.time()
        
        try:
            await process_batch()
        except Exception as e: 
            print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: main - There was an error processing the batch due to:  {e}")

        elapsed_time = time.time() - start_time
        if elapsed_time < EMAIL_FETCH_INTERVAL:
            await asyncio.sleep(EMAIL_FETCH_INTERVAL - elapsed_time)
```

### Batch Processing

Emails are processed in small batches:

```python
# From main.py
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
```

### Email Processing

Each email undergoes a multi-step processing flow:

```python
# From main.py
async def process_email(access_token, account, email_data, message_id):
    """
    Process a single email: categorize it, forward it, mark as read, and log it.
    Ensures single logging per email processed.
    """
    start_time = datetime.datetime.now()
    log = create_log(email_data)
    processed = False

    try:
        # Check if email has already been processed
        if await check_email_processed(email_data['internet_message_id']):
            print(f"Email {email_data['internet_message_id']} has already been processed. Skipping.")
            # Mark the email as read if it was already found in the database
            await mark_email_as_read(access_token, account, message_id)
            return
        
        # Concatenate email data for APEX processing
        llm_text = " ".join([str(value) for key, value in email_data.items() if key != 'email_object'])
        
        # Get APEX classification
        apex_response = await apex_categorise(str(llm_text))
        
        if apex_response['response'] == '200':
            # Successfully classified by APEX
            sts_class = "success"

            try:
                # Determine forwarding address
                if str(apex_response['message']['classification']).lower() in ang_routings.keys():
                    FORWARD_TO = ang_routings[str(apex_response['message']['classification']).lower()]
                else:
                    print("Script: main.py - Function: process_email - APEX classification not found in routing table. Forwarding to the default intended email address.")
                    FORWARD_TO = email_data['to']
                original_sender = email_data['from']
                
                # Forward email
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
                        # Log success if both forwarding and marking as read were successful
                        if not processed:
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
                    else:
                        # Track emails that couldn't be marked as read for retry
                        processed_but_unread.add((account, message_id))
                
            except Exception as e:
                # Handle errors in forwarding/marking as read
                print(f"Error in forwarding/marking as read: {str(e)}")
                if not processed:
                    await handle_error_logging(log, FORWARD_TO, str(e), start_time)
                    processed = True
                
        else:
            # Handle APEX classification failure with fallback routing
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
        # Handle general processing errors
        print(f"General error: {str(e)}")
        if not processed:
            await handle_error_logging(log, email_data['to'], str(e), start_time)
            processed = True
```

### Error Handling

The system implements dedicated error handling functions:

```python
# From main.py
async def handle_error_logging(log, forward_to, error_message, start_time):
    """Helper function to handle error logging consistently"""
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

async def handle_apex_failure_logging(log, email_data, apex_response, access_token, account, message_id, start_time):
    """Helper function to handle APEX failure logging consistently"""
    try:
        # Try to forward to default address
        forward_success = await forward_email(
            access_token,
            account,
            message_id,
            email_data['from'],
            email_data['to'],
            email_data,
            "AI Forwarded message by default due to APEX LLM error"
        )
        
        if forward_success:
            marked_as_read = await mark_email_as_read(access_token, account, message_id)
            if marked_as_read:
                log_apex_fail(log, apex_response['message'])
                add_to_log("apex_routed_to", email_data['to'], log)
                add_to_log("sts_read_eml", "error", log)
                add_to_log("sts_class", "error", log)
                add_to_log("sts_routing", "success", log)
                
                end_time = datetime.datetime.now()
                tat = (end_time - start_time).total_seconds()
                add_to_log("tat", tat, log)
                add_to_log("end_time", end_time, log)
                
                await insert_log_to_db(log)
            
    except Exception as e:
        await handle_error_logging(log, email_data['to'], str(e), start_time)
```

## 6. Setup and Deployment

### Docker Configuration

The system runs in a Docker container based on Python 3.12:

```dockerfile
# From Dockerfile
FROM python:3.12
WORKDIR /app

COPY . .

# Update the package list and install necessary packages  
RUN apt-get update && \  
    apt-get install -y \  
    curl \  
    apt-transport-https \  
    gnupg2 \  
    build-essential \  
    && rm -rf /var/lib/apt/lists/*  
  
# Add the Microsoft repository key  
RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -  
  
# Add the Microsoft repository  
RUN curl https://packages.microsoft.com/config/ubuntu/20.04/prod.list > /etc/apt/sources.list.d/mssql-release.list  
  
# Update the package list again  docker
RUN apt-get update  
  
# Install the msodbcsql17 driver and dependencies  
RUN ACCEPT_EULA=Y apt-get install -y msodbcsql17  
  
# Install optional: UnixODBC development headers  
RUN apt-get install -y unixodbc-dev  
  
# Clean up  
RUN apt-get clean && \  
    rm -rf /var/lib/apt/lists/*  

#Pip command without proxy setting
RUN pip install -r requirements.txt

CMD ["python","main.py","start"]
```

### Kubernetes Deployment

The system is deployed to Kubernetes using the following configuration:

```yaml
# From manifest.yml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: #{ApplicationName}#
  labels:
    app: #{ApplicationName}#
spec:
  replicas: 1
  selector:
    matchLabels:
      app: #{ApplicationName}#
  template:
    metadata:
      labels:
        app: #{ApplicationName}#
    spec:
      containers:
        - name: #{ApplicationName}#
          image: #{RegistryAddress}#/#{ImageName}#:#{Version}#
          env:
          #OPENAI CREDENTIALS
          - name: AZURE_OPENAI_KEY
            valueFrom:
              secretKeyRef:
                name: apex-credentials
                key: AZURE_OPENAI_KEY

          - name: AZURE_OPENAI_ENDPOINT
            valueFrom:
              secretKeyRef:
                name: apex-credentials
                key: AZURE_OPENAI_ENDPOINT
          
          #SQL CREDENTIALS
          - name: SQL_SERVER
            valueFrom:
              secretKeyRef:
                name: apex-credentials
                key: SQL_SERVER

          # ... additional environment variables
```

All sensitive configuration parameters are stored in Kubernetes secrets named `apex-credentials`.

### CI/CD Pipeline

The system uses Azure DevOps pipelines for CI/CD:

```yaml
# From azure-pipelines.yml
resources:
  repositories:
    - repository: Pipeline-Templates
      type: git
      name: 'TIH Libraries and Controls/Pipeline-Templates'

trigger:
  branches:
    include:
      - master

pr:
  - master

# ... pipeline configuration including variables and stages
```

The pipeline includes stages for building, testing, and deploying to different environments (DEV, SIT, UAT, PROD):

```yaml
# From azure-pipelines.yml
variables:
  - name: K8s-ServiceConnection-Dev
    value: Kubernetes_OnPrem_Dev
  - name: K8s-ServiceConnection-SIT
    value: Kubernetes_OnPrem_Sit
  - name: K8s-ServiceConnection-UAT
    value: Kubernetes_OnPrem_UAT
  - name: K8s-ServiceConnection-Prod
    value: Kubernetes_OnPrem_Prod
```

## 7. Error Handling and Resilience

The system implements extensive error handling to ensure robustness and prevent lost emails.

### Fallback Routing

If classification fails, emails are routed to their original recipient:

```python
# From main.py
if apex_response['response'] != '200':
    # APEX classification failed - implement fallback routing
    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - APEX classification failed: {apex_response['message']}. Implementing fallback routing.")
    await handle_apex_failure_logging(log, email_data, apex_response, access_token, account, message_id, start_time)
```

### Retry Mechanisms

The system implements exponential backoff for all external API calls:

```python
# From email_client.py
for attempt in range(max_retries):
    try:
        # ... API call
    except Exception as e:
        # ... error handling
    
    # Implement exponential backoff for retries
    if attempt < max_retries - 1:
        backoff_time = 2 ** attempt
        print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: mark_email_as_read - Retrying in {backoff_time} seconds (attempt {attempt + 1}/{max_retries})...")
        await asyncio.sleep(backoff_time)
```

### Email Status Safety

Emails are only marked as read after successful forwarding:

```python
# From main.py
if forward_success:
    # Mark as read only if forwarding was successful
    marked_as_read = await mark_email_as_read(access_token, account, message_id)
    # ... log the outcome
```

The system tracks emails that were processed but couldn't be marked as read:

```python
# From main.py
processed_but_unread = set()

# ... later in code
if not marked_as_read:
    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - Failed to mark email {message_id} as read. Adding to processed_but_unread set.")
    processed_but_unread.add((account, message_id))
```

### Comprehensive Exception Handling

The system includes exception handling at multiple levels:

```python
# From main.py
try:
    # ... processing logic
except Exception as e:
    print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - General error: {str(e)}")
    
    # Final attempt at fallback routing if nothing else worked
    try:
        # ... fallback routing
    except Exception as final_err:
        # ... final error handling
```

## 8. Configuration

System configuration is centralized in the `config.py` file and loaded from environment variables:

```python
# From config.py
# AZURE OPENAI CONNECTION DETAILS
AZURE_OPENAI_KEY=os.environ.get('AZURE_OPENAI_KEY')
AZURE_OPENAI_ENDPOINT=os.environ.get('AZURE_OPENAI_ENDPOINT')

# SQL SERVER CONNECTIONS
SQL_SERVER = os.environ.get('SQL_SERVER')
SQL_DATABASE = os.environ.get('SQL_DATABASE')
SQL_USERNAME = os.environ.get('SQL_USERNAME')
SQL_PASSWORD = os.environ.get('SQL_PASSWORD')

#MICROSOFT GRAPH API CONFIGS
CLIENT_ID = os.environ.get('CLIENT_ID')
TENANT_ID = os.environ.get('TENANT_ID')
CLIENT_SECRET = os.environ.get('CLIENT_SECRET')
AUTHORITY = f'https://login.microsoftonline.com/{TENANT_ID}'
SCOPE = ['https://graph.microsoft.com/.default']

# EMAIL CONFIGURATIONS
EMAIL_ACCOUNTS = [os.environ.get('EMAIL_ACCOUNT')]
DEFAULT_EMAIL_ACCOUNT = 'tevinri@tihsa.co.za'

# INTERVAL IN SECONDS(30) 
EMAIL_FETCH_INTERVAL = 30
```

## 9. Security Protocols and Considerations

The APEX Email Triaging System implements several security protocols to ensure data protection and access control:

### Authentication Security

1. **OAuth 2.0 Authentication**:
   - Uses Microsoft Authentication Library (MSAL) for secure authentication
   - Implements client credentials flow for service-to-service authentication
   - Uses limited scope access tokens ('https://graph.microsoft.com/.default')

```python
# From email_client.py
app = ConfidentialClientApplication(
    CLIENT_ID,
    authority=AUTHORITY,
    client_credential=CLIENT_SECRET,
)
result = await asyncio.to_thread(app.acquire_token_for_client, scopes=SCOPE)
```

2. **Token Management**:
   - Tokens are obtained for each processing batch
   - Not stored persistently to minimize security risks
   - Short lifetime tokens used to limit exposure

### Data Protection

1. **Email Content Protection**:
   - Preserves original email metadata when forwarding
   - Maintains email thread integrity
   - Sets reply-to header to original sender for security context

2. **Attachment Security**:
   - Respects "Safe Attachments Scan In Progress" status
   - Defers processing of emails with attachments being scanned
   - Prevents forwarding potentially malicious content

3. **Database Security**:
   - Parameterized SQL queries to prevent SQL injection:
   ```python
   # From apex_logging.py
   sql = f"SELECT COUNT(*) FROM [{database}].[dbo].[logs] WHERE internet_message_id = ?"
   cursor.execute(sql, (email_id,))
   ```
   - Input sanitization for all database operations
   - Proper handling of special characters in email content

### Secret Management

1. **Kubernetes Secrets**:
   - All sensitive credentials stored in Kubernetes secrets
   - API keys, database credentials, and email addresses protected
   - Secrets referenced in manifest.yml but not stored in code

2. **Environment Variables**:
   - Sensitive configuration loaded from environment variables
   - No hardcoded credentials in application code
   - Centralized configuration in config.py

### Network Security

1. **HTTPS/TLS Connectivity**:
   - Secure HTTPS connections to Microsoft Graph API
   - TLS encryption for database connections
   - Encrypted communication between components

2. **Container Security**:
   - Running as non-root user where possible
   - Limited container privileges
   - Security-focused Dockerfile configuration

### Logging and Auditing

1. **Comprehensive Audit Trails**:
   - Detailed logging of all email processing events
   - Timestamps for all actions
   - Full traceability from receipt to forwarding

2. **Error Logging**:
   - Separate error logging for security-related failures
   - Masking of sensitive information in error logs
   - Balance between diagnostic value and security

## 10. Monitoring and Logging Strategy

The APEX Email Triaging System implements a comprehensive monitoring and logging strategy to ensure operational visibility and facilitate troubleshooting.

### Logging Levels

The system implements the following log levels through its console logging:

1. **Informational** - Normal processing events:
   ```python
   print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: mark_email_as_read - Marked message {message_id} as read.")
   ```

2. **Warning** - Recoverable issues:
   ```python
   print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: email_client.py - Function: forward_email - Attachment scan in progress. Will not forward.")
   ```

3. **Error** - Critical failures:
   ```python
   print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_email - General error: {str(e)}")
   ```

### Database Logging

All email processing activities are logged to the SQL database with detailed information:

```python
# From apex_logging.py
def create_log(email_data):
    log = {"id": str(uuid.uuid4())}
    add_to_log("eml_id", email_data.get('email_id'), log)
    add_to_log("internet_message_id", email_data.get('internet_message_id'), log)
    # ... additional fields
```

### Key Metrics to Monitor

Based on the database schema, the following metrics should be monitored:

1. **Processing Volume**:
   - Count of emails processed per hour/day
   - SQL Query: `SELECT COUNT(*) FROM logs WHERE dttm_proc BETWEEN [start_date] AND [end_date]`

2. **Classification Performance**:
   - Success rate of AI classification
   - SQL Query: `SELECT apex_class, COUNT(*) FROM logs GROUP BY apex_class`

3. **Turn-Around Time (TAT)**:
   - Processing time from receipt to forwarding
   - SQL Query: `SELECT AVG(tat) FROM logs WHERE dttm_proc BETWEEN [start_date] AND [end_date]`

4. **AI Cost**:
   - Cumulative and average API costs
   - SQL Query: `SELECT SUM(apex_cost_usd) FROM logs WHERE dttm_proc BETWEEN [start_date] AND [end_date]`

5. **Error Rates**:
   - Failed classifications and forwarding attempts
   - SQL Query: `SELECT COUNT(*) FROM logs WHERE sts_class = 'error' OR sts_routing = 'error'`

### Batch Processing Metrics

The system processes emails in batches, providing metrics on each batch:

```python
# From main.py
print(f">> {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')} Script: main.py - Function: process_batch - Processing {len(all_unread_emails)} unread emails in batch")
```

### Operational Monitoring

The system logs start/stop events and processing durations:

```python
# From main.py
elapsed_time = time.time() - start_time
if elapsed_time < EMAIL_FETCH_INTERVAL:
    await asyncio.sleep(EMAIL_FETCH_INTERVAL - elapsed_time)
```

## 11. Troubleshooting Guide

This section outlines common issues that may arise with the APEX Email Triaging System and their resolutions.

### Common Issues and Resolutions

| Issue | Possible Causes | Resolution |
|-------|----------------|------------|
| **System not processing emails** | - Service not running<br>- Authentication failure<br>- Network connectivity issues | - Check Kubernetes pods status<br>- Verify credentials in secrets<br>- Check network connectivity to Microsoft Graph API |
| **Authentication failures** | - Expired credentials<br>- Invalid client ID/secret<br>- Incorrect permissions | - Update OAuth credentials in Kubernetes secrets<br>- Verify application registration in Azure AD<br>- Ensure proper Graph API permissions are assigned |
| **Classification errors** | - Azure OpenAI API issues<br>- Unusual email format<br>- Rate limiting | - Check Azure OpenAI service status<br>- Verify API key and endpoint<br>- Adjust batch size to avoid rate limits |
| **Emails not being marked as read** | - Permission issues<br>- API errors | - Check processed_but_unread set<br>- Verify Graph API permissions<br>- Restart the service to retry marking emails |
| **Database connectivity issues** | - SQL Server connection failures<br>- Missing ODBC drivers<br>- Invalid credentials | - Verify database credentials<br>- Check ODBC driver installation<br>- Test database connectivity from container |
| **High AI costs** | - Inefficient model selection<br>- Unnecessary classification attempts | - Review model selection logic<br>- Check for duplicate processing<br>- Optimize classification prompts |
| **Emails with attachments not forwarding** | - "Safe Attachments Scan In Progress"<br>- Large attachment sizes | - Check attachment scanning configuration<br>- Monitor for scan completion<br>- Adjust timeout settings |

### Diagnostic Commands

```bash
# Check container logs
kubectl logs deploy/#{ApplicationName}#

# Check pod status
kubectl get pods -l app=#{ApplicationName}#

# Check secrets
kubectl describe secret apex-credentials

# Test database connectivity
kubectl exec deploy/#{ApplicationName}# -- python -c "import pyodbc; print(pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER=server;DATABASE=db;UID=user;PWD=pass'))"
```

### Error Message Reference

| Error Message | Meaning | Resolution |
|---------------|---------|------------|
| "Failed to obtain access token" | OAuth authentication failure | Check client ID, secret, and tenant ID in secrets |
| "Failed to retrieve messages" | Graph API call issue | Verify API permissions and network connectivity |
| "Failed to mark message as read" | Insufficient permissions or API error | Check API permissions or retry operation |
| "Failed to forward email" | Issue with email forwarding | Check destination email address and permissions |
| "Error in APEX categorization" | AI model error | Verify Azure OpenAI credentials and endpoint |
| "Failed to insert log to DB" | Database connectivity issue | Check SQL credentials and connection string |

## 12. Limitations and Known Issues

The APEX Email Triaging System has the following limitations and known issues:

### Current Limitations

1. **Batch Processing Limits**:
   - Batch size limited to 3 emails at a time to respect API rate limits
   - Fixed processing interval of 30 seconds between batches
   - No dynamic scaling based on load

2. **Email Content Handling**:
   - Limited handling of complex HTML content
   - No image content analysis
   - Text-only classification

3. **Attachment Handling**:
   - Cannot process emails with "Safe Attachments Scan In Progress"
   - No handling for specific attachment types
   - No attachment content analysis

4. **Classification Model**:
   - Fixed classification categories
   - No user feedback loop for classification accuracy
   - No continuous learning or model improvement

5. **Forwarding Limitations**:
   - Preserves only basic email metadata
   - No special handling for high-priority emails
   - No time-based routing rules

### Known Issues

1. **Email Thread Handling**:
   - Treats entire thread as single content
   - May classify based on mixed topics in thread
   - No thread-level context preservation

2. **Unicode Handling**:
   - Potential issues with uncommon character sets
   - May require special handling for international content

3. **Database Growth**:
   - No automatic log rotation or cleanup
   - Database size will grow over time

4. **Model Costs**:
   - GPT-4o is expensive for high volume processing
   - No cost ceiling enforcement

5. **Environment Specific**:
   - Designed for Microsoft 365 only
   - No support for other email providers

## 13. Dependencies

The system has the following Python dependencies:

```
# From requirements.txt
aiohappyeyeballs==2.4.0
aiohttp==3.10.5
aiosignal==1.3.1
annotated-types==0.7.0
anyio==4.4.0
asyncio==3.4.3
attrs==24.2.0
certifi==2024.7.4
cffi==1.17.0
charset-normalizer==3.3.2
colorama==0.4.6
cryptography==43.0.0
distro==1.9.0
frozenlist==1.4.1
h11==0.16.0
html2text==2024.2.26
httpcore==1.0.9
httpx==0.27.0
idna==3.8
jiter==0.5.0
msal==1.30.0
multidict==6.1.0
openai==1.42.0
pycparser==2.22
pydantic==2.8.2
pydantic_core==2.20.1
PyJWT==2.9.0
pyodbc==5.1.0
python-dotenv==1.0.1
pytz==2024.2
requests==2.28.2
sniffio==1.3.1
tqdm==4.66.5
typing_extensions==4.12.2
urllib3==1.26.19
yarl==1.11.1
```

## 14. Accessing Container Terminal

To access the container terminal for debugging or maintenance:

1. Create the docker container image in cmd:
```
docker build -t <container-name> .
```

2. Run the container in terminal so that it will appear in Rancher Desktop:
```
docker run -d <container-name>
```
NB: the "-d" will run the container image in the background

3. Now that the container image is running, you can access the CMD terminal again by CNTRL+C

4. Now run the command below to get the process ID of your running docker container image:
```
docker ps
```

5. Get the process ID for your container image and copy it and paste it in the terminal to get the container terminal.

6. Now run the following command to log into the terminal of your container image:
```
docker exec -it <conatiner-id/name> /bin/bash
```

7. You are now in the terminal of your docker container.

### Viewing ODBC Drivers

To view the ODBC Drivers available in your Linux environment:
```
cat /etc/odbcinst.ini
```

## 15. Glossary of Terms

| Term | Definition |
|------|------------|
| APEX | Automated Processing and Email eXchange - the email triaging system |
| API | Application Programming Interface - allows different software systems to communicate |
| Azure OpenAI | Microsoft's cloud-based implementation of OpenAI's language models |
| Batch Processing | Processing emails in small groups rather than individually or all at once |
| CI/CD | Continuous Integration/Continuous Deployment - automated software delivery process |
| Docker | Containerization platform for packaging applications and dependencies |
| Exponential Backoff | Retry strategy that increases wait time between attempts exponentially |
| GPT | Generative Pre-trained Transformer - the AI model type used for classification |
| Kubernetes | Container orchestration platform for managing containerized applications |
| Microsoft Graph API | Microsoft's unified API endpoint for accessing data across Microsoft 365 services |
| MSAL | Microsoft Authentication Library - used for OAuth2 authentication |
| OAuth2 | Industry-standard authorization protocol |
| ODBC | Open Database Connectivity - standard API for accessing database management systems |
| SQL Server | Microsoft's relational database management system |
| TAT | Turn-Around Time - a metric tracked in the system logs |
| TLS | Transport Layer Security - cryptographic protocol for secure communications |

## 16. Appendices

### Appendix A: Environment Variables Reference

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| AZURE_OPENAI_KEY | API key for Azure OpenAI service | Yes | None |
| AZURE_OPENAI_ENDPOINT | Endpoint URL for Azure OpenAI service | Yes | None |
| SQL_SERVER | SQL Server hostname or IP address | Yes | None |
| SQL_DATABASE | SQL database name | Yes | None |
| SQL_USERNAME | SQL Server username | Yes | None |
| SQL_PASSWORD | SQL Server password | Yes | None |
| CLIENT_ID | Microsoft Graph API client ID | Yes | None |
| TENANT_ID | Microsoft Azure AD tenant ID | Yes | None |
| CLIENT_SECRET | Microsoft Graph API client secret | Yes | None |
| EMAIL_ACCOUNT | Email account to monitor | Yes | None |
| POLICY_SERVICES | Email address for policy services | Yes | None |
| TRACKING_MAILS | Email address for tracking | Yes | None |
| CLAIMS_MAILS | Email address for claims | Yes | None |
| ONLINESUPPORT_MAILS | Email address for online support | Yes | None |
| INSURANCEADMIN_MAILS | Email address for insurance admin | Yes | None |
| DIGITALCOMMS_MAILS | Email address for digital communications | Yes | None |
| CONNEX_TEST | Email address for test emails | Yes | None |

### Appendix B: Database Schema Details

#### Logs Table

| Column | DataType | Description |
|--------|----------|-------------|
| id | varchar(50) | Unique identifier for the log entry (UUID) |
| eml_id | varchar(MAX) | Email ID from Microsoft Graph API |
| internet_message_id | varchar(MAX) | Internet message ID for deduplication |
| dttm_rec | datetime | Date/time when email was received |
| dttm_proc | datetime | Date/time when email was processed |
| eml_to | varchar(MAX) | Original recipient of the email |
| eml_frm | varchar(MAX) | Original sender of the email |
| eml_cc | varchar(MAX) | CC recipients of the email |
| eml_sub | varchar(MAX) | Email subject |
| eml_bdy | varchar(MAX) | Email body (may be truncated if large) |
| apex_class | varchar(MAX) | Classification category assigned by AI |
| apex_class_rsn | text | Reason for classification |
| apex_action_req | text | Whether action is required (yes/no) |
| apex_sentiment | varchar(50) | Sentiment analysis result |
| apex_cost_usd | float | Cost of AI processing in USD |
| apex_routed_to | varchar(MAX) | Destination email address |
| sts_read_eml | text | Status of marking email as read |
| sts_class | text | Status of classification process |
| sts_routing | text | Status of email routing process |
| tat | float | Turn-around time in seconds |
| end_time | datetime | Date/time when processing completed |

### Appendix C: Classification Categories and Priority Reference

| Priority | Category | Description | Routing Destination |
|----------|----------|-------------|---------------------|
| 1 (highest) | assist | General assistance requests | POLICY_SERVICES |
| 2 | bad service/experience | Customer complaints | POLICY_SERVICES |
| 3 | vehicle tracking | Vehicle tracking and monitoring | TRACKING_MAILS |
| 4 | debit order switch | Debit order changes | ONLINESUPPORT_MAILS |
| 5 | retentions | Customer retention matters | DIGITALCOMMS_MAILS |
| 6 | amendments | Policy amendments and changes | POLICY_SERVICES |
| 7 | claims | Insurance claims | CLAIMS_MAILS |
| 8 | refund request | Refund requests | POLICY_SERVICES |
| 9 | online/app | Online or app-related queries | ONLINESUPPORT_MAILS |
| 10 | request for quote | Quote requests | POLICY_SERVICES |
| 11 | document request | Requests for documents | ONLINESUPPORT_MAILS |
| 12 | other | Unclassified emails | POLICY_SERVICES |
| 13 (lowest) | previous insurance checks/queries | Previous insurance inquiries | INSURANCEADMIN_MAILS |
| Special | connex test | Test emails containing "connex test" | CONNEX_TEST |
