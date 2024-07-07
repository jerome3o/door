import asyncio
import json
import logging
import os
import random
import re
from pathlib import Path
from typing import Dict, Optional

from fastapi import Cookie, Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from pydantic import BaseModel

if os.getenv("ENVIRONMENT") == "development":
    from mockgpio import gpio
else:
    import RPi.GPIO as gpio
from datetime import datetime, timedelta

from anthropic import Anthropic
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader, APIKeyQuery
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

DEFAULT_DELAY = 17

# Key management
KEY_FILE = ".keys.json"


def load_keys() -> Dict[str, str]:
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "r") as f:
            return json.load(f)
    return {}


KEYS = load_keys()

# Logging setup
logging.basicConfig(
    filename="door_access.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
)

# Security key header
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="key", auto_error=False)


# Authentication function
async def get_api_key(
    api_key_header: str = Depends(api_key_header),
    api_key_query: str = Depends(api_key_query),
    api_key_cookie: Optional[str] = Cookie(None, alias="api_key"),
) -> str:
    return api_key_header or api_key_query or api_key_cookie


# Authentication middleware
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # List of paths that don't require authentication
        open_paths = ["/login", "/auth", "/favicon.ico"]

        if request.url.path in open_paths:
            return await call_next(request)

        api_key = await get_api_key(
            api_key_header=request.headers.get("X-API-Key"),
            api_key_query=request.query_params.get("key"),
            api_key_cookie=request.cookies.get("api_key"),
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

with open("example_html.html") as f:
    EXAMPLE_HTML = f.read()


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
* Ensure that any existing id's and scripts loaded are still functional
* Make sure to add the theme name to the door controller website so the user knows what the theme is
* Try and incorporate the theme in the text on the buttons and title
"""

_MESSAGE_TEMPLATE = """\
Please generate html for this website:
```
{html}
```

With the following theme: {theme}
"""

_ADDITIONAL_INFO_TEMPLATE = """
Additional information:
{additional_information}
"""


class Theme(BaseModel):
    theme: str
    additional_information: str


client = Anthropic()


def generate_theme(theme_spec: Theme) -> str:
    theme = theme_spec.theme
    additional_information = theme_spec.additional_information

    content = _MESSAGE_TEMPLATE.format(html=EXAMPLE_HTML, theme=theme)

    if additional_information != "":
        content += _ADDITIONAL_INFO_TEMPLATE.format(
            additional_information=additional_information
        )

    print(content)

    response = client.messages.create(
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
    theme_path = f"fe/staging/{theme_fn}"

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
                _logger.info("Cancelled task")

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
    error_message = ""
    if error == "invalid_key":
        error_message = "<p style='color: red;'>Invalid key. Please try again.</p>"

    return f"""
    <html>
        <body>
            <h1>Enter your key</h1>
            {error_message}
            <form action="/auth" method="post">
                <input type="text" name="key" placeholder="Enter your key">
                <input type="submit" value="Submit">
            </form>
        </body>
    </html>
    """


# Authentication route
@app.post("/auth")
async def auth(key: str = Form(...)):
    user = next((name for name, k in KEYS.items() if k == key), None)
    if user:
        # Set cookie to expire in 10 years
        expiration = datetime.utcnow() + timedelta(days=365 * 10)
        response = RedirectResponse(url="/", status_code=303)  # 303 See Other
        response.set_cookie(
            key="api_key",
            value=key,
            expires=expiration.strftime("%a, %d %b %Y %H:%M:%S GMT"),
            httponly=True,  # Makes the cookie inaccessible to JavaScript
            samesite="Lax",  # Provides some CSRF protection
        )
        return response
    return RedirectResponse(
        url="/login?error=invalid_key", status_code=303
    )  # 303 See Other


gpio.cleanup()

door_controller = DoorController(
    open_actuator=ActuatorController(23, 24),
    close_actuator=ActuatorController(17, 22),
)

origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/unlock")
async def unlock_door(request: Request):
    await door_controller.unlock()
    print(f"{request.state.user} called unlock")
    return {"message": "Unlocking door"}


@app.post("/api/lock")
async def lock_door(request: Request):
    await door_controller.lock()
    print(f"{request.state.user} called lock")
    return {"message": "Locking door"}


@app.post("/api/safe")
async def safe(request: Request):
    await door_controller.safe()
    print(f"{request.state.user} called safe")
    return {"message": "Safing Actuators"}


@app.post("/api/stop")
async def stop(request: Request):
    await door_controller.stop()
    print(f"{request.state.user} called stop")
    return {"message": "Stopping actuators"}


@app.post("/api/generate_theme")
async def generate_theme_endpoint(theme: Theme):
    theme_path = generate_theme(theme)
    return {"message": "Theme generated", "theme_path": theme_path}


class AcceptThemeParams(BaseModel):
    theme_path: str


@app.post("/api/accept_theme")
async def accept_theme(accept_theme: AcceptThemeParams):
    theme_path = accept_theme.theme_path
    # move from ./fe/staging/{theme_path} to ./fe/generated/{theme_path}
    old_path = Path(f"./fe/staging/{theme_path}")
    new_path = Path(f"./fe/generated/{theme_path}")

    if not old_path.exists():
        return {"message": "Theme not found"}

    i = 0
    while new_path.exists():
        i + 1
        new_path = new_path.with_name(f"{new_path.stem}_{i}{new_path.suffix}")

    old_path.rename(new_path)

    return {"message": "Theme accepted"}


@app.get("/")
async def index(request: Request, key: Optional[str] = None):
    if key:
        user = next((name for name, k in KEYS.items() if k == key), None)
        if user:
            # Set cookie to expire in 10 years
            expiration = datetime.utcnow() + timedelta(days=365 * 10)
            response = HTMLResponse(content=get_random_frontend())
            response.set_cookie(
                key="api_key",
                value=key,
                expires=expiration.strftime("%a, %d %b %Y %H:%M:%S GMT"),
                httponly=True,
                samesite="Lax",
            )
            return response
    return HTMLResponse(content=get_random_frontend())


def get_random_frontend():
    _FE_OPTIONS = [str(p) for p in Path("./fe/themes").rglob("*") if p.is_file()]
    _FE_OPTIONS += [str(p) for p in Path("./fe/generated").rglob("*") if p.is_file()]
    random_frontend = random.choice(_FE_OPTIONS)
    with open(random_frontend) as f:
        return f.read()


@app.get("/list")
def list_themes():
    # load all files in the ./fe/themes/ directory
    _FE_OPTIONS = [
        f"/themes/{p.name}" for p in Path("./fe/themes").rglob("*") if p.is_file()
    ]

    # load all files in the ./fe/generated/ directory
    _FE_OPTIONS += [
        f"/generated/{p.name}" for p in Path("./fe/generated").rglob("*") if p.is_file()
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


app.mount("/", StaticFiles(directory="fe"), name="fe")
