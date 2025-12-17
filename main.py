from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

from Repository.Youtube import Youtube
from Repository.Firebase import Firebase
from Repository.sendGrid import SendGridService

from utils.helpers import is_allowed_email, create_verification_token, verify_verification_token, create_unsubscribe_token, verify_unsubscribe_token

YoutubeObj = Youtube()
FirebaseObj = Firebase()
SendGridObj = SendGridService()

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@app.get("/", response_class=HTMLResponse)
async def home_route(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

@app.post("/register")
async def register_user(email: str = Form(...)):
    email = email.lower().strip()

    if not is_allowed_email(email):
        raise HTTPException(status_code=400, detail="Invalid email domain")

    if FirebaseObj.exists("subscribers", "email", email):
        raise HTTPException(status_code=409, detail="Email already registered")

    verification_token = create_verification_token(email)
    unsubscribe_token = create_unsubscribe_token(email)

    FirebaseObj.set_document("subscribers", email, {
        "email": email,
        "isVerified": False,
        "subscribed": False,
        "unsubscribeToken": unsubscribe_token,
        "createdAt": datetime.now(timezone.utc)
    })

    verify_link = f"/verify-email/{verification_token}"

    SendGridObj.send_verification_email(
        email=email,
        verify_link=verify_link
    )

    return JSONResponse(
        {"message": "Verification email sent", "email": email},
        status_code=200
    )

@app.get("/verify-email/{token}", response_class=HTMLResponse)
async def verify_email(token: str, request: Request):
    try:
        email = verify_verification_token(token)
        if not email:
            raise HTTPException(status_code=400, detail="Invalid or expired token")
        
        FirebaseObj.update_document("subscribers", email, {"isVerified": True, "subscribed": True})
        return templates.TemplateResponse(
            "subscription_confirmed.html",
            {"request": request, "email": email}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe_user(token: str, request: Request):
    try:
        email = verify_unsubscribe_token(token)
        if not email:
            raise HTTPException(status_code=400, detail="Invalid token")
        
        FirebaseObj.update_document("subscribers", email, {"subscribed": False})
        SendGridObj.send_unsubscribe_email(email=email)
        return templates.TemplateResponse(
            "unsubscribe.html",
            {"request": request, "email": email}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting FastAPI server...")
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
"""
1. Subscribe to events -> User enters mail address, posted to /submit, user details will be stored in firestore in subscribers collection with { email, isVerified , subscribed (this subscribed will be added upon completion of verification) }
2. Email verification -> after entering email a verification mail has be sent along with the jwt token, then the server endpoint /verify-email will be validating the token and marking that mail as verified in the db
3. Unsubscribe to events -> an link with endpoint /unsubscribe will be sent via email in every mail with attached jwt token for reference
"""