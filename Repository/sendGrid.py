import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, ReplyTo
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")

BASE_URL = os.getenv("BASE_URL", "http://localhost:8001")

class SendGridService:
    def __init__(self):
        self.api_key = os.getenv("SENDGRID_API_KEY")
        
        if not self.api_key:
            raise ValueError("SENDGRID_API_KEY not found in environment variables")
        
        self.from_email = ("keximof870@gamintor.com", "Job Alerts")
        self.client = SendGridAPIClient(self.api_key)

    def _load_template(self, template_name: str) -> str:
        path = f"templates/{template_name}"
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def _send(self, to_email: str, subject: str, html_content: str):
        if not self.api_key:
            raise ValueError("SENDGRID_API_KEY is not configured")
        
        try:
            message = Mail(
                from_email=self.from_email,
                to_emails=to_email,
                subject=subject,
                html_content=html_content
            )
            message.reply_to = ReplyTo("noreply@sendgrid.net")

            response = self.client.send(message)
            return response.status_code
        
        except Exception as e:
            error_message = str(e)
            if "403" in error_message or "Forbidden" in error_message:
                raise ValueError(
                    "SendGrid API Error: 403 Forbidden. Possible causes:\n"
                    "1. Invalid API Key\n"
                    "2. Sender email not verified in SendGrid\n"
                    "3. API key doesn't have send permissions\n"
                    f"Details: {error_message}"
                )
            raise

    def send_verification_email(self, email: str, verify_link: str):
        template = self._load_template("verify_subscription.html")

        full_verify_link = f"{BASE_URL}{verify_link}"

        html = (
            template
            .replace("{{ verifyLink }}", full_verify_link)
            .replace("{{ year }}", str(datetime.now().year))
        )

        return self._send(
            to_email=email,
            subject="Confirm your Job Alerts subscription",
            html_content=html
        )

    def send_subscription_confirmed_email(self, email: str):
        template = self._load_template("subscription_confirmed.html")

        html = (
            template
            .replace("{{ year }}", str(datetime.now().year))
        )

        return self._send(
            to_email=email,
            subject="Subscription Confirmed! 🎉",
            html_content=html
        )

    def send_job_alert_email(self, email: str, openings: list, unsubscribe_token: str):
        template = self._load_template("job_alert.html")

        job_cards_html = ""

        for job in openings:
            skills = ", ".join(job.get("requiredSkills", [])) or "Not specified"
            duration_html = f"<span>⏳ {job.get('duration')}</span>" if job.get("duration") else ""

            card = f"""
            <div class="job-card">
              <div class="job-title">{job.get("role", "N/A")}</div>
              <div class="company">{job.get("company", "N/A")}</div>

              <div class="meta">
                <span>📌 {job.get("employmentType", "N/A")}</span>
                <span>🏠 {job.get("workMode", "N/A")}</span>
                <span>📍 {job.get("location", "N/A")}</span>
                {duration_html}
              </div>

              <div class="skills">
                <strong>Skills:</strong> {skills}
              </div>

              <div class="summary">
                {job.get("summary", "No description available")}
              </div>

              <a class="apply-btn" href="{job.get("applyLink", "#")}" target="_blank">
                Apply Now →
              </a>
            </div>
            """

            job_cards_html += card

        unsubscribe_link = f"{BASE_URL}/unsubscribe/{unsubscribe_token}"

        html = (
            template
            .replace("{{ JOB_CARDS }}", job_cards_html)
            .replace("{{ unsubscribeLink }}", unsubscribe_link)
            .replace("{{ year }}", str(datetime.now().year))
            .replace("{{ jobCount }}", str(len(openings)))
        )

        return self._send(
            to_email=email,
            subject=f"🚨 New Job Openings ({len(openings)})",
            html_content=html
        )

    def send_unsubscribe_email(self, email: str):
        template = self._load_template("unsubscribe.html")

        html = (
            template
            .replace("{{ year }}", str(datetime.now().year))
        )

        return self._send(
            to_email=email,
            subject="You've been unsubscribed from Job Alerts",
            html_content=html
        )
