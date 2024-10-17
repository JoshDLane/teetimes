import logging
import os
import subprocess
import time
from datetime import datetime, timedelta

import requests
import yaml
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
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


def send_pushbullet_notification(
    message: str, access_token: str = PUSHBULLET_ACCESS_TOKEN
):
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
    sound: str = "default"
):
    """
    Sends a local notification on macOS using osascript.

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
    except Exception as e:
        logging.error(f"Error sending macOS notification: {e}")


def check_slots(driver, url, court_name, target_date, booking_time_dt, min_duration):
    """
    Checks available slots for a specific court and date.

    Parameters:
    - driver: Selenium WebDriver instance.
    - url (str): URL of the court booking page.
    - court_name (str): Name of the court.
    - target_date (datetime): Date to check availability.
    - booking_time_dt (datetime): Minimum booking time.
    - min_duration (int): Minimum duration in minutes.
    """
    try:
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
            if (
                date_element.text == str(target_date.day)
                and "react-datepicker__day--outside-month"
                not in date_element.get_attribute("class")
            ):
                date_element.click()
                logging.info(f"Selected date: {target_date.strftime('%A, %d %B %Y')}")
                break

        # Find available slots
        slots = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".swiper-slide"))
        )
        logging.info(
            f"Found {len(slots)} available slots for {court_name} on {target_date.strftime('%A, %d %B %Y')}."
        )

        for slot in slots:
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
                            f"available slot at {time_text} for {duration_minutes} minutes."
                        )
                        send_macos_notification(message)
                        logging.info(f"Notification sent: {message}")
                        return  # Stop after finding the first matching slot
            except Exception as e:
                logging.error(f"Error processing slot: {e}")
                continue

    except Exception as e:
        logging.error(f"Error checking slots for {court_name} on {target_date}: {e}")


def book_availability_checker(court_configs, interval_minutes):
    """
    Periodically checks availability for multiple courts.

    Parameters:
    - court_configs (dict): Dictionary of court configurations.
    - interval_minutes (int): Interval between attempts in minutes.
    """
    while True:
        logging.info("Starting availability check...")
        driver = (
            webdriver.Chrome()
        )  # Initialize WebDriver; ensure chromedriver is in PATH
        try:
            for court_name, url_info in court_configs.items():
                url = url_info["url"]
                days_in_advance = url_info.get("days_in_advance", 7)
                booking_time = url_info.get("min_booking_time", "17:00")
                min_duration = url_info.get("min_duration", 60)
                booking_time_dt = datetime.strptime(booking_time, "%H:%M")

                for day_offset in range(days_in_advance + 1):
                    target_date = datetime.now() + timedelta(days=day_offset)
                    check_slots(
                        driver,
                        url,
                        court_name,
                        target_date,
                        booking_time_dt,
                        min_duration,
                    )
        except Exception as e:
            logging.error(f"An error occurred during the availability check: {e}")
        finally:
            driver.quit()
            logging.info("WebDriver closed.")

        logging.info(f"Waiting for {interval_minutes} minutes before the next check...")
        time.sleep(interval_minutes * 60)  # Wait for the specified interval


if __name__ == "__main__":
    # Example configuration
    court_configs = config  # Use the entire config as court configurations
    check_interval = 1

    book_availability_checker(
        court_configs=court_configs,
        interval_minutes=check_interval,
    )
