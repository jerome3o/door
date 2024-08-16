import logging
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.announcements import play_announcement_if_prompt_exists
from server.telemetry import send_message

from server.constants import (
    OPEN_ACTUATOR_PIN1,
    OPEN_ACTUATOR_PIN2,
    CLOSE_ACTUATOR_PIN1,
    CLOSE_ACTUATOR_PIN2,
    ALLOWED_ORIGINS,
    LOG_FILE,
    LOGIN_HTML_FILE,
)
from server.door_controller import DoorController, ActuatorController, cleanup
from server.auth import (
    AuthMiddleware,
    User,
    router as auth_router,
)
from server.themes import router as theme_generation_router, get_random_frontend
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
