from datetime import datetime
from dotenv import load_dotenv
from openai import AzureOpenAI
import json
import os
import asyncio

# AZURE OPENAI CONNECTION SETTINGS
from config import (
    AZURE_OPENAI_KEY, AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_BACKUP_KEY, AZURE_OPENAI_BACKUP_ENDPOINT
)

FX_RATE = 1

load_dotenv()

# Initialize the primary client - keep variable name as 'client' for compatibility
client = AzureOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY,
    api_version="2024-02-01",
)

# Backup client - initialized only when needed
backup_client = None

# All costs below are in USD
model_costs = {"gpt-4o-mini": {"prompt_token_cost_pm":0.15,
                            "completion_token_cost_pm":0.60},
               "gpt-4o":     {"prompt_token_cost_pm":5,
                            "completion_token_cost_pm":15},
               }

async def call_openai_with_fallback(deployment, messages, temperature=0.1, subject=None):
    """
    Helper function to call OpenAI API with fallback to backup client.
    
    Args:
        deployment (str): The model deployment to use
        messages (list): The messages to send to the API
        temperature (float): The temperature parameter for the API call
        subject (str): Optional subject line for better logging
        
    Returns:
        The API response with additional field indicating which client was used
        
    Raises:
        Exception if both primary and backup clients fail
    """
    global backup_client
    subject_info = f"[Subject: {subject}] " if subject else ""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Try with primary client first
    try:
        print(f">> {timestamp} Using PRIMARY OpenAI deployment ({deployment}) {subject_info}")
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=deployment,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=temperature
        )
        print(f">> {timestamp} PRIMARY OpenAI call successful {subject_info}")
        response.client_used = "primary"
        return response
    except Exception as primary_error:
        print(f">> {timestamp} PRIMARY OpenAI client failed: {str(primary_error)} {subject_info}")
        print(f">> {timestamp} Attempting BACKUP OpenAI deployment ({deployment}) {subject_info}")
        
        # Initialize backup client if not already done
        if backup_client is None:
            backup_client = AzureOpenAI(
                azure_endpoint=AZURE_OPENAI_BACKUP_ENDPOINT,
                api_key=AZURE_OPENAI_BACKUP_KEY,
                api_version="2024-02-01",
            )
        
        # Try with backup client
        try:
            response = await asyncio.to_thread(
                backup_client.chat.completions.create,
                model=deployment,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=temperature
            )
            print(f">> {timestamp} BACKUP OpenAI call successful {subject_info}")
            response.client_used = "backup"
            return response
        except Exception as backup_error:
            print(f">> {timestamp} BACKUP OpenAI client also failed: {str(backup_error)} {subject_info}")
            print(f">> {timestamp} CRITICAL: Both OpenAI endpoints failed, falling back to original destination routing {subject_info}")
            raise Exception(f"Both primary and backup AzureOpenAI clients failed. Primary error: {str(primary_error)}. Backup error: {str(backup_error)}")

async def apex_action_check(text, subject=None):
    """
    Specialized function to determine if an action is required based on the latest email in the thread.
    Uses the smaller GPT-4o-mini model for efficiency.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        # Clean and escape the input text
        cleaned_text = text.replace('\n', '\\n').replace('\r', '\\r').replace('"', '\\"')
        
        deployment = "gpt-4o-mini"
        messages = [
            {"role": "system",
             "content": """You are an intelligent assistant specialized in analyzing email chains to determine if action is required. Focus exclusively on the latest email in the chain and determine if it requires any action, response, or follow-up.

                    Instructions:
                    1. IMPORTANT: Identify the latest email in the chain. In most email formats:
                       - The latest email is typically at the top or beginning of the thread
                       - It often has the most recent timestamp
                       - It may be indicated by being least indented or not having ">" or other quote markers
                    
                    2. Look ONLY at the most recent email in the chain and check if there are any:
                       - Direct questions that need answers
                       - Requests for information or documents
                       - Tasks that need to be performed
                       - Issues that need resolution
                       - Any other items requiring response or action
                    
                    3. DISREGARD the content of previous emails in the thread when determining if action is needed - only use the latest message.
                    
                    4. Respond with only "yes" if action is needed, "no" if no action is needed.

                    The output must be in the following JSON format:
                    {"action_required": "yes"} or {"action_required": "no"}"""
            },
            {"role": "user",
             "content": f"Analyze this email chain and determine if the latest email requires action:\n\n{cleaned_text}"}
        ]
        
        # Use the helper function for API call with fallback
        response = await call_openai_with_fallback(deployment, messages, temperature=0.1, subject=subject)

        try:
            json_output = json.loads(response.choices[0].message.content)
        except json.JSONDecodeError as je:
            print(f">> {timestamp} JSON parsing error in action check: {je}")
            raise Exception(f"Failed to parse JSON response in action check: {str(je)}")

        completion_tokens = response.usage.completion_tokens
        prompt_tokens = response.usage.prompt_tokens
        total_tokens = prompt_tokens + completion_tokens
        
        cost_usd = (completion_tokens/1000000 * model_costs[deployment]["completion_token_cost_pm"] * FX_RATE) + (prompt_tokens/1000000 * model_costs[deployment]["prompt_token_cost_pm"] * FX_RATE)
                
        json_output.update({
            "apex_cost_usd": round(cost_usd, 5),
            "region_used": "main" if response.client_used == "primary" else "backup",
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cached_tokens": 0  # Default to 0 for now
            }
        })
        
        return {"response": "200", "message": json_output}

    except Exception as e:
        print(f">> {timestamp} Error in apex_action_check: {str(e)}")
        return {"response": "500", "message": str(e)}

async def apex_categorise(text, subject=None):
    """
    Main function to categorize emails and determine various attributes including action required.
    Uses the full GPT-4 model for comprehensive analysis.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    subject_info = f"[Subject: {subject}] " if subject else ""
    
    try: 
        # Clean and escape the input text
        cleaned_text = text.replace('\n', '\\n').replace('\r', '\\r').replace('"', '\\"')
        
        print(f">> {timestamp} Starting APEX classification {subject_info}")
        deployment = "gpt-4o"
        messages = [  
            {"role": "system",
            "content": """You are an advanced email classification assistant tasked with analysing email content and performing the list of defined tasks for a South African insurance company. You must accomplish the following list of tasks: 

                                CRITICAL CLASSIFICATION PRIORITY RULES (Check in this exact order):
                                
                                1. **COMPLAINT DETECTION OVERRIDE**: If an email contains complaint language, dissatisfaction, frustration, or negative experiences about services/products, prioritize "bad service/experience" over all other categories, even if the email mentions specific topics like tracking, claims, etc.
                                
                                2. **CANCELLATION + REFUND BUSINESS RULE**: If an email mentions BOTH cancellation/termination AND refund in the same request, ALWAYS classify as "retentions" regardless of how the refund is phrased. The business logic requires cancellation to be processed before any refund can occur.
                                
                                3. **DOCUMENT DIRECTION RULE - REFINED**: Carefully distinguish based on the PRIMARY purpose of the email:
                                   
                                   **PRIMARY PURPOSE ANALYSIS:**
                                   - If the main purpose is REQUESTING documents (customer wants to RECEIVE documents) → "document request"
                                   - If the main purpose is SUBMITTING specific business documents (tracking certificates, claim forms, etc.) → classify by the specific business category (e.g., "vehicle tracking", "claims")
                                   - If the main purpose is pure administrative FOLLOW-UP on previously submitted documents → "other"
                                   
                                   **EXAMPLES OF PRIMARY vs SECONDARY PURPOSES:**
                                   
                                   **SPECIFIC BUSINESS CATEGORY (not "other"):**
                                   - "Attached is my tracking certificate. Please confirm receipt." → "vehicle tracking" (primary purpose: submit tracking cert)
                                   - "Here is my claim form. Kindly acknowledge." → "claims" (primary purpose: submit claim)
                                   - "Please find attached my ID copy for verification. Confirm receipt." → "amendments" (primary purpose: provide verification docs)
                                   
                                   **DOCUMENT REQUEST:**
                                   - "Please send me my policy schedule" → "document request" (wants to receive)
                                   - "I need a copy of my tax certificate" → "document request" (wants to receive)
                                   
                                   **OTHER (administrative follow-up only):**
                                   - "I submitted documents last week but got no confirmation" → "other" (pure administrative follow-up)
                                   - "Did you receive the forms I sent yesterday?" → "other" (pure status inquiry)
                                   - "No confirmation received after uploading documents" → "other" (pure follow-up inquiry)
                                   
                                   **KEY DISTINCTION:** If someone is actively DOING something business-specific (submitting tracking cert, filing claim, providing amendments docs) and just asks for confirmation as courtesy, classify by the business action, NOT as "other".

                                4. **COMPLAINT INDICATORS**: Look for these key phrases and sentiments that indicate complaints:
                                   - "poorly done", "bad service", "disappointed", "frustrated", "unhappy"
                                   - "had to visit multiple times", "took too long", "not satisfied"
                                   - "terrible experience", "awful", "unacceptable", "unprofessional"
                                   - "waste of time", "incompetent", "rude staff", "poor quality"
                                   - Any expression of dissatisfaction with service delivery, quality, or experience
                                
                                5. **TOPIC vs COMPLAINT DISTINCTION**: 
                                   - If email mentions "tracking device" but complains about installation/service = "bad service/experience"
                                   - If email mentions "claims" but complains about claims handling = "bad service/experience"  
                                   - If email mentions any service but expresses dissatisfaction = "bad service/experience"
                                   - Only classify as the specific topic (tracking, claims, etc.) if it's a neutral request without complaint language

                                1. Classify the email content according to the classification categories below. You must return a python list of the top 3 possible categories that the email context aligns to (only if one or more categories apply). The list must always have the top related category as the first element with the third element (if applicable) being the least related. Follow the chronological order of the email conversation when providing the classification and ensure that the latest response is used for classification. Strictly use the following category mapping only:

                                    bad service/experience: **[HIGHEST PRIORITY FOR COMPLAINTS]** Emails about complaints and negative feedback emails from customers indicating bad service or experience related to our products or services. Use this category where the customer's email expresses frustration/irritation or an overall sense of bad service/experience related to a product, service, interaction, experience or lack of response from the insurance company. 
                                    
                                    **IMPORTANT**: This category takes precedence over all others when complaint language is detected, regardless of the topic mentioned. Examples:
                                    - "The tracking device installation was poorly done" → bad service/experience (NOT vehicle tracking)
                                    - "Your claims process is terrible" → bad service/experience (NOT claims)
                                    - "Had to visit the office multiple times, very frustrating" → bad service/experience
                                    - "Disappointed with the service quality" → bad service/experience
                                    
                                    If the email reveals evidence of bad service/experience then this category must be seriously considered before all other categories to prevent potential reputational damage to the insurance company.

                                    vehicle tracking: Emails sent for capturing of vehicle tracking device details, vehicle tracker device certification or capture of vehicle tracking device fitment certificate details. The category handles emails from customers where the client sends through vehicle/car tracking device certificate for verification or capture by the insurance company. 
                                    
                                    **IMPORTANT**: Use this category when the PRIMARY purpose is submitting tracking-related documents, even if they ask for confirmation as courtesy.
                                    
                                    **EXAMPLES:**
                                    - "Attached is my tracking certificate. Please confirm receipt." → vehicle tracking (primary purpose: submit cert)
                                    - "Here is the fitment certificate for my vehicle tracker." → vehicle tracking 
                                    - "Please find attached tracking device documentation." → vehicle tracking
                                    
                                    **NOTE**: Only use "bad service/experience" if there are complaints about tracking services.

                                    retentions: **[CRITICAL BUSINESS RULE]** Email requests for policy cancellation/termination of the entire policy (not just individual risk items), cancellations related to annual review queries, refunds after cancellation (must be cancelled customer). 
                                    
                                    **MOST IMPORTANT**: Use this category when the customer email requests cancelling a policy in its entirety, which usually includes all risk items on the policy.
                                    
                                    **CANCELLATION + REFUND RULE**: When a customer requests BOTH cancellation AND refund in the same email, ALWAYS classify as "retentions" because:
                                    - The retentions department must process the cancellation first
                                    - Only after cancellation can the refund be processed
                                    - This is the correct business workflow
                                    
                                    **EXAMPLES THAT MUST BE "RETENTIONS":**
                                    - "I want to cancel my policy and get a refund"
                                    - "Please terminate my policy and refund the premium"
                                    - "Cancel my policy due to errors and process refund"
                                    - "I would like to cancel and request a refund"
                                    - Any combination of cancellation + refund requests

                                    refund request: Request from email sender for a refund related to the cancellation of a newly taken or existing policy or related insurance services. This category includes new refund requests or follow ups on an existing request. 
                                    
                                    **IMPORTANT DISTINCTION**: This category is ONLY for refund requests that do NOT involve policy cancellation in the same email. If the customer mentions both cancellation and refund, classify as "retentions" instead.
                                    
                                    **EXAMPLES OF PURE REFUND REQUESTS:**
                                    - "I need a refund for the overpayment on my account"
                                    - "Please refund the duplicate premium payment"
                                    - "Refund the excess payment made last month"
                                    - Follow-ups on existing refund requests for already cancelled policies
                                    
                                    **NOT REFUND REQUEST (classify as "retentions"):**
                                    - Any email that mentions both cancellation and refund
                                    - "Cancel and refund" scenarios

                                    document request: **[IMPORTANT: DIRECTION MATTERS]** Email sender requests for a document to be **SENT TO THEM**. This category is ONLY for customers who want to RECEIVE documents from the insurance company. 
                                    
                                    **EXAMPLES OF DOCUMENT REQUESTS (customer wants to receive):**
                                    - "Please send me my policy schedule"
                                    - "I need a copy of my tax certificate"
                                    - "Can you email me the claims history report?"
                                    - "Please provide my noting of interest document"
                                    
                                    **NOT DOCUMENT REQUESTS (classify by primary business purpose):**
                                    - "Attached is my tracking certificate. Please confirm receipt." → vehicle tracking (submitting cert)
                                    - "Here is my claim form. Kindly acknowledge." → claims (submitting claim)
                                    
                                    Requested Documents that customers want to RECEIVE may include: Policy schedule documents, noting of interest, tax letters, cross border documents, statement of services or benefits, claims history, previous claims summary etc. Any request for an actual document TO BE SENT to the client related to their insurance product.

                                    amendments: The following scenarios constitute an ammendment to a policy:                                   
                                                * Add, change, or remove individual risk items or the details of a policy. This includes changes to Risk/Physical address, contact details, policy holder details (name, surname, gender, marital status, etc.), household members details, commencement date, passport details, debit order details (banking details, debit order date), banking deduction details, cashback details, premium waivers, deceased customer details or information. This also includes the cancellation or removal of individual risk items (e.g., a vehicle, building, or home contents item) from a policy whilst other risk items are kept on the policy.
                                                * Add, change, or remove a vehicle or vehicle details from a policy. This includes add/change/removal of Vehicle details, vehicle driver details, vehicle cover details (insurance cover, cover type, vehicle excess, car hire, insured value, etc), vehicle use details (private, business, etc), vehicle parking (day or night) details, vehicle finance details, general cover queries.
                                                * Buildings quote,  Add change or remove Building details, buildings insured value, geyser add, remove or updates, buildings finance corrections, commencement date details, general  buildings cover queries.
                                                * Add change or remove home contents or home content details, contents insured value, security updates, general home contents cover queries.
                                                * Add change or remove portable possesions or portable possession items details (These include small insurable items such as laptops, tablets, jewellery, cellphones, cameras, etc).
                                                * Email requesting items to be insured at different addresses including car/ building / home contents, i.e a split risk. A split risk refers to the need for a customer to insure goods at more than one residential address.
                                                * Email requests from Banks/Banking institutions to change the banking details of the policy holder. This category applies to a bank requesting the insurance company to change the debit order details for the policy holder.
                                                * Email requests for Policy reinstatements. This includes requests to reinstate a policy that has been previously cancelled or terminated.
                                                * Email requests for help with payments, payment receipts or payment success verification on the online/app platforms.
                                                * Requests for quotes to add a new risk item to an existing policy.
                                                
                                                **IMPORTANT**: If customer is submitting documents for amendments (like ID copy, proof of address), classify as "amendments", not "other".
                                     
                                    claims: Emails regarding capturing/registering of an insurance claim for the customer's insurance policy. This also includes emails for following up on an existing insurance claim that has already been submitted. These emails will entail the customer making an insurance claim against their policy. The claim can be for a loss/damage to any of their insured risks or services which incldue vehicles, building, home contents, portable possessions, geysers etc. Requests for claims history or a previous claims summary related to a policy should be classified as "document request" and not claims as this does not relate to the registering of a new claim or following up on an existing claim.
                                    
                                    **IMPORTANT**: If customer is submitting claim forms or claim-related documents, classify as "claims", not "other".
                                    
                                    **NOTE**: If customer complains about claims handling/process, use "bad service/experience" instead.
                                    
                                    online/app: Emails related to System errors or system queries. Systems include the online websites and/or applications. Excludes system errors related to payments, payment receipts or payment success verification on the online/app platforms.
                                    
                                    request for quote: Emails from the customer requesting an insurance quotation or a request to undergo the quotation/underwriting process. A quotation will generally provide the premium the customer must pay for insuring one or more risk items. This excludes requests for quotations that include adding a new risk item to an existing policy, which should be classified as "amendments". Any request to add something new onto a policy that already exist will be classified as "amendments" and not "request for quote". Requests for a quotation will only be used when the customer asks for a quotation and there is no evidence or reference to an existing policy or risk item.
                                                                        
                                    previous insurance checks/queries : Email requests or queries related to a Previous Insurance (PI) check, verification or validation.

                                    assist: Emails requsting roadside assistance, towing assistance or home assist.  Roadside assistance includes 24/7 support for assistance with issues like flat tyres, flat/dead batteries and locked keys requiring locksmith services. Towing assistance includes support for towing s vehicle to the nearest place of safety or a designated repairer. Home assist includes request for assitance with a home emergency where the customer needs urgent help from the services of a plumber, electrician, locksmith or glazier (network of home specialists). 
                                    
                                    other: Use this category ONLY when the email cannot be classified into any of the above categories AND the primary purpose is purely administrative follow-up. This includes:
                                        * Pure follow-up inquiries on documents already submitted by the customer (with no new business action)
                                        * Pure confirmation requests about receipt of documents sent by the customer (with no specific business purpose)
                                        * Pure status inquiries about submitted applications or forms (with no new submission)
                                        * General inquiries that don't fit other specific categories
                                        * Administrative communications with no specific business action
                                        
                                        **IMPORTANT**: Do NOT use "other" if the customer is actively submitting business documents (tracking certs, claim forms, amendment docs, etc.) even if they ask for confirmation. In those cases, classify by the business purpose.
                                                                           
                                    **Do not use any classifications, except for those above.**
 
                                2. Provide a short explanation for the classification in one sentence only.
                                
                                3. Determine if any action is required based on the email content. Use the following instructions to help determine of there is an action required. 
                                    a. Focus exclusively on the latest email in the chain.
                                    b. Identify if there are any requests, questions, or tasks in the latest email that require a response or action.
                                    c. If the latest email indicates that action is required, respond with "yes". Otherwise, respond with "no".
                                    d. All emails classified as Vehicle tracking will have an action required.
                                    e. All emails classified as bad service/experience will have an action required.
                                    f. Do not use any other classification other than "yes" or "no" for action required.
                                    g. Do not use any other classification other than the ones provided above for classification.
                                    
                                4. Classify the sentiment of the email as Positive, Neutral, or Negative. Only classify sentiment when the customer expresses an apparent sentiment towards the products or services offered by the company. Positive to be used if the client expresses satisfaction or offers a compliment on service received. If there is not apparent sentiment then use Neutral.

                                IMPORTANT GUIDELINES FOR EMAIL THREAD ANALYSIS:
                                
                                1. IDENTIFYING THE LATEST EMAIL:
                                   - The latest email will always be the first message in the provided content.
                                   - It may be visually separated from previous messages in the thread.
                                   - It will have the most recent timestamp.
                                   - In many email formats, older messages are indented or preceded by ">" or other quote markers.

                                2. CLASSIFICATION PRIORITY:
                                   - **ALWAYS CHECK FOR COMPLAINT LANGUAGE FIRST** before considering topic-based classification
                                   - **ALWAYS CHECK FOR CANCELLATION + REFUND COMBINATION** and classify as "retentions" if both are present
                                   - **ALWAYS IDENTIFY THE PRIMARY PURPOSE** - what is the main business action being performed?
                                   - **DISTINGUISH PRIMARY vs SECONDARY ACTIONS** - confirmation requests are usually secondary to the main business purpose
                                   - ALWAYS prioritize the content of the latest email for classification, even if it's brief.
                                   - The subject line should be considered but given lower priority than the actual message content.

                                3. USING CONTEXT FROM PREVIOUS MESSAGES:
                                   - Only reference previous messages in the thread if:
                                     a) The latest email is very brief (e.g., "Please do this for me" or "Can you help with this?")
                                     b) The latest email explicitly references previous context (e.g., "As discussed below...")
                                     c) The latest email would be ambiguous without thread context
                                
                                4. EXAMPLES OF PROPER CLASSIFICATION:
                                   - Example 1: "The tracking device installation was poorly done" → "bad service/experience" (complaint overrides topic)
                                   - Example 2: "Attached is my tracking certificate. Please confirm receipt." → "vehicle tracking" (primary purpose: submit cert)
                                   - Example 3: "Your claims team is very slow and unprofessional" → "bad service/experience" (complaint overrides topic)
                                   - Example 4: "I need to submit a claim for my vehicle" → "claims" (neutral request)
                                   - Example 5: "Please send me my policy schedule" → "document request" (requesting to receive)
                                   - Example 6: "I submitted documents last week but got no confirmation" → "other" (pure administrative follow-up)
                                   - Example 7: "I want to cancel my policy and get a refund" → "retentions" (cancellation + refund)
                                   - Example 8: "Please refund my overpayment" → "refund request" (refund only, no cancellation)
                                   - Example 9: "Here is my claim form. Kindly acknowledge." → "claims" (primary purpose: submit claim form)
                                
                                5. COMMON PITFALLS TO AVOID:
                                   - Don't classify based on topic keywords alone - check for complaint sentiment first
                                   - Don't classify "cancel + refund" as "refund request" - it should be "retentions"
                                   - Don't confuse PRIMARY purpose (business action) with SECONDARY purpose (polite confirmation request)
                                   - Don't classify business document submissions as "other" just because they ask for confirmation
                                   - Don't be misled by a subject line that doesn't match the latest email content
                                   - Don't classify based on previous messages if the latest email has changed the topic

                                IMPORTANT: Ensure your output conforms to the following JSON format. Replace the placeholder descriptions with actual content:
                                {  
                                "classification": ["primary_category", "secondary_category_if_applicable", "tertiary_category_if_applicable"],  
                                "rsn_classification": "Provide a clear, specific explanation for why you chose this classification based on the email content and primary purpose analysis",
                                "action_required": "yes or no only",  
                                "sentiment": "Positive, Neutral, or Negative only"
                                }

                                DO NOT use placeholder text like "answer" in your response. Always provide specific, meaningful content for each field."""
            },
            {"role": "user",
            "content": f"Please summarize the following text:\n\n{cleaned_text}"}
        ]
        
        # Initialize token tracking variables
        gpt_4o_prompt_tokens = 0
        gpt_4o_completion_tokens = 0
        gpt_4o_total_tokens = 0
        gpt_4o_cached_tokens = 0
        
        gpt_4o_mini_prompt_tokens = 0
        gpt_4o_mini_completion_tokens = 0
        gpt_4o_mini_total_tokens = 0
        gpt_4o_mini_cached_tokens = 0
        
        # Track which region we're using (main by default)
        region_used = "main"
        
        # Use the helper function for API call with fallback
        response = await call_openai_with_fallback(deployment, messages, temperature=0.2, subject=subject)
        
        # Track token usage from main GPT-4o classification
        gpt_4o_prompt_tokens = response.usage.prompt_tokens
        gpt_4o_completion_tokens = response.usage.completion_tokens
        gpt_4o_total_tokens = gpt_4o_prompt_tokens + gpt_4o_completion_tokens
        
        # Track region used for primary classification
        if response.client_used == "backup":
            region_used = "backup"
        
        # JSONIFY THE APEX CLASSIFICATION OUTPUT
        try:
            json_output = json.loads(response.choices[0].message.content)
            
            # GET THE TOKEN USAGE FOR THE APEX CLASSIFICATION CALL
            completion_tokens = response.usage.completion_tokens
            prompt_tokens = response.usage.prompt_tokens
            apex_cost_usd = (completion_tokens/1000000 * model_costs[deployment]["prompt_token_cost_pm"] * FX_RATE) + (prompt_tokens/1000000 * model_costs[deployment]["completion_token_cost_pm"] * FX_RATE)
 
        except json.JSONDecodeError as je:
            print(f">> {timestamp} JSON parsing error in categorise: {je} {subject_info}")
            raise Exception(f"Failed to parse JSON response in categorise: {str(je)}")
        
        # --> START APEX ACTION CHECK BLOCK 
        try:
            print(f">> {timestamp} Starting action check verification {subject_info}")
            action_check_response = await apex_action_check(text, subject)
            
            # CHECK IF THE ACTION CHECK WAS SUCCESSFUL
            if action_check_response["response"] == "200":
                action_check_result = action_check_response["message"]["action_required"]
                
                # ADD THE COST FOR THE APEX ACTION CHECK TO THE TOTAL COST
                apex_cost_usd += action_check_response["message"]["apex_cost_usd"]
                
                # Track token usage from action check (GPT-4o-mini)
                if "token_usage" in action_check_response["message"]:
                    token_usage = action_check_response["message"]["token_usage"]
                    gpt_4o_mini_prompt_tokens += token_usage.get("prompt_tokens", 0)
                    gpt_4o_mini_completion_tokens += token_usage.get("completion_tokens", 0)
                    gpt_4o_mini_total_tokens += token_usage.get("total_tokens", 0)
                    gpt_4o_mini_cached_tokens += token_usage.get("cached_tokens", 0)

                # CHECK IF THE APEX ACTION CHECK AGENT RESULT IS DIFFERENT FROM THE APEX CLASSIFICATION AGENT 
                if action_check_result != json_output["action_required"]:
                    print(f">> {timestamp} Action check override: Original={json_output['action_required']}, New={action_check_result} {subject_info}")
                    
                    # IF THE CHECK SHOWS DIFFERENT RESULT THEN OVERRIDE THE APEX CLASSIFICATION RESULT WITH THE APEX ACTION CHECK RESULT
                    json_output["action_required"] = action_check_result
               
            print(f">> {timestamp} Action check verification complete {subject_info}")
                
        except Exception as e:
            # IF THE APEX ACTION CHECK FAILS THEN LEAVE THE APEX CLASSIFICATION RESULT AS IS
            print(f">> {timestamp} Error in action check response: {str(e)} {subject_info}")
            
        # --> END APEX ACTION CHECK BLOCK 
        
        # IMPORTANT: Store the original list of categories before prioritization
        # This ensures we capture the top 3 categories before prioritization changes it to a single category
        if isinstance(json_output["classification"], list):
            top_categories = json_output["classification"].copy()
            json_output["top_categories"] = top_categories
        else:
            # If not a list (unexpected), store as is
            json_output["top_categories"] = json_output["classification"]
        
        # --> START APEX PRIORITIZE BLOCK
        try:
            print(f">> {timestamp} Starting category prioritization {subject_info}")
            apex_prioritize_response = await apex_prioritize(text, json_output["classification"], subject)
            
            # CHECK IF APEX PRIORITIZE WAS SUCCESSFUL
            if apex_prioritize_response["response"] == "200":
                
                # ADD THE COST FOR THE APEX PRIORITIZE TO THE TOTAL COST
                apex_cost_usd += apex_prioritize_response["message"]["apex_cost_usd"]
                
                # Track token usage from prioritization (GPT-4o-mini)
                if "token_usage" in apex_prioritize_response["message"]:
                    token_usage = apex_prioritize_response["message"]["token_usage"]
                    gpt_4o_mini_prompt_tokens += token_usage.get("prompt_tokens", 0)
                    gpt_4o_mini_completion_tokens += token_usage.get("completion_tokens", 0)
                    gpt_4o_mini_total_tokens += token_usage.get("total_tokens", 0)
                    gpt_4o_mini_cached_tokens += token_usage.get("cached_tokens", 0)
                
                # UPDATE THE APEX CLASSIFICATION RESULT AND REASON FOR CLASSIFICATION WITH THE PRIORITIZED AGENT RESULTS
                original_category = json_output["classification"][0] if isinstance(json_output["classification"], list) else json_output["classification"]
                final_category = apex_prioritize_response["message"]["final_category"].lower()
                
                json_output["classification"] = final_category
                json_output["rsn_classification"] = apex_prioritize_response["message"]["rsn_classification"]
                
                if original_category != final_category:
                    print(f">> {timestamp} Category reprioritized: Original={original_category}, Final={final_category} {subject_info}")
            
            # IF THE APEX PRIORITIZE FAILS THEN LEAVE THE APEX CLASSIFICATION RESULT AS IS 
            else:
                # SELECT THE FIRST ELEMENT OF THE APEX CLASSIFICATION CATEGORY LIST - DO NOT KEEP AS A LIST
                if isinstance(json_output["classification"], list) and len(json_output["classification"]) > 0:
                    json_output["classification"] = json_output["classification"][0]
                print(f">> {timestamp} Using first category as priority (fallback) {subject_info}")
                                
        except Exception as e:
            print(f">> {timestamp} Error in category prioritization: {str(e)} {subject_info}")

        # --> END OF APEX PRIORITIZE BLOCK

        # Add token tracking information to the response
        json_output.update({
            "apex_cost_usd": round(apex_cost_usd, 5),
            "region_used": region_used,
            "gpt_4o_prompt_tokens": gpt_4o_prompt_tokens,
            "gpt_4o_completion_tokens": gpt_4o_completion_tokens,
            "gpt_4o_total_tokens": gpt_4o_total_tokens,
            "gpt_4o_cached_tokens": gpt_4o_cached_tokens,
            "gpt_4o_mini_prompt_tokens": gpt_4o_mini_prompt_tokens,
            "gpt_4o_mini_completion_tokens": gpt_4o_mini_completion_tokens,
            "gpt_4o_mini_total_tokens": gpt_4o_mini_total_tokens,
            "gpt_4o_mini_cached_tokens": gpt_4o_mini_cached_tokens
        })
        
        print(f">> {timestamp} APEX classification complete: Category={json_output['classification']}, Action={json_output['action_required']}, Sentiment={json_output['sentiment']} {subject_info}")
        
        return {"response": "200", "message": json_output}
        
    except Exception as e: 
        print(f">> {timestamp} ERROR in APEX classification: {str(e)} {subject_info}")
        return {"response": "500", "message": str(e)}

async def apex_prioritize(text, category_list, subject=None):
    """
    Specialized agent to validate the apex classification and prioritise the final classification based on a priority list and the context of the email.
    Enhanced with complaint detection, document direction, cancellation+refund business logic, and primary purpose analysis.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    subject_info = f"[Subject: {subject}] " if subject else ""
    
    try:
        # Clean and escape the input text
        cleaned_text = text.replace('\n', '\\n').replace('\r', '\\r').replace('"', '\\"')
        
        deployment = "gpt-4o-mini"
        messages = [
            {"role": "system",
             "content": """You are an intelligent assistant specialized in analyzing email content and a list of possible categories that the email was classified into. Your task is to determine the single most appropriate final category from the list.

                CRITICAL OVERRIDE RULES (Check in this exact order):

                1. **COMPLAINT DETECTION RULE:**
                - If "bad service/experience" is in the category list AND the email contains complaint language, dissatisfaction, or negative experiences, ALWAYS select "bad service/experience" as the final category, regardless of other topics mentioned.
                
                2. **CANCELLATION + REFUND BUSINESS RULE:**
                - If BOTH "retentions" AND "refund request" are in the category list, analyze the email content:
                  * If the email mentions BOTH cancellation/termination AND refund → select "retentions"
                  * If the email only mentions refund (no cancellation) → select "refund request"
                - This business rule exists because cancellation must be processed before refund can occur
                
                3. **PRIMARY PURPOSE ANALYSIS RULE:**
                - Identify the PRIMARY business purpose of the email vs secondary/courtesy requests
                - If someone is actively performing a specific business action (submitting tracking cert, claim form, amendment docs), classify by that business action even if they ask for confirmation
                - Only use "other" if the PRIMARY purpose is pure administrative follow-up with no specific business action
                
                **PRIMARY PURPOSE EXAMPLES:**
                - "Attached is my tracking certificate. Please confirm receipt." → "vehicle tracking" (PRIMARY: submit tracking cert)
                - "Here is my claim form. Kindly acknowledge." → "claims" (PRIMARY: submit claim)
                - "Please find attached ID for verification. Confirm receipt." → "amendments" (PRIMARY: provide verification)
                - "I submitted documents last week but got no confirmation" → "other" (PRIMARY: administrative follow-up)

                **COMPLAINT INDICATORS to look for:**
                - "poorly done", "bad service", "disappointed", "frustrated", "unhappy", "terrible", "awful"
                - "had to visit multiple times", "took too long", "not satisfied", "unacceptable"
                - "waste of time", "incompetent", "rude", "poor quality", "unprofessional"
                - Any expression of dissatisfaction with service delivery, quality, or experience

                **DECISION PROCESS:**

                STEP 1: CHECK FOR COMPLAINTS FIRST
                - Scan the email content for complaint language and negative sentiment
                - If complaint language is detected AND "bad service/experience" is in the category list, SELECT IT immediately
                - This overrides all other considerations including the priority list below

                STEP 2: CHECK CANCELLATION + REFUND COMBINATION
                - If both "retentions" and "refund request" are in the category list:
                  * Look for cancellation/termination keywords: "cancel", "terminate", "close policy", "end policy"
                  * Look for refund keywords: "refund", "money back", "reimburse"
                  * If BOTH types of keywords are present, select "retentions"
                  * If only refund keywords (no cancellation), select "refund request"

                STEP 3: PRIMARY PURPOSE ANALYSIS  
                - Identify what the customer is actively DOING (not just asking about):
                  * Submitting tracking certificate → "vehicle tracking"
                  * Submitting claim forms → "claims"  
                  * Submitting amendment documents → "amendments"
                  * Pure administrative follow-up → "other"
                - If they're doing a specific business action + asking for confirmation, prioritize the business action
                - Only select "other" if no specific business action is being performed

                STEP 4: DOCUMENT DIRECTION CHECK
                - If "document request" is in the category list, determine the direction:
                  * If customer wants to RECEIVE documents, keep "document request"
                  * If customer is SUBMITTING documents for specific business purpose, select the business category
                
                STEP 5: EVALUATE CATEGORIES NORMALLY (if no overrides apply)
                - The list of categories is in order of relevance as determined by the initial classifier
                - The first category in the list is the primary classification
                - CAREFULLY examine the latest email in the thread to determine if this first category clearly aligns with the actual request or topic of the latest email
                - If the first category in the list clearly matches the latest email's content and purpose, SELECT IT AS THE FINAL CATEGORY
                - If multiple categories seem equally applicable, or if there's genuine ambiguity, use the priority list below:
                    
                    Priority | Category
                    ---------|---------------------------
                    1        | assist   
                    2        | bad service/experience
                    3        | vehicle tracking 
                    4        | retentions
                    5        | amendments
                    6        | claims
                    7        | refund request
                    8        | online/app
                    9        | request for quote
                    10       | document request
                    11       | other
                    12       | previous insurance checks/queries

                **EXAMPLES:**

                Example 1: COMPLAINT DETECTED - OVERRIDE EVERYTHING
                - Email: "The tracking device installation was poorly done"
                - Categories: ["vehicle tracking", "bad service/experience", "other"]
                - Decision: Select "bad service/experience" (complaint language detected)
                - Explanation: The email expresses dissatisfaction with service quality, overriding topic-based classification

                Example 2: PRIMARY PURPOSE - BUSINESS ACTION OVER COURTESY
                - Email: "Attached is my tracking certificate. Please confirm receipt."
                - Categories: ["other", "vehicle tracking", "document request"]
                - Decision: Select "vehicle tracking" (primary purpose: submit tracking certificate)
                - Explanation: Customer is actively submitting a tracking certificate; confirmation request is secondary courtesy

                Example 3: PRIMARY PURPOSE - PURE ADMINISTRATIVE FOLLOW-UP
                - Email: "I submitted documents last week but got no confirmation"
                - Categories: ["other", "vehicle tracking", "document request"]
                - Decision: Select "other" (primary purpose: administrative follow-up only)
                - Explanation: No specific business action being performed, purely following up on previous submission

                Example 4: CANCELLATION + REFUND - BUSINESS RULE OVERRIDE
                - Email: "I want to cancel my policy and get a refund due to errors"
                - Categories: ["refund request", "retentions", "other"]
                - Decision: Select "retentions" (both cancellation and refund mentioned)
                - Explanation: Business rule requires cancellation to be processed before refund, so retentions department handles this

                Example 5: DOCUMENT DIRECTION - WANTS TO RECEIVE
                - Email: "Please send me my policy schedule"
                - Categories: ["document request", "other", "amendments"]
                - Decision: Select "document request" (customer wants to receive documents)
                - Explanation: Customer is requesting documents to be sent to them

                Provide a short explanation for why you've chosen the final classification based on the EMAIL CONTENT. Mention if complaint language, business rule, primary purpose analysis, or priority list was the determining factor.

                Use the following JSON format for your response:
                {
                    "final_category": "answer",
                    "rsn_classification": "answer"
                }"""
            },
            {
                "role": "user",
                "content": f"Analyze this email chain and the list of categories to provide a single category classification. Check for complaints first, then business rules, then identify the primary purpose:\n\n Email text: {cleaned_text} \n\n Category List: {category_list}"
            }
        ]
        
        # Use the helper function for API call with fallback
        response = await call_openai_with_fallback(deployment, messages, temperature=0.1, subject=subject)

        try:
            json_output = json.loads(response.choices[0].message.content)
        except json.JSONDecodeError as je:
            print(f">> {timestamp} JSON parsing error in prioritization: {je} {subject_info}")
            raise Exception(f"Failed to parse JSON response in prioritization: {str(je)}")

        completion_tokens = response.usage.completion_tokens
        prompt_tokens = response.usage.prompt_tokens
        total_tokens = prompt_tokens + completion_tokens
        
        cost_usd = (completion_tokens/1000000 * model_costs[deployment]["completion_token_cost_pm"] * FX_RATE) + (prompt_tokens/1000000 * model_costs[deployment]["completion_token_cost_pm"] * FX_RATE)
                
        json_output.update({
            "apex_cost_usd": round(cost_usd, 5),
            "region_used": "main" if response.client_used == "primary" else "backup",
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cached_tokens": 0  # Default to 0 for now
            }
        })
        
        return {"response": "200", "message": json_output}

    except Exception as e:
        print(f">> {timestamp} Error in apex_prioritize: {str(e)} {subject_info}")
        return {"response": "500", "message": str(e)}

# Synchronous versions for backward compatibility
def apex_categorise_sync(text):
    return asyncio.run(apex_categorise(text))

def apex_action_check_sync(text):
    return asyncio.run(apex_action_check(text))
