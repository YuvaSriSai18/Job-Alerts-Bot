from fastapi import FastAPI, Request, Form, HTTPException, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, HttpUrl
from typing import Optional
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import os
import json


# ================== MODELS ==================

class JobOpening(BaseModel):
    role: str
    company: str
    employmentType: str          # e.g. "Full-Time", "Internship"
    workMode: str                # e.g. "Remote", "On-site", "Hybrid"
    location: str
    duration: Optional[str] = None   # for internships
    requiredSkills: list[str] = []
    summary: str
    applyLink: str


class PostJobRequest(BaseModel):
    openings: list[JobOpening]


class ContactSupportRequest(BaseModel):
    email: str
    name: Optional[str] = None
    subject: str
    description: str
    priority: Optional[str] = "medium"  # low, medium, high

load_dotenv()

from Repository.Youtube import Youtube
from Repository.Firebase import Firebase
from Repository.Gmail import GmailService
from Repository.ErrorLogs import ErrorLogs
from Repository.ContactSupport import ContactSupport
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
GmailObj = GmailService()
ErrorLogsObj = ErrorLogs()
ContactSupportObj = ContactSupport()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

BASE_URL = os.getenv("BASE_URL", "http://localhost:8001")


@app.get("/", response_class=HTMLResponse)
async def home_route(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/resubscribe", response_class=HTMLResponse)
async def resubscribe_route(request: Request):
    """Display the re-subscribe form for users who previously unsubscribed"""
    return templates.TemplateResponse("resubscribe.html", {"request": request})


@app.get("/contact-support", response_class=HTMLResponse)
async def contact_support_route(request: Request):
    """Display the contact support form"""
    return templates.TemplateResponse("contact_support.html", {"request": request})


@app.post("/register")
async def register_user(email: str = Form(...)):
    try:
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
        # print(verify_link)
        GmailObj.send_verification_email(
            email=email,
            verify_link=verify_link
        )

        return JSONResponse(
            {"message": "Verification email sent"},
            status_code=200
        )
    
    except HTTPException:
        raise
    except Exception as e:
        ErrorLogsObj.log_error(e, "user_registration", {"email": email})
        return JSONResponse(
            {"error": "Registration failed. Please try again later."},
            status_code=500
        )


@app.get("/verify-email/{token}", response_class=HTMLResponse)
async def verify_email(token: str, request: Request):
    try:
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
    
    except HTTPException:
        raise
    except Exception as e:
        ErrorLogsObj.log_error(e, "email_verification", {"token": token})
        raise HTTPException(status_code=500, detail="Email verification failed")


@app.get("/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe_user(token: str, request: Request):
    try:
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
    
    except HTTPException:
        raise
    except Exception as e:
        ErrorLogsObj.log_error(e, "user_unsubscribe", {"token": token})
        raise HTTPException(status_code=500, detail="Unsubscribe failed")


@app.post("/resubscribe")
async def resubscribe_user(email: str = Form(...)):
    """
    Handle re-subscription for users who previously unsubscribed.
    Checks if user exists and is not subscribed, then re-activates subscription.
    """
    try:
        email = email.lower().strip()

        if not is_allowed_email(email):
            raise HTTPException(status_code=400, detail="Invalid email")

        # Check if user exists in subscribers collection
        existing_user = FirebaseObj.get_document("subscribers", email)
        
        if not existing_user:
            raise HTTPException(
                status_code=404, 
                detail="Email not found. Please register as a new subscriber."
            )

        # Check if already subscribed
        if existing_user.get("subscribed"):
            raise HTTPException(
                status_code=409, 
                detail="Email is already active. You're already receiving job alerts!"
            )

        # Create new verification token for re-activation
        verification_token = create_verification_token(email)

        # Send re-subscription verification email
        verify_link = f"{BASE_URL}/verify-email/{verification_token}"
        GmailObj.send_verification_email(
            email=email,
            verify_link=verify_link
        )

        return JSONResponse(
            {"message": "Re-subscription verification email sent"},
            status_code=200
        )
    
    except HTTPException:
        raise
    except Exception as e:
        ErrorLogsObj.log_error(e, "user_resubscribe", {"email": email})
        return JSONResponse(
            {"error": "Re-subscription failed. Please try again later."},
            status_code=500
        )


@app.post("/api/contact-support")
async def contact_support(body: ContactSupportRequest):
    """
    Handle user support requests and store them in Firebase.
    
    Body (JSON):
    {
      "email": "user@example.com",
      "name": "John Doe",
      "subject": "Issue with email verification",
      "description": "I'm not receiving verification emails...",
      "priority": "high"
    }
    """
    try:
        # Validate email
        if not is_allowed_email(body.email):
            raise HTTPException(status_code=400, detail="Invalid email address")
        
        # Validate priority
        if body.priority not in ["low", "medium", "high"]:
            raise HTTPException(status_code=400, detail="Priority must be: low, medium, or high")
        
        # Validate inputs
        if not body.subject or not body.description:
            raise HTTPException(status_code=400, detail="Subject and description are required")
        
        # Create support ticket
        timestamp = datetime.now(timezone.utc)
        ticket_id = f"{int(timestamp.timestamp() * 1000)}"
        
        support_data = {
            "timestamp": int(timestamp.timestamp() * 1000),
            "email": body.email.lower().strip(),
            "name": (body.name or "Not provided").strip(),
            "subject": body.subject.strip(),
            "description": body.description.strip(),
            "priority": body.priority.lower(),
            "status": "open",  # open, in-progress, resolved, closed
            "readAt": None,
            "resolvedAt": None,
            "response": None,
            "tags": []
        }
        
        # Store in Firebase
        FirebaseObj.set_document(
            "contact_support",
            ticket_id,
            support_data
        )
        
        print(f"   ✅ Support ticket created: {ticket_id}")
        
        return JSONResponse(
            {
                "status": "success",
                "message": "Support request submitted successfully",
                "ticketId": ticket_id,
                "email": body.email
            },
            status_code=201
        )
    
    except HTTPException:
        raise
    except Exception as e:
        ErrorLogsObj.log_error(e, "contact_support", {"email": body.email})
        return JSONResponse(
            {"error": "Failed to submit support request. Please try again later."},
            status_code=500
        )


@app.post("/api/post-job")
async def post_job_alert(body: PostJobRequest, x_api_secret: str = Header(None)):
    """
    Manually post job openings and send alert emails to all active subscribers.

    Security:
    - Header: x-api-secret
    - Compared against CRON_SECRET environment variable

    Body (JSON):
    {
      "openings": [
        {
          "role": "Backend Engineer",
          "company": "Acme Corp",
          "employmentType": "Full-Time",
          "workMode": "Remote",
          "location": "India",
          "duration": null,
          "requiredSkills": ["Python", "FastAPI"],
          "summary": "Build scalable APIs.",
          "applyLink": "https://example.com/apply"
        }
      ]
    }
    """
    try:
        # ===== SECURITY =====
        API_SECRET = os.getenv("CRON_SECRET")
        if not API_SECRET:
            return JSONResponse({"error": "CRON_SECRET not configured"}, status_code=500)
        if not x_api_secret or x_api_secret != API_SECRET:
            return JSONResponse({"error": "Unauthorized"}, status_code=403)

        if not body.openings:
            raise HTTPException(status_code=400, detail="No job openings provided")

        openings = [job.model_dump() for job in body.openings]

        # ===== FETCH ACTIVE SUBSCRIBERS =====
        subscribers = FirebaseObj.get_all_documents("subscribers")
        active = [
            s for s in subscribers
            if s.get("subscribed") and s.get("isVerified")
        ]

        if not active:
            return JSONResponse(
                {
                    "status": "success",
                    "message": "No active subscribers",
                    "jobs_posted": len(openings),
                    "emails_sent": 0
                },
                status_code=200
            )

        # ===== SEND EMAILS =====
        emails_sent = 0
        emails_failed = 0

        for sub in active:
            try:
                email = sub.get("email")
                token = sub.get("unsubscribeToken")

                if not email or not token:
                    emails_failed += 1
                    continue

                GmailObj.send_job_alert_email(
                    email=email,
                    openings=openings,
                    unsubscribe_token=token
                )
                emails_sent += 1

            except Exception as e:
                ErrorLogsObj.log_email_error(e, sub.get('email'), "job_alert_manual")
                print(f"Failed to send to {sub.get('email')}: {str(e)}")
                emails_failed += 1

        return JSONResponse(
            {
                "status": "success",
                "message": "Job alert sent",
                "jobs_posted": len(openings),
                "emails_sent": emails_sent,
                "emails_failed": emails_failed
            },
            status_code=200
        )
    
    except HTTPException:
        raise
    except Exception as e:
        ErrorLogsObj.log_error(e, "post_job", {"jobsCount": len(body.openings) if body.openings else 0})
        return JSONResponse(
            {"error": "Job posting failed"},
            status_code=500
        )


@app.get("/api/cron/job-alert")
async def cron_job_alert(x_cron_secret: str = Header(None)):
    """
    Protected cron endpoint for job alert scheduler.
    Runs the job alert logic exactly once per request.
    
    Called by GitHub Actions every 3 hours.
    
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
        most_recent_published_at = state.get("mostRecentPublishedAt") if state else None
        
        print(f"   - Most recent processed: {most_recent_published_at or 'Never'}")
        
        # Use the stored timestamp to only fetch videos published after the most recent processed video
        videos = YoutubeObj.get_recent_videos(
            CHANNEL_ID,
            MAX_VIDEOS,
            published_after=most_recent_published_at
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
        videos_with_jobs_data = []  # Track videos that had job openings for timestamp update
        
        for i, video in enumerate(videos, 1):
            try:
                print(f"\n   [{i}/{len(videos)}] Processing: {video['videoId']}")
                
                # Skip if video was already processed (publishedAt <= mostRecentPublishedAt)
                if most_recent_published_at and video["publishedAt"] <= most_recent_published_at:
                    print(f"      ⏭️  Skipping (already processed)")
                    continue
                
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
                        videos_with_jobs_data.append(video)  # Store video data for timestamp tracking
                    else:
                        print(f"      ℹ️  No jobs in this video (isJobVideo={is_job_video}, openings={len(openings) if openings else 0})")
                else:
                    print(f"      ⚠️  Invalid result format: {result}")
                    
            except json.JSONDecodeError as e:
                ErrorLogsObj.log_gemini_error(e, video['videoId'])
                print(f"      ❌ JSON Parse Error: {str(e)}")
                print(f"         This usually means Gemini returned invalid JSON")
                continue
            except Exception as e:
                ErrorLogsObj.log_video_processing_error(e, video['videoId'])
                print(f"      ❌ Error processing video: {type(e).__name__}: {str(e)}")
                import traceback
                traceback.print_exc()
                continue
        
        # Deduplicate openings by (company, role, applyLink) to avoid sending same job multiple times
        seen = set()
        unique_openings = []
        for job in all_openings:
            key = (
                (job.get("company") or "").lower().strip(),
                (job.get("role") or "").lower().strip(),
                (job.get("applyLink") or "").lower().strip()
            )
            if key not in seen:
                seen.add(key)
                unique_openings.append(job)
            else:
                print(f"   🔄 Duplicate skipped: {job.get('role')} at {job.get('company')}")
        
        all_openings = unique_openings
        print(f"   After dedup: {len(all_openings)} unique opening(s)")
        
        if not all_openings:
            print(f"\n📭 [CRON] No job openings found in any video")
            
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
                
                GmailObj.send_job_alert_email(
                    email=email,
                    openings=all_openings,
                    unsubscribe_token=token
                )
                
                print(f"   [{i}/{len(active)}] ✅ Sent to {email}")
                emails_sent += 1
                
            except Exception as e:
                ErrorLogsObj.log_email_error(e, sub.get('email'), "cron_job_alert")
                print(f"   [{i}/{len(active)}] ❌ Failed: {str(e)}")
                emails_failed += 1
        
        # ===== STEP 6: Update state =====
        print(f"\n💾 [CRON] Updating state...")
        
        # Get existing state to check if we need to reset daily counters
        existing_state = FirebaseObj.get_document("system_state", "youtube") or {}
        today = datetime.now(timezone.utc).date().isoformat()
        last_update_date = existing_state.get("lastUpdateDate")
        
        # Initialize or reset daily counters if it's a new day
        if last_update_date != today:
            daily_emails_sent = emails_sent
            daily_emails_failed = emails_failed
            daily_jobs_sent = len(all_openings)
        else:
            # Add to existing daily counters
            daily_emails_sent = existing_state.get("dailyEmailsSent", 0) + emails_sent
            daily_emails_failed = existing_state.get("dailyEmailsFailed", 0) + emails_failed
            daily_jobs_sent = existing_state.get("dailyJobsSent", 0) + len(all_openings)
        
        # Build state update with all relevant metrics
        state_update = {
            "lastRunTime": datetime.now(timezone.utc).isoformat(),
            "emailsSent": emails_sent,
            "emailsFailed": emails_failed,
            "jobPostingsCount": len(all_openings),
            "videosProcessed": len(videos),
            "videosWithJobs": videos_with_jobs,
            "lastUpdateDate": today,
            "dailyEmailsSent": daily_emails_sent,
            "dailyEmailsFailed": daily_emails_failed,
            "dailyJobsSent": daily_jobs_sent
        }
        
        # Only update the timestamp with the most recent publishedAt from videos that contained jobs
        if videos_with_jobs_data:
            latest_published_at = max(v["publishedAt"] for v in videos_with_jobs_data)
            state_update["mostRecentPublishedAt"] = latest_published_at
        
        FirebaseObj.set_document(
            "system_state",
            "youtube",
            state_update
        )
        print(f"   ✅ State updated: {emails_sent} emails sent, {len(all_openings)} job postings")
        print(f"   📊 Daily totals: {daily_emails_sent} emails sent, {daily_emails_failed} failed, {daily_jobs_sent} jobs")
        
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
        ErrorLogsObj.log_error(e, "cron_job_alert", {"step": "general"})
        print(f"\n❌ [CRON] FATAL ERROR: {str(e)}")
        print("="*60 + "\n")
        import traceback
        traceback.print_exc()
        
        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )


@app.get("/api/cron/cleanup-error-logs")
async def cleanup_error_logs(x_cron_secret: str = Header(None)):
    """
    Cleanup endpoint to delete old error logs from Firebase.
    Should be called by GitHub Actions as a scheduled cron job every 7 days.
    
    Security:
    - Header: x-cron-secret
    - Compare against environment variable: CRON_SECRET
    - Returns HTTP 403 if invalid
    
    Returns:
    - error_logs_deleted: Number of error logs deleted
    - timestamp: When cleanup was performed
    """
    
    try:
        # ===== SECURITY: Validate cron secret =====
        CRON_SECRET = os.getenv("CRON_SECRET")
        
        if not CRON_SECRET:
            return JSONResponse(
                {"error": "CRON_SECRET not configured"},
                status_code=500
            )
        
        if not x_cron_secret or x_cron_secret != CRON_SECRET:
            return JSONResponse(
                {"error": "Unauthorized"},
                status_code=403
            )
        
        print("\n" + "="*60)
        print(f"🧹 [CLEANUP] Starting error log cleanup at {datetime.now(timezone.utc)}")
        print("="*60)
        
        # ===== CLEANUP ERROR LOGS =====
        print(f"\n🗑️  [CLEANUP] Deleting error logs older than 7 days...")
        
        deleted_count = ErrorLogsObj.clear_old_errors(days=7)
        
        print(f"   ✅ Successfully deleted {deleted_count} old error logs")
        
        # ===== COMPLETION =====
        print(f"\n🎉 [CLEANUP] Cleanup completed successfully!")
        print(f"   - Error logs deleted: {deleted_count}")
        print("="*60 + "\n")
        
        return JSONResponse(
            {
                "status": "success",
                "message": "Cleanup completed",
                "error_logs_deleted": deleted_count,
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            status_code=200
        )
    
    except Exception as e:
        ErrorLogsObj.log_error(e, "cron_cleanup_error_logs", {"step": "general"})
        print(f"\n❌ [CLEANUP] FATAL ERROR: {str(e)}")
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
4. Cron job -> /api/cron/job-alert endpoint (called by GitHub Actions every 3 hours)
5. Unsubscribe -> User clicks unsubscribe link with JWT token to stop receiving emails

CRON EXECUTION (GitHub Actions):
- GitHub Actions calls GET /api/cron/job-alert with x-cron-secret header every 3 hours
- Endpoint authenticates using CRON_SECRET environment variable
- Processes YouTube videos, extracts jobs, and sends emails to subscribers
- Stateless HTTP endpoint: safe to call multiple times
- State tracked in Firestore (mostRecentPublishedAt stores timestamp from last video with job openings)
- Only updates timestamp when videos with actual job openings are processed
- Job openings are deduplicated by (company, role, applyLink) before sending
"""