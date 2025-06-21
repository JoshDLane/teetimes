#!/usr/bin/env python3
"""
Utility script to check the status of the Redis-based notification tracker.
"""

import logging

from notification_tracker import get_notification_tracker

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

def main():
    """Display notification tracker statistics."""
    try:
        tracker = get_notification_tracker()
        stats = tracker.get_stats()
        
        print("=== Notification Tracker Statistics ===")
        print(f"Total notified slots: {stats['total_notified_slots']}")
        print(f"Redis connected: {stats['redis_connected']}")
        
        # Show some Redis info
        redis_info = stats['redis_info']
        print(f"Redis version: {redis_info.get('redis_version', 'Unknown')}")
        print(f"Used memory: {redis_info.get('used_memory_human', 'Unknown')}")
        print(f"Connected clients: {redis_info.get('connected_clients', 'Unknown')}")
        
        # Optional: Show some example keys
        if stats['total_notified_slots'] > 0:
            print("\n=== Example Notified Slots ===")
            pattern = "notified_slot:*"
            keys = tracker.redis_client.keys(pattern)
            for key in keys[:5]:  # Show first 5 keys
                print(f"  {key}")
            if len(keys) > 5:
                print(f"  ... and {len(keys) - 5} more")
                
    except Exception as e:
        print(f"Error getting notification tracker stats: {e}")
        logging.error(f"Error: {e}")

if __name__ == "__main__":
    main() 