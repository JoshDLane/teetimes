#!/usr/bin/env python3
"""
Test script to verify Bright Data Web Unlocker proxy configuration
"""
import os

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_proxy_connection():
    """Test the proxy connection using requests library"""
    
    # Get proxy configuration from environment
    proxy_host = os.getenv("PROXY_HOST")
    proxy_port = os.getenv("PROXY_PORT")
    proxy_username = os.getenv("PROXY_USERNAME")
    proxy_password = os.getenv("PROXY_PASSWORD")
    
    if not all([proxy_host, proxy_port, proxy_username, proxy_password]):
        print("❌ Missing proxy configuration in .env file")
        return False
    
    print(f"🔧 Testing proxy: {proxy_host}:{proxy_port}")
    print(f"👤 Username: {proxy_username}")
    print(f"🔑 Password: {proxy_password[:10]}...{proxy_password[-10:]}")
    
    # Test different authentication methods
    test_methods = [
        {
            "name": "Standard HTTP Proxy",
            "proxies": {
                "http": f"http://{proxy_username}:{proxy_password}@{proxy_host}:{proxy_port}",
                "https": f"http://{proxy_username}:{proxy_password}@{proxy_host}:{proxy_port}"
            }
        },
        {
            "name": "With explicit auth",
            "proxies": {
                "http": f"http://{proxy_host}:{proxy_port}",
                "https": f"http://{proxy_host}:{proxy_port}"
            },
            "auth": requests.auth.HTTPProxyAuth(proxy_username, proxy_password)
        }
    ]
    
    for method in test_methods:
        print(f"\n🧪 Testing: {method['name']}")
        try:
            kwargs = {"proxies": method["proxies"], "timeout": 10}
            if "auth" in method:
                kwargs["auth"] = method["auth"]
                
            response = requests.get("http://geo.brdtest.com/welcome.txt", **kwargs)
            
            if response.status_code == 200:
                print("✅ Proxy connection successful!")
                print(f"📄 Response: {response.text.strip()}")
                return True
            else:
                print(f"❌ Failed with status code: {response.status_code}")
                print(f"📄 Response: {response.text[:200]}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Connection failed: {e}")
    
    return False

def test_curl_equivalent():
    """Test using the exact same format as the curl command from Bright Data"""
    print("\n🔄 Testing curl-equivalent method...")
    
    # This mimics the curl command from your email
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer 249084963b762c2a5f57e6305612d0515ea62e0fee358ad7aab27c06c82c6f8a"
    }
    
    data = {
        "zone": "web_unlocker2",
        "url": "http://geo.brdtest.com/welcome.txt",
        "format": "raw"
    }
    
    try:
        response = requests.post(
            "https://api.brightdata.com/request",
            headers=headers,
            json=data,
            timeout=10
        )
        
        if response.status_code == 200:
            print("✅ Bright Data API call successful!")
            print(f"📄 Response: {response.text.strip()}")
            return True
        else:
            print(f"❌ API call failed with status code: {response.status_code}")
            print(f"📄 Response: {response.text[:200]}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ API call failed: {e}")
    
    return False

if __name__ == "__main__":
    print("🧪 Testing Bright Data Web Unlocker Configuration")
    print("=" * 60)
    
    # Test proxy method
    proxy_success = test_proxy_connection()
    
    # Test API method
    api_success = test_curl_equivalent()
    
    if proxy_success or api_success:
        print("\n🎉 At least one method is working!")
        if proxy_success:
            print("✅ Proxy method works - you can use it with Selenium")
        if api_success:
            print("✅ API method works - you might want to use this instead")
    else:
        print("\n🔧 Both methods failed. Please check:")
        print("1. Your API key is correct")
        print("2. Your zone name is correct")
        print("3. Your account is active")
        print("\n📧 Contact Bright Data support if issues persist")
