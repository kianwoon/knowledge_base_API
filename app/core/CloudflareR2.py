import os
import boto3
import urllib.parse
from botocore.exceptions import NoCredentialsError, ClientError
from app.core.config import config

# --- Configuration ---
# Get Cloudflare R2 credentials from config
ACCOUNT_ID =  config.get('cloudflare_r2', {}).get('account_id', '')
ACCESS_KEY_ID =  config.get('cloudflare_r2', {}).get('access_key_id', '') 
SECRET_ACCESS_KEY =  config.get('cloudflare_r2', {}).get('secret_access_key', '')
BUCKET_NAME =  config.get('cloudflare_r2', {}).get('bucket_name', 'knowledgebase')
R2_ENDPOINT_URL = f'https://{ACCOUNT_ID}.r2.cloudflarestorage.com'

# Initialize the S3 client for R2
s3_client = boto3.client(
    's3',
    endpoint_url=R2_ENDPOINT_URL,
    aws_access_key_id=ACCESS_KEY_ID,
    aws_secret_access_key=SECRET_ACCESS_KEY,
    region_name='auto'  # R2 specific setting
)


def upload_file(file_path, object_name=None):
    """Upload a file to the R2 bucket.

    :param file_path: Path to the file to upload.
    :param object_name: S3 object name. If not specified, file_path's base name is used.
    :return: True if file was uploaded, else False.
    """
    if object_name is None:
        object_name = os.path.basename(file_path)

    try:
        print(f"Uploading {file_path} to {BUCKET_NAME}/{object_name}...")
        s3_client.upload_file(file_path, BUCKET_NAME, object_name)
        print("Upload successful.")
        return True
    except FileNotFoundError:
        print(f"Error: The file {file_path} was not found.")
        return False
    except NoCredentialsError:
        print("Error: AWS credentials not found. Configure environment variables or AWS config.")
        return False
    except ClientError as e:
        print(f"ClientError during upload: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred during upload: {e}")
        return False

def download_file(object_name, jobid:str, filename:str) -> str:
    """Download a file from the R2 bucket.

    :param object_name: S3 object name to download.
    :param jobid: Job ID for creating the folder structure.
    :param filename: Local filename to save the downloaded file as.
    :return: Path to the downloaded file if successful, else False.
    """

    download_path = os.path.join("data", "r2", jobid)

    # Ensure download directory exists
    # if not os.path.exists(download_path):
    #     os.makedirs(download_path)
    
    try:
        full_path = os.path.join(download_path, filename)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        print(f"Downloading {BUCKET_NAME}/{object_name} to {full_path}...")
        
        # Decode object_name if it's URL-encoded
        decoded_object_name = urllib.parse.unquote(object_name)
        
        s3_client.download_file(BUCKET_NAME, decoded_object_name, full_path)
 
        print(f"File downloaded to {full_path}")
    
        return full_path
    except NoCredentialsError:
        raise ValueError("Error: AWS credentials not found. Configure environment variables or AWS config.")
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            raise ValueError(f"Error: The object {object_name} does not exist in bucket {BUCKET_NAME}.")
        else:
            raise ValueError(f"ClientError during download: {e}")
    except Exception as e:
        raise ValueError(f"An unexpected error occurred during download: {e}")
