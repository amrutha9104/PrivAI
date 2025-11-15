# webcam_stream.py
import cv2
from threading import Thread

class WebcamStream:
    """
    Dedicated thread for reading frames from cv2.VideoCapture to overcome 
    OpenCV's sequential read/process bottleneck and reduce latency.
    """
    def __init__(self, src=0):
        # Use DSHOW backend for better resource sharing on Windows
        self.stream = cv2.VideoCapture(src, cv2.CAP_DSHOW) 
        
        if not self.stream.isOpened():
            print("Error: Could not open webcam source.")
            self.stopped = True
            return

        (self.grabbed, self.frame) = self.stream.read()
        self.stopped = False
        self.t = Thread(target=self.update, args=(), daemon=True)

    def start(self):
        """Starts the thread to read frames from the video stream."""
        self.t.start()
        return self

    def update(self):
        """Continuously reads frames in a loop until the thread is stopped."""
        while True:
            if self.stopped:
                break
            (self.grabbed, self.frame) = self.stream.read()
            if not self.grabbed:
                self.stopped = True
                break

    def read(self):
        """Returns the frame most recently read."""
        return self.frame

    def stop(self):
        """Indicates that the thread should be stopped."""
        self.stopped = True
        self.t.join()
        self.stream.release()