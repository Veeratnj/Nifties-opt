"""
Test script to verify the kill switch API is working correctly
"""
import requests
import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/db")

def test_kill_switch(token: str = "25"):
    """Test the kill switch API endpoint"""
    url = f"{BASE_URL}/admin/kill-trade-signal"
    payload = {"token": token}
    
    print(f"Testing kill switch for token: {token}")
    print(f"URL: {url}")
    print(f"Payload: {payload}")
    print("-" * 50)
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        
        print(f"✅ Response Status: {response.status_code}")
        print(f"Response Data: {data}")
        print("-" * 50)
        
        kill_status = data.get("kill", False)
        if kill_status:
            print("🔴 KILL SWITCH ACTIVE - Trade will be exited")
        else:
            print("🟢 KILL SWITCH INACTIVE - Normal trading")
            
        return kill_status
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error calling API: {e}")
        return False

if __name__ == "__main__":
    # Test with token "25"
    test_kill_switch("25")
    
    print("\n" + "=" * 50)
    print("To activate the kill switch, you need to:")
    print("1. Call the API endpoint that sets kill=true for the token")
    print("2. Or update the database directly")
    print("=" * 50)
