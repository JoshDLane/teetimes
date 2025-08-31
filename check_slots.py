import json
import logging
import time as time_module
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, RootModel, field_validator
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from utils import AvailableSlot, create_driver, notify_about_new_openings


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
    dates: Optional[List[str]] = Field(default=None)
    n_players: NPlayerOptions = Field(default=NPlayerOptions.ANY)
    full_course_name: str = Field(default="Bethpage Black Course")
    
    @field_validator("dates", mode="before")
    def validate_dates(cls, v):
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("dates must be a list of strings")
        
        for day in v:
            try:
                datetime.strptime(day, "%m/%d")
            except ValueError:
                raise ValueError(f"Invalid date format: '{day}'. Must be MM/DD.")
        return v


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

INTERVAL_SECONDS = 30


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

def login_to_eazylinks(driver: WebDriver, course_config: CourseConfig, course_name: str) -> bool:
    """Login to eazylinks from /search."""
    try:
        url = str(course_config.url)
        driver.get(url)
        logging.info(f"Navigated to {url}")
        
        # Helper function to find elements in shadow DOM
        def find_element_in_shadow_dom(host_selector, target_selector):
            """Find an element inside shadow DOM using JavaScript."""
            script = f"""
            const host = document.querySelector('{host_selector}');
            if (host && host.shadowRoot) {{
                return host.shadowRoot.querySelector('{target_selector}');
            }}
            return null;
            """
            return driver.execute_script(script)
        
        def click_element_in_shadow_dom(host_selector, target_selector):
            """Click an element inside shadow DOM using JavaScript."""
            script = f"""
            const host = document.querySelector('{host_selector}');
            if (host && host.shadowRoot) {{
                const element = host.shadowRoot.querySelector('{target_selector}');
                if (element) {{
                    element.click();
                    return true;
                }}
            }}
            return false;
            """
            return driver.execute_script(script)
        
        # Handle "Verify you are human" checkbox that may appear on first page load
        try:
            # Wait for either human verification checkbox OR sign in link to appear
            def either_condition(drv):
                # Check for human verification checkbox (regular DOM)
                try:
                    checkbox = drv.find_element(By.XPATH, "//input[@type='checkbox']")
                    if checkbox.is_displayed() and checkbox.is_enabled():
                        return "checkbox"
                except Exception:
                    pass
                
                # Check for human verification checkbox in shadow DOM
                try:
                    shadow_checkbox = find_element_in_shadow_dom("*", "input[type='checkbox']")
                    if shadow_checkbox:
                        return "shadow_checkbox"
                except Exception:
                    pass
                
                # Check for sign in link
                try:
                    sign_in = drv.find_element(By.CSS_SELECTOR, "a[href='#/login'][ui-sref='login']")
                    if sign_in.is_displayed() and sign_in.is_enabled():
                        return "sign_in"
                except Exception:
                    pass
                
                return False  # Keep waiting
            
            result = WebDriverWait(driver, 10).until(either_condition)
            
            if result == "checkbox":
                # Human verification checkbox appeared first (regular DOM)
                checkbox = driver.find_element(By.XPATH, "//input[@type='checkbox']")
                checkbox.click()
                logging.info("Clicked 'Verify you are human' checkbox")
                
                # Wait for verification to complete (sign in link should appear)
                WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href='#/login'][ui-sref='login']"))
                )
                logging.info("Human verification completed - sign in link is now available")
                
            elif result == "shadow_checkbox":
                # Human verification checkbox appeared first (shadow DOM)
                success = click_element_in_shadow_dom("*", "input[type='checkbox']")
                if success:
                    logging.info("Clicked 'Verify you are human' checkbox in shadow DOM")
                    
                    # Wait for verification to complete (sign in link should appear)
                    WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href='#/login'][ui-sref='login']"))
                    )
                    logging.info("Human verification completed - sign in link is now available")
                else:
                    logging.warning("Failed to click checkbox in shadow DOM")
                    
            else:
                # Sign in link appeared directly (no verification needed)
                logging.info("No human verification needed - sign in link is available")
                
        except Exception as e:
            logging.info(f"Error during human verification check: {e}")
        
        # Click the Sign In link
        sign_in_link = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "a[href='#/login'][ui-sref='login']")
            )
        )
        sign_in_link.click()
        logging.info("Clicked Sign In link")

        # Enter username
        username_input = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "input[data-ng-model='loginModel.username'][name='login']")
            )
        )
        username_input.send_keys("Jdlane22")
        logging.info("Entered username")

        # Enter password
        password_input = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "input[type='password'][data-ng-model='loginModel.password']")
            )
        )
        password_input.send_keys("Jdl10014!")
        logging.info("Entered password")

        # Click the login button
        login_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button[data-ng-click='login()'][type='submit']")
            )
        )
        login_button.click()
        logging.info("Clicked login button")

        # Wait for login to complete - wait for "My Account" link to appear
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//a[contains(text(), 'My Account')]"))
        )
        logging.info("Login completed successfully - My Account link is visible")

        return True
        
    except Exception as e:
        logging.error(f"Failed to login to {course_name}: {e}")
        return False

def login_to_foreupsoftware(driver: WebDriver, course_config: CourseConfig, course_name: str) -> bool:
    """Login to foreupsoftware and select NYS Resident status. Returns True if successful."""
    try:
        url = str(course_config.url)
        driver.get(url)
        logging.info(f"Navigated to {url}")
        
        # Click login link
        log_in_link = driver.find_element(
            By.CSS_SELECTOR, "ul.navbar-right.visible-lg a.login"
        )
        log_in_link.click()
        logging.info("Clicked Log In")

        # Enter email
        email_input = driver.find_element(By.ID, "login_email")
        email_input.send_keys("joshdlane22@gmail.com")
        
        # Enter password
        password_input = driver.find_element(By.ID, "login_password")
        password_input.send_keys("Jdlane22")
        
        # Submit login
        login_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//button[contains(@class, 'login') and normalize-space(text())='Log In']",
                )
            )
        )
        login_btn.click()
        logging.info("Submitted login")
        
        # Wait for login modal to disappear
        WebDriverWait(driver, 10).until(
            EC.invisibility_of_element_located((By.ID, "login"))
        )
        
        # Select NYS Resident
        if course_name == "bethpage_black":
            nys_resident_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//button[contains(text(), 'Verified NYS Resident - Bethpage/Sunken Meadow')]",
                    )
                )
            ) 
        else: 
            print("montauk")
            nys_resident_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//button[contains(text(), 'Resident')]",
                    )
                )
            ) 
        nys_resident_btn.click()
        logging.info("Selected NYS Resident status")
        
        return True
        
    except Exception as e:
        logging.error(f"Failed to login to {course_name}: {e}")
        return False


def get_eazylinks_times(
    driver: WebDriver,
    course_name: str,
    date_checking: date,
    course_config: CourseConfig,
    earliest_time: time = datetime.strptime("7:00", "%H:%M").time(),
    latest_time: time = datetime.strptime("16:00", "%H:%M").time(),
) -> list[AvailableSlot]:
    """Get available times for eazylinks courses for a specific date."""
    available_slots: list[AvailableSlot] = []
    logging.info(f"Getting times for {course_name} on {date_checking}")
    
    try:
        # Wait for the page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "ngrs-range-slider"))
        )
        
        # 1. Select the date
        date_str = date_checking.strftime('%m/%d/%Y')
        logging.info(f"Selecting date: {date_str}")
        
        # Find and click the date input/selector
        try:
            # Look for a date input field or date picker
            date_input = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[data-ng-model*='date'], input[type='date'], .date-picker input"))
            )
            driver.execute_script("arguments[0].value = '';", date_input)
            date_input.send_keys(date_str)
            logging.info(f"Entered date: {date_str}")
        except Exception as e:
            logging.warning(f"Could not find date input, trying alternative selectors: {e}")
            # Try alternative date selection methods
            try:
                # Look for date picker or calendar element
                date_picker = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".date-picker, .calendar, [data-ng-model*='date']"))
                )
                date_picker.click()
                # You might need to add more specific date selection logic here
                logging.info("Clicked date picker")
            except Exception:
                logging.warning("Could not find date selector, proceeding without date selection")
        
        # 2. Adjust the time range slider based on earliest and latest time
        logging.info(f"Adjusting time range to {earliest_time} - {latest_time}")
        
        # Convert times to minutes since midnight for the slider
        earliest_minutes = earliest_time.hour * 60 + earliest_time.minute
        latest_minutes = latest_time.hour * 60 + latest_time.minute
        
        try:
            # Find the range slider
            range_slider = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "ngrs-range-slider"))
            )
            
            # Find the min and max handles
            min_handle = range_slider.find_element(By.CLASS_NAME, "ngrs-handle-min")
            max_handle = range_slider.find_element(By.CLASS_NAME, "ngrs-handle-max")
            
            # Get the slider width to calculate positions
            slider_width = range_slider.size['width']
            
            # Calculate positions as percentages
            # Assuming the slider range is from 0 to 1440 minutes (24 hours)
            min_position = (earliest_minutes / 1440) * 100
            max_position = (latest_minutes / 1440) * 100
            
            # Use JavaScript to set the slider values
            driver.execute_script(f"""
                var slider = arguments[0];
                var minHandle = arguments[1];
                var maxHandle = arguments[2];
                var minPos = arguments[3];
                var maxPos = arguments[4];
                
                // Set the model values
                var scope = angular.element(slider).scope();
                scope.ec.timeRange.userMinOne = {earliest_minutes};
                scope.ec.timeRange.userMaxOne = {latest_minutes};
                scope.$apply();
                
                // Update handle positions
                minHandle.style.left = minPos + '%';
                maxHandle.style.left = maxPos + '%';
            """, range_slider, min_handle, max_handle, min_position, max_position)
            
            logging.info(f"Set time range slider to {earliest_minutes}-{latest_minutes} minutes")
            
        except Exception as e:
            logging.warning(f"Could not adjust time range slider: {e}")
        
        # 3. Adjust player number
        logging.info(f"Selecting {course_config.n_players.value} players")
        try:
            # Look for player selection buttons or dropdown
            player_selector = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((
                    By.XPATH, 
                    f"//button[contains(text(), '{course_config.n_players.value}') or contains(@data-ng-model, '{course_config.n_players.value}')]"
                ))
            )
            player_selector.click()
            logging.info(f"Selected {course_config.n_players.value} players")
        except Exception as e:
            logging.warning(f"Could not select player number: {e}")
        
        # 4. Look for available times
        # Wait a moment for the page to update after our selections
        time_module.sleep(2)
        
        # Look for time slots using the specific structure from eazylinks
        try:
            # First check if the tee-time-block exists
            tee_time_block = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "ul.tee-time-block"))
            )
            
            # Find all time spans within the tee-time-block
            time_slots = tee_time_block.find_elements(By.CSS_SELECTOR, "span.time.ng-binding")
            
            logging.info(f"Found {len(time_slots)} time slots")
            
            for slot in time_slots:
                try:
                    time_text = slot.text.strip()
                    logging.info(f"Processing time slot: {time_text}")
                    
                    # Parse the time text (format: "3:50 PM", "4:30 PM", etc.)
                    time_text_clean = time_text.split()[0]  # Take first part in case there's additional text
                    
                    # Try different time formats
                    slot_time = None
                    for time_format in ["%I:%M %p", "%I:%M%p", "%H:%M", "%I:%M"]:
                        try:
                            slot_time = datetime.strptime(time_text_clean, time_format).time()
                            break
                        except ValueError:
                            continue
                    
                    if slot_time is None:
                        logging.warning(f"Could not parse time: {time_text}")
                        continue
                    
                    # Check if time is within our window
                    if earliest_time <= slot_time <= latest_time:
                        # Create a datetime by combining the date and time
                        slot_datetime = datetime.combine(date_checking, slot_time)
                        available_slots.append(
                            AvailableSlot(datetime=slot_datetime, course=course_name)
                        )
                        logging.info(f"Found available slot at {time_text}")
                        
                except Exception as e:
                    logging.warning(f"Error processing time slot: {e}")
                    continue
                    
        except TimeoutException:
            logging.info("No time slots found or timeout waiting for tee-time-block")
        except Exception as e:
            logging.error(f"Error looking for time slots: {e}")
            
    except Exception as e:
        logging.error(f"Error getting times for {course_name} on {date_checking}: {e}")
        
    return available_slots
    
    
def get_foreupsoftware_times(
    driver: WebDriver,
    course_name: str,
    date_checking: date,
    course_config: CourseConfig,
    earliest_time: time = datetime.strptime("7:00", "%H:%M").time(),
    latest_time: time = datetime.strptime("16:00", "%H:%M").time(),
) -> list[AvailableSlot]:
    """Get available times for Bethpage Black Course for a specific date."""
    available_slots: list[AvailableSlot] = []
    logging.info(f"Getting times for {course_name} on {date_checking}")
    try:
        # Select black course
        course_selector = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "schedule_select"))
        )
        select = Select(course_selector)
        select.select_by_visible_text(course_config.full_course_name)
        logging.info(f"Selected {course_config.full_course_name}")
        
        # Enter date
        date_input = driver.find_element(By.NAME, 'date')
        driver.execute_script("arguments[0].value = '';", date_input)
        date_str = date_checking.strftime('%m-%d-%Y')
        date_input.send_keys(date_str)
        logging.info(f"Entered date: {date_str}")
        
        # Select n players
        logging.info(f"Selecting {course_config.n_players.value} players")
        any_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    f"//a[contains(@class, 'btn') and contains(@class, 'btn-primary') and text()='{course_config.n_players.value}']",
                )
            )
        )
        any_btn.click()
        logging.info('Clicked n players')
        
        # Search for times
        time_slots = wait_for_times_or_no_times(driver, timeout=20)
        time_texts = [slot.text.strip() for slot in time_slots]
        
        logging.info(f'Checking times between {earliest_time} and {latest_time}')
        for time_text in time_texts:
            logging.info(f'Processing time: {time_text}')
            try:
                # Parse the time text (e.g., "5:30pm")
                slot_time = datetime.strptime(time_text, "%I:%M%p").time()
                
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
                
    except Exception as e:
        logging.error(f"Error getting times for {course_name} on {date_checking}: {e}")
        
    return available_slots


site_parsers = {
    "bethpage_black": get_foreupsoftware_times,
    "montauk_downs": get_foreupsoftware_times,
    "marine_park": get_eazylinks_times,
}


def check_slots_for_course(
    driver: WebDriver,
    course_name: str,
    course_config: CourseConfig,
    date_checking: date,
) -> list[AvailableSlot]:
    """
    Checks available slots for a specific course and date.

    Parameters:
    - driver: Selenium WebDriver instance.
    - course_name: Name of the course.
    - course_config: Configuration for the course.
    - date_checking: Date to check availability.

    Returns:
    - List[AvailableSlot]: List of available slots found.
    """
    site_parser = site_parsers[course_name]
    earliest_time = datetime.strptime(course_config.earliest_time, "%H:%M").time()
    latest_time = datetime.strptime(course_config.latest_time, "%H:%M").time()
    
    available_slots = site_parser(
        driver,
        course_name,
        date_checking,
        course_config,
        earliest_time,
        latest_time,
    )
    
    if available_slots:
        logging.info(
            f"Found {len(available_slots)} available slots for {course_name} on {date_checking}"
        )
        notify_about_new_openings(available_slots, str(course_config.url))

    return available_slots


def parse_date_from_config(date_str: str, year: int = None) -> date:
    """Parse a date string from config (MM/DD format) and return a date object."""
    if year is None:
        year = datetime.now().year
    
    # Parse MM/DD format
    month, day = map(int, date_str.split('/'))
    
    # If the date has already passed this year, use next year
    target_date = date(year, month, day)
    if target_date < date.today():
        target_date = date(year + 1, month, day)
    
    return target_date


def get_dates_to_check(course_config: CourseConfig) -> List[date]:
    """Get list of dates to check based on course configuration."""
    dates_to_check = []
    
    if course_config.dates:
        # Use specific dates from config
        for date_str in course_config.dates:
            dates_to_check.append(parse_date_from_config(date_str))
    else:
        # Use allowed_days_in_advance to generate dates
        for i in range(1, course_config.allowed_days_in_advance + 1):
            check_date = date.today() + timedelta(days=i)
            dates_to_check.append(check_date)
    print("dates to check", dates_to_check)
    return dates_to_check


class CourseManager:
    """Manages a single course with its own browser instance."""
    
    def __init__(self, course_name: str, course_config: CourseConfig):
        self.course_name = course_name
        self.course_config = course_config
        self.driver: Optional[WebDriver] = None
        self.is_logged_in = False
        self.running = False
        self.max_session_duration = 300  # 5 minutes in seconds
        self.session_start_time = None

    def handle_login(self) -> bool:
        """Handle login for a course."""
        if self.course_name.lower() in ["bethpage_black", "montauk_downs"]:
            login_to_foreupsoftware(self.driver, self.course_config, self.course_name)
        elif self.course_name.lower() == "marine_park":
            login_to_eazylinks(self.driver, self.course_config, self.course_name)
            
    def should_refresh_session(self) -> bool:
        """Check if we should refresh the session."""
        if not self.session_start_time:
            return True
        elapsed = time_module.time() - self.session_start_time
        return elapsed > self.max_session_duration

    def refresh_session(self) -> bool:
        """Refresh the driver session."""
        try:
            if self.driver:
                self.driver.quit()
            self.driver = create_driver()
            self.handle_login()
            self.is_logged_in = True
            self.session_start_time = time_module.time()
            logging.info(f"Refreshed session for {self.course_name}")
            return True
        except Exception as e:
            logging.error(f"Failed to refresh session for {self.course_name}: {e}")
            return False

    def initialize_driver(self) -> bool:
        """Initialize the driver and login if needed."""
        try:
            self.driver = create_driver()            
        except Exception as e:
            logging.error(f"Failed to initialize driver for {self.course_name}: {e}")
            return False
        try:
            self.handle_login()
            self.is_logged_in = True
        except Exception as e:
            logging.error(f"Failed to login for {self.course_name}: {e}")
            return False
        logging.info(f"Successfully initialized driver for {self.course_name}")
        return True
    
    def check_course_availability(self) -> None:
        """Check availability for all configured dates for this course."""
        if self.should_refresh_session():
            if not self.refresh_session():
                logging.error(f"Cannot check availability for {self.course_name}: failed to refresh session")
                return
        
        if not self.driver or not self.is_logged_in:
            logging.error(f"Cannot check availability for {self.course_name}: driver not initialized or not logged in")
            return
        
        dates_to_check = get_dates_to_check(self.course_config)
        logging.info(f"Checking {self.course_name} for {len(dates_to_check)} dates: {[d.strftime('%m/%d') for d in dates_to_check]}")
        
        for check_date in dates_to_check:
            try:
                logging.info(f"Checking {self.course_name} for {check_date.strftime('%m/%d/%Y')}")
                available_slots = check_slots_for_course(
                    self.driver,
                    self.course_name,
                    self.course_config,
                    check_date,
                )
                
                if available_slots:
                    logging.info(f"Found {len(available_slots)} slots for {self.course_name} on {check_date}")
                
            except Exception as e:
                error_msg = str(e)
                if (
                    "Couldn't access session" in error_msg
                    or "timeout" in error_msg.lower()
                ):
                    logging.warning(
                        f"Session timeout detected for {self.course_name}, attempting to refresh..."
                    )
                    if self.refresh_session():
                        logging.info(
                            f"Session refreshed successfully for {self.course_name}"
                        )
                        # Retry the current date
                        try:
                            available_slots = check_slots_for_course(
                                self.driver,
                                self.course_name,
                                self.course_config,
                                check_date,
                            )
                            if available_slots:
                                logging.info(
                                    f"Retry successful: Found {len(available_slots)} slots for {self.course_name} on {check_date}"
                                )
                        except Exception as retry_e:
                            logging.error(
                                f"Retry failed for {self.course_name} on {check_date}: {retry_e}"
                            )
                    else:
                        logging.error(
                            f"Failed to refresh session for {self.course_name}"
                        )
                else:
                    logging.error(
                        f"Error checking {self.course_name} for {check_date}: {e}"
                    )
    
    def run_continuous_checking(self, interval_seconds: int) -> None:
        """Run continuous checking for this course."""
        self.running = True
        logging.info(f"Starting continuous checking for {self.course_name} with {interval_seconds}s intervals")
        
        while self.running:
            try:
                self.check_course_availability()
                time_module.sleep(interval_seconds)
            except Exception as e:
                logging.error(f"Error in continuous checking for {self.course_name}: {e}")
                time_module.sleep(interval_seconds)
    
    def stop(self) -> None:
        """Stop the continuous checking."""
        self.running = False
        if self.driver:
            self.driver.quit()
            logging.info(f"Stopped and closed driver for {self.course_name}")


def run_browsers_for_all_courses(
    courses: Dict[str, CourseConfig], interval_seconds: int
) -> None:
    """
    Run multiple course managers concurrently using ThreadPoolExecutor.
    """
    course_managers = []
    
    try:
        # Initialize all course managers
        for course_name, course_config in courses.items():
            manager = CourseManager(course_name, course_config)
            if manager.initialize_driver():
                course_managers.append(manager)
                logging.info(f"Initialized {course_name}")
            else:
                logging.error(f"Failed to initialize {course_name}")
        
        if not course_managers:
            logging.error("No course managers were successfully initialized")
            return
        
        # Use ThreadPoolExecutor to manage threads
        with ThreadPoolExecutor(max_workers=len(course_managers), thread_name_prefix="CourseManager") as executor:
            # Submit all course managers to the thread pool
            future_to_manager = {
                executor.submit(manager.run_continuous_checking, interval_seconds): manager 
                for manager in course_managers
            }
            
            logging.info(f"Started {len(course_managers)} course managers in thread pool")
            
            # Wait for all futures to complete (or handle exceptions)
            for future in as_completed(future_to_manager):
                manager = future_to_manager[future]
                try:
                    # This will only return if the thread completes normally
                    future.result()
                except Exception as e:
                    logging.error(f"Course manager {manager.course_name} encountered an error: {e}")
                    
    except KeyboardInterrupt:
        logging.info("Received interrupt signal, stopping all course managers...")
        for manager in course_managers:
            manager.stop()
    except Exception as e:
        logging.error(f"Error in main loop: {e}")
        for manager in course_managers:
            manager.stop()
    finally:
        # Ensure all managers are stopped
        for manager in course_managers:
            if manager.running:
                manager.stop()


if __name__ == "__main__":
    run_browsers_for_all_courses(
        courses=config,
        interval_seconds=INTERVAL_SECONDS,
    )
