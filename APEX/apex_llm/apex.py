from datetime import datetime, timedelta
from dotenv import load_dotenv
from openai import AzureOpenAI
import json
import os
import asyncio

# AZURE OPENAI CONNECTION SETTINGS
from config import AZURE_OPENAI_KEY, AZURE_OPENAI_ENDPOINT

FX_RATE = 1

load_dotenv()

endpoint = AZURE_OPENAI_ENDPOINT
deployment = 'gpt-4o'#'gpt4omini'     #Options 'gpt4omini', 'gpt-4o'
api_key = AZURE_OPENAI_KEY

client = AzureOpenAI(
    azure_endpoint=endpoint,
    api_key=api_key,
    api_version="2024-02-01",
)

# All costs below are in USD
model_costs = {"gpt-4o-mini": {"prompt_token_cost_pm":0.15,
                            "completion_token_cost_pm":0.60},
               "gpt-4o":     {"prompt_token_cost_pm":5,
                            "completion_token_cost_pm":15},
               }

async def apex_action_check(text):
    """
    Specialized function to determine if an action is required based on the latest email in the thread.
    Uses the smaller GPT-4-mini model for efficiency.
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
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )

        try:
            json_output = json.loads(response.choices[0].message.content)
        except json.JSONDecodeError as je:
            print(f"JSON parsing error in action check: {je}")
            print(f"Raw response content: {response.choices[0].message.content}")
            raise Exception(f"Failed to parse JSON response in action check: {str(je)}")

        completion_tokens = response.usage.completion_tokens
        prompt_tokens = response.usage.prompt_tokens
        
        cost_usd = (completion_tokens/1000000 * model_costs[deployment]["completion_token_cost_pm"] * FX_RATE) + (prompt_tokens/1000000 * model_costs[deployment]["prompt_token_cost_pm"] * FX_RATE)
                
        json_output.update({"apex_cost_usd": round(cost_usd, 5)})
        
        return {"response": "200", "message": json_output}

    except Exception as e:
        print(f"Error in apex_action_check: {str(e)}")
        return {"response": "500", "message": str(e)}


async def apex_categorise(text):
    """
    Main function to categorize emails and determine various attributes including action required.
    Uses the full GPT-4 model for comprehensive analysis.
    """
    try: 
        # Clean and escape the input text
        cleaned_text = text.replace('\n', '\\n').replace('\r', '\\r').replace('"', '\\"')
        
        deployment = "gpt-4o"
        response = await asyncio.to_thread(
            client.chat.completions.create,  
            model=deployment,  
            messages=[  
                {"role": "system",
                "content": """You are an advanced email classification assistant tasked with analysing email content and performing the list of defined tasks. You must accomplish the following list of tasks: 

                                1. Classify the email content according to the classification categories below. You must return a python list of the top 3 possible categories that the email context aligns to (only if one or more categories apply). The list must always have the top related category as the first element with the third element (if applicable) being the least related. Follow the chronological order of the email conversation when providing the classification and ensure that the latest response is used for classification. Strictly use the following category mapping only:

                                    amendments: The following scenarios constitute an ammendment to a policy:                                   
                                                * Add, change, or remove individual risk items or the details of a policy. This includes changes to Risk/Physical address, contact details, policy holder details (name, surname, gender, marital status, etc.), household members details, commencement date, passport details, debit order details (banking details, debit order date), banking deduction details, cashback details, premium waivers, deceased customer details or information. This also includes the cancellation or removal of individual risk items (e.g., a vehicle, building, or home contents item) from a policy whilst other risk items are kept on the policy.
                                                * Add, change, or remove a vehicle or vehicle details from a policy. This includes add/change/removal of Vehicle details, vehicle driver details, vehicle cover details (insurance cover, cover type, vehicle excess, car hire, insured value, etc), vehicle use details (private, business, etc), vehicle parking (day or night) details, vehicle finance details, general cover queries.
                                                * Buildings quote,  Add change or remove Building details, buildings insured value, geyser add, remove or updates, buildings finance corrections, commencement date details, general  buildings cover queries.
                                                * Add change or remove home contents or home content details, contents insured value, security updates, general home contents cover queries.
                                                * Add change or remove portable possesions or portable possession items details (These include small insurable items such as laptops, tablets, jewellery, cellphones, cameras, etc).
                                                * Email requesting items to be insured at different addresses including car/ building / home contents, i.e a split risk. A split risk refers to the need for a customer to insure goods at more than one residential address.
                                     
                                    vehicle tracking: Email containing a shared tracking device fitment certification by the sender for capturing of vehicle inspection details, vehicle tracker device certification or capture of vehicle tracking device fitment certificate or vehicle fitness certificate or any email related to vehicle tracking device(s). Emails for document requests or documents that are addressed to Autogen Tracking <tracking@autogen.co.za> will be classified as Vehicle tracking unless there is a specific request for something else.

                                    bad service/experience: Emails about complaints and negative feedback emails from customers indicating bad service or experience related to our products or services.
                                    
                                    claims: Emails regarding capturing of an insurance claim against a policy or following up on an existing insurance claim that has been submitted. These emails will entail the customer making an insurance claim against their policy. The claim can be for a loss/damage to any of their insured risks or services which incldue vehicles, building, home contents, portable possessions, geysers etc.
                                    
                                    refund request: Request from email sender for a refund related to a new or existing policy or related services. Including new refund request or follow up on an existing request.
                                    
                                    document request: Email sender requests for a document to be sent to them. Requested Documents may include Policy schedule documents, claims history, noting of interest, tax letters, cross border documents, statement of services or benefits, etc. Any request for an actual document related to the client and their insurance product. 

                                    online/app: Emais related to System errors or system queries. Sytems include the online websites and/or applications.

                                    retentions: Email requests for Policy reinstatements, policy cancellation/termination of the entire policy (not just individual risk items), cancellations related to annual review queries, refunds after cancellation (must be cancelled customer). Use this category when the customer email requests cancelling a policy in its entirety, which usually includes all risk items on the policy.
                                    
                                    request for quote: Emails from the customer requesting an insurance quotation or a request to undergo the quotation/underwriting process. A quotation will generally provide the premium the customer must pay for insuring one or more risk items.
                                    
                                    debit order switch: Email requests from Banks/Banking institutions to change the banking details of the policy holder. This category applies to a bank requesting the insurance company to change the debit order details for the policy holder.
                                                                        
                                    previous insurance checks/queries : Email requests or queries related to a Previous Insurance (PI) check, verification or validation.

                                    assist: Emails requsting roadside assistance, towing assistance or home assist.  Roadside assistance includes 24/7 support for assistance with issues like flat tyres, flat/dead batteries and locked keys requiring locksmith services. Towing assistance includes support for towing s vehicle to the nearest place of safety or a designated repairer. Home assist includes request for assitance with a home emergency where the customer needs urgent help from the services of a plumber, electrician, locksmith or glazier (network of home specialists). 
                                                                           
                                    If the email cannot be classified into one of the above categories, please classify it as "other". 
                                    
                                    Do not use any classifications, except for those above.
 
                                2. Provide a short explanation for the classification in one sentence only.
                                
                                3. Determine if any action is required based on the email content. Use the following instructions to help determine of there is an action required. 
                                    a. Focus exclusively on the latest email in the chain.
                                    b. Identify if there are any requests, questions, or tasks in the latest email that require a response or action.
                                    c. If the latest email indicates that action is required, respond with "yes". Otherwise, respond with "no".
                                    d. All emails classified as Vehicle tracking will have an action required.
                                    e. Do not use any other classification other than "yes" or "no" for action required.
                                    f. Do not use any other classification other than the ones provided above for classification.
                                    
                                4. Classify the sentiment of the email as Positive, Neutral, or Negative. Only classify sentiment when the customer expresses an apparent sentiment towards the products or services offered by the company. Positive to be used if the client expresses satisfaction or offers a compliment on service received. If there is not apparent sentiment then use Neutral.

                                IMPORTANT GUIDELINES FOR EMAIL THREAD ANALYSIS:
                                
                                1. IDENTIFYING THE LATEST EMAIL:
                                   - The latest email will always be the first message in the provided content.
                                   - It may be visually separated from previous messages in the thread.
                                   - It will have the most recent timestamp.
                                   - In many email formats, older messages are indented or preceded by ">" or other quote markers.

                                2. CLASSIFICATION PRIORITY:
                                   - ALWAYS prioritize the content of the latest email for classification, even if it's brief.
                                   - The subject line should be considered but given lower priority than the actual message content.
                                   - When the latest email clearly indicates a purpose (e.g., "Please send me my policy document"), 
                                     use that for classification, regardless of the subject line or previous messages.

                                3. USING CONTEXT FROM PREVIOUS MESSAGES:
                                   - Only reference previous messages in the thread if:
                                     a) The latest email is very brief (e.g., "Please do this for me" or "Can you help with this?")
                                     b) The latest email explicitly references previous context (e.g., "As discussed below...")
                                     c) The latest email would be ambiguous without thread context
                                
                                4. EXAMPLES OF PROPER THREAD ANALYSIS:
                                   - Example 1: Latest email says "Please send me my policy document" but thread is about a claim
                                     → Classify as "document request" (prioritize latest message)
                                   - Example 2: Latest email says "Please help with this" and previous message discusses vehicle tracking
                                     → Use thread context to classify as "vehicle tracking"
                                   - Example 3: Latest email discusses multiple topics
                                     → Prioritize based on the main request in the latest email
                                
                                5. COMMON PITFALLS TO AVOID:
                                   - Don't be misled by a subject line that doesn't match the latest email content
                                   - Don't classify based on previous messages if the latest email has changed the topic
                                   - Don't assume the topic hasn't changed just because it's the same thread

                                Ensure your output conforms to the following JSON format with the following keys:
                                {  
                                "classification": ["category1", "category2", "category3"],  
                                "rsn_classification": "answer",
                                "action_required": "answer",  
                                "sentiment": "answer"
                                }"""                          
                },
                {"role": "user",
                "content": f"Please summarize the following text:\n\n{cleaned_text}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.2
        ) 
        
        # JSONIFY THE APEX CLASSIFICATION OUTPUT
        try:
            json_output = json.loads(response.choices[0].message.content)
            
            # GET THE TOKEN USAGE FOR THE APEX CLASSIFICATION CALL
            completion_tokens = response.usage.completion_tokens
            prompt_tokens = response.usage.prompt_tokens
            apex_cost_usd = (completion_tokens/1000000 * model_costs[deployment]["completion_token_cost_pm"] * FX_RATE) + (prompt_tokens/1000000 * model_costs[deployment]["prompt_token_cost_pm"] * FX_RATE)
 
        except json.JSONDecodeError as je:
            print(f"JSON parsing error in categorise: {je}")
            print(f"Raw response content: {response.choices[0].message.content}")
            raise Exception(f"Failed to parse JSON response in categorise: {str(je)}")
        
        # --> START APEX ACTION CHECK BLOCK 
        try:
            action_check_response = await apex_action_check(text)
            
            # CHECK IF THE ACTION CHECK WAS SUCCESSFUL
            if action_check_response["response"] == "200":
                action_check_result = action_check_response["message"]["action_required"]
                
                # ADD THE COST FOR THE APEX ACTION CHECK TO THE TOTAL COST - THIS WILL NEED TO BE UPDATED WHETHER THE ACTION CHECK IS SUCCESSFUL OR NOT
                apex_cost_usd += action_check_response["message"]["apex_cost_usd"]

                # CHECK IF THE APEX ACTION CHECK AGENT RESULT IS DIFFERENT FROM THE APEX CLASSIFICATION AGENT 
                if action_check_result != json_output["action_required"]:
                    print(f"Action check override: Original={json_output['action_required']}, New={action_check_result}")
                    
                    # IF THE CHECK SHOWS DIFFERENT RESULT THEN OVERRIDE THE APEX CLASSIFICATION RESULT WITH THE APEX ACTION CHECK RESULT
                    json_output["action_required"] = action_check_result
               
                else:
                   # IF THE RESULTS ARE THE SAME THEN LEAVE THE APEX CLASSIFICATION RESULT AS IS
                   pass
                
        except Exception as e:
            # IF THE APEX ACTION CHECK FAILS THEN LEAVE THE APEX CLASSIFICATION RESULT AS IS
            print(f"Error in action check response: {str(e)}")
            json_output = json_output
            
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
            apex_prioritize_response = await apex_prioritize(text, json_output["classification"])
            print(type(json_output["classification"]))
            print("All Categories: " ,json_output["classification"])
            print("First element: ",json_output["classification"][0])
            print("Final Category: ", apex_prioritize_response["message"]["final_category"])
            
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

        # --> END OF APEX PRIORITIZE BLOCK

        json_output.update({"apex_cost_usd": round(apex_cost_usd, 5)})
        
        return {"response": "200", "message": json_output}
        
    except Exception as e: 
        print(f"Error in apex_categorise: {str(e)}")
        return {"response": "500", "message": str(e)}


# LLM AGENT TO CHECK IF THE CLASSIFICATION HAS BEEN DONE CORRECTLTY AND ALIGNS WITH CATEGORISATION PRIORITIES
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
                1. Use the provided email context and the priority list of categories to make a final decision on a single most appropriate category. The final decision must be based on the context of the email as the primary factor. Only refer to the below priority list if there is ambiguity or uncertainty in determining the single most appropriate category.
                2. Only if there is ambiguity and more than one possible category for the email context, then you must consider the following category priority list when making your decision (1 is highest priority): 
                    
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
                    
                    You must evaluate the category list and use the email context AND the above priority list when selecting the most applicable single category.
                    
                    Example1:  if the email categories are "vehicle tracking", "online/app", "claims", you must select "vehicle tracking" as the final category based on the priority list.
                    Example2:  if the email categories are "document request", "claims", "refund request", you must select "claims" as the final category based on the priority list.
                    Example3:  if the email categories are "document_request", you must select "document_request" as the final category based on the priority list.
                    
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

        try:
            json_output = json.loads(response.choices[0].message.content)
        except json.JSONDecodeError as je:
            print(f"JSON parsing error in action check: {je}")
            print(f"Raw response content: {response.choices[0].message.content}")
            raise Exception(f"Failed to parse JSON response in action check: {str(je)}")

        completion_tokens = response.usage.completion_tokens
        prompt_tokens = response.usage.prompt_tokens
        
        cost_usd = (completion_tokens/1000000 * model_costs[deployment]["completion_token_cost_pm"] * FX_RATE) + (prompt_tokens/1000000 * model_costs[deployment]["prompt_token_cost_pm"] * FX_RATE)
                
        json_output.update({"apex_cost_usd": round(cost_usd, 5)})
        
        return {"response": "200", "message": json_output}

    except Exception as e:
        print(f"Error in apex_action_check: {str(e)}")
        return {"response": "500", "message": str(e)}



# Synchronous versions for backward compatibility
def apex_categorise_sync(text):
    return asyncio.run(apex_categorise(text))

def apex_action_check_sync(text):
    return asyncio.run(apex_action_check(text))
