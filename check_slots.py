import json
import logging
import os
import random
import threading
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Dict

import requests
from pydantic import BaseModel, Field, HttpUrl, RootModel
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from environment_vars import PUSHOVER_TOKEN, PUSHOVER_URL, PUSHOVER_USER
from notifs import (
    NOTIFICATION_JSON_PATH,
    NOTIFICATION_LOG_PATH,
    Notification,
)


class NPlayerOptions(Enum):
    TWO = 2
    THREE = 3
    FOUR = 4
    ANY = 'Any'
    

class CourseConfig(BaseModel):
    """Configuration for a single course."""
    url: HttpUrl
    allowed_days_in_advance: int = Field(default=7, ge=1, le=30)
    earliest_time: str = Field(default="7:00", pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")
    latest_time: str = Field(default="16:00", pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")
    n_players: NPlayerOptions = Field(default=NPlayerOptions.ANY)
class CourseConfigs(RootModel):
    """Configuration for all courses."""
    root: Dict[str, CourseConfig]

# Load and validate configuration from JSON file
with open("courses.json", "r") as file:
    raw_config = json.load(file)
    config = CourseConfigs.model_validate(raw_config).root

# Configure loggingL
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

INTERVAL_SECONDS = 30

notified_slots = set()


# Define the path for the notification file
if not os.path.exists(os.path.dirname(NOTIFICATION_LOG_PATH)):
    os.makedirs(os.path.dirname(NOTIFICATION_LOG_PATH))
if not os.path.exists(os.path.dirname(NOTIFICATION_JSON_PATH)):
    os.makedirs(os.path.dirname(NOTIFICATION_JSON_PATH))

class AvailableSlot(BaseModel):
    datetime: datetime
    course: str
    
def wait_for_times_or_no_times(driver, timeout=20) -> list[WebElement]:
    """Wait until either time slots are present or the 'no times' message appears."""

    def either_condition(drv):
        # 1. Check for time slots
        slots = drv.find_elements(By.CLASS_NAME, "booking-start-time-label")
        if slots:
            return slots  # Return the slots if found

        # 2. Check for the 'no times' message
        try:
            no_times_elem = drv.find_element(
                By.XPATH,
                "//*[contains(text(), 'Use Time/Day filters to find desired teetime')]",
            )
            if no_times_elem.is_displayed():
                return "no_times"
        except Exception:
            pass  # Not found yet

        return False  # Keep waiting

    try:
        result = WebDriverWait(driver, timeout).until(either_condition)
        if result == "no_times":
            logging.info(
                "No time slots found: 'Use Time/Day filters to find desired teetime' message is displayed."
            )
            return []
        else:
            return result  # This is the list of slot elements
    except TimeoutException:
        logging.warning("Timed out waiting for time slots or 'no times' message.")
        return []
    
def get_bethpage_black_times(
    driver: WebDriver,
    course_name: str,
    date_checking: date,
    n_players: NPlayerOptions = NPlayerOptions.ANY,
    earliest_time: time = datetime.strptime("7:00", "%H:%M").time(),
    latest_time: time = datetime.strptime("16:00", "%H:%M").time(),
) -> list[AvailableSlot]:
    available_slots: list[AvailableSlot] = []
    url = 'https://foreupsoftware.com/index.php/booking/19765/2431#teetimes'
    driver.get(url)
    logging.info(f"Navigated to {url}")
    log_in_link = driver.find_element(
        By.CSS_SELECTOR, "ul.navbar-right.visible-lg a.login"
    )
    print("log_in_link", log_in_link)
    log_in_link.click()
    print("Clicked Log In")

    print("enter email")
    email_input = driver.find_element(By.ID, "login_email")
    email_input.send_keys("joshdlane22@gmail.com")
    
    # enter password
    print("enter password")
    password_input = driver.find_element(By.ID, "login_password")
    password_input.send_keys("Jdlane22")
    
    # submit login
    login_btn = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                "//button[contains(@class, 'login') and normalize-space(text())='Log In']",
            )
        )
    )
    login_btn.click()
    # password_input.submit()
    print("submitted login")
    # select NYS Resident 
    # wait for login modal to disappear
    # Wait for the modal to disappear
    WebDriverWait(driver, 10).until(
        EC.invisibility_of_element_located((By.ID, "login"))
    )
    # Wait for NYS Resident button to be clickable, then click im
    nys_resident_btn = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                "//button[contains(text(), 'Verified NYS Resident - Bethpage/Sunken Meadow')]",
            )
        )
    ) 
    nys_resident_btn.click()
    print("clicked nys resident")
    # select black course
    course_selector = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.ID, "schedule_select"))
    )
    select = Select(course_selector)
    select.select_by_visible_text("Bethpage Black Course")
    print("selected black course")
    # enter date
    date_input = driver.find_element(By.NAME, 'date')
    driver.execute_script("arguments[0].value = '';", date_input)
    # date_input.clear()
    print('cleared date')
    date_str = date_checking.strftime('%Y-%m-%d')
    date_input.send_keys(date_str)
    print('entered date')
    # select n players
    print(f"Selecting {n_players.value} players")
    any_btn = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                f"//a[contains(@class, 'btn') and contains(@class, 'btn-primary') and text()='{n_players.value}']",
            )
        )
    )
    any_btn.click()
    print('clicked n players')
    
    # search for times
    time_slots = wait_for_times_or_no_times(driver, timeout=20)
    time_texts = [slot.text.strip() for slot in time_slots]
    
    print('earliest_time', earliest_time)
    print('latest_time', latest_time)
    for time_text in time_texts:
        print('time_text', time_text)
        try:
            # Parse the time text (e.g., "5:30pm")
            slot_time = datetime.strptime(time_text, "%I:%M%p").time()
            if isinstance(earliest_time, str):
                earliest_time = datetime.strptime(earliest_time, "%H:%M").time()
            if isinstance(latest_time, str):
                latest_time = datetime.strptime(latest_time, "%H:%M").time()
            # Check if time is within our window
            if earliest_time <= slot_time <= latest_time:
                # Create a datetime by combining the date and time
                slot_datetime = datetime.combine(date_checking, slot_time)
                available_slots.append(
                    AvailableSlot(datetime=slot_datetime, course=course_name)
                )
                logging.info(f"Found available slot at {time_text}")
        except ValueError as e:
            logging.warning(f"Could not parse time slot: {time_text}, error: {e}")
            continue
    return available_slots

site_parsers = {
    "bethpage_black": get_bethpage_black_times,
}

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

def check_slots_for_course(
    driver: WebDriver,
    course_name: str,
    course_config: CourseConfig,
    date_checking: datetime,
):
    """
    Checks available slots for a specific court and date.

    Parameters:
    - driver: Selenium WebDriver instance.
    - url (str): URL of the court booking page.
    - court_name (str): Name of the court.
    - target_date (datetime): Date to check availability.
    - booking_time_dt (datetime): Minimum booking time.
    - min_duration (int): Minimum duration in minutes.

    Returns:
    - List[NotificationMessage]: A list of new notifications sent.
    """
    site_parser = site_parsers[course_name]
    earliest_time = datetime.strptime(course_config.earliest_time, "%H:%M").time()
    latest_time = datetime.strptime(course_config.latest_time, "%H:%M").time()
    available_slots = site_parser(
        driver,
        course_name,
        date_checking,
        course_config.n_players,
        earliest_time,
        latest_time,
    )
    if available_slots:
        logging.info(
            f"Found {len(available_slots)} available slots for {course_name} on {date_checking.date()}"
        )
        notify_about_new_openings(available_slots)

    return available_slots

def book_availability_checker(
    courses: Dict[str, CourseConfig], interval_minutes: int, start_date: str | None = None
) -> None:
    """
    Periodically checks availability for multiple courts in a loop.
    """
    if start_date:
        start_date_dt = datetime.strptime(start_date, "%Y/%m/%d")
    else:
        start_date_dt = datetime.now()

    while True:
        logging.info("--- Starting new availability check cycle ---")
        for course_name, course_config in courses.items():
            logging.info(f"Checking course: {course_name}")

            # Set up Chrome options for headless mode
            chrome_options = Options()
            # chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")  # Bypass OS security model
            chrome_options.add_argument(
                "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_experimental_option(
                "prefs",
                {
                    "credentials_enable_service": False,
                    "profile.password_manager_enabled": False,
                    "profile.password_manager_leak_detection": False,
                },
            )
            chrome_options.add_argument("--disable-dev-shm-usage")

            driver = webdriver.Chrome(options=chrome_options)

            try:
                days_in_advance = course_config.allowed_days_in_advance
                for day_offset in range(days_in_advance + 1):
                    date_checking = datetime.now() + timedelta(days=day_offset)
                    if date_checking < start_date_dt:
                        continue

                    logging.info(
                        f"Checking {course_name} for date: {date_checking.strftime('%Y-%m-%d')}"
                    )
                    check_slots_for_course(driver, course_name, course_config, date_checking)
            except Exception as e:
                logging.error(
                    f"An unhandled error occurred for course {course_name}: {e}",
                    exc_info=True,
                )
            finally:
                driver.quit()

        # Wait for the next cycle
        variance = random.uniform(-0.2, 0.2)  # +/- 20% variance
        wait_time = interval_seconds * (1 + variance)
        logging.info(f"Check cycle complete. Waiting for {wait_time:.2f} seconds...")
        time.sleep(wait_time)


if __name__ == "__main__":
    book_availability_checker(
        courses=config,
        interval_seconds=INTERVAL_SECONDS,
    )
