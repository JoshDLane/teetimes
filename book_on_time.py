# User credentials and booking preferences
import logging
import os
import time
from datetime import datetime, timedelta

import yaml
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

load_dotenv(".env.local")
username = os.getenv("USERNAME")
password = os.getenv("PASSWORD")

# Load configuration from YAML file
with open("courts.yaml", "r") as file:
    config = yaml.safe_load(file)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def book_reservation(
    url: str,
    opening_time: str,
    days_in_advance: int,
    booking_time: str,
    min_duration: int,
    n_attempts: int,
):
    """
    Automates the reservation booking process.

    Parameters:
    - opening_time (str): Time to start the booking process (24-hour format, e.g., "08:00").
    - days_in_advance (int): Number of days in advance to book.
    - booking_time (str): Earliest booking time (24-hour format, e.g., "17:00").
    - min_duration (int): Minimum duration in minutes.
    - retries (int): Number of retry attempts in case of failure.
    """
    # Pre processing
    current_time = datetime.now()
    opening_time_dt = datetime.strptime(opening_time, "%H:%M").replace(
        year=current_time.year, month=current_time.month, day=current_time.day
    )

    # Calculate the time to wait until the opening time
    wait_time = (opening_time_dt - current_time).total_seconds()
    if wait_time > 0:
        print(f"Waiting for {wait_time} seconds until the opening time...")
        while wait_time > 0:
            mins, secs = divmod(wait_time, 60)
            time_format = f"{int(mins):02}:{int(secs):02}"
            print(f"Time remaining: {time_format}", end="\r")
            time.sleep(1)
            wait_time -= 1

    booking_time_dt = datetime.strptime(booking_time, "%H:%M")
    duration_mapping = {30: "30 min", 60: "1 hour", 90: "90 min", 120: "2 hours"}

    attempt = 0
    while attempt < n_attempts:
        attempt += 1
        driver = None
        try:
            if not username or not password:
                raise ValueError(
                    "Username or password not found in environment variables."
                )

            # Initialize the WebDriver inside the retry loop
            driver = webdriver.Chrome()  # or webdriver.Firefox() if using Firefox
            print("WebDriver initialized.")

            # Navigate to the login page
            driver.get(url)
            print("Navigated to login page.")

            # Click the menu button in the top right corner
            driver.find_element(By.ID, "radix-:r0:").click()  # Click the menu button
            print("Clicked menu button.")

            # Wait for the login options to appear
            WebDriverWait(driver, 1).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[contains(text(), 'Log In')]")
                )
            )
            print("Login options appeared.")

            # Click the "Log In" option
            driver.find_element(By.XPATH, "//div[contains(text(), 'Log In')]").click()
            print("Clicked Log In option.")

            # Wait for the login dialog to appear
            WebDriverWait(driver, 1).until(
                EC.presence_of_element_located((By.ID, "radix-:ri:"))
            )
            print("Login dialog appeared.")

            # Enter username and password
            driver.find_element(By.ID, "email").send_keys(username)  # Enter email
            print(f"Entered username: {username}")
            driver.find_element(By.ID, "password").send_keys(password)  # Enter password
            print("Entered password.")

            # Click the login submit button to validate login
            driver.find_element(
                By.XPATH, "//button[contains(text(), 'log in & continue')]"
            ).click()
            print("Clicked login submit button to validate login.")

            # Open the date picker
            print("Opening the date picker...")
            date_picker_container = driver.find_element(
                By.CLASS_NAME, "react-datepicker__input-container"
            )
            date_picker_input = date_picker_container.find_element(By.TAG_NAME, "input")
            date_picker_input.click()
            print("Date picker opened.")

            # Calculate the target date
            target_date = datetime.now() + timedelta(days=days_in_advance)
            target_day = target_date.day

            # Select the target date
            print(f"Selecting date {target_date.strftime('%A, %B %d, %Y')}...")
            date_elements = driver.find_elements(By.CLASS_NAME, "react-datepicker__day")
            for date_element in date_elements:
                if date_element.text == str(
                    target_day
                ) and "react-datepicker__day--outside-month" not in (
                    date_element.get_attribute("class") or ""
                ):
                    date_element.click()
                    print(f"Date {target_date.strftime('%A, %B %d, %Y')} selected.")
                    break

            # Find available slots
            slots = driver.find_elements(By.CSS_SELECTOR, ".swiper-slide")
            print(f"Found {len(slots)} available slots.")

            while True:
                for slot in slots:
                    # Check if the slot contains the expected elements
                    try:
                        if not slot.is_displayed():
                            print(f"Slot {slot} is not displayed properly")
                            driver.execute_script(
                                "arguments[0].scrollIntoView(true);", slot
                            )
                            # time.sleep(0.1)
                        time_text = slot.find_element(By.TAG_NAME, "p").text
                        durations = slot.find_elements(
                            By.CLASS_NAME, "text-neutral-600"
                        )
                        print(
                            f"Checking slot with time: {time_text} and durations: {[duration.text for duration in durations]}"
                        )

                        # Convert time_text to a datetime object for comparison
                        slot_time = datetime.strptime(
                            time_text, "%I:%M %p"
                        )  # Adjust format as needed

                        # Check if the slot matches the criteria
                        if slot_time >= booking_time_dt:
                            print(
                                f"Slot {time_text} matches booking time {booking_time}. Checking durations..."
                            )
                            for duration in durations:
                                if int(duration.text) >= min_duration:
                                    print(
                                        f"Duration {duration.text} is sufficient (>= {min_duration} minutes). Clicking the slot..."
                                    )
                                    slot.click()  # Click the slot

                                    # Wait for the booking dialog to appear
                                    print("Waiting for the booking dialog to appear...")
                                    WebDriverWait(driver, 1).until(
                                        EC.presence_of_element_located(
                                            (By.CLASS_NAME, "fixed")
                                        )
                                    )
                                    print("Booking dialog appeared.")

                                    # Select duration and participant
                                    print("Attempting to select duration...")
                                    desired_duration_text = duration_mapping[
                                        min_duration
                                    ]
                                    # Locate the duration dropdown button
                                    duration_button = driver.find_element(
                                        By.XPATH,
                                        "//label[text()='Duration']/following-sibling::button",
                                    )
                                    duration_button.click()
                                    print("Duration dropdown opened.")
                                    # Wait for the dropdown to open and locate the desired duration option
                                    desired_duration = driver.find_element(
                                        By.XPATH,
                                        f"//div[contains(text(), '{desired_duration_text}')]",
                                    )
                                    desired_duration.click()
                                    print(f"Duration {desired_duration_text} selected.")

                                    # Select the participant
                                    print("Selecting participant...")
                                    participant_button = driver.find_element(
                                        By.XPATH,
                                        "//h6[text()='Participant']/following-sibling::div/button",
                                    )
                                    participant_button.click()
                                    print("Participant button clicked.")

                                    account_owner_option = driver.find_element(
                                        By.XPATH,
                                        "//li[.//div[contains(text(), 'Oscar Courbit')]]",
                                    )
                                    account_owner_option.click()
                                    print("Account owner selected.")

                                    print("Attempting to click the book button...")
                                    book_button = WebDriverWait(driver, 1).until(
                                        EC.element_to_be_clickable(
                                            (By.XPATH, "//button[text()='Book']")
                                        )
                                    )
                                    book_button.click()
                                    print("Booking clicked.")

                                    # Locate and click the "Send Code" button
                                    print(
                                        "Attempting to click the 'Send Code' button..."
                                    )
                                    # Add an explicit wait to ensure the button is present
                                    WebDriverWait(driver, 1).until(
                                        EC.element_to_be_clickable(
                                            (By.XPATH, "//button[text()='Send Code']")
                                        )
                                    )
                                    send_code_button = driver.find_element(
                                        By.XPATH, "//button[text()='Send Code']"
                                    )
                                    send_code_button.click()
                                    print(
                                        "'Send Code' button clicked. Waiting for code verification..."
                                    )

                                    # Wait for user to manually enter the code
                                    verification_code = input(
                                        "Please enter the verification code sent to your phone: "
                                    )

                                    # Locate the verification code input field and enter the code
                                    print("Entering the verification code...")
                                    verification_input = driver.find_element(
                                        By.ID, "totp"
                                    )
                                    verification_input.send_keys(verification_code)
                                    print("Verification code entered.")

                                    # Locate and click the "Confirm" button
                                    print("Attempting to click the 'Confirm' button...")
                                    WebDriverWait(driver, 1).until(
                                        EC.element_to_be_clickable(
                                            (
                                                By.XPATH,
                                                "//button[contains(text(), 'Confirm')]",
                                            )
                                        )
                                    )  # Wait for the button to be clickable
                                    confirm_button = driver.find_element(
                                        By.XPATH,
                                        "//button[contains(text(), 'Confirm')]",
                                    )
                                    confirm_button.click()
                                    print("Reservation confirmed.")

                                    time.sleep(20)
                                    break

                    except Exception as e:
                        logging.error(
                            f"Error accessing slot elements: {e}. Continuing to next slot."
                        )
                        continue  # Continue to the next slot

                else:
                    print("No suitable slots found.")
                    break

        except Exception as e:
            logging.error(f"Attempt {attempt} failed: {e}")
            if "Connection refused" in str(e):
                logging.warning("Connection refused. Retrying...")
            if attempt < n_attempts:
                logging.info("Retrying...")
                time.sleep(5)  # Wait before retrying
            else:
                logging.error("All retry attempts failed. Please check the issue.")
                raise
        finally:
            # Ensure the browser is closed after each attempt
            if driver:
                driver.quit()
                print("Browser closed.")


if __name__ == "__main__":
    court_info = config["jackson"]
    book_reservation(
        url=court_info["url"],
        opening_time=court_info["opening_time"],
        days_in_advance=court_info["days_in_advance"],
        booking_time=court_info["min_booking_time"],
        min_duration=court_info["min_duration"],
        n_attempts=3,
    )
