# video_filter.py
import cv2
import numpy as np
from ultralytics import YOLO
import torch
import threading
import time 
import os # Added for path/OS checks
import pyvirtualcam # <--- NEW: For sending output to a virtual webcam
# video_filter.py (Replace the old line with these two lines)

from pyvirtualcam import PixelFormat
from webcam_stream import WebcamStream 
from shared_state import DETECTION_STATE 

# --- Configuration ---
MODEL_PATH = 'yolov8n-seg.pt'
try:
    # Load the model outside the loop
    model = YOLO(MODEL_PATH).to('cuda') 
    print("YOLOv8 model loaded to CUDA (GPU).")
except:
    model = YOLO(MODEL_PATH)
    print("YOLOv8 model loaded to CPU.")

INPAINT_RADIUS = 5 
SENSITIVE_CLASS_IDS = [   # ID for 'person' (used for background blurring)
    67,   # cell phone
    64,   # laptop
    66,   # keyboard
    74,   # book
    39,   # bottle
    65,   # remote
    63    # mouse
] 

# Foreground Subject Exclusion Constant
MAX_MAIN_SUBJECT_AREA_RATIO = 0.50 # Assume person taking >50% of screen is the main subject

# Tuning Parameters
CONFIDENCE_THRESHOLD = 0.40 
IOU_THRESHOLD = 0.70          

def process_frame_segmentation(frame):
    # Get frame dimensions for area calculation
    H, W, _ = frame.shape
    FRAME_AREA = H * W
    
    results = model(
        frame, 
        conf=CONFIDENCE_THRESHOLD, 
        iou=IOU_THRESHOLD,          
        stream=False, 
        verbose=False
    )
    result = results[0]

    if result.masks is None or len(result.masks) == 0:
        DETECTION_STATE.set_sensitive_status(False)
        return frame 

    class_ids = result.boxes.cls.cpu().numpy().astype(int)
    all_masks_data = result.masks.data
    boxes = result.boxes.xyxy.cpu().numpy().astype(int)
    
    sensitive_indices = []
    max_person_area = 0
    main_subject_index = -1
    
    # 1. First Pass: Find the largest 'person' and track its index
    for i, (box, class_id) in enumerate(zip(boxes, class_ids)):
        if class_id == 0: # Is a 'person'
            x1, y1, x2, y2 = box
            area = (x2 - x1) * (y2 - y1)
            if area > max_person_area:
                max_person_area = area
                main_subject_index = i

    # Determine if the largest person is considered the main subject
    is_main_subject_too_large = (max_person_area / FRAME_AREA) > MAX_MAIN_SUBJECT_AREA_RATIO
    
    # 2. Second Pass: Determine which objects to blur (excluding the foreground person)
    sensitive_found = False
    
    for i, class_id in enumerate(class_ids):
        # Always include non-person sensitive items
        if class_id != 0 and class_id in SENSITIVE_CLASS_IDS:
            sensitive_indices.append(i)
            sensitive_found = True
        
        # Include 'person' ONLY if they are NOT the large, central subject
        elif class_id == 0 and class_id in SENSITIVE_CLASS_IDS:
            # Blur if they are NOT the largest person
            if i != main_subject_index:
                sensitive_indices.append(i)
                sensitive_found = True
            # Blur the largest person only if they are very far away (area is small)
            elif not is_main_subject_too_large and main_subject_index == i:
                sensitive_indices.append(i)
                sensitive_found = True

    # --- Remainder of the code ---
    
    if not sensitive_indices:
        DETECTION_STATE.set_sensitive_status(False)
        return frame 
    
    DETECTION_STATE.set_sensitive_status(True)

    # 3. Precise Mask Generation and Anonymization
    sensitive_masks_tensor = all_masks_data[sensitive_indices]
    combined_mask_tensor = torch.any(sensitive_masks_tensor, dim=0).int() * 255
    mask = combined_mask_tensor.cpu().numpy().astype(np.uint8)

    inpainted_frame = cv2.inpaint(
        src=frame, 
        inpaintMask=mask, 
        inpaintRadius=INPAINT_RADIUS, 
        flags=cv2.INPAINT_NS
    )

    # 4. Apply Blur and Blend (Anonymization effect)
    blurred_inpainted_area = cv2.GaussianBlur(inpainted_frame, (35, 35), 0) 
    final_frame = np.where(mask[:, :, None] == 255, blurred_inpainted_area, inpainted_frame)

    return final_frame


def run_video_loop(stop_event: threading.Event):
    """
    Main loop using the multi-threaded webcam reader and sending output to a 
    virtual camera device using pyvirtualcam.
    """
    streamer = WebcamStream(src=0).start() 
    if streamer.stopped:
        stop_event.set()
        return

    # Get video dimensions and FPS from the capture object
    W = int(streamer.stream.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(streamer.stream.get(cv2.CAP_PROP_FRAME_HEIGHT))
    FPS = streamer.stream.get(cv2.CAP_PROP_FPS) or 30 # Default to 30 FPS if unavailable

    frame_count = 0
    start_time = time.time()

    # --- CRITICAL CHANGE: Initialize Virtual Camera ---
    try:
        # pyvirtualcam expects RGB, while OpenCV outputs BGR. 
        # We will use cv2.COLOR_BGR2RGB for conversion before sending.
        with pyvirtualcam.Camera(width=W, height=H, fps=FPS, fmt=pyvirtualcam.PixelFormat.RGB) as cam:
            print(f"Video Output: Sending stream to virtual camera device '{cam.device}' at {FPS:.1f} FPS")
            
            while not stop_event.is_set():
                if streamer.stopped:
                    break
                    
                frame = streamer.read()
                
                if frame is None:
                    time.sleep(0.01)
                    continue
                    
                # --- Processing ---
                filtered_frame = process_frame_segmentation(frame)
                
                # Convert BGR (OpenCV) to RGB (pyvirtualcam standard)
                rgb_frame = cv2.cvtColor(filtered_frame, cv2.COLOR_BGR2RGB)

                # --- Send to Virtual Camera ---
                cam.send(rgb_frame)
                
                # --- Display (For local debugging/feedback) ---
                cv2.imshow('Debug Filtered Output | Press Q to Quit', filtered_frame) 
                
                # Tell the virtual camera to wait for the next frame time
                cam.sleep_until_next_frame() 
                
                # --- FPS Calculation and Exit Check ---
                frame_count += 1
                elapsed_time = time.time() - start_time
                if elapsed_time > 1: 
                    fps = frame_count / elapsed_time
                    start_time = time.time()
                    frame_count = 0
                    print(f"Video FPS: {fps:.2f} | Sensitive: {DETECTION_STATE.get_sensitive_status()}")

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    stop_event.set()
                    break

    except Exception as e:
        print(f"Virtual Cam Error or Video Filter UNEXPECTED Error: {e}")
        stop_event.set()
    finally:
        # Cleanup
        streamer.stop()
        cv2.destroyAllWindows()
        print("Video Filter Thread Terminated.")