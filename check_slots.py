import logging
import os
import subprocess
import time
from datetime import datetime, timedelta

import requests
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Load environment variables
load_dotenv(".env.local")
PUSHBULLET_ACCESS_TOKEN = os.getenv("PUSHBULLET_ACCESS_TOKEN", "")
if not PUSHBULLET_ACCESS_TOKEN:
    raise ValueError("PUSHBULLET_ACCESS_TOKEN must be set")

# Load configuration from YAML file
with open("courts.yaml", "r") as file:
    config = yaml.safe_load(file)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Define the path for the notification file
INTERVAL_MINUTES = 15
NOTIFICATION_LOG_PATH = "logs/notifications.log"  # Updated path
NOTIFICATION_JSON_PATH = "logs/notifications.jsonl"  # Updated path

if not os.path.exists(os.path.dirname(NOTIFICATION_LOG_PATH)):
    os.makedirs(os.path.dirname(NOTIFICATION_LOG_PATH))
if not os.path.exists(os.path.dirname(NOTIFICATION_JSON_PATH)):
    os.makedirs(os.path.dirname(NOTIFICATION_JSON_PATH))


# Define a Pydantic model for notifications
class NotificationMessage(BaseModel):
    court_name: str
    date: str
    time: str
    duration: int


def load_notified_messages() -> list[NotificationMessage]:
    if not os.path.exists(NOTIFICATION_JSON_PATH):
        logging.warning(
            f"{NOTIFICATION_JSON_PATH} does not exist. Returning an empty list."
        )
        return []  # Return an empty list if the file does not exist
    with open(NOTIFICATION_JSON_PATH, "r") as json_file:
        return [NotificationMessage.model_validate_json(line) for line in json_file]


def save_notified_messages(notified_messages: list[NotificationMessage]) -> None:
    with open(NOTIFICATION_JSON_PATH, "w") as json_file:
        for msg in notified_messages:
            json_file.write(msg.model_dump_json() + "\n")


def send_pushbullet_notification(
    message: str, access_token: str = PUSHBULLET_ACCESS_TOKEN
) -> None:
    try:
        data = {"type": "note", "title": "Court Slot Available!", "body": message}
        headers = {"Access-Token": access_token, "Content-Type": "application/json"}
        response = requests.post(
            "https://api.pushbullet.com/v2/pushes", json=data, headers=headers
        )
        if response.status_code == 200:
            logging.info("Pushbullet notification sent successfully.")
        else:
            logging.error(f"Failed to send Pushbullet notification: {response.text}")
    except Exception as e:
        logging.error(f"Error sending Pushbullet notification: {e}")


def send_macos_notification(
    message: str,
    title: str = "Court Slot Available!",
    subtitle: str = "",
    sound: str = "default",
) -> None:
    """
    Sends a local notification on macOS using osascript and logs it to a file.

    Parameters:
    - message (str): The message to display in the notification.
    - title (str): The title of the notification.
    - subtitle (str): The subtitle of the notification.
    - sound (str): The sound to play with the notification.
    """
    try:
        script = f'display notification "{message}" with title "{title}"'
        if subtitle:
            script += f' subtitle "{subtitle}"'
        if sound:
            script += f' sound name "{sound}"'

        subprocess.run(["osascript", "-e", script], check=True)
        logging.info("macOS notification sent successfully.")

        # Write the notification message to the file
        with open(NOTIFICATION_LOG_PATH, "a") as notification_file:
            notification_file.write(f"{datetime.now()}: {message}\n")
    except Exception as e:
        logging.error(f"Error sending macOS notification: {e}")


def check_slots(
    driver: WebDriver,
    url: str,
    court_name: str,
    target_date: datetime,
    booking_time_dt: datetime,
    min_duration: int,
    notified_messages: list[NotificationMessage],
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
    - notified_messages (List[NotificationMessage]): List of already notified messages.

    Returns:
    - List[NotificationMessage]: A list of new notifications sent.
    """
    new_notifications = []
    driver.get(url)
    logging.info(f"Navigated to {court_name} booking page.")

    # Open the date picker
    date_picker_input = (
        WebDriverWait(driver, 10)
        .until(
            EC.element_to_be_clickable(
                (By.CLASS_NAME, "react-datepicker__input-container")
            )
        )
        .find_element(By.TAG_NAME, "input")
    )
    date_picker_input.click()
    logging.info("Date picker opened.")

    # Select the target date
    date_elements = driver.find_elements(By.CLASS_NAME, "react-datepicker__day")
    for date_element in date_elements:
        if date_element.text == str(
            target_date.day
        ) and "react-datepicker__day--outside-month" not in (
            date_element.get_attribute("class") or ""
        ):
            date_element.click()
            logging.info(f"Selected date: {target_date.strftime('%A, %d %B %Y')}")
            break

    # Find available slots
    slots = WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".swiper-slide"))
    )
    logging.info(
        f"Found {len(slots)} slots for {court_name} on {target_date.strftime('%A, %d %B %Y')}."
    )

    notified_slots = []  # Track notified slots
    error_slots = []  # Track slots with errors
    unnotified_slots = []  # Track slots that do not meet requirements
    already_notified_slots = []  # Track slots that have already been notified

    for i, slot in enumerate(slots):
        try:
            if not slot.is_displayed():
                driver.execute_script("arguments[0].scrollIntoView(true);", slot)

            time_text = slot.find_element(By.TAG_NAME, "p").text
            slot_time = datetime.strptime(time_text, "%I:%M %p")

            durations = slot.find_elements(By.CLASS_NAME, "text-neutral-600")
            for duration in durations:
                duration_minutes = int(duration.text)
                if slot_time >= booking_time_dt and duration_minutes >= min_duration:
                    message = (
                        f"For court {court_name}, on {target_date.strftime('%A, %d %B %Y')}, "
                        f"a matching slot is at {time_text} for {duration_minutes} minutes."
                    )
                    # Create a notification message
                    notification = NotificationMessage(
                        court_name=court_name,
                        date=target_date.strftime("%A, %d %B %Y"),
                        time=time_text,
                        duration=duration_minutes,
                    )
                    # Check if the message has already been notified
                    if notification not in notified_messages:
                        send_macos_notification(message)
                        notified_slots.append(f"{i}: {time_text}")
                        new_notifications.append(notification)
                    else:
                        already_notified_slots.append(f"{i}: {time_text}")
            # Append to unnotified_slots if no duration met
            unnotified_slots.append(f"{i}: {time_text}")
        except Exception:
            error_slots.append(i)
            continue

    # Log the results after processing all slots
    if notified_slots:
        logging.info(
            f"Notifications sent for the following slots: {', '.join(notified_slots)}"
        )
    if already_notified_slots:
        logging.info(
            f"Slots that were already notified: {', '.join(already_notified_slots)}"
        )
    if unnotified_slots:
        logging.info(
            f"Slots that were checked but did not meet requirements: {', '.join(unnotified_slots)}"
        )
    if error_slots:
        logging.error(
            f"Errors encountered for the following slots: {', '.join(map(str, error_slots))}"
        )

    return new_notifications


def book_availability_checker(
    court_configs: dict[str, dict], interval_minutes: int
) -> None:
    """
    Periodically checks availability for multiple courts.

    Parameters:
    - court_configs (Dict[str, Dict]): Dictionary of court configurations.
    - interval_minutes (int): Interval between attempts in minutes.
    """
    notified_messages = load_notified_messages()
    while True:
        logging.info("Starting availability check...")

        print(f"Checking for courts: {court_configs.keys()}")
        for court_name, url_info in court_configs.items():
            print(f"Court {court_name} and url info: {url_info}")
            url = url_info["url"]
            days_in_advance = url_info.get("days_in_advance", 7)
            booking_time = url_info.get("min_booking_time", "17:00")
            min_duration = url_info.get("min_duration", 60)
            booking_time_dt = datetime.strptime(booking_time, "%H:%M")

            # Set up Chrome options for headless mode
            chrome_options = Options()
            chrome_options.add_argument("--headless")  # Run in headless mode
            chrome_options.add_argument("--no-sandbox")  # Bypass OS security model
            chrome_options.add_argument(
                "--disable-dev-shm-usage"
            )  # Overcome limited resource problems

            driver = webdriver.Chrome(
                options=chrome_options
            )  # Initialize WebDriver with options

            for day_offset in range(days_in_advance + 1):
                target_date = datetime.now() + timedelta(days=day_offset)
                try:
                    new_notifs = check_slots(
                        driver,
                        url,
                        court_name,
                        target_date,
                        booking_time_dt,
                        min_duration,
                        notified_messages,
                    )
                    if new_notifs:
                        notified_messages.extend(new_notifs)
                except Exception as e:
                    logging.error(
                        f"An error occurred for court {court_name} on {target_date}: {e}"
                    )
            save_notified_messages(notified_messages)
            driver.quit()
            logging.info("WebDriver closed.")

        logging.info(f"Waiting for {interval_minutes} minutes before the next check...")
        time.sleep(interval_minutes * 60)  # Wait for the specified interval


if __name__ == "__main__":
    book_availability_checker(
        court_configs=config,
        interval_minutes=INTERVAL_MINUTES,
    )
