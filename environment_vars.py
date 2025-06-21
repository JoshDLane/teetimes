import os

from dotenv import load_dotenv

load_dotenv() 

PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN")
PUSHOVER_USER = os.getenv("PUSHOVER_USER")
PUSHOVER_URL = os.getenv("PUSHOVER_URL")