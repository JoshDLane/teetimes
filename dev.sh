#!/bin/bash

set -e

echo "🔧 Development Mode - Tee Time Notification System"

# Load environment variables from .env file
if [ -f .env ]; then
    echo "📄 Loading environment variables from .env file..."
    export $(cat .env | grep -v '^#' | xargs)
fi

# Function to cleanup on exit
cleanup() {
    echo "🧹 Cleaning up..."
    # Stop any background processes
    jobs -p | xargs -r kill
    echo "✅ Cleanup complete"
}

# Set up trap to cleanup on script exit
trap cleanup EXIT

# Check if REDIS_URL is set
if [ -n "$REDIS_URL" ]; then
    echo "📡 Using Redis URL: $REDIS_URL"
else
    echo "❌ REDIS_URL environment variable is required"
    exit 1
fi

# Install dependencies
echo "📦 Installing dependencies with UV..."
uv sync

# Show notification tracker status
echo "📊 Current notification tracker status:"
uv run python check_notification_stats.py

echo ""
echo "🎯 Development options:"
echo "1. Run tee time checker (main app)"
echo "2. Check notification stats"
echo "4. Clean up old notifications"
echo "5. Exit"
echo ""

read -p "Choose an option (1-5): " choice

case $choice in
    1)
        echo "🏌️ Starting tee time checker in development mode..."
        uv run python check_slots.py
        ;;
    2)
        echo "📊 Checking notification stats..."
        uv run python check_notification_stats.py
        ;;
    4)
        echo "🧹 Cleaning up old notifications..."
        uv run python -c "
from notification_tracker import get_notification_tracker
tracker = get_notification_tracker()
cleaned = tracker.cleanup_old_slots(7)
print(f'Cleaned up {cleaned} old notifications')
"
        ;;
    5)
        echo "👋 Exiting..."
        exit 0
        ;;
    *)
        echo "❌ Invalid option"
        exit 1
        ;;
esac
