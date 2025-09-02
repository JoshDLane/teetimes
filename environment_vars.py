import os

from dotenv import load_dotenv

load_dotenv() 

PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN")
PUSHOVER_USER = os.getenv("PUSHOVER_USER")
PUSHOVER_URL = "https://api.pushover.net/1/messages.json"

# Redis configuration - Railway provides REDIS_URL
REDIS_URL = os.getenv("REDIS_URL")

# Proxy configuration
PROXY_HOST = os.getenv("PROXY_HOST")
PROXY_PORT = os.getenv("PROXY_PORT")
PROXY_USERNAME = os.getenv("PROXY_USERNAME")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD")
PROXY_TYPE = os.getenv("PROXY_TYPE", "http")  # http, https, socks4, socks5