# mock_picamera.py

import io
import time
import threading
from PIL import Image, ImageDraw, ImageFont


class MockCamera:
    def __init__(self, resolution=(640, 480), framerate=24):
        if isinstance(resolution, str):
            resolution = tuple(map(int, resolution.split("x")))

        self.resolution = resolution
        self.framerate = framerate
        self.recording = False
        self.output = None
        self.thread = None

    def start_recording(self, output, format="mjpeg"):
        self.output = output
        self.recording = True
        self.thread = threading.Thread(target=self._record_thread)
        self.thread.start()

    def stop_recording(self):
        self.recording = False
        if self.thread:
            self.thread.join()

    def _record_thread(self):
        while self.recording:
            frame = self._generate_debug_frame()
            self.output.write(frame)
            time.sleep(1 / self.framerate)

    def _generate_debug_frame(self):
        image = Image.new("RGB", self.resolution, color="gray")
        draw = ImageDraw.Draw(image)

        # Try to use a default font, fallback to using default font
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except IOError:
            font = ImageFont.load_default()

        text = f"Mock Camera: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        position = (10, 10)

        draw.text(position, text, fill="black", font=font)

        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format="JPEG")
        return img_byte_arr.getvalue()


class PiCamera(MockCamera):
    pass


# Usage example:
if __name__ == "__main__":

    class DummyOutput:
        def write(self, buf):
            print(f"Received {len(buf)} bytes")

    camera = PiCamera(resolution=(640, 480), framerate=24)
    output = DummyOutput()
    camera.start_recording(output, format="mjpeg")
    time.sleep(5)  # Simulate running for 5 seconds
    camera.stop_recording()
