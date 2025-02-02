import logging
import os
from datetime import datetime

from pydantic import BaseModel

NOTIFICATION_LOG_PATH = "logs/notifications.log"  # Updated path
NOTIFICATION_JSON_PATH = "logs/notifications.jsonl"  # Updated path


class NotificationMessage(BaseModel):
    court_name: str
    date: str
    time: str
    duration: int
    is_viewed: bool = False


def load_notified_messages() -> list[NotificationMessage]:
    if not os.path.exists(NOTIFICATION_JSON_PATH):
        logging.warning(
            f"{NOTIFICATION_JSON_PATH} does not exist. Returning an empty list."
        )
        return []  # Return an empty list if the file does not exist
    with open(NOTIFICATION_JSON_PATH, "r") as json_file:
        return [NotificationMessage.model_validate_json(line) for line in json_file]


def save_notified_messages(notified_messages: list[NotificationMessage]) -> None:
    # Sort messages by is_viewed, then by date, and then by court name
    notified_messages.sort(
        key=lambda msg: (
            msg.is_viewed,
            datetime.strptime(msg.date, "%A, %d %B %Y"),
            msg.court_name,
        )
    )

    with open(NOTIFICATION_JSON_PATH, "w") as json_file:
        for msg in notified_messages:
            json_file.write(msg.model_dump_json() + "\n")
