import asyncio
import json
import logging
import os
import random
import re
import requests
import string
from pathlib import Path
import secrets
from typing import Dict, Annotated, Optional
from urllib.parse import urlencode
from datetime import datetime, time

from fastapi import Cookie, Depends, FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

# not found exception
from fastapi.exceptions import HTTPException

from elevenlabs import play
from elevenlabs.client import ElevenLabs
import os
import asyncio
import anthropic
from pydantic import BaseModel

from datetime import datetime, timedelta

from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader, APIKeyQuery

from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from server.telemetry import failed_login, send_message

from server.constants import (
    ELEVENLABS_API_KEY,
    NTFY_TOPIC,
    SEED_KEY_FILE,
    KEY_FILE,
    PROMPTS_FILE,
    OPEN_ACTUATOR_PIN1,
    OPEN_ACTUATOR_PIN2,
    CLOSE_ACTUATOR_PIN1,
    CLOSE_ACTUATOR_PIN2,
    DEFAULT_DELAY,
    ALLOWED_ORIGINS,
    THEMES_DIR,
    GENERATED_DIR,
    STAGING_DIR,
    COOKIE_EXPIRATION_DAYS,
    WELCOME_START_TIME,
    WELCOME_END_TIME,
    LOG_FILE,
    EXAMPLE_HTML_FILE,
    LOGIN_HTML_FILE,
    API_KEY_HEADER_NAME,
    API_KEY_QUERY_NAME,
    API_KEY_COOKIE_NAME,
    FLATMATES
)
from server.door_controller import DoorController, ActuatorController, cleanup
from server.auth import AuthMiddleware, Flatmate, User, AddKeyParams, router as auth_router

try:
    with open(PROMPTS_FILE, 'r') as file:
        _USER_WELCOME_PROMPTS: dict[str, list[str]] = json.load(file)
except FileNotFoundError:
    _USER_WELCOME_PROMPTS = {}

elevenlabs_client = ElevenLabs(
    api_key=ELEVENLABS_API_KEY,
)

with open(EXAMPLE_HTML_FILE) as f:
    EXAMPLE_HTML = f.read()

async def generate_welcome(prompt):
    anthropic_client = anthropic.AsyncAnthropic()
    message = await anthropic_client.messages.create(
        model="claude-3-opus-20240229",
        max_tokens=300,
        temperature=0.7,
        system=(
            "This is a conversation between a user and a welcoming bot/assistant, "
            "the assistant creates welcome messages for people to the Tower House "
            "Apartment in London. The welcome messages should be at maximum 1 sentence long."
        ),
        messages=[
            {"role": "user", "content": f"Write welcome for: {prompt}"}
        ]
    )

    if not isinstance(message.content[0], anthropic.types.ContentBlock):
        raise ValueError("Unexpected content type")
    if message.content[0].type != "text":
        raise ValueError(f"Unexpected content type: {message.content[0].type}")


    msg = message.content[0].text
    return msg

async def generate_and_play_audio(text, voice="Chris", model="eleven_multilingual_v2"):
    audio = elevenlabs_client.generate(
        text=text,
        voice=voice,
        model=model
    )

    play(audio)

async def poem_to_speech(prompt: str, delay: float=1.0):
    await asyncio.sleep(delay)
    welcome = await generate_welcome(prompt)
    asyncio.create_task(generate_and_play_audio(welcome))


# Logging setup
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
)


_logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
This is a conversation between a user and Claude, a helpful AI assistant. The user is making a \
website to control a mechanism that locks and unlocks their apartment door, and would like help \
styling the website. The user will request a theme and some html for the website, and Claude will \
then respond with an update html file with the styles inlined.

When generating the html claude should:
* Use a lot of emojis
* Not include any images
* Respond with only the html content, enclosed in triple backticks
* Use animations and javascript where appropriate to make the website interesting
* Ensure the websites are mobile friendly
* Ensure that any existing scripts are loaded and still functional, specifically id "message"
* Make sure to add the theme name to the door controller website so the user knows what the theme is
* Try and incorporate the theme in the text on the buttons and title
* Try and use canvases, javascript, or other interactive elements to make the website more interesting
* Try an go above and beyond to make the website interesting, fun, novel, and engaging using your knowledge of web development and design
"""

_MESSAGE_TEMPLATE = """\
Please generate html for this website:
```
{html}
```

With the following theme: {theme}
{additional_information}

If it seems appropriate, try and use javascript and canvases (or three.js etc) to make it interesting

Then write out the full html file enclosed in triple backticks.
"""

_ADDITIONAL_INFO_TEMPLATE = """
Additional information:
{additional_information}
"""
class Theme(BaseModel):
    theme: str
    additional_information: str


client = anthropic.AsyncAnthropic()


async def generate_theme(theme_spec: Theme) -> str:
    theme = theme_spec.theme
    additional_information = theme_spec.additional_information

    additional_content = ""
    if additional_information != "":
        additional_content += _ADDITIONAL_INFO_TEMPLATE.format(
            additional_information=additional_information
        )

    content = _MESSAGE_TEMPLATE.format(
        html=EXAMPLE_HTML,
        theme=theme,
        additional_information=additional_content,
    )

    response = await client.messages.create(
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        model="claude-3-5-sonnet-20240620",
        messages=[{"role": "user", "content": content}],
    )

    if not isinstance(response.content[0], anthropic.types.ContentBlock):
        raise ValueError("Unexpected content type")
    if response.content[0].type != "text":
        raise ValueError(f"Unexpected content type: {response.content[0].type}")

    content = response.content[0].text

    # replace all ```html with just ```
    content = content.replace("```html", "```")

    if "```" not in content:
        raise ValueError("Response does not contain html content")

    # get content of ```
    content = content.split("```")[1]

    # make theme file name safe
    theme_fn = theme.replace(" ", "_").lower()
    theme_fn = re.sub(r"[^a-zA-Z0-9_]", "", theme_fn)
    theme_fn += ".html"
    theme_path = f"{STAGING_DIR}/{theme_fn}"

    # save to fe/generated
    with open(theme_path, "w") as f:
        f.write(content)

    return theme_fn


app = FastAPI()


# Add the middleware to the app
app.add_middleware(AuthMiddleware)
app.include_router(auth_router)

# Login page route
@app.get("/login", response_class=HTMLResponse)
async def login_page(error: str | None = None):
    # load in the login page from fe/login.html
    with open(LOGIN_HTML_FILE) as f:
        login_page = f.read()

    return HTMLResponse(content=login_page)


cleanup()
door_controller = DoorController(
    open_actuator=ActuatorController(OPEN_ACTUATOR_PIN1, OPEN_ACTUATOR_PIN2),
    close_actuator=ActuatorController(CLOSE_ACTUATOR_PIN1, CLOSE_ACTUATOR_PIN2),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/unlock")
async def unlock_door(user: User):
    await door_controller.unlock()
    send_message(f"{user} called unlock")

    # Generate and play welcome poem asynchronously
    if user in _USER_WELCOME_PROMPTS:
        current_time = datetime.now().time()
        if WELCOME_START_TIME <= current_time < WELCOME_END_TIME:
            # If a string, set that as the prompt, if a list, choose a random one
            prompt = _USER_WELCOME_PROMPTS[user]
            if isinstance(prompt, list):
                prompt = random.choice(prompt)
            asyncio.create_task(poem_to_speech(prompt, delay=8))

    return {"message": "Unlocking door"}


@app.post("/api/lock")
async def lock_door(user: User):
    await door_controller.lock()
    send_message(f"{user} called lock")
    return {"message": "Locking door"}


@app.post("/api/safe")
async def safe(user: User):
    await door_controller.safe()
    send_message(f"{user} called safe")
    return {"message": "Safing Actuators"}


@app.post("/api/stop")
async def stop(user: User):
    await door_controller.stop()
    send_message(f"{user} called stop")
    return {"message": "Stopping actuators"}


@app.post("/api/generate_theme")
async def generate_theme_endpoint(theme: Theme, user: User):
    _logger.info(f"{user} requested theme: {theme.theme}")
    theme_path = await generate_theme(theme)
    return {"message": "Theme generated", "theme_path": theme_path}


class AcceptThemeParams(BaseModel):
    theme_path: str


@app.post("/api/accept_theme")
async def accept_theme(accept_theme: AcceptThemeParams, user: User):
    _logger.info(f"{user} accepted theme: {accept_theme.theme_path}")
    theme_path = accept_theme.theme_path
    old_path = Path(f"{STAGING_DIR}/{theme_path}")
    new_path = Path(f"{GENERATED_DIR}/{theme_path}")

    if not old_path.exists():
        return {"message": "Theme not found"}

    i = 0
    while new_path.exists():
        i = i + 1
        new_path = new_path.with_name(f"{new_path.stem}_{i}{new_path.suffix}")

    old_path.rename(new_path)

    return {"message": "Theme accepted"}


@app.get("/")
async def index():
    return HTMLResponse(content=get_random_frontend())


def get_random_frontend():
    _FE_OPTIONS = [str(p) for p in Path(THEMES_DIR).rglob("*") if p.is_file()]
    _FE_OPTIONS += [str(p) for p in Path(GENERATED_DIR).rglob("*") if p.is_file()]
    random_frontend = random.choice(_FE_OPTIONS)
    with open(random_frontend) as f:
        return f.read()


@app.get("/list")
def list_themes():
    _FE_OPTIONS = [
        f"/themes/{p.name}" for p in Path(THEMES_DIR).rglob("*") if p.is_file()
    ]

    _FE_OPTIONS += [
        f"/generated/{p.name}" for p in Path(GENERATED_DIR).rglob("*") if p.is_file()
    ]

    return HTMLResponse(
        content="<br>".join(
            f'<a href="{p}">{p}</a>' for p in _FE_OPTIONS if p.endswith(".html")
        )
    )


@app.get("/favicon.ico")
async def favicon():
    file_path = os.path.join(os.path.dirname(__file__), "fe", "favicon.svg")
    return FileResponse(file_path, media_type="image/svg+xml")


@app.get("/logs")
def logs(user: User):
    _logger.info(f"{user} requested logs")
    with open(LOG_FILE) as f:
        return HTMLResponse(content=f"<pre>{f.read()}</pre>")


class AnnouncementModel(BaseModel):
    message: str

@app.post("/api/announce")
async def announce(announcement: AnnouncementModel, flatmate: Flatmate):
    _logger.info(f"{flatmate} made an announcement: {announcement.message}")
    asyncio.create_task(generate_and_play_audio(announcement.message))
    send_message(f"Announcement from {flatmate}: {announcement.message}")
    return {"message": "Announcement made successfully"}

app.mount("/", StaticFiles(directory="fe"), name="fe")
