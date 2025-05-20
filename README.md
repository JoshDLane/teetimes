# BookBot

A Python automation tool for checking and booking tennis court slots on rec.us.

## Overview

BookBot is designed to automate the process of finding and booking tennis court reservations. It includes several scripts:

- `check_slots.py`: Monitors available court slots and sends notifications when matching slots are found.
- `book_on_time.py`: Automatically books a court at a specific time.
- `mark_as_viewed.py`: Utility to mark notifications as viewed in the notification tracking system.
- `notifs.py`: Handles notification storage and retrieval.

## Features

- Configurable court preferences via `courts.yaml`
- Desktop notifications for available court slots
- Automatic booking capabilities
- Notification history tracking

## Setup

### Prerequisites

- Python 3.7+
- Chrome browser (for Selenium WebDriver)
- `terminal-notifier` for macOS notifications

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/bookbot.git
   cd bookbot
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env.local` file with your credentials (for booking functionality):
   ```
   USERNAME=your_email@example.com
   PASSWORD=your_password
   ```

4. Configure your court preferences in `courts.yaml`

## Usage

### Checking Available Slots

The primary script is `check_slots.py`, which checks for available slots on rec.us:

```
python check_slots.py
```

This will run continuously, checking for slots at the configured interval.

### Automatic Booking

To automatically book a court when slots become available:

```
python book_on_time.py
```

**Note**: While `book_on_time.py` works, it may need optimization for better efficiency.

### Managing Notifications

To mark all notifications as viewed:

```
python mark_as_viewed.py
```

**Note**: This is mainly useful if you don't regularly clean the notifications in the JSONL file.

## Configuration

Edit `courts.yaml` to configure court preferences:
- `url`: The booking URL for the court
- `days_in_advance`: How many days ahead to check
- `opening_time`: When the booking window opens
- `min_booking_time_weekday`/`min_booking_time_weekend`: Earliest time to book
- `min_duration`: Minimum reservation duration in minutes

## Implementation Notes

- The notification system uses both a log file and a JSONL file to track notifications
- Notifications include court name, date, time, duration, and viewed status
- Selenium WebDriver is used to interact with the rec.us website
