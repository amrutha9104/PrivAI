# main_app.py

import threading
import time
import cv2
import video_filter 
import audio_filter 
import shared_state 
import sys

# Import specific functions for thread communication
from video_filter import run_video_loop 
from audio_filter import run_audio_distortion, set_audio_mute, get_audio_mute_state, set_background_mute_factor, get_background_mute_factor
from shared_state import DETECTION_STATE 

# Global event used to signal threads to stop execution cleanly
STOP_EVENT = threading.Event()

# State variable for the main app to track manual overrides
is_muted_override = False 
is_distortion_override = False

# Debounce timer for smooth control changes
LAST_DETECTION_TIME = 0.0
SENSITIVE_HOLD_TIME = 1.0 

def adaptive_control_loop(stop_event: threading.Event):
    """
    Runs in a dedicated thread to monitor video detection status and adjust audio filters.
    """
    global is_distortion_override
    global LAST_DETECTION_TIME
    
    NORMAL_MUTE = 1.0 
    HIGH_MUTE = 3.0 
    
    print("\n--- Adaptive Control Loop Running ---")
    
    while not stop_event.is_set():
        # 1. Get Video Detection Status
        sensitive_detected = DETECTION_STATE.get_sensitive_status()
        
        # 2. Update Detection Timer
        if sensitive_detected:
            LAST_DETECTION_TIME = time.time()
        
        # 3. Adaptive Logic: Adjust Muting based on detection and debounce
        if not is_distortion_override:
            
            if sensitive_detected or (time.time() - LAST_DETECTION_TIME < SENSITIVE_HOLD_TIME):
                # Apply high mute factor if detected OR within the hold time
                if get_background_mute_factor() != HIGH_MUTE:
                    set_background_mute_factor(HIGH_MUTE)
                    print("CONTROL: Applying HIGH Mute (Sensitive Content Detected / Hold Active)")
            else:
                # Return to normal only if clear AND hold time has expired
                if get_background_mute_factor() != NORMAL_MUTE:
                    set_background_mute_factor(NORMAL_MUTE)
                    print("CONTROL: Returning to NORMAL Mute (Content Clear)")
        
        time.sleep(0.1) 

def manual_control_loop(stop_event: threading.Event):
    """
    Handles manual mute/distortion overrides via terminal.
    """
    global is_muted_override
    global is_distortion_override
    
    print("\nManual Controls: 'm' to Toggle Mute, 'd' to Toggle Background Muting")
    
    # Use sys.stdin.fileno() to check for input availability without blocking entirely
    if sys.stdin.isatty():
        print("Listening for manual input...")
    else:
        print("Manual controls disabled (not running in interactive terminal).")
        return

    while not stop_event.is_set():
        try:
            # Note: This is simplified blocking input, intended for debugging/testing
            user_input = input().strip().lower()
            
            if user_input == 'm':
                is_muted_override = not is_muted_override
                set_audio_mute(is_muted_override)
                print(f"CONTROL: Manual Mute {'ON' if is_muted_override else 'OFF'}")
                
            elif user_input == 'd':
                is_distortion_override = not is_distortion_override
                
                if is_distortion_override:
                    set_background_mute_factor(3.0) 
                    print("CONTROL: Manual Mute Override ON (Factor 3.0)")
                else:
                    set_background_mute_factor(1.0)
                    print("CONTROL: Manual Mute Override OFF. Adaptive control resumed.")
            
        except EOFError:
            pass
        except KeyboardInterrupt:
            stop_event.set()
        
        time.sleep(0.1)


def main():
    
    video_thread = threading.Thread(target=run_video_loop, args=(STOP_EVENT,), daemon=True)
    audio_thread = threading.Thread(target=run_audio_distortion, args=(STOP_EVENT,), daemon=True)
    control_thread = threading.Thread(target=adaptive_control_loop, args=(STOP_EVENT,), daemon=True)
    manual_thread = threading.Thread(target=manual_control_loop, args=(STOP_EVENT,), daemon=True)

    print("--- Adaptive Privacy Filter Initialized ---")
    
    video_thread.start()
    audio_thread.start()
    control_thread.start()
    manual_thread.start()

    print("Waiting for virtual camera to stabilize (5 seconds)...")
    time.sleep(5) # <-- Added startup delay for driver stabilization
    
    # Wait for the stop event to be set
    try:
        while not STOP_EVENT.is_set():
            time.sleep(1) 
    except KeyboardInterrupt:
        print("\nKeyboard Interrupt detected. Signaling threads to stop...")
        STOP_EVENT.set()

    # Wait for all threads to finish (with timeout for stuck I/O threads)
    print("Waiting for final thread cleanup (Max 1 second timeout per thread)...")
    video_thread.join(timeout=1)
    audio_thread.join(timeout=1)
    control_thread.join(timeout=1)
    manual_thread.join(timeout=1)
    
    print("--- Application Shut Down Successfully ---")

if __name__ == '__main__':
    main()