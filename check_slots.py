import json
import logging
import os
import random
import time
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Dict

from pydantic import BaseModel, Field, HttpUrl, RootModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import Select

from notifs import (
    NOTIFICATION_JSON_PATH,
    NOTIFICATION_LOG_PATH,
    NotificationMessage,
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

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

INTERVAL_MINUTES = 1

notified_messages = []


# Define the path for the notification file
if not os.path.exists(os.path.dirname(NOTIFICATION_LOG_PATH)):
    os.makedirs(os.path.dirname(NOTIFICATION_LOG_PATH))
if not os.path.exists(os.path.dirname(NOTIFICATION_JSON_PATH)):
    os.makedirs(os.path.dirname(NOTIFICATION_JSON_PATH))

class AvailableSlot(BaseModel):
    datetime: datetime
    
def get_bethpage_black_times(driver: WebDriver, date_checking: date, n_players: NPlayerOptions = NPlayerOptions.ANY, earliest_time: datetime = datetime.strptime("7:00", "%H:%M"), latest_time: datetime = datetime.strptime("16:00", "%H:%M")
) -> list[AvailableSlot]:
    available_slots: list[AvailableSlot] = []
    url = 'https://foreupsoftware.com/index.php/booking/19765/2431#teetimes'
    driver.get(url)
    logging.info(f"Navigated to {url}")
    log_in_link = driver.find_element(
        By.CSS_SELECTOR, "ul.navbar-right.visible-lg a.login"
    )
    print('log_in_link', log_in_link)
    log_in_link.click()
    print("Clicked Log In")

    print('enter email')
    email_input = driver.find_element(By.ID, 'login_email')
    email_input.send_keys('joshdlane22@gmail.com')
    
    # enter password
    print('enter password')
    password_input = driver.find_element(By.ID, 'login_password')
    password_input.send_keys('Jdlane22')
    
    # submit login
    password_input.submit()
    
    # select NYS Resident 
    nys_resident_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Verified NYS Resident - Bethpage/Sunken Meadow')]")
    nys_resident_btn.click()
    
    # select black course
    course_selector = driver.find_element(By.ID, 'schedule_select')
    select = Select(course_selector)
    select.select_by_visible_text("Bethpage Black Course")
    
    # enter date
    date_input = driver.find_element(By.NAME, 'date')
    date_input.clear()
    date_str = date_checking.strftime('%Y-%m-%d')
    date_input.send_keys(date_str)
    
    # select n players
    print(f"Selecting {n_players} players")
    button = driver.find_element(By.XPATH, f"//button[@class='btn btn-primary' and text()={n_players}]")
    button.click()
    
    # search for times
    time_slots = driver.find_elements(By.CLASS_NAME, 'booking-start-time-label')
    for slot in time_slots:
        try:
            # Parse the time text (e.g., "5:30pm")
            time_text = slot.text.strip()
            slot_time = datetime.strptime(time_text, "%I:%M%p").time()
            
            # Check if time is within our window
            if earliest_time <= slot_time <= latest_time:
                # Create a datetime by combining the date and time
                slot_datetime = datetime.combine(date_checking, slot_time)
                available_slots.append(AvailableSlot(datetime=slot_datetime))
                logging.info(f"Found available slot at {time_text}")
        except ValueError as e:
            logging.warning(f"Could not parse time slot: {time_text}, error: {e}")
            continue
    
site_parsers = {
    'bethpage_black': get_bethpage_black_times,
}
def check_slots(
    driver: WebDriver,
    course_name: str,
    course_config: CourseConfig,
    date_checking: datetime,
) -> list[NotificationMessage]:
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
    new_notifications = []
    available_slots = site_parser(driver, date_checking, course_config.n_players, course_config.earliest_time, course_config.latest_time)
    for slot in available_slots:
        notification_id = f"{course_name}-{slot.datetime}"
        if notification_id in notified_messages:
            pass
        print(f'Notifying for {notification_id}')
        notified_messages.append(NotificationMessage)

    return new_notifications


def clean_outdated_notifications(
    notified_messages: list[NotificationMessage],
    start_date: str | None = None,
) -> list[NotificationMessage]:
    """
    Cleans out notifications that are from past dates.

    Parameters:
    - notified_messages (List[NotificationMessage]): List of notified messages.
    - start_date (str | None): Optional start date in "YYYY/MM/DD" format.

    Returns:
    - List[NotificationMessage]: Filtered list of notifications with only future dates.
    """
    current_date = datetime.now().date()

    # If start_date is provided, use it as the cutoff date if it's later than current date
    cutoff_date = current_date
    if start_date:
        start_date_dt = datetime.strptime(start_date, "%Y/%m/%d").date()
        cutoff_date = max(current_date, start_date_dt)

    return [
        msg
        for msg in notified_messages
        if datetime.strptime(msg.date, "%A, %d %B %Y").date() >= cutoff_date
    ]


def book_availability_checker(
    courses: Dict[str, CourseConfig], interval_minutes: int, start_date: str | None = None
) -> None:
    """
    Periodically checks availability for multiple courts.

    Parameters:
    - courses (Dict[str, CourseConfig]): Dictionary of course configurations.
    - interval_minutes (int): Interval between attempts in minutes.
    - start_date (str): The date to start checking slots in "YYYY/MM/DD" format.
    """
    # Convert start_date string to datetime object
    if start_date:
        start_date_dt = datetime.strptime(start_date, "%Y/%m/%d")
    else:
        start_date_dt = datetime.now()

    while True:
        logging.info("Starting availability check...")
        print('courses', courses)
        print(f"Checking for courses: {courses.keys()}")
        for course_name, course_config in courses.items():
            print(f"Course: {course_name}")
            days_in_advance = course_config.allowed_days_in_advance

            # Set up Chrome options for headless mode
            chrome_options = Options()
            # chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")  # Bypass OS security model
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
            chrome_options.add_argument('--window-size=1920,1080')  # Full HD resolution

            chrome_options.add_argument(
                "--disable-dev-shm-usage"
            )  # Overcome limited resource problems

            driver = webdriver.Chrome(
                options=chrome_options
            )  # Initialize WebDriver with options

            for day_offset in range(days_in_advance + 1):
                date_checking = datetime.now() + timedelta(days=day_offset)
                if date_checking < start_date_dt:
                    continue
                
                earliest_time = datetime.strptime(course_config.earliest_time, "%H:%M")
                latest_time = datetime.strptime(course_config.latest_time, "%H:%M")
                print(f"Checking for {course_name} on {date_checking} between {earliest_time} and {latest_time}")

                try:
                    new_notifs = check_slots(
                        driver,
                        course_name,
                        course_config,
                        date_checking,
                    )
                except Exception as e:
                    logging.error(
                        f"An error occurred for court {course_name} on {date_checking}: {e}"
                    )
            driver.quit()
            logging.info("WebDriver closed.")

        # Add randomness to the wait time
        randomness = random.uniform(-0.1, 0.1)  # Randomness between -10% and +10%
        wait_time = interval_minutes * 60 * (1 + randomness)  # Calculate the wait time
        while wait_time > 0:
            mins, secs = divmod(int(wait_time), 60)
            time_format = f"{int(mins):02}:{int(secs):02}"
            print(f"Time remaining: {time_format}", end="\r")
            time.sleep(1)
            wait_time -= 1
        print()  # Move to the next line after countdown


if __name__ == "__main__":
    book_availability_checker(
        courses=config,
        interval_minutes=INTERVAL_MINUTES,
    )
