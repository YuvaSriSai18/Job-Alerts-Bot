#!/usr/bin/env python3
"""Debug script to test the job extraction pipeline"""

from Repository.Youtube import Youtube
from dotenv import load_dotenv
import json

load_dotenv()

# Test the video that's returning "No jobs found"
video_id = "P-9izfdbKDU"

print("="*60)
print(f"Testing video: {video_id}")
print("="*60)

yt = Youtube()

# Step 1: Get transcript
print("\n1️⃣  Fetching transcript...")
transcript = yt.get_transcript(video_id)
print(f"   Transcript length: {len(transcript)} chars")
print(f"   First 100 chars: {transcript[:100]}")

# Step 2: Get title and description
print("\n2️⃣  Fetching title and description...")
meta = yt.get_title_description(video_id)
print(f"   Title: {meta['title']}")
print(f"   Description length: {len(meta['description'])} chars")

# Step 3: Extract jobs
print("\n3️⃣  Extracting jobs with Gemini...")
result = yt.extract_jobs_with_gemini(
    meta["title"],
    meta["description"],
    transcript
)

print(f"\n   Result type: {type(result)}")
print(f"   Full result:\n{json.dumps(result, indent=2)}")

# Step 4: Check conditions
print("\n4️⃣  Checking conditions...")
print(f"   result: {result}")
print(f"   isinstance(result, dict): {isinstance(result, dict)}")
if result and isinstance(result, dict):
    is_job_video = result.get("isJobVideo", False)
    openings = result.get("openings", [])
    print(f"   isJobVideo: {is_job_video}")
    print(f"   openings: {openings}")
    print(f"   len(openings): {len(openings) if openings else 0}")
    print(f"   Condition (is_job_video and openings and len(openings) > 0): {is_job_video and openings and len(openings) > 0}")
