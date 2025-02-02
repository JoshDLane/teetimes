import logging
import os

from notifs import (
    NOTIFICATION_JSON_PATH,
    load_notified_messages,
    save_notified_messages,
)


def mark_all_as_viewed() -> None:
    """
    Marks all notifications as viewed and saves them back to the file.
    """
    if not os.path.exists(NOTIFICATION_JSON_PATH):
        logging.warning(
            f"{NOTIFICATION_JSON_PATH} does not exist. No notifications to mark as viewed."
        )
        return

    notified_messages = load_notified_messages()
    for message in notified_messages:
        message.is_viewed = True

    save_notified_messages(notified_messages)
    logging.info("All notifications have been marked as viewed.")


if __name__ == "__main__":
    mark_all_as_viewed()
