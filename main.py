from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import RPi.GPIO as gpio


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


app = FastAPI()

gpio.cleanup()
controller_1 = ActuatorController(17, 22)
controller_2 = ActuatorController(23, 24)


class ControllerSelectionSchema(BaseModel):
    name: str


controllers = {
    "opener": controller_1,
    "closer": controller_2,
}

origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/controllers")
def get_controller_list():
    return list(controllers.keys())


@app.post("/api/extend")
def extend(controller: ControllerSelectionSchema):
    controllers[controller.name].extend()


@app.post("/api/retract")
def retract(controller: ControllerSelectionSchema):
    controllers[controller.name].retract()


@app.post("/api/stop")
def retract(controller: ControllerSelectionSchema):
    controllers[controller.name].stop()


@app.get("/", response_class=HTMLResponse)
def index():
    with open("./fe/index.html") as f:
        return f.read()


app.mount("/", StaticFiles(directory="fe"), name="fe")
