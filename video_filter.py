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

MODEL_PATH = 'yolov8n-seg.pt'
try:
    model = YOLO(MODEL_PATH).to('cuda')
    print("✅ YOLOv8 (Seg) loaded to CUDA (GPU).")
except:
    model = YOLO(MODEL_PATH)
    print("⚠️ YOLOv8 (Seg) loaded to CPU.")

CLASSES = model.names
sio = socketio.Client()

def connect_socket():
    try:
        sio.connect('http://localhost:3000')
        print("✅ Video Filter connected to Signaling Server")
    except Exception as e:
        print(f"⚠️  Socket Error: {e}")

def calculate_iou(box1, box2):
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - intersection
    return intersection / union if union > 0 else 0

def find_main_person(boxes, class_ids):
    max_area = 0
    main_idx = -1
    for i, cls_id in enumerate(class_ids):
        if cls_id == 0: # Person
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
    
    # 1. Base: Full Black Mask (Everything Blurred)
    visibility_mask = np.zeros((H, W), dtype=np.uint8) 

    if result.masks is None:
        pass 
    else:
        masks = result.masks.data.cpu().numpy()
        boxes = result.boxes.xyxy.cpu().numpy()
        class_ids = result.boxes.cls.cpu().numpy().astype(int)
        
        if masks.shape[1:] != (H, W):
             masks_resized = []
             for m in masks:
                 masks_resized.append(cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR))
             masks = np.array(masks_resized)

        main_person_idx = find_main_person(boxes, class_ids)
        tracked_objs = DETECTION_STATE.get_all_tracked_objects()
        
        for i, (mask, box, cls_id) in enumerate(zip(masks, boxes, class_ids)):
            binary_mask = (mask * 255).astype(np.uint8)
            class_name = CLASSES[cls_id]
            
            # --- Case A: Main User (Always Visible) ---
            if i == main_person_idx:
                visibility_mask = cv2.bitwise_or(visibility_mask, binary_mask)
                continue

            # --- Case B: Other Objects ---
            # 1. Try to match with existing tracked object
            matched_id = None
            for obj_id, data in tracked_objs.items():
                if data['class'] == class_name and calculate_iou(box, data['bbox']) > 0.4:
                    matched_id = obj_id
                    break
            
            current_choice = "blur" # Default

            if matched_id is None:
                # NEW OBJECT FOUND
                new_id = DETECTION_STATE.get_next_id()
                
                # Register it. This checks if we have a saved preference!
                # If we saved "retain" for "bottle", current_choice becomes "retain" automatically.
                current_choice = DETECTION_STATE.register_object(new_id, class_name, box)
                matched_id = new_id

                # ONLY Popup if we don't have a preference yet
                existing_pref = DETECTION_STATE.get_class_preference(class_name)
                
                if existing_pref is None and sio.connected:
                    # We have no rule for this object class yet. Ask the user.
                    print(f"🚨 Unknown Object: {class_name}. Asking User...")
                    sio.emit('new-detection', {
                        'objectId': new_id,
                        'className': class_name
                    })
            else:
                # EXISTING OBJECT
                DETECTION_STATE.update_object_position(matched_id, box)
                # Check preference again (in case user just clicked a button)
                pref = DETECTION_STATE.get_class_preference(class_name)
                if pref:
                    current_choice = pref
                else:
                    current_choice = DETECTION_STATE.get_object_choice(matched_id)

            # 2. Apply the Choice
            if current_choice == 'retain':
                # "Reveal" -> Add to visibility mask (White)
                visibility_mask = cv2.bitwise_or(visibility_mask, binary_mask)
            else:
                # "Blur" -> Do nothing (Mask stays black at this spot)
                pass

    DETECTION_STATE.cleanup_stale_objects()

    # Composite
    blurred_frame = cv2.GaussianBlur(frame, (55, 55), 0)
    visibility_mask_3ch = cv2.cvtColor(visibility_mask, cv2.COLOR_GRAY2BGR)
    output = np.where(visibility_mask_3ch > 0, frame, blurred_frame)
    
    return output

def run_video_loop(stop_event: threading.Event):
    connect_socket()
    streamer = WebcamStream(src=0).start()
    
    W, H = 1280, 720
    try:
        cameras = pyvirtualcam.Camera.enumerate_devices()
        cam_name = cameras[0].name if cameras else "OBS Virtual Camera"
    except:
        cam_name = "OBS Virtual Camera"
        
    print(f"📹 Streaming on {cam_name}")
    
    with pyvirtualcam.Camera(width=W, height=H, fps=30, device=cam_name, fmt=PixelFormat.RGB) as cam:
        while not stop_event.is_set():
            frame = streamer.read()
            if frame is None: continue
            frame = cv2.resize(frame, (W, H))
            processed_frame = process_frame_segmentation(frame)
            cam.send(cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB))
            cam.sleep_until_next_frame()
            
            cv2.imshow("Admin View (Q to quit)", processed_frame)
            if cv2.waitKey(1) == ord('q'):
                stop_event.set()

    streamer.stop()
    cv2.destroyAllWindows()