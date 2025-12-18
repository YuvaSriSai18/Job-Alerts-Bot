from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from contextlib import asynccontextmanager
import asyncio
import os
from fastapi_utilities import repeat_every

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

@repeat_every(seconds=60 * 2)
async def job_alert_scheduler():
    CHANNEL_ID = "UCbEd9lNwkBGLFGz8ZxsZdVA"
    MAX_VIDEOS = 3

    state = FirebaseObj.get_document("system_state", "youtube")
    last_processed_at = state.get("lastProcessedAt") if state else None

    videos = YoutubeObj.get_recent_videos(
        CHANNEL_ID,
        MAX_VIDEOS,
        published_after=last_processed_at
    )

    if not videos:
        return

    all_openings = []

    for video in videos:
        result = YoutubeObj.process_video_for_jobs(video["videoId"])
        if result.get("isJobVideo"):
            all_openings.extend(result.get("openings", []))

    if not all_openings:
        return

    subscribers = FirebaseObj.get_all_documents("subscribers")
    active = [
        s for s in subscribers
        if s.get("subscribed") and s.get("isVerified")
    ]

    for sub in active:
        email = sub.get("email")
        token = sub.get("unsubscribeToken")
        if not email or not token:
            continue

        unsubscribe_link = f"{BASE_URL}/unsubscribe/{token}"

        SendGridObj.send_job_alert_email(
            email=email,
            openings=all_openings,
            unsubscribe_link=unsubscribe_link
        )

    latest_published_at = max(v["publishedAt"] for v in videos)

    FirebaseObj.set_document(
        "system_state",
        "youtube",
        {"lastProcessedAt": latest_published_at}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)

"""
1. Subscribe to events -> User enters mail address, posted to /submit, user details will be stored in firestore in subscribers collection with { email, isVerified , subscribed (this subscribed will be added upon completion of verification) }
2. Email verification -> after entering email a verification mail has be sent along with the jwt token, then the server endpoint /verify-email will be validating the token and marking that mail as verified in the db
3. Unsubscribe to events -> an link with endpoint /unsubscribe will be sent via email in every mail with attached jwt token for reference
"""