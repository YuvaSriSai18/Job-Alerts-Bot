from datetime import datetime, timezone
from typing import Optional
from Repository.Firebase import Firebase


class ContactSupport:
    """
    Manages customer support tickets stored in Firebase.
    Provides admin functionality to view, update, and manage support requests.
    """
    
    STATUS_OPTIONS = ["open", "in-progress", "resolved", "closed"]
    PRIORITY_OPTIONS = ["low", "medium", "high"]
    
    def __init__(self):
        self.firebase = Firebase()
        self.collection_name = "contact_support"
    
    def get_ticket(self, ticket_id: str) -> Optional[dict]:
        """
        Retrieve a specific support ticket.
        
        Args:
            ticket_id: The support ticket ID
        
        Returns:
            Ticket document or None
        """
        try:
            return self.firebase.get_document(self.collection_name, ticket_id)
        except Exception as e:
            print(f"   ❌ Failed to retrieve ticket: {str(e)}")
            return None
    
    def get_all_tickets(self, limit: int = 100) -> list:
        """
        Get all support tickets sorted by timestamp (newest first).
        
        Args:
            limit: Maximum number of tickets to retrieve
        
        Returns:
            List of support tickets
        """
        try:
            all_tickets = self.firebase.get_all_documents(self.collection_name)
            sorted_tickets = sorted(
                all_tickets,
                key=lambda x: -x.get("timestamp", 0)
            )
            return sorted_tickets[:limit]
        except Exception as e:
            print(f"   ❌ Failed to retrieve tickets: {str(e)}")
            return []
    
    def get_open_tickets(self, limit: int = 50) -> list:
        """
        Get all open support tickets sorted by priority and timestamp.
        
        Args:
            limit: Maximum number of tickets
        
        Returns:
            List of open tickets
        """
        try:
            all_tickets = self.firebase.get_all_documents(self.collection_name)
            open_tickets = [t for t in all_tickets if t.get("status") in ["open", "in-progress"]]
            
            # Sort by priority (high first) then by timestamp (newest first)
            priority_order = {"high": 0, "medium": 1, "low": 2}
            sorted_tickets = sorted(
                open_tickets,
                key=lambda x: (priority_order.get(x.get("priority", "medium"), 3), -x.get("timestamp", 0))
            )
            return sorted_tickets[:limit]
        except Exception as e:
            print(f"   ❌ Failed to retrieve open tickets: {str(e)}")
            return []
    
    def get_high_priority_tickets(self, limit: int = 20) -> list:
        """
        Get all high-priority support tickets.
        
        Args:
            limit: Maximum number of tickets
        
        Returns:
            List of high priority tickets
        """
        try:
            all_tickets = self.firebase.get_all_documents(self.collection_name)
            high_priority = [t for t in all_tickets if t.get("priority") == "high" and not t.get("resolved")]
            sorted_tickets = sorted(
                high_priority,
                key=lambda x: -x.get("timestamp", 0)
            )
            return sorted_tickets[:limit]
        except Exception as e:
            print(f"   ❌ Failed to retrieve high priority tickets: {str(e)}")
            return []
    
    def update_ticket_status(self, ticket_id: str, new_status: str) -> bool:
        """
        Update the status of a support ticket.
        
        Args:
            ticket_id: The support ticket ID
            new_status: New status (open, in-progress, resolved, closed)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if new_status not in self.STATUS_OPTIONS:
                print(f"   ❌ Invalid status: {new_status}")
                return False
            
            update_data = {
                "status": new_status
            }
            
            # Set resolved timestamp if marking as resolved
            if new_status == "resolved":
                update_data["resolvedAt"] = int(datetime.now(timezone.utc).timestamp() * 1000)
            
            self.firebase.update_document(
                self.collection_name,
                ticket_id,
                update_data
            )
            print(f"   ✅ Ticket {ticket_id} status updated to: {new_status}")
            return True
        except Exception as e:
            print(f"   ❌ Failed to update ticket status: {str(e)}")
            return False
    
    def mark_as_read(self, ticket_id: str) -> bool:
        """
        Mark a support ticket as read by admin.
        
        Args:
            ticket_id: The support ticket ID
        
        Returns:
            True if successful
        """
        try:
            self.firebase.update_document(
                self.collection_name,
                ticket_id,
                {"readAt": int(datetime.now(timezone.utc).timestamp() * 1000)}
            )
            print(f"   ✅ Ticket {ticket_id} marked as read")
            return True
        except Exception as e:
            print(f"   ❌ Failed to mark as read: {str(e)}")
            return False
    
    def add_response(self, ticket_id: str, response_text: str) -> bool:
        """
        Add admin response to a support ticket.
        
        Args:
            ticket_id: The support ticket ID
            response_text: Admin's response message
        
        Returns:
            True if successful
        """
        try:
            if not response_text or not response_text.strip():
                print(f"   ❌ Response cannot be empty")
                return False
            
            response_data = {
                "response": response_text.strip(),
                "respondedAt": int(datetime.now(timezone.utc).timestamp() * 1000),
                "status": "in-progress"
            }
            
            self.firebase.update_document(
                self.collection_name,
                ticket_id,
                response_data
            )
            print(f"   ✅ Response added to ticket {ticket_id}")
            return True
        except Exception as e:
            print(f"   ❌ Failed to add response: {str(e)}")
            return False
    
    def add_tag(self, ticket_id: str, tag: str) -> bool:
        """
        Add a tag to a support ticket (bug, feature-request, account-issue, etc.).
        
        Args:
            ticket_id: The support ticket ID
            tag: Tag to add
        
        Returns:
            True if successful
        """
        try:
            ticket = self.firebase.get_document(self.collection_name, ticket_id)
            if not ticket:
                print(f"   ❌ Ticket not found: {ticket_id}")
                return False
            
            current_tags = ticket.get("tags", [])
            if tag not in current_tags:
                current_tags.append(tag)
                self.firebase.update_document(
                    self.collection_name,
                    ticket_id,
                    {"tags": current_tags}
                )
                print(f"   ✅ Tag '{tag}' added to ticket {ticket_id}")
            return True
        except Exception as e:
            print(f"   ❌ Failed to add tag: {str(e)}")
            return False
    
    def get_tickets_by_email(self, email: str, limit: int = 20) -> list:
        """
        Get all support tickets from a specific email address.
        
        Args:
            email: User's email address
            limit: Maximum number of tickets
        
        Returns:
            List of tickets from that email
        """
        try:
            all_tickets = self.firebase.get_all_documents(self.collection_name)
            user_tickets = [t for t in all_tickets if t.get("email") == email.lower()]
            sorted_tickets = sorted(
                user_tickets,
                key=lambda x: -x.get("timestamp", 0)
            )
            return sorted_tickets[:limit]
        except Exception as e:
            print(f"   ❌ Failed to retrieve tickets by email: {str(e)}")
            return []
    
    def get_tickets_by_tag(self, tag: str, limit: int = 50) -> list:
        """
        Get all support tickets with a specific tag.
        
        Args:
            tag: Tag to filter by
            limit: Maximum number of tickets
        
        Returns:
            List of tickets with that tag
        """
        try:
            all_tickets = self.firebase.get_all_documents(self.collection_name)
            tagged_tickets = [t for t in all_tickets if tag in t.get("tags", [])]
            sorted_tickets = sorted(
                tagged_tickets,
                key=lambda x: -x.get("timestamp", 0)
            )
            return sorted_tickets[:limit]
        except Exception as e:
            print(f"   ❌ Failed to retrieve tickets by tag: {str(e)}")
            return []
    
    def get_stats(self) -> dict:
        """
        Get support ticket statistics.
        
        Returns:
            Dictionary with ticket counts and metrics
        """
        try:
            all_tickets = self.firebase.get_all_documents(self.collection_name)
            
            stats = {
                "total": len(all_tickets),
                "open": len([t for t in all_tickets if t.get("status") == "open"]),
                "in_progress": len([t for t in all_tickets if t.get("status") == "in-progress"]),
                "resolved": len([t for t in all_tickets if t.get("status") == "resolved"]),
                "closed": len([t for t in all_tickets if t.get("status") == "closed"]),
                "high_priority": len([t for t in all_tickets if t.get("priority") == "high"]),
                "medium_priority": len([t for t in all_tickets if t.get("priority") == "medium"]),
                "low_priority": len([t for t in all_tickets if t.get("priority") == "low"]),
            }
            return stats
        except Exception as e:
            print(f"   ❌ Failed to get stats: {str(e)}")
            return {}
