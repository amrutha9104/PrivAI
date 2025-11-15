# shared_state.py
import threading
import time

class SharedState:
    def __init__(self):
        self._lock = threading.Lock()
        
        # Tracks active objects in the current frame
        self._tracked_objects = {} 
        self._object_id_counter = 0
        self._object_lock = threading.Lock()

        # NEW: Remembers user choices by Class Name (e.g., 'person': 'retain')
        self._class_preferences = {} 
        self._prefs_lock = threading.Lock()

    def get_next_id(self) -> int:
        with self._object_lock:
            self._object_id_counter += 1
            return self._object_id_counter

    # --- Preference Logic (The Fix) ---
    def set_class_preference(self, class_name, choice):
        """Remember that ALL objects of this class should be blurred/retained."""
        with self._prefs_lock:
            self._class_preferences[class_name] = choice
            print(f"🔒 CLASS RULE SAVED: All '{class_name}' objects will be -> {choice.upper()}")

    def get_class_preference(self, class_name):
        """Check if we already have a rule for this class."""
        with self._prefs_lock:
            return self._class_preferences.get(class_name, None)

    # --- Object Tracking Logic ---
    def register_object(self, obj_id, class_name, bbox):
        with self._object_lock:
            # Check if we already have a rule for this class
            saved_choice = self.get_class_preference(class_name)
            
            # If rule exists, use it. If not, default to 'blur'.
            initial_choice = saved_choice if saved_choice else "blur"
            
            self._tracked_objects[obj_id] = {
                "class": class_name,
                "choice": initial_choice, 
                "bbox": bbox,
                "last_seen": time.time()
            }
            return initial_choice # Return the choice so we know if we need to popup

    def update_object_position(self, obj_id, bbox):
        with self._object_lock:
            if obj_id in self._tracked_objects:
                self._tracked_objects[obj_id]["bbox"] = bbox
                self._tracked_objects[obj_id]["last_seen"] = time.time()

    def get_object_choice(self, obj_id):
        with self._object_lock:
            return self._tracked_objects.get(obj_id, {}).get("choice", "blur")

    def get_all_tracked_objects(self):
        with self._object_lock:
            return self._tracked_objects.copy()

    def cleanup_stale_objects(self, max_age=1.0):
        with self._object_lock:
            current_time = time.time()
            keys_to_remove = [k for k, v in self._tracked_objects.items() 
                              if current_time - v["last_seen"] > max_age]
            for k in keys_to_remove:
                del self._tracked_objects[k]

DETECTION_STATE = SharedState()