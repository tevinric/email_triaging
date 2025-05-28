import asyncio
import datetime
import os
import re
import uuid
import aiohttp
from bs4 import BeautifulSoup
from azure.storage.blob.aio import BlobServiceClient
from email_processor.email_client import get_access_token
from config import AZURE_STORAGE_CONNECTION_STRING, BLOB_CONTAINER_NAME, AZURE_STORAGE_PUBLIC_URL, EMAIL_TO_FOLDER_MAPPING

# Default mapping from email address to blob store folder
# If not defined in config.py, use the empty mapping
DEFAULT_EMAIL_TO_FOLDER_MAPPING = {}

async def get_template_from_blob(recipient_email):
    """
    Retrieve template from Azure Blob Storage based on recipient email.
    
    Args:
        recipient_email (str): Email address the message was sent to
        
    Returns:
        tuple: (template_content, template_folder) if found, (None, None) otherwise
    """
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        # Extract the mailbox name and domain from the email address
        email_parts = recipient_email.lower().split('@')
        mailbox_name = email_parts[0]
        domain = email_parts[1] if len(email_parts) > 1 else 'company.co.za'  # Default domain if not present
        
        # Check if we have a custom folder mapping for this email address
        folder_name = None
        
        # Try to match the full email address first
        if recipient_email.lower() in EMAIL_TO_FOLDER_MAPPING:
            folder_name = EMAIL_TO_FOLDER_MAPPING[recipient_email.lower()]
            print(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Using custom folder mapping for {recipient_email}: {folder_name}")
        # Then try to match just the mailbox part
        elif mailbox_name in EMAIL_TO_FOLDER_MAPPING:
            folder_name = EMAIL_TO_FOLDER_MAPPING[mailbox_name]
            print(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Using custom folder mapping for {mailbox_name}: {folder_name}")
        # If no mapping found, use the mailbox name as before
        else:
            folder_name = mailbox_name
            print(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - No custom mapping found, using mailbox name: {folder_name}")
        
        # Template file is in the folder with the same name as specified in the mapping
        # Use the domain from the email instead of hardcoding 'mail.co.za'
        template_path = f"{folder_name}/{mailbox_name}@{domain}.htm"
        
        print(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Retrieving template from path: {template_path}")
        
        # Create BlobServiceClient
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        
        # Get container client
        container_client = blob_service_client.get_container_client(BLOB_CONTAINER_NAME)
        
        # Get blob client
        blob_client = container_client.get_blob_client(template_path)
        
        # Check if blob exists
        if await blob_client.exists():
            # Download blob content
            download_stream = await blob_client.download_blob()
            template_content = await download_stream.readall()
            return template_content.decode('utf-8'), folder_name
        else:
            # Try fallback to html extension
            alt_template_path = f"{folder_name}/{mailbox_name}@{domain}.html"
            blob_client = container_client.get_blob_client(alt_template_path)
            
            if await blob_client.exists():
                download_stream = await blob_client.download_blob()
                template_content = await download_stream.readall()
                return template_content.decode('utf-8'), folder_name
            else:
                # Try one more fallback to a simple named file
                simple_template_path = f"{folder_name}/{folder_name}.html"
                blob_client = container_client.get_blob_client(simple_template_path)
                
                if await blob_client.exists():
                    download_stream = await blob_client.download_blob()
                    template_content = await download_stream.readall()
                    return template_content.decode('utf-8'), folder_name
                else:
                    print(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Template not found in blob storage for folder: {folder_name}")
                    # Return None
                    return None, None
            
    except Exception as e:
        print(f">> {timestamp} Script: autoresponse.py - Function: get_template_from_blob - Error retrieving template from blob storage: {str(e)}")
        return None, None
