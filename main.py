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

if os.getenv("ENVIRONMENT") == "development":
    from mockgpio import gpio
else:
    import RPi.GPIO as gpio
from datetime import datetime, timedelta

from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader, APIKeyQuery
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

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
    API_KEY_COOKIE_NAME
)
FLATMATES: set[str] = set(os.environ["FLATMATES"].split(","))

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

def generate_key(length=32):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def load_keys() -> Dict[str, str]:
    keys = {}
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE) as f:
            keys = json.load(f)

    if os.path.exists(SEED_KEY_FILE):
        with open(SEED_KEY_FILE) as f:
            seed_keys = json.load(f)
        keys = {**keys, **seed_keys}

    return keys


KEYS = load_keys()

# Logging setup
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
)

# Security key header
api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)
api_key_query = APIKeyQuery(name=API_KEY_QUERY_NAME, auto_error=False)
# Authentication function
async def get_api_key(
    api_key_header: str = Depends(api_key_header),
    api_key_cookie: Optional[str] = Cookie(None, alias=API_KEY_COOKIE_NAME),
) -> str:
    return api_key_header or api_key_cookie

def get_user(request: Request) -> str:
    user = request.state.user

    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    return user


User = Annotated[str, Depends(get_user)]


def get_flatmate(user: User) -> str:
    if user not in FLATMATES:
        raise HTTPException(status_code=403, detail="Not authorized")
    return user


Flatmate = Annotated[str, Depends(get_flatmate)]


# Authentication middleware
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # List of paths that don't require authentication
        open_paths = ["/login", "/auth", "/favicon.ico"]

        query_param_key = request.query_params.get(API_KEY_QUERY_NAME)
        if query_param_key:
            user = next(
                (name for name, k in KEYS.items() if k == query_param_key), None
            )
            if user:
                # Set cookie to expire in 10 years
                expiration = datetime.utcnow() + timedelta(days=COOKIE_EXPIRATION_DAYS)

                # Preserve other query parameters if any
                query_params = dict(request.query_params)
                query_params.pop(API_KEY_QUERY_NAME, None)
                if query_params:
                    query_string = f"?{urlencode(query_params)}"
                else:
                    query_string = ""

                response = RedirectResponse(
                    # redirect to the same page to avoid the key being in the
                    #   url bar
                    url=f"{request.url.path}{query_string}",
                    status_code=303,
                )  # 303 See Other
                response.set_cookie(
                    key=API_KEY_COOKIE_NAME,
                    value=query_param_key,
                    expires=expiration.strftime("%a, %d %b %Y %H:%M:%S GMT"),
                    httponly=True,
                    samesite="Lax",
                )
                return response

            else:
                _failed_login(request, query_param_key)
                return RedirectResponse(url="/login?error=invalid_key", status_code=303)

        if request.url.path in open_paths:
            return await call_next(request)

        api_key = await get_api_key(
            api_key_header=request.headers.get(API_KEY_HEADER_NAME),
            api_key_cookie=request.cookies.get(API_KEY_COOKIE_NAME),
        )

        if api_key is None:
            if request.method == "POST":
                return JSONResponse(
                    status_code=401, content={"detail": "Authentication required"}
                )
            return RedirectResponse(url="/login")

        user = next((name for name, key in KEYS.items() if key == api_key), None)
        if user is None:
            if request.method == "POST":
                return JSONResponse(
                    status_code=403, content={"detail": "Invalid API Key"}
                )
            return RedirectResponse(url="/login")

        request.state.user = user
        response = await call_next(request)
        return response


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


class ActuatorController:
    def __init__(self, p1: int, p2: int):
        self.p1, self.p2 = p1, p2
        self.init_pins()

    def init_pins(self):
        gpio.setmode(gpio.BCM)
        gpio.setup(self.p1, gpio.OUT)
        gpio.setup(self.p2, gpio.OUT)

    def extend(self):
        gpio.output(self.p1, False)
        gpio.output(self.p2, True)

    def retract(self):
        gpio.output(self.p1, True)
        gpio.output(self.p2, False)

    def stop(self):
        gpio.output(self.p1, False)
        gpio.output(self.p2, False)


class DoorController:
    def __init__(
        self,
        open_actuator: ActuatorController,
        close_actuator: ActuatorController,
        delay: float = DEFAULT_DELAY,
    ):
        self._open_actuator = open_actuator
        self._close_actuator = close_actuator
        self._delay = delay
        self._current_task: asyncio.Task | None = None

    async def _extend_both_after_delay(self):
        await asyncio.sleep(self._delay)
        await self.safe()

    async def safe(self):
        await self._cancel_task()
        self._open_actuator.extend()
        self._close_actuator.extend()

    async def stop(self):
        await self._cancel_task()
        self._open_actuator.stop()
        self._close_actuator.stop()

    async def _cancel_task(self):
        # Cancel any existing task
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            try:
                await self._current_task
            except asyncio.CancelledError:
                pass

    async def unlock(self):
        await self._cancel_task()

        self._open_actuator.retract()
        self._close_actuator.extend()

        self._current_task = asyncio.create_task(self._extend_both_after_delay())

    async def lock(self):
        await self._cancel_task()

        self._open_actuator.extend()
        self._close_actuator.retract()

        self._current_task = asyncio.create_task(self._extend_both_after_delay())


app = FastAPI()


# Add the middleware to the app
app.add_middleware(AuthMiddleware)


# Login page route
@app.get("/login", response_class=HTMLResponse)
async def login_page(error: str = None):
    # load in the login page from fe/login.html
    with open(LOGIN_HTML_FILE) as f:
        login_page = f.read()

    return HTMLResponse(content=login_page)


# Authentication route
@app.post("/auth")
async def auth(request: Request, key: str = Form(...)):
    user = next((name for name, k in KEYS.items() if k == key), None)
    if user:
        # Set cookie to expire in 10 years
        expiration = datetime.utcnow() + timedelta(days=COOKIE_EXPIRATION_DAYS)
        response = RedirectResponse(url="/", status_code=303)  # 303 See Other
        response.set_cookie(
            key=API_KEY_COOKIE_NAME,
            value=key,
            expires=expiration.strftime("%a, %d %b %Y %H:%M:%S GMT"),
            httponly=True,  # Makes the cookie inaccessible to JavaScript
            samesite="Lax",  # Provides some CSRF protection
        )
        _send_message(f"{user} logged in via /auth")
        return response

    _failed_login(request, key)
    return RedirectResponse(
        url="/login?error=invalid_key", status_code=303
    )  # 303 See Other


gpio.cleanup()

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


def _send_message(msg: str):
    _logger.info(msg)
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=msg,
        )
    except Exception as e:
        _logger.error(f"Failed to send ntfy message: {e}")


def _failed_login(request, key):
    _send_message(
        f"Someone tried to access with an invalid key: {key}, "
        f"IP: {request.client.host}"
    )


@app.post("/api/unlock")
async def unlock_door(user: User):
    await door_controller.unlock()
    _send_message(f"{user} called unlock")

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
    _send_message(f"{user} called lock")
    return {"message": "Locking door"}


@app.post("/api/safe")
async def safe(user: User):
    await door_controller.safe()
    _send_message(f"{user} called safe")
    return {"message": "Safing Actuators"}


@app.post("/api/stop")
async def stop(user: User):
    await door_controller.stop()
    _send_message(f"{user} called stop")
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


@app.get("/api/keys")
def get_keys(
    flatmate: Flatmate,
):
    return list(KEYS.items())


class AddKeyParams(BaseModel):
    name: str


class DeleteKeyParams(BaseModel):
    name: str


@app.post("/api/keys")
def add_keys(
    AddKeyParams: AddKeyParams,
    flatmate: Flatmate,
):
    key = generate_key()
    KEYS[AddKeyParams.name] = key

    with open(KEY_FILE, "w") as f:
        json.dump(KEYS, f, indent=2)

    _send_message(f"{flatmate} added key for {AddKeyParams.name}")

    return {"message": "Key added", "key": key, "name": AddKeyParams.name}


@app.delete("/api/keys")
def delete_keys(
    DeleteKeyParams: DeleteKeyParams,
    flatmate: Flatmate,
):

    if DeleteKeyParams.name in FLATMATES:
        return {"message": "Cannot delete flatmate keys"}

    key = KEYS.pop(DeleteKeyParams.name, None)

    with open(KEY_FILE, "w") as f:
        json.dump(KEYS, f, indent=2)

    _send_message(f"{flatmate} deleted key for {DeleteKeyParams.name}")

    return {"message": "Key deleted", "key": key, "name": DeleteKeyParams.name}

class AnnouncementModel(BaseModel):
    message: str

@app.post("/api/announce")
async def announce(announcement: AnnouncementModel, flatmate: Flatmate):
    _logger.info(f"{flatmate} made an announcement: {announcement.message}")
    asyncio.create_task(generate_and_play_audio(announcement.message))
    _send_message(f"Announcement from {flatmate}: {announcement.message}")
    return {"message": "Announcement made successfully"}

app.mount("/", StaticFiles(directory="fe"), name="fe")
