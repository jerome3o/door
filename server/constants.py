import os
from datetime import time


# API Keys and Endpoints
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
NTFY_TOPIC = os.getenv("NTFY_TOPIC")

# File Paths
SEED_KEY_FILE = ".keys.json"
KEY_FILE = ".keys.db.json"
PROMPTS_FILE = ".prompts.json"

# GPIO Pin Configurations
OPEN_ACTUATOR_PIN1 = 23
OPEN_ACTUATOR_PIN2 = 24
CLOSE_ACTUATOR_PIN1 = 17
CLOSE_ACTUATOR_PIN2 = 22

# Default Values
DEFAULT_DELAY = 17

# API Settings
ALLOWED_ORIGINS = ["*"]

# File Directories
THEMES_DIR = "./fe/themes"
GENERATED_DIR = "./fe/generated"
STAGING_DIR = "./fe/staging"

# Time Constants
COOKIE_EXPIRATION_DAYS = 365 * 10
WELCOME_START_TIME = time(9, 0)
WELCOME_END_TIME = time(22, 0)

# Log File
LOG_FILE = "door_access.log"

# HTML Templates
EXAMPLE_HTML_FILE = "example_html.html"
LOGIN_HTML_FILE = "fe/login.html"

# API Key Header Names
API_KEY_HEADER_NAME = "X-API-Key"
API_KEY_QUERY_NAME = "key"
API_KEY_COOKIE_NAME = "api_key"


FLATMATES: set[str] = set(os.environ["FLATMATES"].split(","))
