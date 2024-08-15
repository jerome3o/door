import asyncio
import json
import logging
import os
import random
from pathlib import Path
from typing import Dict, Annotated, Optional
from datetime import datetime, time

from fastapi import Cookie, Depends, FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.exceptions import HTTPException

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from server.announcements import play_announcement_if_prompt_exists
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
from server.themes import router as theme_generation_router
from server.announcements import router as announcements_router


# Logging setup
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
)


_logger = logging.getLogger(__name__)

app = FastAPI()


# Add the middleware to the app
app.add_middleware(AuthMiddleware)
app.include_router(auth_router)
app.include_router(theme_generation_router)
app.include_router(announcements_router)

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
    play_announcement_if_prompt_exists(user)

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


app.mount("/", StaticFiles(directory="fe"), name="fe")
