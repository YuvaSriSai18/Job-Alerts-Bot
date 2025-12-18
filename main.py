from fastapi import FastAPI, Request, Form, HTTPException, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
import os
import json

load_dotenv()

from Repository.Youtube import Youtube
from Repository.Firebase import Firebase
from Repository.sendGrid import SendGridService
from utils.helpers import (
    is_allowed_email,
    create_verification_token,
    verify_verification_token,
    create_unsubscribe_token,
    verify_unsubscribe_token
)


app = FastAPI()

YoutubeObj = Youtube()
FirebaseObj = Firebase()
SendGridObj = SendGridService()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

BASE_URL = os.getenv("BASE_URL", "http://localhost:8001")


@app.get("/", response_class=HTMLResponse)
async def home_route(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/register")
async def register_user(email: str = Form(...)):
    email = email.lower().strip()

    if not is_allowed_email(email):
        raise HTTPException(status_code=400, detail="Invalid email")

    if FirebaseObj.exists("subscribers", "email", email):
        raise HTTPException(status_code=409, detail="Email already registered")

    verification_token = create_verification_token(email)
    unsubscribe_token = create_unsubscribe_token(email)

    FirebaseObj.set_document(
        "subscribers",
        email,
        {
            "email": email,
            "isVerified": False,
            "subscribed": False,
            "unsubscribeToken": unsubscribe_token,
            "createdAt": datetime.now(timezone.utc)
        }
    )

    verify_link = f"{BASE_URL}/verify-email/{verification_token}"

    SendGridObj.send_verification_email(
        email=email,
        verify_link=verify_link
    )

    return JSONResponse(
        {"message": "Verification email sent"},
        status_code=200
    )


@app.get("/verify-email/{token}", response_class=HTMLResponse)
async def verify_email(token: str, request: Request):
    email = verify_verification_token(token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid token")

    FirebaseObj.update_document(
        "subscribers",
        email,
        {"isVerified": True, "subscribed": True}
    )

    return templates.TemplateResponse(
        "subscription_confirmed.html",
        {"request": request, "email": email}
    )


@app.get("/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe_user(token: str, request: Request):
    email = verify_unsubscribe_token(token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid token")

    FirebaseObj.update_document(
        "subscribers",
        email,
        {"subscribed": False}
    )

    return templates.TemplateResponse(
        "unsubscribe.html",
        {"request": request, "email": email}
    )


@app.get("/api/cron/job-alert")
async def cron_job_alert(x_cron_secret: str = Header(None)):
    """
    Protected cron endpoint for job alert scheduler.
    Runs the job alert logic exactly once per request.
    
    Called by GitHub Actions every 6 hours.
    
    Security:
    - Header: x-cron-secret
    - Compare against environment variable: CRON_SECRET
    - Returns HTTP 403 if invalid
    - Returns JSON with execution details
    """
    
    # ===== SECURITY: Validate cron secret =====
    CRON_SECRET = os.getenv("CRON_SECRET")
    
    if not CRON_SECRET:
        return JSONResponse(
            {"error": "CRON_SECRET not configured"},
            status_code=500
        )
    # print(CRON_SECRET)
    if not x_cron_secret or x_cron_secret != CRON_SECRET:
        return JSONResponse(
            {"error": "Unauthorized"},
            status_code=403
        )
    
    try:
        print("\n" + "="*60)
        print(f"🔔 [CRON] Starting job alert at {datetime.now(timezone.utc)}")
        print("="*60)
        
        # ===== STEP 1: Configuration =====
        CHANNEL_ID = "UCbEd9lNwkBGLFGz8ZxsZdVA"
        MAX_VIDEOS = 3
        
        print(f"\n📋 [CRON] Configuration:")
        print(f"   - Channel ID: {CHANNEL_ID}")
        print(f"   - Max Videos: {MAX_VIDEOS}")
        
        # ===== STEP 2: Fetch state and get videos =====
        print(f"\n📺 [CRON] Fetching videos...")
        
        state = FirebaseObj.get_document("system_state", "youtube")
        last_processed_at = state.get("lastProcessedAt") if state else None
        
        print(f"   - Last processed: {last_processed_at or 'Never'}")
        
        videos = YoutubeObj.get_recent_videos(
            CHANNEL_ID,
            MAX_VIDEOS,
            published_after=last_processed_at
        )
        
        if not videos:
            print("   ⚠️  No new videos found")
            return JSONResponse(
                {"status": "success", "message": "No new videos", "videos_processed": 0},
                status_code=200
            )
        
        print(f"   ✅ Found {len(videos)} video(s)")
        for v in videos:
            print(f"      📹 {v['title'][:50]}...")
        
        # ===== STEP 3: Extract jobs from videos =====
        print(f"\n🔍 [CRON] Extracting jobs from videos...")
        
        all_openings = []
        videos_with_jobs = 0
        
        for i, video in enumerate(videos, 1):
            try:
                print(f"\n   [{i}/{len(videos)}] Processing: {video['videoId']}")
                
                result = YoutubeObj.process_video_for_jobs(video["videoId"])
                
                # DEBUG: Print result structure
                print(f"      Result type: {type(result)}, Result: {result}")
                
                if result and isinstance(result, dict):
                    is_job_video = result.get("isJobVideo", False)
                    openings = result.get("openings", [])
                    
                    print(f"      isJobVideo: {is_job_video}, Openings count: {len(openings) if openings else 0}")
                    
                    if is_job_video and openings and len(openings) > 0:
                        job_count = len(openings)
                        print(f"      ✅ Found {job_count} job opening(s)")
                        all_openings.extend(openings)
                        videos_with_jobs += 1
                    else:
                        print(f"      ℹ️  No jobs in this video (isJobVideo={is_job_video}, openings={len(openings) if openings else 0})")
                else:
                    print(f"      ⚠️  Invalid result format: {result}")
                    
            except json.JSONDecodeError as e:
                print(f"      ❌ JSON Parse Error: {str(e)}")
                print(f"         This usually means Gemini returned invalid JSON")
                continue
            except Exception as e:
                print(f"      ❌ Error processing video: {type(e).__name__}: {str(e)}")
                import traceback
                traceback.print_exc()
                continue
        
        if not all_openings:
            print(f"\n📭 [CRON] No job openings found in any video")
            
            # Update state anyway
            if videos:
                latest_published_at = max(v["publishedAt"] for v in videos)
                FirebaseObj.set_document(
                    "system_state",
                    "youtube",
                    {"lastProcessedAt": latest_published_at}
                )
            
            return JSONResponse(
                {
                    "status": "success",
                    "message": "No jobs found",
                    "videos_processed": len(videos),
                    "videos_with_jobs": videos_with_jobs,
                    "jobs_extracted": 0
                },
                status_code=200
            )
        
        print(f"\n🎯 [CRON] Total jobs extracted: {len(all_openings)}")
        
        # ===== STEP 4: Get active subscribers =====
        print(f"\n👥 [CRON] Fetching subscribers...")
        
        subscribers = FirebaseObj.get_all_documents("subscribers")
        active = [
            s for s in subscribers
            if s.get("subscribed") and s.get("isVerified")
        ]
        
        if not active:
            print("   📭 No active subscribers")
            
            # Update state
            if videos:
                latest_published_at = max(v["publishedAt"] for v in videos)
                FirebaseObj.set_document(
                    "system_state",
                    "youtube",
                    {"lastProcessedAt": latest_published_at}
                )
            
            return JSONResponse(
                {
                    "status": "success",
                    "message": "No active subscribers",
                    "videos_processed": len(videos),
                    "videos_with_jobs": videos_with_jobs,
                    "jobs_extracted": len(all_openings),
                    "emails_sent": 0
                },
                status_code=200
            )
        
        print(f"   Total subscribers: {len(subscribers)}")
        print(f"   Active subscribers: {len(active)}")
        print(f"   Emails to send: {[s.get('email') for s in active]}")
        
        # ===== STEP 5: Send job alerts =====
        print(f"\n📧 [CRON] Sending job alerts...")
        
        emails_sent = 0
        emails_failed = 0
        
        for i, sub in enumerate(active, 1):
            try:
                email = sub.get("email")
                token = sub.get("unsubscribeToken")
                
                if not email or not token:
                    print(f"   [{i}/{len(active)}] ⚠️  Skipping - missing data")
                    emails_failed += 1
                    continue
                
                unsubscribe_link = f"{BASE_URL}/unsubscribe/{token}"
                
                SendGridObj.send_job_alert_email(
                    email=email,
                    openings=all_openings,
                    unsubscribe_link=unsubscribe_link
                )
                
                print(f"   [{i}/{len(active)}] ✅ Sent to {email}")
                emails_sent += 1
                
            except Exception as e:
                print(f"   [{i}/{len(active)}] ❌ Failed: {str(e)}")
                emails_failed += 1
        
        # ===== STEP 6: Update state =====
        print(f"\n💾 [CRON] Updating state...")
        
        if videos:
            latest_published_at = max(v["publishedAt"] for v in videos)
            FirebaseObj.set_document(
                "system_state",
                "youtube",
                {"lastProcessedAt": latest_published_at}
            )
            print(f"   ✅ State updated: {latest_published_at}")
        
        # ===== COMPLETION =====
        print(f"\n🎉 [CRON] Job completed successfully!")
        print(f"   - Videos processed: {len(videos)}")
        print(f"   - Videos with jobs: {videos_with_jobs}")
        print(f"   - Total jobs: {len(all_openings)}")
        print(f"   - Emails sent: {emails_sent}")
        print(f"   - Emails failed: {emails_failed}")
        print("="*60 + "\n")
        
        return JSONResponse(
            {
                "status": "success",
                "message": "Job alert completed",
                "videos_processed": len(videos),
                "videos_with_jobs": videos_with_jobs,
                "jobs_extracted": len(all_openings),
                "emails_sent": emails_sent,
                "emails_failed": emails_failed
            },
            status_code=200
        )
        
    except Exception as e:
        print(f"\n❌ [CRON] FATAL ERROR: {str(e)}")
        print("="*60 + "\n")
        import traceback
        traceback.print_exc()
        
        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)

"""
APPLICATION FLOW:
1. Subscribe -> User enters email, stored in Firestore with isVerified=False
2. Verification -> User receives verification email with JWT token
3. Verify endpoint -> Validates token, sets isVerified=True and subscribed=True
4. Cron job -> /api/cron/job-alert endpoint (called by GitHub Actions every 6 hours)
5. Unsubscribe -> User clicks unsubscribe link with JWT token to stop receiving emails

CRON EXECUTION (GitHub Actions):
- GitHub Actions calls GET /api/cron/job-alert with x-cron-secret header every 6 hours
- Endpoint authenticates using CRON_SECRET environment variable
- Processes YouTube videos, extracts jobs, and sends emails to subscribers
- Stateless HTTP endpoint: safe to call multiple times
- State tracked in Firestore (lastProcessedAt prevents duplicate processing)
"""