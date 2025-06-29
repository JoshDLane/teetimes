import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import redis


class NotificationTracker:
    """Tracks notified slots using Redis with automatic cleanup after 7 days."""
    
    def __init__(self):
        """Initialize Redis connection."""
        try:
            # Get Redis URL from environment (Railway provides this)
            redis_url = os.getenv("REDIS_URL")
            if not redis_url:
                raise ValueError("REDIS_URL environment variable is required")
            
            logging.info("Connecting to Redis using REDIS_URL")
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            
            # Test the connection
            self.redis_client.ping()
            logging.info("Successfully connected to Redis")
        except redis.ConnectionError as e:
            logging.error(f"Failed to connect to Redis: {e}")
            raise
    
    def _generate_slot_key(self, course: str, slot_datetime: datetime) -> str:
        """Generate a unique key for a slot."""
        return f"notified_slot:{course}:{slot_datetime.isoformat()}2"
    
    def is_slot_notified(self, course: str, slot_datetime: datetime) -> bool:
        """Check if a slot has already been notified about."""
        key = self._generate_slot_key(course, slot_datetime)
        return self.redis_client.exists(key) > 0
    
    def mark_slot_notified(self, course: str, slot_datetime: datetime, ttl_days: int = 7) -> None:
        """Mark a slot as notified with automatic cleanup after specified days."""
        key = self._generate_slot_key(course, slot_datetime)
        ttl_seconds = ttl_days * 24 * 60 * 60  # Convert days to seconds
        
        # Store the slot with TTL for automatic cleanup
        self.redis_client.setex(key, ttl_seconds, slot_datetime.isoformat())
        logging.debug(f"Marked slot as notified: {key} (TTL: {ttl_days} days)")
    
    def get_notified_slots_count(self) -> int:
        """Get the total number of notified slots currently tracked."""
        pattern = "notified_slot:*"
        keys = self.redis_client.keys(pattern)
        return len(keys)
    
    def cleanup_old_slots(self, days_old: int = 7) -> int:
        """Manually cleanup slots older than specified days (optional, Redis TTL handles this automatically)."""
        pattern = "notified_slot:*"
        keys = self.redis_client.keys(pattern)
        cutoff_time = datetime.now() - timedelta(days=days_old)
        cleaned_count = 0
        
        for key in keys:
            try:
                slot_time_str = self.redis_client.get(key)
                if slot_time_str:
                    slot_time = datetime.fromisoformat(slot_time_str)
                    if slot_time < cutoff_time:
                        self.redis_client.delete(key)
                        cleaned_count += 1
            except Exception as e:
                logging.warning(f"Error processing key {key}: {e}")
        
        if cleaned_count > 0:
            logging.info(f"Manually cleaned up {cleaned_count} old slot notifications")
        
        return cleaned_count
    
    def get_stats(self) -> dict:
        """Get statistics about the notification tracker."""
        pattern = "notified_slot:*"
        keys = self.redis_client.keys(pattern)
        
        stats = {
            "total_notified_slots": len(keys),
            "redis_connected": self.redis_client.ping(),
            "redis_info": self.redis_client.info()
        }
        
        return stats


# Global instance for easy access
_notification_tracker: Optional[NotificationTracker] = None


def get_notification_tracker() -> NotificationTracker:
    """Get or create the global notification tracker instance."""
    global _notification_tracker
    if _notification_tracker is None:
        _notification_tracker = NotificationTracker()
    return _notification_tracker


def is_slot_notified(course: str, slot_datetime: datetime) -> bool:
    """Check if a slot has already been notified about."""
    tracker = get_notification_tracker()
    return tracker.is_slot_notified(course, slot_datetime)


def mark_slot_notified(course: str, slot_datetime: datetime, ttl_days: int = 7) -> None:
    """Mark a slot as notified with automatic cleanup after specified days."""
    tracker = get_notification_tracker()
    tracker.mark_slot_notified(course, slot_datetime, ttl_days) 