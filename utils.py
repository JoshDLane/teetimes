import logging
import os
import threading
import time
from datetime import date, datetime
from typing import Dict

import requests
from pydantic import BaseModel
from selenium.webdriver import Remote
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chromium.remote_connection import (
    ChromiumRemoteConnection as Connection,
)
from selenium.webdriver.common.action_chains import ActionChains

from environment_vars import PUSHOVER_TOKEN, PUSHOVER_URL, PUSHOVER_USER
from notification_tracker import is_slot_notified, mark_slot_notified


class AvailableSlot(BaseModel):
    datetime: datetime
    course: str


class Notification(BaseModel):
    course: str
    date_times: list[datetime]
    url: str


def wait_for_cloudflare_challenge(driver, timeout=30):
    """
    Wait for Cloudflare challenge to complete and page to load properly.
    
    Args:
        driver: Selenium WebDriver instance
        timeout: Maximum time to wait in seconds
    
    Returns:
        bool: True if page loaded successfully, False if timeout
    """
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            # Check if we're still on Cloudflare challenge page
            page_source = driver.page_source.lower()
            
            if "just a moment" in page_source or "checking your browser" in page_source:
                logging.info("Still on Cloudflare challenge page, waiting...")
                time.sleep(2)
                continue
            
            # Check if page has loaded properly (look for golf-related content)
            if "golf" in page_source or "tee time" in page_source or "booking" in page_source:
                logging.info("Page loaded successfully after Cloudflare challenge")
                return True
            
            # If we get here, page might be loaded but we need to wait a bit more
            time.sleep(1)
            
        except Exception as e:
            logging.warning(f"Error while waiting for Cloudflare challenge: {e}")
            time.sleep(1)
    
    logging.warning("Timeout waiting for Cloudflare challenge to complete")
    return False


def create_driver():
    """
    Create a driver with enhanced stealth capabilities.
    Supports both SeleniumBase UC mode (local) and remote server (deployed).
    """
    # Check if remote server is available (deployed environment)
    if os.environ.get("REMOTE_SERVER"):
        # Use remote server (your existing setup)
        chrome_options = Options()
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-web-security")
        
        connection = Connection(os.environ["REMOTE_SERVER"], "goog", "chrome")
        return Remote(connection, options=chrome_options)
        
    # Check if browserless is available (alternative deployed environment)
    elif os.environ.get("BROWSER_TOKEN") and os.environ.get("BROWSER_WEBDRIVER_ENDPOINT"):
        # Use Browserless (deployed environment)
        chrome_options = Options()
        chrome_options.set_capability("browserless:token", os.environ["BROWSER_TOKEN"])
        chrome_options.add_argument("--headless=new")
        
        return Remote(
            command_executor=os.environ["BROWSER_WEBDRIVER_ENDPOINT"],
            options=chrome_options,
        )
    else:
        # Use SeleniumBase with UC mode for local development
        from seleniumbase import Driver
        driver = Driver(uc=True, headless=False, incognito=True)
        return driver
    
    
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

    logging.info(
        f"Found {len(newly_found_slots)} new slots, of {len(available_slots)} total"
    )

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


def click_checkbox_at_coordinates(driver, x_offset=10, y_offset=162):
    """
    Simulates a click on a checkbox using calculated coordinates.
    
    Args:
        driver: Selenium WebDriver instance
        x_offset: Additional x offset from the calculated position (default: 10px)
        y_offset: Additional y offset from the calculated position (default: 162px)
    
    The calculation assumes:
    - Screen width: 1200px
    - Box width: 63rem
    - Y position: 8rem + y_offset
    """
    # Convert rem to pixels (assuming 1rem = 16px)
    rem_to_px = 16
    
    # Calculate x coordinate: 1200 - (63rem / 2) + x_offset
    box_width_px = 63 * rem_to_px  # 63rem converted to pixels
    x = 1200 - (box_width_px / 2) + x_offset
    
    # Calculate y coordinate: 8rem + y_offset
    y = (8 * rem_to_px) + y_offset
    
    logging.info(f"Clicking at coordinates: x={x}, y={y}")
    
    # Use ActionChains to perform the click
    actions = ActionChains(driver)
    actions.move_by_offset(x, y).click().perform()
    
    # Reset the mouse position to avoid affecting subsequent actions
    actions.move_by_offset(-x, -y).perform()
    
    logging.info("Checkbox click simulated successfully")


def navigate_with_uc(driver, url):
    """
    Navigate to URL with appropriate method based on driver type.
    
    Args:
        driver: WebDriver instance (SeleniumBase or Remote)
        url: URL to navigate to
    
    Returns:
        bool: True if navigation successful, False otherwise
    """
    try:
        # Check if this is a SeleniumBase driver (has UC methods)
        if hasattr(driver, 'uc_open_with_reconnect'):
            # Use SeleniumBase UC mode for local development
            logging.info(f"Using SeleniumBase UC mode to navigate to {url}")
            
            # Open URL using UC mode with 6 second reconnect time
            driver.uc_open_with_reconnect(url, reconnect_time=6)
            
            # Attempt to click the CAPTCHA checkbox if present
            driver.uc_gui_click_captcha()
            
        else:
            # Use regular navigation for remote drivers
            logging.info(f"Using regular navigation for remote driver to {url}")
            driver.get(url)
        
        # Wait for Cloudflare challenge to complete
        if not wait_for_cloudflare_challenge(driver, timeout=30):
            logging.error(f"Failed to bypass Cloudflare challenge for {url}")
            return False
            
        logging.info(f"Successfully navigated to {url}")
        return True
        
    except Exception as e:
        logging.error(f"Failed to navigate to {url}: {e}")
        return False
