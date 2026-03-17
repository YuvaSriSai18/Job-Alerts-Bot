import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")

BASE_URL = os.getenv("BASE_URL", "http://localhost:8001")

from Repository.Firebase import FirebaseService
FirebaseObj = FirebaseService()


class GmailService:
    def __init__(self):
        self.gmail_address = os.getenv("GMAIL_ADDRESS")
        self.gmail_app_password = os.getenv("GMAIL_APP_PASSWORD")

        if not self.gmail_address:
            raise ValueError("GMAIL_ADDRESS not found in environment variables")
        if not self.gmail_app_password:
            raise ValueError("GMAIL_APP_PASSWORD not found in environment variables")

        self.from_name = "Job Alerts"

    def _load_template(self, template_name: str) -> str:
        path = f"templates/{template_name}"
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def _increment_total_emails_sent(self, count: int):
        """Increment total emails sent counter in Firebase."""
        try:
            state = FirebaseObj.get_document("system_state", "email_stats") or {}
            current_total = state.get("totalEmailsSent", 0)
            FirebaseObj.set_document(
                "system_state",
                "email_stats",
                {"totalEmailsSent": current_total + count}
            )
        except Exception as e:
            print(f"Failed to increment email counter: {str(e)}")

    def _send(self, to_email: str, subject: str, html_content: str):
        try:
            message = MIMEMultipart("alternative")
            message["From"] = f"{self.from_name} <{self.gmail_address}>"
            message["To"] = to_email
            message["Subject"] = subject
            message["Reply-To"] = self.gmail_address

            html_part = MIMEText(html_content, "html")
            message.attach(html_part)

            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(self.gmail_address, self.gmail_app_password)
                server.sendmail(self.gmail_address, to_email, message.as_string())

            # Increment total emails sent counter
            self._increment_total_emails_sent(1)
            print("E-Mail has been sent")
            return 200

        except smtplib.SMTPAuthenticationError as e:
            raise ValueError(
                "Gmail SMTP Authentication Error. Possible causes:\n"
                "1. Invalid Gmail address or app password\n"
                "2. App password not generated correctly (use https://myaccount.google.com/apppasswords)\n"
                "3. 2-Step Verification not enabled on Google account\n"
                f"Details: {str(e)}"
            )
        except Exception as e:
            print(f"Failed to send email: {str(e)}")
            raise

    def _send_batch_bcc(self, bcc_emails: list, subject: str, html_content: str):
        """Send a single email to multiple recipients via BCC for higher throughput."""
        try:
            if not bcc_emails:
                raise ValueError("BCC recipient list cannot be empty")

            message = MIMEMultipart("alternative")
            message["From"] = f"{self.from_name} <{self.gmail_address}>"
            message["Subject"] = subject
            message["Reply-To"] = self.gmail_address

            html_part = MIMEText(html_content, "html")
            message.attach(html_part)

            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(self.gmail_address, self.gmail_app_password)
                server.sendmail(self.gmail_address, bcc_emails, message.as_string())

            # Increment total emails sent counter by number of BCC recipients
            self._increment_total_emails_sent(len(bcc_emails))
            print(f"E-Mail has been sent to {len(bcc_emails)} recipients via BCC")
            return 200

        except smtplib.SMTPAuthenticationError as e:
            raise ValueError(
                "Gmail SMTP Authentication Error. Possible causes:\n"
                "1. Invalid Gmail address or app password\n"
                "2. App password not generated correctly (use https://myaccount.google.com/apppasswords)\n"
                "3. 2-Step Verification not enabled on Google account\n"
                f"Details: {str(e)}"
            )
        except Exception as e:
            print(f"Failed to send batch email: {str(e)}")
            raise

    def send_verification_email(self, email: str, verify_link: str):
        template = self._load_template("verify_subscription.html")
        # print(verify_link)
        html = (
            template
            .replace("{{ verifyLink }}", verify_link)
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

    def send_job_alert_email_batch(self, bcc_emails: list, openings: list):
        """Send job alert emails to multiple recipients via BCC for higher throughput."""
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

        html = (
            template
            .replace("{{ JOB_CARDS }}", job_cards_html)
            .replace("{{ unsubscribeLink }}", "#")  # BCC recipients won't have personalized unsubscribe links
            .replace("{{ year }}", str(datetime.now().year))
            .replace("{{ jobCount }}", str(len(openings)))
        )

        return self._send_batch_bcc(
            bcc_emails=bcc_emails,
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
