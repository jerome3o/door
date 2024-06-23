import os

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
import io
import threading
from starlette.responses import RedirectResponse

if os.environ.get("ENVIRONMENT") == "development":
    import cam.mock_picamera as picamera
else:
    import picamera  # type: ignore


class StreamingOutput(object):
    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = threading.Condition()

    def write(self, buf):
        if buf.startswith(b"\xff\xd8"):
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)


output = StreamingOutput()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global camera
    camera = picamera.PiCamera(resolution="640x480", framerate=24)
    camera.start_recording(output, format="mjpeg")
    yield
    camera.stop_recording()


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
        yield (b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")


@app.get("/stream.mjpg")
async def stream():
    return StreamingResponse(
        generate(), media_type="multipart/x-mixed-replace; boundary=frame"
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
