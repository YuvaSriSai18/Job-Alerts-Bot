#!/usr/bin/env python3
"""
Test script for the Vercel serverless cron endpoint.
Tests the /api/cron/job-alert endpoint locally.
"""

import os
import httpx
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def test_cron_endpoint():
    """Test the cron endpoint with proper authentication."""
    
    # Get configuration
    base_url = os.getenv("BASE_URL", "http://localhost:8001")
    cron_secret = os.getenv("CRON_SECRET", "test-secret-key")
    
    print(f"\n{'='*60}")
    print("🧪 Testing Vercel Serverless Cron Endpoint")
    print(f"{'='*60}\n")
    
    print(f"Base URL: {base_url}")
    print(f"Using CRON_SECRET: {'***' + cron_secret[-8:] if cron_secret else 'NOT SET'}")
    
    # Test 1: Without secret (should fail with 403)
    print(f"\n\n{'─'*60}")
    print("Test 1: Missing x-cron-secret header (should return 403)")
    print(f"{'─'*60}\n")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{base_url}/api/cron/job-alert")
            print(f"Status: {response.status_code}")
            print(f"Response: {response.json()}")
            
            if response.status_code == 403:
                print("✅ Correctly rejected unauthorized request")
            else:
                print("❌ Expected 403, got different status")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    # Test 2: With wrong secret (should fail with 403)
    print(f"\n\n{'─'*60}")
    print("Test 2: Wrong x-cron-secret header (should return 403)")
    print(f"{'─'*60}\n")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{base_url}/api/cron/job-alert",
                headers={"x-cron-secret": "wrong-secret"}
            )
            print(f"Status: {response.status_code}")
            print(f"Response: {response.json()}")
            
            if response.status_code == 403:
                print("✅ Correctly rejected wrong secret")
            else:
                print("❌ Expected 403, got different status")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    # Test 3: With correct secret (should execute)
    print(f"\n\n{'─'*60}")
    print("Test 3: Correct x-cron-secret header (should execute)")
    print(f"{'─'*60}\n")
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            print("Sending request... (this may take a minute)")
            response = await client.get(
                f"{base_url}/api/cron/job-alert",
                headers={"x-cron-secret": cron_secret}
            )
            print(f"\nStatus: {response.status_code}")
            print(f"Response:")
            
            import json
            result = response.json()
            print(json.dumps(result, indent=2))
            
            if response.status_code == 200 and result.get("status") == "success":
                print("\n✅ Cron endpoint executed successfully!")
                print(f"   - Videos processed: {result.get('videos_processed', 0)}")
                print(f"   - Videos with jobs: {result.get('videos_with_jobs', 0)}")
                print(f"   - Jobs extracted: {result.get('jobs_extracted', 0)}")
                print(f"   - Emails sent: {result.get('emails_sent', 0)}")
                print(f"   - Emails failed: {result.get('emails_failed', 0)}")
            else:
                print("⚠️  Response received but unexpected status/format")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print(f"\n{'='*60}")
    print("✅ Testing complete")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    print("\n🚀 Starting cron endpoint tests...\n")
    asyncio.run(test_cron_endpoint())
