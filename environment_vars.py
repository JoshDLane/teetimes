import os

from dotenv import load_dotenv

load_dotenv() 

PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN")
PUSHOVER_USER = os.getenv("PUSHOVER_USER")
PUSHOVER_URL = "https://api.pushover.net/1/messages.json"

# Redis configuration - Railway provides REDIS_URL
REDIS_URL = os.getenv("REDIS_URL")