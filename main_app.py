# main_app.py

import threading
import time
import cv2
import sys
import socketio

# Import module functions
from video_filter import run_video_loop
from audio_filter import run_audio_distortion, set_audio_mute, get_audio_mute_state, set_background_mute_factor, get_background_mute_factor
from shared_state import DETECTION_STATE

# Global Control Event
STOP_EVENT = threading.Event()

# State variables for manual overrides
is_muted_override = False
is_distortion_override = False

# Adaptive Audio logic timers
LAST_DETECTION_TIME = 0.0
SENSITIVE_HOLD_TIME = 1.0

# Initialize Socket.IO Client
sio = socketio.Client()

@sio.event
def connect():
    print("✅ Main app connected to signaling server")
    # --- FIX: Identify as Python Backend ---
    # Without this, the Node server won't forward "Reveal" commands to us.
    sio.emit('client-type', 'python')

@sio.event
def disconnect():
    print("⚠️  Main app disconnected from signaling server")

# --- CRITICAL: Handle User Choice ---
@sio.on('detection-choice')
def handle_detection_choice(data):
    """
    Receive user choice from Frontend Toast Notification.
    Updates the shared state so the Video Filter knows what to reveal.
    """
    object_id = data.get('objectId')
    choice = data.get('choice')   # 'blur' or 'retain'
    class_name = data.get('className') 
    
    print(f"📩 User Update: {choice.upper()} for '{class_name}' (ID: {object_id})")
    
    # Pass class_name explicitly to save the rule permanently
    DETECTION_STATE.update_object_choice(object_id, choice, class_name=class_name)

def connect_to_server():
    """Continuously try to connect to Node.js server"""
    while not STOP_EVENT.is_set():
        try:
            if not sio.connected:
                sio.connect('http://localhost:3000')
            time.sleep(5)
        except Exception as e:
            time.sleep(5)

def adaptive_control_loop(stop_event: threading.Event):
    """
    Monitors video detections and adjusts audio masking.
    """
    global LAST_DETECTION_TIME
    
    NORMAL_MUTE = 1.0
    HIGH_MUTE = 3.0
    
    print("\n--- Adaptive Control Loop Running ---")
    
    while not stop_event.is_set():
        try:
            # Check if video filter sees something sensitive
            sensitive_detected = DETECTION_STATE.get_sensitive_status()
            
            if sensitive_detected:
                LAST_DETECTION_TIME = time.time()
            
            if not is_distortion_override:
                if sensitive_detected or (time.time() - LAST_DETECTION_TIME < SENSITIVE_HOLD_TIME):
                    if get_background_mute_factor() != HIGH_MUTE:
                        set_background_mute_factor(HIGH_MUTE)
                else:
                    if get_background_mute_factor() != NORMAL_MUTE:
                        set_background_mute_factor(NORMAL_MUTE)
        
        except Exception as e:
            print(f"Control Loop Error: {e}")
            
        time.sleep(0.1)

def manual_control_loop(stop_event: threading.Event):
    """Keyboard controls for debugging"""
    global is_muted_override, is_distortion_override
    
    print("\nManual Controls: 'm' = Toggle Mic Mute | 'd' = Toggle Audio Distortion")
    
    if not sys.stdin.isatty():
        return

    while not stop_event.is_set():
        try:
            user_input = input().strip().lower()
            
            if user_input == 'm':
                is_muted_override = not is_muted_override
                set_audio_mute(is_muted_override)
                print(f"CONTROL: Manual Mic Mute {'ON' if is_muted_override else 'OFF'}")
                
            elif user_input == 'd':
                is_distortion_override = not is_distortion_override
                factor = 3.0 if is_distortion_override else 1.0
                set_background_mute_factor(factor)
                print(f"CONTROL: Manual Distortion {'ON' if is_distortion_override else 'OFF'}")
            
        except:
            pass
        
        time.sleep(0.1)

def main():
    server_thread = threading.Thread(target=connect_to_server, daemon=True)
    server_thread.start()
    
    video_thread = threading.Thread(target=run_video_loop, args=(STOP_EVENT,), daemon=True)
    audio_thread = threading.Thread(target=run_audio_distortion, args=(STOP_EVENT,), daemon=True)
    control_thread = threading.Thread(target=adaptive_control_loop, args=(STOP_EVENT,), daemon=True)
    manual_thread = threading.Thread(target=manual_control_loop, args=(STOP_EVENT,), daemon=True)

    print("--- PrivAI Platform Initialized ---")
    print("Initializing filters...")
    
    video_thread.start()
    audio_thread.start()
    control_thread.start()
    manual_thread.start()

    print("Waiting for virtual camera to stabilize (5s)...")
    time.sleep(5)
    
    try:
        while not STOP_EVENT.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        STOP_EVENT.set()

    print("\nWaiting for threads to cleanup...")
    video_thread.join(timeout=2)
    audio_thread.join(timeout=2)
    control_thread.join(timeout=1)
    
    if sio.connected:
        sio.disconnect()
    
    print("--- Application Shut Down Successfully ---")

if __name__ == '__main__':
    main()