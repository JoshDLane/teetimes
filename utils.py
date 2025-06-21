
import logging
import subprocess
import threading
from datetime import date, datetime
from typing import Dict

import httpx
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from environment_vars import PUSHOVER_TOKEN, PUSHOVER_URL, PUSHOVER_USER
from notifs import (
    NOTIFICATION_LOG_PATH,
    Notification,
)
from utils import create_driver

ntfy_url = "https://ntfy.sh/court-slots"
def send_macos_notification(
    message: str,
    title: str = "Court Slot Available!",
    subtitle: str = "",
    sound: str = "default",
) -> None:
    """
    Sends a local notification on macOS using terminal-notifier and logs it to a file.
    """
    try:
        # Build the terminal-notifier command
        command = ["terminal-notifier", "-title", title, "-message", message]
        if subtitle:
            command.extend(["-subtitle", subtitle])
        if sound:
            command.extend(["-sound", sound])

        logging.info(f"Sending notification with command: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True, check=True)

        logging.info("Notification sent successfully.")
        logging.info(f"Command output: {result.stdout}")

        with open(NOTIFICATION_LOG_PATH, "a") as notification_file:
            notification_file.write(f"{datetime.now()}: {message}\n")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error sending notification: {e}")
        logging.error(f"Command output: {e.output}")
        logging.error(f"Command stderr: {e.stderr}")
    except Exception as e:
        logging.error(f"Error sending notification: {e}")
        logging.error(f"Error type: {type(e)}")
        import traceback

        logging.error(f"Traceback: {traceback.format_exc()}")

async def send_mobile_notification(message: str) -> None:
    """
    Sends a mobile notification using the Pushover API.
    """
    async with httpx.AsyncClient() as client:
        await client.post(ntfy_url, content=message)


def create_driver():
    # Set up Chrome options for headless mode
    chrome_options = Options()
    # chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")  # Bypass OS security model
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    chrome_options.add_argument("--window-size=1920,1080")  # Full HD resolution
    chrome_options.add_experimental_option(
        "prefs",
        {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.password_manager_leak_detection": False,  # <--- Add this line
        },
    )
    chrome_options.add_argument(
        "--disable-dev-shm-usage"
    )  # Overcome limited resource problems

    return webdriver.Chrome(
        options=chrome_options
    )  # Initialize WebDriver with options
    
    
def send_notification_worker(notification: Notification):
    """Sends a single notification in a background thread."""
    try:
        time_strs = [
            dt.strftime("%-I:%M %p").strip() for dt in sorted(notification.date_times)
        ]
        message = (
            f"New tee time(s) at {notification.course} for "
            f"{notification.date_times[0].strftime('%A, %b %d')}: {', '.join(time_strs)}"
        )

        data = {
            "token": PUSHOVER_TOKEN,
            "user": PUSHOVER_USER,
            "message": message,
            "title": f"Tee Time Alert: {notification.course}",
        }
        resp = requests.post(PUSHOVER_URL, data=data)
        resp.raise_for_status()
        logging.info(f"Notification sent for {notification.course}")
    except Exception as e:
        logging.error(f"Failed to send notification for {notification.course}: {e}")


def send_notification(notification: Notification):
    """Launches a daemon thread to send a notification without blocking."""
    thread = threading.Thread(target=send_notification_worker, args=(notification,))
    thread.daemon = True
    thread.start()


def notify_about_new_openings(available_slots: list[AvailableSlot]):
    """Filters for new slots, groups them by course, and sends notifications."""
    newly_found_slots = []
    for slot in available_slots:
        slot_id = f"{slot.course}-{slot.datetime}"
        if slot_id not in notified_slots:
            newly_found_slots.append(slot)
            notified_slots.add(slot_id)

    if not newly_found_slots:
        return

    # Group new slots by course and date
    notifications_to_send: Dict[tuple[str, date], Notification] = {}
    for slot in newly_found_slots:
        key = (slot.course, slot.datetime.date())
        if key not in notifications_to_send:
            notifications_to_send[key] = Notification(course=slot.course, date_times=[])
        notifications_to_send[key].date_times.append(slot.datetime)

    for notification in notifications_to_send.values():
        send_notification(notification)
