import os
import json
import ee
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

def test_production_auth():
    key_json_str = os.getenv("EE_SERVICE_ACCOUNT_KEY_JSON")
    
    if not key_json_str:
        print("❌ Error: EE_SERVICE_ACCOUNT_KEY_JSON not found in environment!")
        return

    try:
        # Parse the JSON string from environment variables
        key_dict = json.loads(key_json_str)
        
        # Initialize credentials directly via the Service Account key dictionary
        credentials = ee.ServiceAccountCredentials(key_dict['client_email'], key_data=key_json_str)
        ee.Initialize(credentials=credentials, project='airflow-gcp-project')
        
        print("✅ Success: Authenticated with Earth Engine using Service Account!")
        
        # Pull a small piece of metadata from a public dataset to prove data access
        dem = ee.Image('USGS/SRTMGL1_003')
        print("🛰️ Verified Data Access. Dataset ID:", dem.getInfo()['id'])
        
    except Exception as e:
        print("❌ Production Authentication Failed!")
        print(f"Details: {str(e)}")

if __name__ == "__main__":
    test_production_auth()
