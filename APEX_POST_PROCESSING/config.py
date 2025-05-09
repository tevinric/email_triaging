import os

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