import os
import sys
import psycopg2
import requests
from dotenv import load_dotenv
import warnings
from requests.packages.urllib3.exceptions import InsecureRequestWarning

# Suppress SSL warnings
warnings.simplefilter('ignore', InsecureRequestWarning)

# Load env
load_dotenv()

# --- USER PROVIDED TOKEN FOR TESTING ---
TEST_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ6encwOTc3MyIsInR5cGUiOiJhY2Nlc3MiLCJpYXQiOjE3NjQ3Mzk0ODYsImV4cCI6MTc4MDI5MTQ4Niwic2NvcGVzIjpbIm1vZGVsczpyZWFkIiwiY2hhdDpiYXNlIiwiY2hhdDphZ2VudDpteS1hZ2VudC1mb3ItdGVzdCIsImNoYXQ6YWdlbnQ6bXktZG9jLWFnZW50IiwiZW1iZWRkaW5nczpiYXNlIl19.nmUg1FYM9UlSpe6nC7j52y4v215k3qKgaNZaPzN0ZZk"

def test_db():
    raw_url = os.environ.get("PGVECTOR_URL")
    # Fix URL for psycopg2
    url = raw_url.replace("postgresql+psycopg2://", "postgresql://")
    
    print(f"Testing DB connection to: {url}")
    try:
        conn = psycopg2.connect(url)
        conn.close()
        print("✅ DB Connection Success!")
        return True
    except Exception as e:
        print(f"❌ DB Connection Failed: {e}")
        return False

def test_api():
    base_url = os.environ.get("EMBED_API_BASE")
    
    # USE THE TEST TOKEN
    api_key = TEST_TOKEN
    
    model = os.environ.get("EMBED_MODEL_NAME", "nvidia/nv-embed-v2")
    
    print(f"Testing Embed API connection to: {base_url} (Model: {model})")
    
    # Try a standard OpenAI-style embedding request
    try:
        full_url = f"{base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "input": "Hello world",
            "model": model
        }
        
        # Verify=False to bypass SSL issues
        resp = requests.post(full_url, json=payload, headers=headers, timeout=5, verify=False)
        
        if resp.status_code == 200:
            print("✅ API Connection Success! (Token works)")
            # print(resp.json())
            return True
        else:
            print(f"❌ API Error: Status {resp.status_code}")
            print(f"Response: {resp.text}")
            return False
            
    except Exception as e:
        print(f"❌ API Connection Failed: {e}")
        return False

if __name__ == "__main__":
    print("--- DIAGNOSTIC START ---")
    db_ok = test_db()
    api_ok = test_api()
    print("--- DIAGNOSTIC END ---")
    
    if not (db_ok and api_ok):
        sys.exit(1)