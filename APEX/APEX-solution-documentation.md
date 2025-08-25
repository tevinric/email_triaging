# APEX Email Triaging Solution - Technical Solutions Documentation

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-01-25 | Solutions Team | Initial documentation |

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Solution Overview](#2-solution-overview)
3. [Solution Architecture](#3-solution-architecture)
4. [Solution Components](#4-solution-components)
5. [Data Models and Database Schema](#5-data-models-and-database-schema)
6. [Email Processing Workflow](#6-email-processing-workflow)
7. [AI Classification Engine](#7-ai-classification-engine)
8. [Routing Rules and Business Logic](#8-routing-rules-and-business-logic)
9. [Configuration Management](#9-configuration-management)
10. [Security Considerations](#10-security-considerations)
11. [Error Handling and Recovery](#11-error-handling-and-recovery)
12. [Performance and Scalability](#12-performance-and-scalability)
13. [Monitoring and Logging](#13-monitoring-and-logging)
14. [Deployment and Operations](#14-deployment-and-operations)
15. [Appendices](#15-appendices)

---

## 1. Executive Summary

APEX (Automated Processing and Email eXtraction) is an AI-powered email triaging solution designed for a South African insurance company. The system uses Azure OpenAI services to automatically classify, route, and respond to customer emails.

### Key Capabilities
- Automated email classification using Azure OpenAI GPT models
- Automated routing to appropriate departments
- Automatic response generation for common inquiries
- Duplicate email detection and prevention
- Comprehensive audit logging and monitoring
- Multi-environment support (DEV, SIT, UAT, PREPROD, PROD)

### Business Benefits
- [ASSUMPTION] Reduced email processing time from minutes to seconds
- [ASSUMPTION] Improved accuracy in email routing
- 24/7 automated processing capability
- [ASSUMPTION] Enhanced customer experience through faster responses
- Detailed analytics and reporting capabilities

---

## 2. Solution Overview

### 2.1 Objectives

The APEX solution is designed to achieve the following objectives:

1. **Automated Email Processing**: Eliminate manual email sorting and routing
2. **AI Classification**: Use AI to categorize email content and determine intent
3. **Automated Routing**: Direct emails to the appropriate department based on classification
4. **Auto-Response**: Provide immediate acknowledgment to customers
5. **Audit Trail**: Maintain comprehensive logs for compliance and analysis
6. **Scalability**: [ASSUMPTION] Handle increasing email volumes without performance degradation

### 2.2 System Boundaries

**In Scope:**
- Email retrieval from Microsoft Exchange via Graph API
- AI-powered email classification
- Automated routing to predefined departments
- Auto-response generation
- Logging and monitoring
- Error handling and recovery

**Out of Scope:**
- Email composition by agents
- Direct manipulation of customer accounts
- Processing of attachments beyond forwarding
- Real-time chat or voice interactions

### 2.3 Key Stakeholders

- **End Users**: Customer service agents receiving routed emails
- **Customers**: Individuals sending emails to the insurance company
- **System Administrators**: IT personnel managing the APEX system
- **Business Analysts**: Personnel analyzing email patterns and system performance
- **Compliance Officers**: Ensuring system meets regulatory requirements

---

## 3. Solution Architecture

### 3.1 High-Level Architecture

The APEX solution follows a microservices architecture pattern with the following key architectural principles:

```
┌─────────────────────────────────────────────────────────────┐
│                     Email Sources                            │
│              (Microsoft Exchange/Outlook)                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  Microsoft Graph API                         │
│                 (Email Retrieval Layer)                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    APEX Core Engine                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Main Processing Loop                     │   │
│  │         (Async Batch Processing Engine)              │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           Email Processing Pipeline                   │   │
│  │  • Duplicate Detection                               │   │
│  │  • Content Extraction                                │   │
│  │  • AI Classification                                 │   │
│  │  • Routing Decision                                  │   │
│  │  • Auto-response Generation                          │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────────────┘
                       │
           ┌───────────┼───────────┬──────────────┐
           ▼           ▼           ▼              ▼
┌──────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│Azure OpenAI  │ │SQL Server│ │Azure Blob│ │Email     │
│(GPT Models)  │ │Database  │ │Storage   │ │Services  │
└──────────────┘ └──────────┘ └──────────┘ └──────────┘
```

### 3.2 Component Architecture

The solution consists of the following architectural layers:

1. **Presentation Layer**: Not applicable (headless service)
2. **Integration Layer**: Microsoft Graph API integration
3. **Processing Layer**: Core APEX engine with async processing
4. **AI Layer**: Azure OpenAI integration for classification
5. **Data Layer**: SQL Server for persistence
6. **Infrastructure Layer**: Azure cloud services

### 3.3 Deployment Architecture

The system is containerized using Docker and deployed on Azure infrastructure:

- **Container Platform**: Docker
- **Orchestration**: Azure Container Instances/AKS
- **Database**: Azure SQL Database
- **Storage**: Azure Blob Storage
- **AI Services**: Azure OpenAI Service
- **Monitoring**: Azure Monitor and Application Insights

---

## 4. Solution Components

### 4.1 Core Processing Engine (main.py)

**Purpose**: Orchestrates the entire email processing workflow

**Key Functions**:
- `trigger_email_triage()`: Entry point for the application
- `main()`: Main processing loop that runs continuously
- `process_batch()`: Processes batches of unread emails
- `process_email()`: Processes individual emails through the pipeline
- `retry_unread_emails()`: Handles retry logic for failed operations

**Inputs**:
- Command line argument: 'start' to initiate processing
- Environment variables for configuration

**Outputs**:
- Processed and routed emails
- Log entries in database
- System logs to console

**Processing Logic**:
1. Fetches unread emails every 30 seconds
2. Processes up to 3 emails in parallel (MS Graph API limit)
3. Implements retry logic with exponential backoff
4. Maintains a retry queue for emails that couldn't be marked as read

### 4.2 Email Client Module (email_processor/email_client.py)

**Purpose**: Handles all interactions with Microsoft Graph API for email operations

**Key Functions**:
- `get_access_token()`: Obtains OAuth token for API access
- `fetch_unread_emails()`: Retrieves unread emails from mailbox
- `mark_email_as_read()`: Marks processed emails as read
- `forward_email()`: Forwards emails to designated recipients
- `send_email()`: Sends new emails (used for auto-responses)

**Authentication**:
- Uses MSAL (Microsoft Authentication Library)
- Implements OAuth 2.0 client credentials flow
- Token caching for performance

**Error Handling**:
- Retry logic with exponential backoff
- Graceful degradation on API failures
- Comprehensive error logging

### 4.3 AI Classification Module (apex_llm/apex.py)

**Purpose**: Implements AI-powered email classification using Azure OpenAI

**Key Components**:

#### 4.3.1 Primary Classification (`apex_categorise`)
- Uses GPT-4o model for comprehensive analysis
- Classifies emails into predefined categories
- Determines action requirements
- Analyzes sentiment
- Implements multi-agent validation

#### 4.3.2 Action Check Agent (`apex_action_check`)
- Uses GPT-4o-mini for efficiency
- Validates if action is required
- Focuses on latest email in thread
- Provides secondary validation

#### 4.3.3 Prioritization Agent (`apex_prioritize`)
- Determines final category from multiple possibilities
- Implements business rules and overrides
- Handles complaint detection
- Manages cancellation+refund scenarios

**Classification Categories**: See detailed definitions in Section 7.2 AI Classification Engine

**AI Model Configuration**:
- Primary endpoint with automatic failover to backup
- Token usage tracking and cost calculation
- Temperature settings for consistency
- JSON response format enforcement

### 4.4 Routing Module (apex_llm/apex_routing.py)

**Purpose**: Maps email classifications to destination email addresses

**Routing Table**:
```python
{
    "amendments": POLICY_SERVICES,
    "assist": POLICY_SERVICES,
    "vehicle tracking": TRACKING_MAILS,
    "bad service/experience": POLICY_SERVICES,
    "claims": CLAIMS_MAILS,
    "refund request": POLICY_SERVICES,
    "document request": ONLINESUPPORT_MAILS,
    "online/app": ONLINESUPPORT_MAILS,
    "retentions": DIGITALCOMMS_MAILS,
    "request for quote": POLICY_SERVICES,
    "previous insurance checks/queries": INSURANCEADMIN_MAILS,
    "other": POLICY_SERVICES
}
```

### 4.5 Auto-Response Module (apex_llm/autoresponse.py)

**Purpose**: Generates and sends automatic responses to customers

**Key Features**:
- Loop prevention mechanisms
- Template-based responses
- Environment-specific email mappings
- Azure Blob Storage integration for templates
- Comprehensive skip conditions

**Loop Prevention Checks**:
1. Empty sender validation
2. Direct email to consolidation bin detection
3. Self-initiated loop prevention
4. Microsoft Exchange system detection
5. System address pattern matching
6. Bounce message detection
7. Auto-reply chain detection

### 4.6 Logging Module (apex_llm/apex_logging.py)

**Purpose**: Comprehensive logging and audit trail management

**Key Functions**:
- `create_log()`: Initializes log entry for email
- `log_apex_success()`: Records successful classification
- `log_apex_fail()`: Records classification failures
- `insert_log_to_db()`: Persists logs to database
- `check_email_processed()`: Duplicate detection
- `log_skipped_email()`: Records skipped emails
- `insert_system_log_to_db()`: System-level logging

**Logging Levels**:
1. **Application Logs**: Processing details and errors
2. **Audit Logs**: Complete email processing trail
3. **System Logs**: Infrastructure and performance metrics
4. **Skipped Email Logs**: Emails not processed with reasons

---

## 5. Data Models and Database Schema

### 5.1 Main Logs Table (logs)

```sql
CREATE TABLE logs(
    id VARCHAR(50),                    -- Unique identifier (UUID)
    eml_id VARCHAR(MAX),               -- Email ID
    internet_message_id VARCHAR(MAX),   -- RFC Internet Message ID
    dttm_rec DATETIME,                 -- Receipt timestamp
    dttm_proc DATETIME,                -- Processing timestamp
    eml_to VARCHAR(MAX),               -- Recipient address
    eml_frm VARCHAR(MAX),              -- Sender address
    eml_cc VARCHAR(MAX),               -- CC recipients
    eml_sub VARCHAR(MAX),              -- Subject line
    eml_bdy VARCHAR(MAX),              -- Email body
    apex_class VARCHAR(50),            -- Classification result
    apex_class_rsn TEXT,               -- Classification reason
    apex_action_req TEXT,              -- Action required flag
    apex_sentiment VARCHAR(50),        -- Sentiment analysis
    apex_cost_usd FLOAT,               -- AI processing cost
    apex_routed_to VARCHAR(MAX),       -- Routing destination
    sts_read_eml TEXT,                 -- Read status
    sts_class TEXT,                    -- Classification status
    sts_routing TEXT,                  -- Routing status
    tat FLOAT,                         -- Turn-around time
    end_time DATETIME,                 -- Completion timestamp
    apex_intervention TEXT,            -- AI intervention flag
    apex_top_categories VARCHAR(MAX),  -- Top 3 categories
    region_used VARCHAR(10),           -- AI region used
    gpt_4o_prompt_tokens INT,          -- GPT-4o prompt tokens
    gpt_4o_completion_tokens INT,      -- GPT-4o completion tokens
    gpt_4o_total_tokens INT,          -- GPT-4o total tokens
    gpt_4o_cached_tokens INT,         -- GPT-4o cached tokens
    gpt_4o_mini_prompt_tokens INT,    -- GPT-4o-mini prompt tokens
    gpt_4o_mini_completion_tokens INT, -- GPT-4o-mini completion
    gpt_4o_mini_total_tokens INT,     -- GPT-4o-mini total
    gpt_4o_mini_cached_tokens INT,    -- GPT-4o-mini cached
    auto_response_sent VARCHAR(50)    -- Auto-response status
);
```

### 5.2 Skipped Emails Table (skipped_mails)

```sql
CREATE TABLE skipped_mails (
    id varchar(50) NOT NULL,
    eml_id varchar(MAX),
    internet_message_id varchar(900),
    dttm_rec datetime,
    dttm_proc datetime,
    eml_frm varchar(MAX),
    eml_to varchar(MAX),
    eml_cc varchar(MAX),
    eml_subject varchar(MAX),
    eml_body varchar(MAX),
    rsn_skipped varchar(MAX) NOT NULL,
    created_timestamp datetime DEFAULT GETDATE(),
    processing_time_seconds float DEFAULT 0.0,
    account_processed varchar(500),
    skip_type varchar(100) DEFAULT 'DUPLICATE'
);
```

### 5.3 System Logs Table (system_logs)

```sql
CREATE TABLE system_logs (
    id VARCHAR(50) PRIMARY KEY,
    email_id VARCHAR(MAX),
    internet_message_id VARCHAR(MAX),
    timestamp DATETIME DEFAULT GETDATE(),
    log_level VARCHAR(20),
    component VARCHAR(100),
    message TEXT,
    details TEXT,
    autoresponse_attempted BIT,
    autoresponse_successful BIT,
    autoresponse_skip_reason VARCHAR(MAX),
    autoresponse_recipient VARCHAR(500),
    autoresponse_error TEXT
);
```

### 5.4 Model Costs Table (model_costs)

```sql
CREATE TABLE model_costs (
    id INT IDENTITY(1,1) PRIMARY KEY,
    model_name VARCHAR(50),
    prompt_token_cost_pm FLOAT,
    completion_token_cost_pm FLOAT,
    cached_token_cost_pm FLOAT,
    effective_date DATETIME,
    currency VARCHAR(10) DEFAULT 'USD'
);
```

---

## 6. Email Processing Workflow

### 6.1 Main Processing Flow

```
1. START
   │
   ├─► Initialize System
   │   └─► Load Configuration
   │   └─► Establish Database Connection
   │   └─► Initialize AI Clients
   │
   ├─► Main Processing Loop (Every 30 seconds)
   │   │
   │   ├─► Get Access Token
   │   │   └─► OAuth Authentication with Microsoft
   │   │
   │   ├─► For Each Email Account
   │   │   │
   │   │   ├─► Fetch Unread Emails
   │   │   │   └─► Microsoft Graph API Call
   │   │   │
   │   │   └─► Process Email Batch (3 parallel)
   │       │
   │       └─► For Each Email (Async)
   │           │
   │           ├─► Check Duplicate
   │           │   ├─► YES → Mark as Read → Log Skip → END
   │           │   └─► NO → Continue
   │           │
   │           ├─► Check Exchange Patterns
   │           │   ├─► YES → Mark as Read → Log Skip → END
   │           │   └─► NO → Continue
   │           │
   │           ├─► Start Auto-Response (Async)
   │           │
   │           ├─► Extract Content
   │           │   └─► Prepare for AI Processing
   │           │
   │           ├─► AI Classification
   │           │   ├─► Primary Classification (GPT-4o)
   │           │   ├─► Action Check (GPT-4o-mini)
   │           │   └─► Prioritization (GPT-4o-mini)
   │           │
   │           ├─► Determine Routing
   │           │   └─► Map Category to Department
   │           │
   │           ├─► Forward Email
   │           │   ├─► Success → Continue
   │           │   └─► Failure → Fallback Routing
   │           │
   │           ├─► Mark as Read
   │           │   ├─► Success → Continue
   │           │   └─► Failure → Add to Retry Queue
   │           │
   │           └─► Log Processing
   │               ├─► Audit Log
   │               └─► System Log
   │
   └─► Retry Failed Operations
       └─► Process Retry Queue
```

### 6.2 Email Classification Process

The classification process involves three AI agents working in sequence:

#### Stage 1: Primary Classification
- Analyzes complete email content
- Returns top 3 possible categories
- Determines action requirement
- Performs sentiment analysis

#### Stage 2: Action Validation
- Focuses on latest email in thread
- Validates action requirement
- Overrides primary classification if needed

#### Stage 3: Category Prioritization
- Applies business rules
- Checks for complaint indicators
- Handles special cases (cancellation+refund)
- Determines final single category

### 6.3 Routing Decision Logic

```
IF classification == "bad service/experience" THEN
    route_to = POLICY_SERVICES (Priority handling)
ELSE IF classification == "vehicle tracking" THEN
    route_to = TRACKING_MAILS
ELSE IF classification == "claims" THEN
    route_to = CLAIMS_MAILS
ELSE IF classification == "retentions" THEN
    route_to = DIGITALCOMMS_MAILS
ELSE IF classification in routing_table THEN
    route_to = routing_table[classification]
ELSE
    route_to = original_destination (No intervention)
```

### 6.4 Auto-Response Flow

```
1. Check Skip Conditions
   ├─► Is sender empty? → Skip
   ├─► Is recipient consolidation bin? → Skip
   ├─► Is sender system address? → Skip
   ├─► Is this a bounce message? → Skip
   └─► All checks pass → Continue

2. Determine Template
   ├─► Map recipient to folder
   └─► Fetch template from Azure Blob

3. Generate Response
   ├─► Merge template with email data
   └─► Add tracking headers

4. Send Response
   ├─► Use Graph API to send
   └─► Log response status
```

---

## 7. AI Classification Engine

### 7.1 Multi-Agent Architecture

The APEX system employs a three-agent AI architecture for email analysis:

#### 7.1.1 Primary Classification Agent (`apex_categorise`)
- **Model**: GPT-4o
- **Temperature**: 0.2 (balanced consistency)
- **Purpose**: Comprehensive email analysis and initial classification
- **Response Format**: JSON
- **Context Window**: 128k tokens
- **Output**: Top 3 possible categories, sentiment analysis, action requirement, classification reasoning

#### 7.1.2 Action Validation Agent (`apex_action_check`) 
- **Model**: GPT-4o-mini
- **Temperature**: 0.1 (high consistency)
- **Purpose**: Validates if action is required based on latest email in thread
- **Focus**: Latest email content only (ignores previous messages)
- **Output**: Binary action requirement (yes/no)
- **Function**: Provides secondary validation and overrides primary classification when needed

#### 7.1.3 Category Prioritization Agent (`apex_prioritize`)
- **Model**: GPT-4o-mini 
- **Temperature**: 0.1 (high consistency)
- **Purpose**: Determines final single category from multiple possibilities
- **Business Rules**: Implements complaint detection, cancellation+refund logic, primary purpose analysis
- **Output**: Final single category with reasoning

### 7.2 Classification Categories and Definitions

The system classifies emails into the following 12 categories:

#### 7.2.1 Priority Categories

**1. bad service/experience** (Highest Priority)
- **Definition**: Complaints and negative feedback about company services/products
- **Indicators**: "poorly done", "disappointed", "frustrated", "terrible experience", "unacceptable"
- **Business Logic**: Takes precedence over all other categories when complaint language is detected
- **Examples**: 
  - "The tracking device installation was poorly done" → bad service/experience (not vehicle tracking)
  - "Your claims process is terrible" → bad service/experience (not claims)
- **Action Required**: Always yes
- **Routing**: Policy Services (priority handling)

**2. vehicle tracking**
- **Definition**: Vehicle tracker certificate submissions and fitment documentation
- **Purpose**: Capture and verify vehicle tracking device certificates
- **Examples**:
  - "Attached is my tracking certificate. Please confirm receipt."
  - "Here is the fitment certificate for my vehicle tracker."
- **Action Required**: Always yes
- **Routing**: Tracking Team

**3. retentions**
- **Definition**: Policy cancellations/terminations, including cancellation+refund combinations
- **Critical Business Rule**: When email mentions BOTH cancellation AND refund, always classify as retentions
- **Logic**: Cancellation must be processed before refund can occur
- **Examples**:
  - "I want to cancel my policy and get a refund" → retentions (not refund request)
  - "Please terminate my policy due to errors and process refund" → retentions
- **Routing**: Digital Communications

**4. assist**
- **Definition**: Roadside assistance, towing, home emergencies
- **Services**: 24/7 roadside support, locksmith, plumber, electrician, glazier
- **Priority**: Highest in routing hierarchy (emergency services)
- **Examples**: Flat tires, dead batteries, locked keys, home emergencies
- **Routing**: Policy Services

#### 7.2.2 Standard Business Categories

**5. claims**
- **Definition**: Insurance claim submissions and follow-ups on existing claims
- **Includes**: New claim registrations, claim status inquiries, claim form submissions
- **Excludes**: Claims history requests (classify as "document request")
- **Note**: If complaint about claims handling detected, classify as "bad service/experience"
- **Routing**: Claims Department

**6. amendments**
- **Definition**: Policy changes, additions, removals of risk items or policy details
- **Includes**: Address changes, contact details, banking details, vehicle additions/removals, building changes, contents updates
- **Document Submission**: If customer submitting amendment documents (ID, proof of address), classify as amendments
- **Routing**: Policy Services

**7. refund request**
- **Definition**: Refund requests WITHOUT policy cancellation
- **Important**: Only for pure refund requests (overpayments, duplicate payments)
- **Excludes**: Any email mentioning both cancellation and refund (classify as "retentions")
- **Examples**: "Refund my duplicate premium payment", "I need a refund for overpayment"
- **Routing**: Policy Services

**8. document request**
- **Definition**: Customer requesting documents TO BE SENT to them
- **Direction**: Customer wants to RECEIVE documents from company
- **Examples**: Policy schedules, tax certificates, claims history, cross-border letters
- **Contrast**: If customer is SUBMITTING documents, classify by business purpose
- **Routing**: Online Support

**9. online/app**
- **Definition**: System errors, website/application issues
- **Excludes**: Payment-related system errors (classify as "amendments")
- **Focus**: Technical system functionality problems
- **Routing**: Online Support

**10. request for quote**
- **Definition**: New insurance quotations (no existing policy reference)
- **Requirement**: No evidence of existing policy
- **Contrast**: Adding items to existing policy is "amendments"
- **Routing**: Policy Services

**11. previous insurance checks/queries**
- **Definition**: Previous Insurance (PI) verification requests
- **Purpose**: Validate previous insurance history
- **Routing**: Insurance Admin

**12. other**
- **Definition**: Pure administrative follow-up with no specific business action
- **Usage**: Only when email cannot fit other categories AND primary purpose is administrative
- **Examples**: "Did you receive documents I sent yesterday?", "No confirmation after uploading"
- **Important**: Do NOT use if customer is actively performing business actions
- **Routing**: Policy Services

### 7.3 Prompting Technique and Architecture

#### 7.3.1 Primary Classification Prompt Structure

The primary classification prompt follows a multi-component structure:

**1. Role Definition**
```
"You are an email classification assistant tasked with analysing email content and performing the list of defined tasks for a South African insurance company."
```

**2. Critical Priority Rules (Hierarchical Order)**
- Complaint Detection Override
- Cancellation + Refund Business Rule  
- Document Direction Rule
- Primary Purpose Analysis

**3. Category Definitions Section**
- Detailed description of each category
- Specific examples and counter-examples
- Business logic and routing rationale

**4. Classification Instructions**
- Return top 3 possible categories in priority order
- Provide single-sentence reasoning
- Determine action requirement
- Analyze sentiment (Positive/Neutral/Negative)

**5. JSON Output Format Specification**
```json
{
  "classification": ["primary_category", "secondary_category", "tertiary_category"],
  "rsn_classification": "explanation",
  "action_required": "yes/no",
  "sentiment": "Positive/Neutral/Negative"
}
```

#### 7.3.2 Action Check Prompt Structure

The action validation agent uses a focused prompt design:

**Focus**: Latest email in thread only
**Task**: Determine if action/response is required
**Logic**: 
- Identify latest email (typically first/least indented)
- Check for questions, requests, tasks, issues
- Ignore previous messages in thread
- Return binary yes/no decision

**Output Format**:
```json
{"action_required": "yes"} or {"action_required": "no"}
```

#### 7.3.3 Prioritization Prompt Structure

The category prioritization agent implements business rule hierarchy:

**Step 1**: Complaint Detection Override
**Step 2**: Cancellation + Refund Business Rule
**Step 3**: Primary Purpose Analysis  
**Step 4**: Document Direction Check
**Step 5**: Category Priority List Evaluation

**Priority Hierarchy** (when multiple categories apply):
1. assist (emergency services)
2. bad service/experience  
3. vehicle tracking
4. retentions
5. amendments
6. claims
7. refund request
8. online/app
9. request for quote
10. document request
11. other
12. previous insurance checks/queries

### 7.4 Category Determination Hierarchy

The system follows a strict hierarchical decision tree:

```
1. COMPLAINT DETECTION (Override All)
   ├─► Contains complaint language? 
   │   ├─► YES → "bad service/experience" (regardless of topic)
   │   └─► NO → Continue to Step 2
   │
2. BUSINESS RULE CHECK
   ├─► Contains both cancellation AND refund?
   │   ├─► YES → "retentions" 
   │   └─► NO → Continue to Step 3
   │
3. PRIMARY PURPOSE ANALYSIS  
   ├─► What is customer actively DOING?
   │   ├─► Submitting tracking cert → "vehicle tracking"
   │   ├─► Submitting claim forms → "claims"
   │   ├─► Submitting amendment docs → "amendments"
   │   ├─► Pure admin follow-up → "other"
   │   └─► Continue to Step 4
   │
4. DOCUMENT DIRECTION CHECK
   ├─► Customer wants to RECEIVE docs → "document request"
   ├─► Customer is SUBMITTING docs → classify by business purpose
   └─► Continue to Step 5
   │
5. CATEGORY EVALUATION
   ├─► Use primary category from initial classification
   ├─► If ambiguous, apply priority hierarchy
   └─► Return final single category
```

### 7.5 Output Format and Structure

The system produces structured JSON responses with comprehensive metadata:

**Primary Classification Output**:
```json
{
  "classification": ["primary", "secondary", "tertiary"],
  "rsn_classification": "reasoning",
  "action_required": "yes/no",
  "sentiment": "Positive/Neutral/Negative",
  "apex_cost_usd": 0.00123,
  "region_used": "main/backup",
  "top_categories": ["stored_before_prioritization"],
  "gpt_4o_prompt_tokens": 1500,
  "gpt_4o_completion_tokens": 150,
  "gpt_4o_mini_prompt_tokens": 200,
  "gpt_4o_mini_completion_tokens": 50
}
```

### 7.6 Cost Optimization and Token Management

**Token Tracking**: Comprehensive usage tracking across all models:
- GPT-4o: Prompt tokens, completion tokens, cached tokens
- GPT-4o-mini: Prompt tokens, completion tokens, cached tokens
- Cost calculation: Per-million token pricing with exchange rate conversion

**Optimization Strategies**:
- Strategic model selection (GPT-4o for complex analysis, GPT-4o-mini for validation)
- Text cleaning and escaping to reduce token count
- Structured prompt design to maximize efficiency
- Caching capabilities for repeated patterns

### 7.7 Failover Strategy and Reliability

**Dual-Endpoint Architecture**:
1. Primary Azure OpenAI endpoint with fallback capability
2. Backup endpoint with automatic initialization
3. Seamless failover with continued processing
4. Region tracking for monitoring and cost analysis

**Failover Process**:
```
Primary Endpoint Failure
    │
    ├─► Initialize Backup Client (if not already done)
    │
    ├─► Retry with Backup Endpoint
    │   ├─► Success → Continue with backup (track region)
    │   └─► Failure → Raise exception, fallback to original routing
    │
    └─► Log all endpoint failures for monitoring
```

**Error Handling**:
- JSON parsing validation with detailed error logging
- Token usage tracking even during failures
- Comprehensive logging with subject line context
- Graceful degradation to original email routing

---

## 8. Routing Rules and Business Logic

### 8.1 Business Rules

1. **Complaint Override Rule**
   - Any email with complaint language → "bad service/experience"
   - Overrides all other classifications
   - Priority routing to Policy Services

2. **Cancellation + Refund Rule**
   - Both cancellation AND refund mentioned → "retentions"
   - Business requirement: cancellation before refund
   - Routes to Digital Communications

3. **Document Direction Rule**
   - Customer requesting documents → "document request"
   - Customer submitting documents → classify by purpose
   - Administrative follow-up → "other"

4. **Primary Purpose Rule**
   - Focus on main business action
   - Ignore courtesy confirmation requests
   - Classify by what customer is doing, not asking

### 8.2 Routing Priority

| Priority | Category | Department |
|----------|----------|------------|
| 1 | bad service/experience | Policy Services |
| 2 | assist | Policy Services |
| 3 | vehicle tracking | Tracking Team |
| 4 | retentions | Digital Comms |
| 5 | claims | Claims Department |
| 6 | amendments | Policy Services |
| 7 | refund request | Policy Services |
| 8 | online/app | Online Support |
| 9 | document request | Online Support |
| 10 | request for quote | Policy Services |
| 11 | previous insurance | Insurance Admin |
| 12 | other | Policy Services |

### 8.3 Intervention Logic

The system tracks when AI changes the original routing:

```python
if original_destination != final_destination:
    apex_intervention = "true"
    log_intervention_details()
else:
    apex_intervention = "false"
```

---

## 9. Configuration Management

### 9.1 Environment Variables

**Azure OpenAI Configuration**:
- `AZURE_OPENAI_KEY`: Primary API key
- `AZURE_OPENAI_ENDPOINT`: Primary endpoint URL
- `AZURE_OPENAI_BACKUP_KEY`: Backup API key
- `AZURE_OPENAI_BACKUP_ENDPOINT`: Backup endpoint URL

**Database Configuration**:
- `SQL_SERVER`: Database server address
- `SQL_DATABASE`: Database name
- `SQL_USERNAME`: Database username
- `SQL_PASSWORD`: Database password [PLACEHOLDER]

**Microsoft Graph Configuration**:
- `CLIENT_ID`: Azure AD application ID
- `TENANT_ID`: Azure AD tenant ID
- `CLIENT_SECRET`: Application secret [PLACEHOLDER]

**Email Configuration**:
- `EMAIL_ACCOUNT`: Primary processing account
- `POLICY_SERVICES`: Policy services email
- `TRACKING_MAILS`: Tracking department email
- `CLAIMS_MAILS`: Claims department email
- `ONLINESUPPORT_MAILS`: Online support email
- `DIGITALCOMMS_MAILS`: Digital communications email

**Azure Storage Configuration**:
- `AZURE_STORAGE_CONNECTION_STRING`: Storage connection [PLACEHOLDER]
- `BLOB_CONTAINER_NAME`: Container for templates
- `AZURE_STORAGE_PUBLIC_URL`: Public blob URL

### 9.2 Environment-Specific Settings

The system supports multiple environments:

```python
ENV_TYPE = os.environ.get('ENV_TYPE')
# Values: DEV, SIT, UAT, PREPROD, PROD
```

Each environment has specific:
- Email account mappings
- Template folder structures
- Database connections
- Processing intervals

### 9.3 Processing Configuration

**Performance Settings**:
- `EMAIL_FETCH_INTERVAL`: 30 seconds
- `BATCH_SIZE`: 3 emails (MS Graph limit)
- `MAX_RETRIES`: 3 attempts
- `BACKOFF_MULTIPLIER`: 2x exponential

---

## 10. Security Considerations

### 10.1 Authentication and Authorization

**Service Authentication**:
- OAuth 2.0 client credentials flow
- Service principal with minimal required permissions
- Token refresh handled automatically
- No user credentials stored

**API Security**:
- TLS 1.2+ for all communications
- Certificate validation enabled
- API key rotation policy
- Rate limiting compliance

### 10.2 Data Protection

**Sensitive Data Handling**:
- PII data encrypted in transit
- Database encryption at rest
- Sensitive fields masked in logs
- No credentials in source code

**Access Control**:
- Role-based access to database
- Principle of least privilege
- Service account isolation
- Network segmentation

### 10.3 Compliance and Audit

**Audit Trail**:
- Complete processing history
- Immutable log records
- Timestamp integrity
- User action tracking

**Data Retention**:
- Configurable retention periods
- Automated purging of old records
- Compliance with data protection laws
- Right to erasure support

### 10.4 Security Best Practices

1. **Input Validation**
   - Email content sanitization
   - SQL injection prevention
   - XSS protection in templates

2. **Error Handling**
   - No sensitive data in error messages
   - Graceful degradation
   - Security event logging

3. **Monitoring**
   - Anomaly detection
   - Failed authentication alerts
   - Unusual pattern detection

---

## 11. Error Handling and Recovery

### 11.1 Error Categories

**Category 1: Transient Errors**
- Network timeouts
- Temporary API unavailability
- Token expiration
- **Recovery**: Automatic retry with exponential backoff

**Category 2: Data Errors**
- Malformed email content
- Invalid classification
- Missing required fields
- **Recovery**: Log and skip, process next email

**Category 3: System Errors**
- Database connection failure
- AI service unavailable
- Configuration errors
- **Recovery**: Fallback routing, alert administrators

### 11.2 Retry Mechanisms

```python
Retry Strategy:
- Initial retry: 2 seconds
- Second retry: 4 seconds
- Third retry: 8 seconds
- Max retries: 3
- Retry conditions: 
  * HTTP 429 (Rate limit)
  * HTTP 503 (Service unavailable)
  * Network timeout
```

### 11.3 Fallback Procedures

**AI Classification Failure**:
1. Try backup AI endpoint
2. If both fail, route to original destination
3. Log failure for manual review

**Email Forwarding Failure**:
1. Retry with exponential backoff
2. Try alternative routing
3. If all fail, keep in unread state
4. Add to manual processing queue

### 11.4 Recovery Procedures

**System Recovery**:
1. Automatic restart on crash
2. Process from last checkpoint
3. No duplicate processing
4. Maintain processing state

**Data Recovery**:
1. Transaction logging
2. Point-in-time recovery
3. Backup restoration procedures
4. Data integrity validation

---

## 12. Performance and Scalability

### 12.1 Performance Metrics

**Performance Characteristics**:
- [ASSUMPTION] Email processing rate: 6 emails/minute
- [ASSUMPTION] Average classification time: 2-3 seconds
- [ASSUMPTION] Auto-response time: < 5 seconds
- [ASSUMPTION] Database query time: < 100ms

*Note: Performance figures are estimates and should be validated through system testing and monitoring.*

**Optimization Strategies**:
- Asynchronous processing
- Parallel batch processing
- Connection pooling
- Query optimization

### 12.2 Scalability Design

**Horizontal Scaling**:
- Stateless service design
- Multiple container instances
- Load balancing capability
- Shared database backend

**Vertical Scaling**:
- Configurable batch sizes
- Adjustable processing intervals
- Resource allocation tuning
- Cache size management

### 12.3 Bottlenecks and Limitations

**Current Limitations**:
1. MS Graph API: 3 concurrent operations
2. AI API: Rate limits per minute
3. Database connections: Pool size
4. Memory: Email content size

**Mitigation Strategies**:
- Request throttling
- Queue management
- Resource pooling
- Content truncation (300k characters)

---

## 13. Monitoring and Logging

### 13.1 Logging Framework

**Log Levels**:
- **ERROR**: System failures, unrecoverable errors
- **WARNING**: Recoverable issues, degraded performance
- **INFO**: Normal operations, key events
- **DEBUG**: Detailed processing information

**Log Categories**:
1. **Application Logs**: Processing logic and flow
2. **Audit Logs**: Complete email trail
3. **Performance Logs**: Timing and metrics
4. **Security Logs**: Access and authentication

### 13.2 Monitoring Points

**System Health**:
- Service availability
- API endpoint status
- Database connectivity
- Queue depths

**Performance Monitoring**:
- Processing times (TAT)
- [ASSUMPTION] Classification accuracy
- Token usage and costs
- Error rates

**Business Metrics**:
- Emails processed per hour
- Classification distribution
- Auto-response rate
- Intervention rate

### 13.3 Alerting Rules

**Critical Alerts**:
- Service down > 5 minutes
- Database connection failure
- AI service unavailable
- Authentication failures

**Warning Alerts**:
- High error rate (>5%)
- Slow processing (TAT >10s)
- Queue backup (>100 emails)
- Cost threshold exceeded

---

## 14. Deployment and Operations

### 14.1 Deployment Process

**Prerequisites**:
1. Azure subscription configured
2. Database provisioned and initialized
3. API keys and secrets configured
4. Network access configured

**Deployment Steps**:
```bash
# Build Docker image
docker build -t apex-email-processor .

# Push to registry
docker push [registry]/apex-email-processor:latest

# Deploy to Azure
az container create --resource-group [RG] \
  --name apex-processor \
  --image [registry]/apex-email-processor:latest \
  --environment-variables ENV_TYPE=PROD

# Start processing
docker exec apex-processor python main.py start
```

### 14.2 Operational Procedures

**Daily Operations**:
1. Monitor processing dashboard
2. Review error logs
3. Check queue status
4. Validate auto-responses

**Weekly Tasks**:
1. Performance review
2. Cost analysis
3. [ASSUMPTION] Classification accuracy check
4. Capacity planning

**Monthly Tasks**:
1. Security audit
2. Database maintenance
3. Model performance review
4. SLA compliance check

### 14.3 Maintenance Windows

**Planned Maintenance**:
- Schedule: Monthly, Sunday 02:00-04:00
- Activities: Updates, patches, optimization
- Notification: 48 hours advance
- Fallback: Manual processing ready

**Emergency Maintenance**:
- Trigger: Critical security patches
- Notification: Immediate
- Duration: Minimized
- Recovery: Automatic catchup

---

## 15. Appendices

### Appendix A: Script Descriptions

#### A.1 main.py
The main orchestration script that manages the entire email processing lifecycle. It implements:
- Continuous polling loop (30-second intervals)
- Batch processing with parallelization
- Comprehensive error handling
- Retry queue management
- Graceful shutdown handling

Key design patterns:
- Async/await for concurrent processing
- Factory pattern for log creation
- Strategy pattern for routing decisions
- Observer pattern for event logging

#### A.2 apex.py
The AI classification engine implementing multi-agent architecture:
- Three specialized agents for classification
- Failover mechanism for high availability
- Cost tracking and optimization
- Token usage monitoring

Classification strategy:
- Hierarchical classification with validation
- Business rule enforcement
- Confidence scoring
- Fallback mechanisms

#### A.3 email_client.py
Microsoft Graph API integration layer:
- OAuth 2.0 authentication
- Connection pooling
- Retry logic with backoff
- Error recovery

API operations:
- Batch email fetching
- Atomic mark-as-read operations
- Template-based forwarding
- Attachment handling

#### A.4 autoresponse.py
Automated response generation system:
- Template management via Azure Blob
- Loop prevention algorithms
- Multi-language support capability
- Personalization engine

Safety mechanisms:
- Sender validation
- Pattern-based filtering
- Rate limiting
- Bounce detection

#### A.5 apex_logging.py
Comprehensive logging and audit system:
- Structured logging format
- Database persistence
- Real-time streaming
- Log aggregation

Audit capabilities:
- Complete email trail
- User action tracking
- System event recording
- Compliance reporting

#### A.6 apex_routing.py
Rule-based routing engine:
- Category-to-department mapping
- Dynamic routing tables
- Override mechanisms
- Load balancing ready

Business logic:
- Priority-based routing
- Escalation paths
- Special handling rules
- Default routing

### Appendix B: Database Indexes

```sql
-- Performance indexes for logs table
CREATE INDEX IX_logs_internet_message_id ON logs(internet_message_id);
CREATE INDEX IX_logs_dttm_proc ON logs(dttm_proc);
CREATE INDEX IX_logs_apex_class ON logs(apex_class);
CREATE INDEX IX_logs_eml_frm ON logs(eml_frm);

-- Composite indexes for common queries
CREATE INDEX IX_logs_date_class ON logs(dttm_proc, apex_class);
CREATE INDEX IX_logs_from_date ON logs(eml_frm, dttm_proc);

-- Skipped mails indexes
CREATE INDEX IX_skipped_internet_msg ON skipped_mails(internet_message_id);
CREATE INDEX IX_skipped_type_date ON skipped_mails(skip_type, created_timestamp);
```

### Appendix C: Error Codes

| Code | Description | Action |
|------|-------------|---------|
| E001 | Authentication failure | Check credentials |
| E002 | API rate limit exceeded | Implement backoff |
| E003 | Database connection lost | Retry connection |
| E004 | AI classification failed | Use fallback routing |
| E005 | Email forward failed | Retry with fallback |
| E006 | Invalid email format | Skip and log |
| E007 | Duplicate email detected | Mark as read |
| E008 | Configuration missing | Check environment |
| E009 | Network timeout | Retry operation |
| E010 | Unknown error | Manual intervention |

### Appendix D: Glossary

| Term | Definition |
|------|------------|
| APEX | Automated Processing and Email eXtraction |
| TAT | Turn Around Time - Processing duration |
| Classification | AI-determined email category |
| Routing | Directing email to appropriate department |
| Intervention | When AI changes original destination |
| Consolidation Bin | Central email account for processing |
| Skip Type | Reason for not processing an email |
| Token | Unit of text for AI processing |
| Fallback | Alternative processing when primary fails |
| Throttling | Rate limiting to prevent overload |

### Appendix E: Support Contacts

**Technical Support**:
- Email: [PLACEHOLDER]
- Phone: [PLACEHOLDER]
- Hours: 24/7 for critical issues

**Escalation Matrix**:
1. Level 1: System Administrators
2. Level 2: Development Team
3. Level 3: Architecture Team
4. Level 4: Executive Stakeholders

---

## Document Sign-off

**Prepared by**: Solutions Team  
**Date**: 2025-01-25  
**Version**: 1.0  

**Review and Approval**:

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Solutions Architect | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] |
| Technical Lead | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] |
| Security Officer | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] |
| Business Owner | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] |

---

*End of Document*