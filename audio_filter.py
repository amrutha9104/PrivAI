# audio_filter.py - FINAL VERSION with Background Muting

import pyaudio
import numpy as np
import threading
import webrtcvad 
from scipy import signal 
import time

# --- Configuration ---
RATE_HW = 44100     
CHUNK_HW = int(RATE_HW * 0.030) # 30ms @ 44100 Hz
RATE_VAD = 16000    
CHUNK_VAD = int(RATE_VAD * 0.030) # 30ms @ 16000 Hz (480 frames)
FORMAT = pyaudio.paInt16 
CHANNELS = 1        

# =================================================================
# Specialized Processing Class (Handles State and Algorithms)
# =================================================================

class AudioProcessor:
    def __init__(self, vad_rate):
        self.vad_rate = vad_rate
        
        # VAD Tuning Parameters
        self._vad_aggressiveness = 2 
        self.vad = webrtcvad.Vad(self._vad_aggressiveness)
        self._vad_confirmation_count = 0
        self._vad_confirm_threshold = 2 
        
        # State variables
        self._is_muted = False
        # Renamed variable for clarity in this mode (1.0 = Muting OFF, >1.0 = Muting ON)
        self._background_mute_factor = 1.0 
        self._is_speaking_confirmed = False 
        self._state_lock = threading.Lock() 
        print(f"Audio Processor: VAD initialized at {vad_rate}Hz (Level {self._vad_aggressiveness}).")

    def set_vad_aggressiveness(self, level: int):
        """Sets the VAD aggressiveness level (0-3)."""
        level = max(0, min(3, level))
        with self._state_lock:
            self._vad_aggressiveness = level
            self.vad = webrtcvad.Vad(level)
            print(f"🎵 VAD Aggressiveness set to Level {level}")
    
    # --- Control Methods ---
    def set_mute(self, mute: bool):
        with self._state_lock:
            if self._is_muted != mute:
                self._is_muted = mute
                print(f"🔊 Audio Mute set to: {self._is_muted}")

    # Updated name and purpose for background control
    def set_background_mute(self, factor: float):
        """Sets the factor (1.0 = Background Mute OFF, >1.0 = Background Mute ON)."""
        with self._state_lock:
            self._background_mute_factor = factor
            # Log the state change clearly for debugging
            state = "ON" if factor > 1.0 else "OFF"
            print(f"🔇 Adaptive Background Muting set to: {state}")

    def is_muted(self):
        with self._state_lock:
            return self._is_muted
            
    def get_background_mute_factor(self):
        with self._state_lock:
            return self._background_mute_factor
    # --- End Control Methods ---

    def process_chunk(self, audio_data_vad: bytes) -> bytes:
        """
        Processes 16kHz audio chunk. If speech is present, it passes clear audio. 
        If NO speech is present, it is aggressively silenced.
        """
        with self._state_lock:
            background_mute_factor = self._background_mute_factor
            
        audio_np = np.frombuffer(audio_data_vad, dtype=np.int16)
        
        # 1. VAD Confirmation Window (Debounce)
        is_speech_instant = self.vad.is_speech(audio_data_vad, self.vad_rate)
        
        with self._state_lock:
            if is_speech_instant:
                self._vad_confirmation_count += 1
            else:
                self._vad_confirmation_count = 0
            
            if self._vad_confirmation_count >= self._vad_confirm_threshold:
                self._is_speaking_confirmed = True
            elif self._vad_confirmation_count == 0 and self._is_speaking_confirmed:
                self._is_speaking_confirmed = False

            is_speaking_confirmed = self._is_speaking_confirmed
        
        # --- 2. Filtering Logic: Pass Speech, Mute Background ---
        
        if is_speaking_confirmed:
            # VAD is TRUE: User is speaking (confirmed). Pass audio through CLEARLY.
            # Your clear voice is passed here.
            pass
            
        else:
            # VAD is FALSE: Background noise/non-speech audio. MUTE THIS.
            
            # The adaptive control (background_mute_factor) acts as the trigger.
            if background_mute_factor > 1.0:
                # Sensitive visuals detected: Aggressively silence background audio.
                audio_np = np.zeros_like(audio_np)
            else:
                # No sensitive visuals: Still aggressively silence background noise
                # (This ensures quiet periods even when adaptive control is OFF).
                audio_np = np.zeros_like(audio_np)
            
        return audio_np.tobytes()

# =================================================================
# Main Threading Loop & Public Control Functions 
# =================================================================

audio_processor = AudioProcessor(RATE_VAD) 

# audio_filter.py (Updated run_audio_distortion function)

def run_audio_distortion(stop_event: threading.Event):
    p = pyaudio.PyAudio()
    stream = None
    
    try:
        # --- CRITICAL FIX: Only open the INPUT stream (Microphone) ---
        # We remove output=True to stop local playback/feedback.
        stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE_HW,
                        input=True,
                        output=False, # <--- CHANGED FROM True to False
                        frames_per_buffer=CHUNK_HW)

        print(f"Audio Filter: Loop running. HW Rate: {RATE_HW}Hz. VAD Rate: {RATE_VAD}Hz.")
        print("Note: Local audio playback (loopback) is now DISABLED to prevent feedback.")

        while not stop_event.is_set():
            if audio_processor.is_muted():
                try:
                    # Read and discard input to keep buffers clear
                    data = stream.read(CHUNK_HW, exception_on_overflow=False) 
                    # We skip writing data to output stream since it's disabled.
                except IOError:
                    continue
                continue

            # 1. Read from Hardware Stream
            data = None
            # ... (Reading logic remains the same) ...
            try:
                data = stream.read(CHUNK_HW, exception_on_overflow=False)
            except IOError as e:
                if e.errno == -9981: 
                    continue 
                raise e 
            
            audio_np_hw = np.frombuffer(data, dtype=np.int16)
            
            # 2. Downsample, Process, and Upsample (Logic remains the same)
            num_samples_vad = int(len(audio_np_hw) * RATE_VAD / RATE_HW)
            audio_np_vad = signal.resample(audio_np_hw, num_samples_vad).astype(np.int16)
            processed_data_vad = audio_processor.process_chunk(audio_np_vad.tobytes())
            
            processed_np_vad = np.frombuffer(processed_data_vad, dtype=np.int16)
            output_num_samples_hw = len(audio_np_hw) 
            processed_np_output = signal.resample(processed_np_vad, output_num_samples_hw).astype(np.int16)
            
            # --- CRITICAL FIX: The processed data is now sent nowhere locally ---
            # In a real app, this processed data (processed_np_output.tobytes()) 
            # would be sent directly over the network via WebRTC, not played locally.
            # We must READ the data but skip the WRITE step.

            # Since the stream object was opened with output=False, we no longer call:
            # stream.write(processed_np_output.tobytes()) 
            pass # We just discard the processed data locally.

    except Exception as e:
        if not stop_event.is_set():
            print(f"Audio Filter UNEXPECTED Error: {e}")
            stop_event.set()
    finally:
        # ... (Cleanup remains the same) ...
        if stream:
            try:
                if stream.is_active():
                    stream.stop_stream()
                stream.close()
            except Exception as cleanup_e:
                print(f"Error during stream cleanup: {cleanup_e}")
        p.terminate()
        print("Audio Filter Thread Terminated.")

# --- Public Control Functions for main_app.py to call ---
# NOTE: Renamed the functions to reflect the new muting purpose
def set_audio_mute(mute: bool):
    audio_processor.set_mute(mute)
def get_audio_mute_state():
    return audio_processor.is_muted()
def set_background_mute_factor(factor: float): # RENAMED
    audio_processor.set_background_mute(factor)
def get_background_mute_factor(): # RENAMED
    return audio_processor.get_background_mute_factor()
def set_vad_aggressiveness(level: int):
    audio_processor.set_vad_aggressiveness(level)