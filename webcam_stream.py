# webcam_stream.py
import cv2
from threading import Thread

class WebcamStream:
    def __init__(self, src=0):
        # Try to force high resolution, but fall back if needed
        self.stream = cv2.VideoCapture(src, cv2.CAP_DSHOW)
        
        # Set resolution to match what we expect (1280x720)
        self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        
        if not self.stream.isOpened():
            print(f"❌ Error: Could not open webcam source {src}.")
            self.stopped = True
            return

        (self.grabbed, self.frame) = self.stream.read()
        
        if not self.grabbed:
            print(f"⚠️ Warning: Camera {src} opened but returned empty frame.")
            self.stopped = True
        else:
            self.stopped = False
            
        self.t = Thread(target=self.update, args=(), daemon=True)

    def start(self):
        self.t.start()
        return self

    def update(self):
        while True:
            if self.stopped:
                break
            (self.grabbed, self.frame) = self.stream.read()
            if not self.grabbed:
                self.stopped = True
                break

    def read(self):
        return self.frame

    def stop(self):
        self.stopped = True
        if self.t.is_alive():
            self.t.join()
        self.stream.release()