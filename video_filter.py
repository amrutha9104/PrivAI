# video_filter.py
import cv2
import numpy as np
from ultralytics import YOLO
import threading
import time
import pyvirtualcam
from pyvirtualcam import PixelFormat
from webcam_stream import WebcamStream
from shared_state import DETECTION_STATE
import socketio
import warnings

warnings.filterwarnings("ignore")

# --- CONFIGURATION ---
MODEL_PATH = 'yolov8n-seg.pt'

# 1. Define which objects trigger a Pop-up.
# Note: YOLO COCO dataset uses 'book' for papers/files usually.
CRITICAL_CLASSES = ['cell phone', 'book', 'laptop', 'tablet'] 

# Load YOLO
try:
    model = YOLO(MODEL_PATH).to('cuda')
    print("✅ YOLOv8 (Seg) loaded to CUDA.")
except:
    model = YOLO(MODEL_PATH)
    print("⚠️ YOLOv8 (Seg) loaded to CPU.")

CLASSES = model.names
sio = socketio.Client()

def connect_socket():
    try:
        if not sio.connected:
            sio.connect('http://localhost:3000')
    except: pass

def find_main_person_index(boxes, class_ids):
    """Find the largest person in the frame (The User)"""
    max_area = 0
    main_idx = -1
    for i, cls_id in enumerate(class_ids):
        if CLASSES[cls_id] == 'person':
            x1, y1, x2, y2 = boxes[i]
            area = (x2 - x1) * (y2 - y1)
            if area > max_area:
                max_area = area
                main_idx = i
    return main_idx

def process_frame_segmentation(frame):
    H, W, _ = frame.shape
    results = model(frame, verbose=False, stream=False, retina_masks=True)
    result = results[0]
    
    # Default: Everything is HIDDEN (0)
    visibility_mask = np.zeros((H, W), dtype=np.uint8) 
    has_sensitive_content = False

    if result.masks is not None:
        masks = result.masks.data.cpu().numpy()
        boxes = result.boxes.xyxy.cpu().numpy()
        class_ids = result.boxes.cls.cpu().numpy().astype(int)
        
        if masks.shape[1:] != (H, W):
            masks_resized = [cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR) for m in masks]
            masks = np.array(masks_resized)

        main_user_idx = find_main_person_index(boxes, class_ids)

        for i, (mask, box, cls_id) in enumerate(zip(masks, boxes, class_ids)):
            binary_mask = (mask * 255).astype(np.uint8)
            class_name = CLASSES[cls_id]
            
            should_show = False
            
            # --- 1. MAIN USER (ALWAYS VISIBLE) ---
            if i == main_user_idx:
                should_show = True
            
            # --- 2. OBJECTS (PHONES, BOOKS, BOTTLES) ---
            else:
                # A. Check if we have a Saved Preference (Sticky Rule)
                # This FIXES the "Reveal" button. If you said "retain", it applies here immediately.
                class_pref = DETECTION_STATE.get_class_preference(class_name)
                
                if class_pref == 'retain':
                    should_show = True
                
                elif class_pref == 'blur':
                    should_show = False
                    has_sensitive_content = True
                
                else:
                    # B. No preference yet. Check if it's a "Critical" object.
                    if class_name in CRITICAL_CLASSES:
                        # It's a Phone/Book. We must ALERT the user.
                        # But keeps it blurred until they click Reveal.
                        should_show = False 
                        has_sensitive_content = True
                        
                        # Register detection to trigger pop-up
                        # (shared_state handles logic to not spam the same ID)
                        new_id = DETECTION_STATE.get_next_id()
                        DETECTION_STATE.register_object(new_id, class_name, box)
                        
                        if sio.connected:
                            sio.emit('new-detection', {'objectId': new_id, 'className': class_name})
                    
                    else:
                        # C. It's a random object (Bottle, Cup). 
                        # Silent Blur. No Pop-up.
                        should_show = False

            # Apply visibility
            if should_show:
                visibility_mask = cv2.bitwise_or(visibility_mask, binary_mask)

    # Update Audio Mute Logic
    DETECTION_STATE.set_sensitive_status(has_sensitive_content)
    DETECTION_STATE.cleanup_stale_objects()

    # Composite Frame
    blurred_frame = cv2.GaussianBlur(frame, (255, 255), 0)
    visibility_mask_3ch = cv2.cvtColor(visibility_mask, cv2.COLOR_GRAY2BGR)
    output = np.where(visibility_mask_3ch > 0, frame, blurred_frame)
    
    return output

def run_video_loop(stop_event: threading.Event):
    connect_socket()
    
    # --- CHANGE THIS IF SCREEN IS BLACK ---
    MY_CAMERA_ID = 0
    
    streamer = WebcamStream(src=MY_CAMERA_ID).start()
    
    W, H = 1280, 720
    try:
        cameras = pyvirtualcam.Camera.enumerate_devices()
        cam_name = cameras[0].name if cameras else "OBS Virtual Camera"
    except:
        cam_name = "OBS Virtual Camera"
        
    print(f"📹 Video Filter active on: {cam_name}")
    print(f"🔔 Notifications enabled for: {CRITICAL_CLASSES}")
    
    with pyvirtualcam.Camera(width=W, height=H, fps=30, device=cam_name, fmt=PixelFormat.RGB) as cam:
        while not stop_event.is_set():
            frame = streamer.read()
            if frame is None:
                time.sleep(0.1)
                continue
            
            frame = cv2.resize(frame, (W, H))
            try:
                output = process_frame_segmentation(frame)
                cam.send(cv2.cvtColor(output, cv2.COLOR_BGR2RGB))
            except: pass
                
            cam.sleep_until_next_frame()
            cv2.imshow("Admin View (Q to Quit)", output)
            if cv2.waitKey(1) == ord('q'):
                stop_event.set()

    streamer.stop()
    cv2.destroyAllWindows()