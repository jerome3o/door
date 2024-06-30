import os
import io
import time
import logging
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from starlette.responses import RedirectResponse
from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


output = StreamingOutput()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global picam2
    picam2 = Picamera2()
    video_config = picam2.create_video_configuration(main={"size": (640, 480)})
    picam2.configure(video_config)

    # Check if camera is working
    logger.debug("Capturing test image")
    picam2.start()
    picam2.capture_file("test.jpg")
    logger.debug("Test image captured")

    encoder = JpegEncoder(q=70)
    picam2.start_recording(encoder, FileOutput(output))
    logger.debug("Camera recording started")

    yield

    picam2.stop_recording()
    logger.debug("Camera recording stopped")


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return RedirectResponse(url="/index.html")


@app.get("/index.html", response_class=HTMLResponse)
async def index():
    return """
    <html>
    <head>
    <title>Raspberry Pi - Surveillance Camera</title>
    </head>
    <body style="margin:0">
    <img src="/stream.mjpg" style="max-height: 100%; width: 100vw;">
    </center>
    </body>
    </html>
    """


def generate():
    while True:
        with output.condition:
            output.condition.wait()
            frame = output.frame
        if frame is None:
            logger.debug("No frame available")
            continue
        logger.debug(f"Sending frame of size {len(frame)} bytes")
        yield (b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")


@app.get("/stream.mjpg")
async def stream():
    logger.debug("Stream requested")
    return StreamingResponse(
        generate(), media_type="multipart/x-mixed-replace; boundary=frame"
    )


if __name__ == "__main__":
    import uvicorn

    logger.debug("Starting server")
    uvicorn.run(app, host="0.0.0.0", port=8000)
