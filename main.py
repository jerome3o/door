import asyncio
import logging
import random
import os

import RPi.GPIO as gpio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

DEFAULT_DELAY = 17

_logger = logging.getLogger(__name__)


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
async def unlock_door():
    await door_controller.unlock()
    return {"message": "Unlocking door"}


@app.post("/api/lock")
async def lock_door():
    await door_controller.lock()
    return {"message": "Locking door"}


@app.post("/api/safe")
async def safe():
    await door_controller.safe()
    return {"message": "Safing Actuators"}


@app.post("/api/stop")
async def stop():
    await door_controller.stop()
    return {"message": "Stopping actuators"}


_FE_OPTIONS = [
    "cursed.html",
    "hannah.html",
    "index.html",
    "kindacursed.html",
    "spinning.html",
    "frog.html",
    "misalignedfrog.html",
    "windows.html",
]


@app.get("/", response_class=HTMLResponse)
def index():

    random_frontend = random.choice(_FE_OPTIONS)

    with open(f"./fe/{random_frontend}") as f:
        return f.read()


@app.get("/favicon.ico")
async def favicon():
    file_path = os.path.join(os.path.dirname(__file__), "fe", "favicon.svg")
    return FileResponse(file_path, media_type="image/svg+xml")


app.mount("/", StaticFiles(directory="fe"), name="fe")
