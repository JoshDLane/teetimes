# User credentials and booking preferences
import os
from datetime import datetime
import time

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

load_dotenv(".env.local")
username = os.getenv("USERNAME")
password = os.getenv("PASSWORD")
booking_time = "12:30"
min_duration = 60  # Minimum duration in minutes

# Pre processing
booking_time_dt = datetime.strptime(booking_time, "%H:%M")

# Initialize the WebDriver
driver = webdriver.Chrome()  # or webdriver.Firefox() if using Firefox
print("WebDriver initialized.")

try:
    # Navigate to the login page
    # driver.get('https://www.rec.us/login')  # Update with the actual login URL
    # print("Navigated to login page.")

    # # Log in
    # driver.find_element(By.ID, 'username_field_id').send_keys(username)  # Update with actual field ID
    # print(f"Entered username: {username}")
    # driver.find_element(By.ID, 'password_field_id').send_keys(password)  # Update with actual field ID
    # print("Entered password.")
    # driver.find_element(By.ID, 'login_button_id').click()  # Update with actual button ID
    # print("Clicked login button.")
    # We'll redefine the login process later

    # Navigate to the booking page
    driver.get(
        "https://www.rec.us/locations/360736ab-a655-478d-aab5-4e54fea0c140?tab=book-now"
    )
    print("Navigated to booking page.")

    # Wait for the page to load
    print("Waiting for the page to load...")
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CLASS_NAME, "swiper-slide"))
    )
    print("Page loaded successfully.")

    # Find available slots
    slots = driver.find_elements(By.CLASS_NAME, "swiper-slide")
    print(f"Found {len(slots)} available slots.")

    for slot in slots:
        time_text = slot.find_element(By.TAG_NAME, "p").text
        durations = slot.find_elements(By.CLASS_NAME, "text-neutral-600")
        print(
            f"Checking slot with time: {time_text} and durations: {[duration.text for duration in durations]}"
        )

        # Convert time_text to a datetime object for comparison
        slot_time = datetime.strptime(time_text, "%I:%M %p")  # Adjust format as needed

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
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "fixed"))
                    )
                    print("Booking dialog appeared.")

                    # Select duration and participant
                    print("Attempting to select duration...")
                    duration_button = driver.find_element(
                        By.XPATH, "//label[text()='Duration']/following-sibling::button"
                    )
                    duration_button.click()
                    print("Duration button clicked. Please select the desired duration.")

                    # Select court (if necessary)
                    # print("Attempting to select court...")
                    # court_button = driver.find_element(
                    #     By.XPATH,
                    #     "//h6[text()='Select a court']/following-sibling::button",
                    # )
                    # court_button.click()
                    # print("Court button clicked. Please select the desired court.")

                    # add a little wait to debug
                    time.sleep(5)

                    # Click the book button
                    print("Attempting to click the book button...")
                    book_button = driver.find_element(
                        By.XPATH, "//button[text()='Book']"
                    )
                    book_button.click()
                    print("Booking successful!")
                    break

    else:
        print("No suitable slots found.")

finally:
    # Close the browser
    driver.quit()
    print("Browser closed.")
