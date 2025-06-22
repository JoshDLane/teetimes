import logging
import threading
from datetime import date, datetime
from typing import Dict

import requests
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from environment_vars import PUSHOVER_TOKEN, PUSHOVER_URL, PUSHOVER_USER
from notification_tracker import is_slot_notified, mark_slot_notified


class AvailableSlot(BaseModel):
    datetime: datetime
    course: str


class Notification(BaseModel):
    course: str
    date_times: list[datetime]
    url: str

def create_driver():
    # Set up Chrome options for headless mode
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")  # Enable headless mode for Railway
    chrome_options.add_argument("--no-sandbox")  # Bypass OS security model
    chrome_options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems
    chrome_options.add_argument("--disable-gpu")  # Disable GPU hardware acceleration
    chrome_options.add_argument("--disable-extensions")  # Disable extensions
    chrome_options.add_argument("--disable-plugins")  # Disable plugins
    chrome_options.add_argument("--disable-images")  # Disable images for faster loading
    chrome_options.add_argument("--disable-web-security")  # Disable web security
    chrome_options.add_argument("--allow-running-insecure-content")  # Allow insecure content
    chrome_options.add_argument("--disable-features=VizDisplayCompositor")  # Disable display compositor
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    chrome_options.add_argument("--window-size=1920,1080")  # Full HD resolution
    chrome_options.add_experimental_option(
        "prefs",
        {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.password_manager_leak_detection": False,
        },
    )

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
            f"New tee time(s) at {notification.course} for:\n"
            f"{notification.date_times[0].strftime('%A, %b %d')}:\n- {'\n- '.join(time_strs)}\n\n"
            f"Site: {notification.url}"
        )

        data = {
            "token": PUSHOVER_TOKEN,
            "user": PUSHOVER_USER,
            "message": message,
            "title": f"Tee Time Alert: {notification.course}",
        }
        
        # Debug logging
        logging.info(f"PUSHOVER_TOKEN: {PUSHOVER_TOKEN}")
        logging.info(f"PUSHOVER_USER: {PUSHOVER_USER}")
        logging.info(f"PUSHOVER_URL: {PUSHOVER_URL}")
        logging.info(f"Message length: {len(message)}")
        logging.info(f"Full data being sent: {data}")
        
        resp = requests.post(PUSHOVER_URL, data=data)
        resp.raise_for_status()
        logging.info(f"Notification sent for {notification.course}")
    except Exception as e:
        logging.error(f"Failed to send notification for {notification.course}: {e}")
        # Log the response content if available
        if hasattr(e, 'response') and e.response is not None:
            logging.error(f"Response content: {e.response.text}")


def send_notification(notification: Notification):
    """Launches a daemon thread to send a notification without blocking."""
    thread = threading.Thread(target=send_notification_worker, args=(notification,))
    thread.daemon = True
    thread.start()


def notify_about_new_openings(available_slots: list[AvailableSlot], url: str):
    """Filters for new slots, groups them by course, and sends notifications."""
    newly_found_slots = []
    for slot in available_slots:
        if not is_slot_notified(slot.course, slot.datetime):
            newly_found_slots.append(slot)
            mark_slot_notified(slot.course, slot.datetime)

    if not newly_found_slots:
        return

    # Group new slots by course and date
    notifications_to_send: Dict[tuple[str, date], Notification] = {}
    for slot in newly_found_slots:
        key = (slot.course, slot.datetime.date())
        if key not in notifications_to_send:
            notifications_to_send[key] = Notification(
                course=slot.course, date_times=[], url=url
            )
        notifications_to_send[key].date_times.append(slot.datetime)

    for notification in notifications_to_send.values():
        send_notification(notification)
