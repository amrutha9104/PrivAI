# shared_state.py

import threading

class SharedState:
    """
    Thread-safe storage for detection results, accessed by the video and control threads.
    """
    def __init__(self):
        self._sensitive_detected = False
        self._lock = threading.Lock()

    def set_sensitive_status(self, status: bool):
        """Sets the sensitive object detection status."""
        with self._lock:
            self._sensitive_detected = status

    def get_sensitive_status(self) -> bool:
        """Gets the sensitive object detection status."""
        with self._lock:
            return self._sensitive_detected

# Create a single, globally accessible instance
DETECTION_STATE = SharedState()