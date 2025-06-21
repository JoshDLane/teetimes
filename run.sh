#!/bin/bash

# Production run script for Railway deployment
set -e

echo "🚀 Starting Tee Time Notification System on Railway..."


# Check notification tracker status
echo "📊 Checking notification tracker status..."
uv run python check_notification_stats.py

# Start the main application
echo "🏌️ Starting tee time checker..."
uv run python check_slots.py
