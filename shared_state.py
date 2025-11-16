# shared_state.py
import threading
import time

class SharedState:
    def __init__(self):
        self._lock = threading.Lock()
        self._sensitive_detected = False
        
        # Tracking
        self._tracked_objects = {} 
        self._object_id_counter = 0
        self._object_lock = threading.Lock()
        
        # Whitelist/Blacklist Preferences
        self._class_preferences = {} 
        self._prefs_lock = threading.Lock()

    # --- Audio/Sensitive Logic ---
    def set_sensitive_status(self, status: bool):
        with self._lock:
            self._sensitive_detected = status

    def get_sensitive_status(self) -> bool:
        with self._lock:
            return self._sensitive_detected

    # --- Detection Logic ---
    def get_next_id(self):
        with self._object_lock:
            self._object_id_counter += 1
            return self._object_id_counter

    def set_class_preference(self, class_name, choice):
        with self._prefs_lock:
            self._class_preferences[class_name] = choice
            print(f"📝 Rule Saved: All '{class_name}' -> {choice}")

    def get_class_preference(self, class_name):
        with self._prefs_lock:
            return self._class_preferences.get(class_name, None)

    def register_object(self, obj_id, class_name, bbox):
        with self._object_lock:
            initial_choice = self.get_class_preference(class_name) or "blur"
            self._tracked_objects[obj_id] = {
                "class": class_name,
                "choice": initial_choice,
                "bbox": bbox,
                "last_seen": time.time()
            }
            return initial_choice

    def update_object_position(self, obj_id, bbox):
        with self._object_lock:
            if obj_id in self._tracked_objects:
                self._tracked_objects[obj_id]["bbox"] = bbox
                self._tracked_objects[obj_id]["last_seen"] = time.time()

    def update_object_choice(self, obj_id, choice):
        with self._object_lock:
            if obj_id in self._tracked_objects:
                self._tracked_objects[obj_id]["choice"] = choice
                # Save Rule
                cls = self._tracked_objects[obj_id]["class"]
                self.set_class_preference(cls, choice)

    def get_object_choice(self, obj_id):
        with self._object_lock:
            return self._tracked_objects.get(obj_id, {}).get("choice", "blur")

    def get_all_tracked_objects(self):
        with self._object_lock:
            return self._tracked_objects.copy()

    def cleanup_stale_objects(self):
        with self._object_lock:
            now = time.time()
            self._tracked_objects = {k:v for k,v in self._tracked_objects.items() if now - v['last_seen'] < 1.0}

DETECTION_STATE = SharedState()# shared_state.py
import threading
import time

class SharedState:
    def __init__(self):
        self._lock = threading.Lock()
        self._sensitive_detected = False
        self._tracked_objects = {} 
        self._object_id_counter = 0
        self._object_lock = threading.Lock()
        self._class_preferences = {} 
        self._prefs_lock = threading.Lock()

    # --- Audio/Sensitive Logic ---
    def set_sensitive_status(self, status: bool):
        with self._lock:
            self._sensitive_detected = status

    def get_sensitive_status(self) -> bool:
        with self._lock:
            return self._sensitive_detected

    # --- Detection Logic ---
    def get_next_id(self):
        with self._object_lock:
            self._object_id_counter += 1
            return self._object_id_counter

    def set_class_preference(self, class_name, choice):
        """Whitelists/Blacklists a whole class of objects"""
        with self._prefs_lock:
            self._class_preferences[class_name] = choice
            print(f"📝 Rule Saved: All '{class_name}' -> {choice}")

    def get_class_preference(self, class_name):
        with self._prefs_lock:
            return self._class_preferences.get(class_name, None)

    def register_object(self, obj_id, class_name, bbox):
        with self._object_lock:
            initial_choice = self.get_class_preference(class_name) or "blur"
            self._tracked_objects[obj_id] = {
                "class": class_name,
                "choice": initial_choice,
                "bbox": bbox,
                "last_seen": time.time()
            }
            return initial_choice

    def update_object_position(self, obj_id, bbox):
        with self._object_lock:
            if obj_id in self._tracked_objects:
                self._tracked_objects[obj_id]["bbox"] = bbox
                self._tracked_objects[obj_id]["last_seen"] = time.time()

    # --- THE FIX IS HERE ---
    def update_object_choice(self, obj_id, choice, class_name=None):
        """
        Updates the choice. 
        Crucial Fix: Accepts class_name explicitly to save preference 
        even if the specific object_id has expired.
        """
        with self._object_lock:
            # 1. Try to find the object and get its class
            if obj_id in self._tracked_objects:
                self._tracked_objects[obj_id]["choice"] = choice
                found_class = self._tracked_objects[obj_id]["class"]
                self.set_class_preference(found_class, choice)
            
            # 2. Fallback: If object is gone but we know the class, save the rule anyway!
            elif class_name:
                print(f"⚠️ Object {obj_id} expired, but saving rule for '{class_name}'")
                self.set_class_preference(class_name, choice)

    def get_object_choice(self, obj_id):
        with self._object_lock:
            return self._tracked_objects.get(obj_id, {}).get("choice", "blur")

    def get_all_tracked_objects(self):
        with self._object_lock:
            return self._tracked_objects.copy()

    def cleanup_stale_objects(self):
        with self._object_lock:
            now = time.time()
            self._tracked_objects = {k:v for k,v in self._tracked_objects.items() if now - v['last_seen'] < 1.0}

DETECTION_STATE = SharedState()