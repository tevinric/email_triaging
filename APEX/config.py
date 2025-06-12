import os

ENV_TYPE = os.environ.get('ENV_TYPE')

# PRIMARY AZURE OPENAI CONNECTION DETAILS
AZURE_OPENAI_KEY=os.environ.get('AZURE_OPENAI_KEY')
AZURE_OPENAI_ENDPOINT=os.environ.get('AZURE_OPENAI_ENDPOINT')

# BACKUP AZURE OPENAI CONNECTION DETAILS
AZURE_OPENAI_BACKUP_KEY=os.environ.get('AZURE_OPENAI_BACKUP_KEY')
AZURE_OPENAI_BACKUP_ENDPOINT=os.environ.get('AZURE_OPENAI_BACKUP_ENDPOINT')

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
DEFAULT_EMAIL_ACCOUNT = ''

# INTERVAL IN SECONDS(30) 
EMAIL_FETCH_INTERVAL = 30

# AZURE BLOB STORAGE SETTINGS
AZURE_STORAGE_CONNECTION_STRING = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
BLOB_CONTAINER_NAME = os.environ.get('BLOB_CONTAINER_NAME')
AZURE_STORAGE_PUBLIC_URL = os.environ.get('AZURE_STORAGE_PUBLIC_URL')  # Public URL for blob storage account

# Import the routing configurations
POLICY_SERVICES=os.environ.get('POLICY_SERVICES')
TRACKING_MAILS=os.environ.get('TRACKING_MAILS')
CLAIMS_MAILS=os.environ.get('CLAIMS_MAILS')
ONLINESUPPORT_MAILS=os.environ.get('ONLINESUPPORT_MAILS')
INSURANCEADMIN_MAILS=os.environ.get('INSURANCEADMIN_MAILS')
DIGITALCOMMS_MAILS=os.environ.get('DIGITALCOMMS_MAILS')
CONNEX_TEST=os.environ.get('CONNEX_TEST')

# Configure the mail-template mappings for autoresponse mails
def get_email_prefix(email):
    if email and "@" in email:
        return email.split("@")[0]
    return email

ONLINESUPPORT_MAILS_MAPPING = get_email_prefix(ONLINESUPPORT_MAILS)
POLICY_SERVICES_MAPPING = get_email_prefix(POLICY_SERVICES)
TRACKING_MAILS_MAPPING = get_email_prefix(TRACKING_MAILS)
CLAIMS_MAILS_MAPPING = get_email_prefix(CLAIMS_MAILS)
DIGITALCOMMS_MAILS_MAPPING = get_email_prefix(DIGITALCOMMS_MAILS)

# Set the mapping based on the deployment environment

if ENV_TYPE == 'DEV':
    EMAIL_TO_FOLDER_MAPPING = {
        "onlinesupport-aitest": "onlinesupport",
        "policyservice-aitest": "policyservice",
        "tracking-aitest": "tracking",
        "digital.comms-aitest": "digitalcomms",
        "claims-aitest": "claims",
    }
elif ENV_TYPE == 'SIT':
    EMAIL_TO_FOLDER_MAPPING = {
        "onlinesupport-aisit": "onlinesupport",
        "policyservice-aisit": "policyservice",
        "tracking-aisit": "tracking",
        "digital.comms-aisit": "digitalcomms",
        "claims-aisit": "claims",
    }
elif ENV_TYPE == 'UAT':
    EMAIL_TO_FOLDER_MAPPING = {
        "onlinesupport-aiuat": "onlinesupport",
        "policyservice-aiuat": "policyservice",
        "tracking-aiuat": "tracking",
        "digital.comms-aiuat": "digitalcomms",
        "claims-aiuat": "claims",
    }
elif ENV_TYPE == 'PREPROD':
    EMAIL_TO_FOLDER_MAPPING = {
        "onlinesupport-aipreprod": "onlinesupport",
        "policyservice-aipreprod": "policyservice",
        "tracking-aipreprod": "tracking",
        "digital.comms-aipreprod": "digitalcomms",
        "claims-aipreprod": "claims",
    }

elif ENV_TYPE == 'PROD':
    EMAIL_TO_FOLDER_MAPPING = {
        "onlinesupport": "onlinesupport",
        "policyservice": "policyservice",
        "tracking": "tracking",
        "digital.comms": "digitalcomms",
        "claims": "claims",
    }

# Configure subject lines per template
EMAIL_SUBJECT_MAPPING = {
    "onlinesupport": "Thank you for contacting us",
    "policyservice": "Thank you for contacting us", 
    "tracking": "Auto Reply",
    "claims": "Auto Response",
    "digitalcomms": "Auto Reply",
    "default": "Thank you for contacting us"
}


