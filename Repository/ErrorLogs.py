import traceback
import re
from datetime import datetime, timezone
from typing import Optional
from Repository.Firebase import Firebase


class ErrorLogs:
    """
    Handles error logging to Firebase.
    Stores error information with admin-friendly summaries and actionable insights.
    """
    
    # Error severity mappings
    ERROR_SEVERITY_MAP = {
        "SMTPDataError": "CRITICAL",
        "SMTPAuthenticationError": "CRITICAL",
        "SMTPServerDisconnected": "ERROR",
        "ConnectionError": "ERROR",
        "TimeoutError": "ERROR",
        "JSONDecodeError": "ERROR",
        "KeyError": "ERROR",
        "ValueError": "WARNING",
        "TypeError": "WARNING",
        "AttributeError": "ERROR",
        "FileNotFoundError": "ERROR",
        "PermissionError": "CRITICAL",
        "HTTPException": "WARNING",
    }
    
    # Service affected mappings
    SERVICE_MAP = {
        "send_emails": "Gmail SMTP",
        "email_verification": "Email Verification",
        "user_resubscribe": "User Resubscription",
        "user_registration": "User Registration",
        "user_unsubscribe": "User Unsubscribe",
        "post_job": "Job Posting",
        "cron_job_alert": "Cron Job Alert",
        "video_processing": "YouTube Processing",
        "gemini_extraction": "Gemini AI Extraction",
    }
    
    # Suggested actions
    ACTION_MAP = {
        "SMTPDataError": "Check Gmail account daily sending limit. Increase quota or use multiple sender accounts.",
        "SMTPAuthenticationError": "Verify Gmail credentials and app password. Update GMAIL_PASSWORD in environment.",
        "ConnectionError": "Check internet connection and firewall. Verify email server is accessible.",
        "TimeoutError": "Gmail server is slow. Increase timeout settings or retry after some time.",
        "JSONDecodeError": "Gemini API returned invalid JSON. Check API response format and retry video processing.",
        "PermissionError": "Firebase authentication failed. Verify service account credentials.",
        "HTTPException": "Invalid request parameters. Check email format and token validity.",
    }
    
    def __init__(self):
        self.firebase = Firebase()
        self.collection_name = "job_alerts_error_logs"
 
    def _extract_error_code(self, error_message: str) -> Optional[str]:
        """Extract error code from error message (e.g., SMTP code 550)"""
        match = re.search(r'\((\d+)', error_message)
        return match.group(1) if match else None
    
    def _get_severity(self, error_type: str) -> str:
        """Determine error severity"""
        return self.ERROR_SEVERITY_MAP.get(error_type, "ERROR")
    
    def _get_service(self, step: str) -> str:
        """Get affected service name"""
        return self.SERVICE_MAP.get(step, step)
    
    def _get_summary(self, error_type: str, error_message: str, step: str) -> str:
        """Create admin-friendly error summary"""
        service = self._get_service(step)
        
        if "Daily user sending limit exceeded" in error_message:
            return f"⚠️ Gmail daily email limit reached - no more emails can be sent today"
        elif "SMTPAuthenticationError" in error_message:
            return f"🔐 Gmail authentication failed - check credentials"
        elif "ConnectionError" in error_message:
            return f"🔌 Connection error to email server - network issue"
        elif "JSONDecodeError" in error_message:
            return f"📝 Gemini API returned invalid JSON format"
        elif "timeout" in error_message.lower():
            return f"⏱️ Request timeout - service took too long to respond"
        elif error_type == "KeyError":
            return f"❌ Missing required data field in request/config"
        elif error_type == "PermissionError":
            return f"🚫 Permission denied - authentication or authorization failed"
        else:
            return f"⚠️ {service} - {error_type}"
    
    def _get_suggested_action(self, error_type: str, error_message: str) -> str:
        """Get actionable suggestion for admin"""
        # Check specific error types first
        for err_type, action in self.ACTION_MAP.items():
            if err_type in error_type or err_type in error_message:
                return action
        
        # Default suggestions
        if "Gmail" in error_message or "SMTP" in error_type:
            return "Check Gmail account status and sending limits."
        elif "timeout" in error_message.lower():
            return "Check network connectivity and service availability. Retry the operation."
        elif "authentication" in error_message.lower():
            return "Verify authentication credentials and permissions."
        else:
            return "Review error logs and check service status."
    
    def _is_resolvable(self, error_type: str) -> bool:
        """Check if error is auto-resolvable with retry"""
        resolvable_errors = ["TimeoutError", "ConnectionError", "SMTPServerDisconnected"]
        return error_type in resolvable_errors
    
    def log_error(
        self,
        error: Exception,
        step: str,
        context: Optional[dict] = None
    ) -> str:
        """
        Log an error to Firebase with admin-friendly information.
        
        Args:
            error: The exception that occurred
            step: Which step of the process failed (e.g., "video_processing", "send_emails")
            context: Additional context data (e.g., {"videoId": "xxx", "email": "user@example.com"})
        
        Returns:
            The document ID of the logged error
        """
        try:
            timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)  # milliseconds
            error_type = type(error).__name__
            error_message = str(error)
            
            # Extract error code if present
            error_code = self._extract_error_code(error_message)
            
            error_data = {
                "timestamp": timestamp,
                "errorType": error_type,
                "errorMessage": error_message,
                "errorCode": error_code,
                "step": step,
                "service": self._get_service(step),
                "severity": self._get_severity(error_type),
                "summary": self._get_summary(error_type, error_message, step),
                "suggestedAction": self._get_suggested_action(error_type, error_message),
                "isResolvable": self._is_resolvable(error_type),
                "retryCount": 0,
                "resolved": False,
                "stackTrace": traceback.format_exc(),
            }
            
            # Add context if provided
            if context:
                error_data["context"] = context
            
            # Generate document ID based on timestamp for easy sorting
            doc_id = str(timestamp)
            
            # Add to Firebase
            self.firebase.set_document(
                self.collection_name,
                doc_id,
                error_data
            )
            
            print(f"   ✅ Error logged to Firebase: {error_data['summary']}")
            return doc_id
            
        except Exception as e:
            print(f"   ❌ Failed to log error to Firebase: {str(e)}")
            return None
    
    def mark_error_resolved(self, doc_id: str) -> bool:
        """Mark an error as resolved by admin"""
        try:
            self.firebase.update_document(
                self.collection_name,
                doc_id,
                {"resolved": True, "resolvedAt": int(datetime.now(timezone.utc).timestamp() * 1000)}
            )
            print(f"   ✅ Error marked as resolved: {doc_id}")
            return True
        except Exception as e:
            print(f"   ❌ Failed to mark error as resolved: {str(e)}")
            return False
    
    def increment_retry_count(self, doc_id: str) -> bool:
        """Increment retry count for an error"""
        try:
            error = self.firebase.get_document(self.collection_name, doc_id)
            if error:
                current_retries = error.get("retryCount", 0)
                self.firebase.update_document(
                    self.collection_name,
                    doc_id,
                    {"retryCount": current_retries + 1}
                )
                return True
            return False
        except Exception as e:
            print(f"   ❌ Failed to increment retry count: {str(e)}")
            return False
    
    def get_critical_errors(self, limit: int = 20) -> list:
        """Get all CRITICAL severity errors"""
        try:
            all_errors = self.firebase.get_all_documents(self.collection_name)
            critical = [e for e in all_errors if e.get("severity") == "CRITICAL"]
            sorted_errors = sorted(
                critical,
                key=lambda x: x.get("timestamp", 0),
                reverse=True
            )
            return sorted_errors[:limit]
        except Exception as e:
            print(f"   ❌ Failed to retrieve critical errors: {str(e)}")
            return []
    
    def get_unresolved_errors(self, limit: int = 50) -> list:
        """Get all unresolved errors sorted by severity"""
        try:
            all_errors = self.firebase.get_all_documents(self.collection_name)
            unresolved = [e for e in all_errors if not e.get("resolved", False)]
            # Sort by severity (CRITICAL first) then by timestamp
            severity_order = {"CRITICAL": 0, "ERROR": 1, "WARNING": 2, "INFO": 3}
            sorted_errors = sorted(
                unresolved,
                key=lambda x: (severity_order.get(x.get("severity", "INFO"), 4), -x.get("timestamp", 0))
            )
            return sorted_errors[:limit]
        except Exception as e:
            print(f"   ❌ Failed to retrieve unresolved errors: {str(e)}")
            return []
    
    def log_email_error(
        self,
        error: Exception,
        email: str,
        subject: str = "unknown"
    ) -> str:
        """
        Log an email sending error to Firebase.
        
        Args:
            error: The exception that occurred
            email: The destination email address
            subject: The email subject
        
        Returns:
            The document ID of the logged error
        """
        context = {
            "email": email,
            "subject": subject
        }
        return self.log_error(error, "send_emails", context)
    
    def log_video_processing_error(
        self,
        error: Exception,
        video_id: str
    ) -> str:
        """
        Log a video processing error to Firebase.
        
        Args:
            error: The exception that occurred
            video_id: The YouTube video ID being processed
        
        Returns:
            The document ID of the logged error
        """
        context = {
            "videoId": video_id
        }
        return self.log_error(error, "video_processing", context)
    
    def log_gemini_error(
        self,
        error: Exception,
        video_id: str
    ) -> str:
        """
        Log a Gemini AI extraction error to Firebase.
        
        Args:
            error: The exception that occurred
            video_id: The YouTube video ID being processed
        
        Returns:
            The document ID of the logged error
        """
        context = {
            "videoId": video_id
        }
        return self.log_error(error, "gemini_extraction", context)
    
    def get_recent_errors(self, limit: int = 50) -> list:
        """
        Get recent errors from Firebase, sorted by severity then timestamp.
        
        Args:
            limit: Maximum number of errors to retrieve
        
        Returns:
            List of error documents
        """
        try:
            all_errors = self.firebase.get_all_documents(self.collection_name)
            # Sort by severity (CRITICAL first) then by timestamp (newest first)
            severity_order = {"CRITICAL": 0, "ERROR": 1, "WARNING": 2, "INFO": 3}
            sorted_errors = sorted(
                all_errors,
                key=lambda x: (severity_order.get(x.get("severity", "INFO"), 4), -x.get("timestamp", 0))
            )
            return sorted_errors[:limit]
        except Exception as e:
            print(f"   ❌ Failed to retrieve errors from Firebase: {str(e)}")
            return []
    
    def get_errors_by_step(self, step: str, limit: int = 50) -> list:
        """
        Get errors from a specific step, sorted by timestamp newest first.
        
        Args:
            step: The step name to filter by
            limit: Maximum number of errors to retrieve
        
        Returns:
            List of error documents for that step
        """
        try:
            all_errors = self.firebase.get_all_documents(self.collection_name)
            # Filter by step and sort by timestamp
            filtered = [e for e in all_errors if e.get("step") == step]
            sorted_errors = sorted(
                filtered,
                key=lambda x: -x.get("timestamp", 0)
            )
            return sorted_errors[:limit]
        except Exception as e:
            print(f"   ❌ Failed to retrieve errors by step: {str(e)}")
            return []
    
    def clear_old_errors(self, days: int = 30) -> int:
        """
        Delete errors older than specified days.
        
        Args:
            days: Delete errors older than this many days
        
        Returns:
            Number of errors deleted
        """
        try:
            from datetime import timedelta
            cutoff_timestamp = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)  # milliseconds
            
            all_errors = self.firebase.get_all_documents(self.collection_name)
            deleted_count = 0
            
            for error in all_errors:
                if error.get("timestamp", 0) < cutoff_timestamp:
                    self.firebase.delete_document(self.collection_name, error.get("id") or error.get("name"))
                    deleted_count += 1
            
            print(f"   ✅ Deleted {deleted_count} old errors (older than {days} days)")
            return deleted_count
            
        except Exception as e:
            print(f"   ❌ Failed to clear old errors: {str(e)}")
            return 0
