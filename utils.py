
import logging
import subprocess
import httpx
from datetime import datetime
from notifs import (
    NOTIFICATION_LOG_PATH,
)

ntfy_url = "https://ntfy.sh/court-slots"
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

async def send_mobile_notification(message: str) -> None:
    """
    Sends a mobile notification using the Pushover API.
    """
    async with httpx.AsyncClient() as client:
        await client.post(ntfy_url, content=message)
