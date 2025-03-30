import logging
import os
import random
import subprocess
import time
from datetime import datetime, timedelta

import yaml
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from notifs import (
    NOTIFICATION_JSON_PATH,
    NOTIFICATION_LOG_PATH,
    NotificationMessage,
    load_notified_messages,
    save_notified_messages,
)

# Load configuration from YAML file
with open("courts.yaml", "r") as file:
    config = yaml.safe_load(file)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Define the path for the notification file
INTERVAL_MINUTES = 10
if not os.path.exists(os.path.dirname(NOTIFICATION_LOG_PATH)):
    os.makedirs(os.path.dirname(NOTIFICATION_LOG_PATH))
if not os.path.exists(os.path.dirname(NOTIFICATION_JSON_PATH)):
    os.makedirs(os.path.dirname(NOTIFICATION_JSON_PATH))


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
    court_sections = driver.find_elements(By.CLASS_NAME, "mb-4")
    notified_slots = []  # Track notified slots
    error_slots = []  # Track slots with errors
    unnotified_slots = []  # Track slots that do not meet requirements
    already_notified_slots = []  # Track slots that have already been notified

    for section in court_sections:
        # Check if the section is for Tennis
        court_type = section.find_element(By.TAG_NAME, "p").text
        if "Tennis" not in court_type:
            logging.info(f"Skipping non-tennis section: {court_type}")
            continue  # Skip non-tennis sections

        slots = section.find_elements(By.CLASS_NAME, "swiper-slide")
        logging.info(
            f"Processing {len(slots)} slots for {court_name} on {target_date.strftime('%A, %d %B %Y')}."
        )

        for i, slot in enumerate(slots):
            try:
                if not slot.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView(true);", slot)

                time_text = slot.find_element(By.TAG_NAME, "p").text
                slot_time = datetime.strptime(time_text, "%I:%M %p")

                durations = slot.find_elements(By.CLASS_NAME, "text-neutral-600")
                for duration in durations:
                    duration_minutes = int(duration.text)
                    if (
                        slot_time >= booking_time_dt
                        and duration_minutes >= min_duration
                    ):
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
                            is_viewed=False,
                        )
                        # Check if the message has already been notified (ignoring is_viewed)
                        if not any(
                            n.court_name == notification.court_name
                            and n.date == notification.date
                            and n.time == notification.time
                            and n.duration == notification.duration
                            for n in notified_messages
                        ):
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
    court_configs: dict[str, dict], interval_minutes: int, start_date: str | None = None
) -> None:
    """
    Periodically checks availability for multiple courts.

    Parameters:
    - court_configs (Dict[str, Dict]): Dictionary of court configurations.
    - interval_minutes (int): Interval between attempts in minutes.
    - start_date (str): The date to start checking slots in "YYYY/MM/DD" format.
    """
    notified_messages = load_notified_messages()
    notified_messages = clean_outdated_notifications(notified_messages, start_date)

    # Convert start_date string to datetime object
    if start_date:
        start_date_dt = datetime.strptime(start_date, "%Y/%m/%d")
    else:
        start_date_dt = datetime.now()

    while True:
        logging.info("Starting availability check...")

        print(f"Checking for courts: {court_configs.keys()}")
        for court_name, url_info in court_configs.items():
            print(f"Court {court_name} and url info: {url_info}")
            url = url_info["url"]
            days_in_advance = url_info.get("days_in_advance", 7)
            min_duration = url_info.get("min_duration", 60)

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
                if target_date < start_date_dt:
                    continue
                # Determine if the target date is a weekday or weekend
                if target_date.weekday() < 5:  # Monday to Friday
                    booking_time = url_info.get("min_booking_time_weekday", "17:00")
                else:  # Saturday and Sunday
                    booking_time = url_info.get("min_booking_time_weekend", "8:00")
                booking_time_dt = datetime.strptime(booking_time, "%H:%M")
                print(f"Checking for {court_name} on {target_date} at {booking_time}")

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
        court_configs=config,
        interval_minutes=INTERVAL_MINUTES,
        start_date="2025/03/11",
    )
