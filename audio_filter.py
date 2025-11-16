# audio_filter.py

import pyaudio
import numpy as np
import threading
import webrtcvad 
from scipy import signal 
import time

# --- Configuration ---
RATE_HW = 44100     # Hardware Sample Rate (Host rate)
CHUNK_HW = int(RATE_HW * 0.030) 
RATE_VAD = 16000    # WebRTC/VAD Processing Rate
CHUNK_VAD = int(RATE_VAD * 0.030) 
FORMAT = pyaudio.paInt16 
CHANNELS = 1        

# --- CRITICAL CONFIGURATION: VB-CABLE DEVICE INDEX ---
# We use a placeholder and attempt to find the index later.
VB_CABLE_OUTPUT_NAME = "CABLE Input" # The name the VB-Cable output device typically uses
OUTPUT_DEVICE_INDEX = -1 

# =================================================================
# Specialized Processing Class (AudioProcessor remains unchanged)
# =================================================================

class AudioProcessor:
    # ... (All methods: __init__, set_mute, process_chunk, etc., remain exactly the same) ...
    def __init__(self, vad_rate):
        self.vad_rate = vad_rate
        
        self._vad_aggressiveness = 2 
        self.vad = webrtcvad.Vad(self._vad_aggressiveness)
        self._vad_confirmation_count = 0
        self._vad_confirm_threshold = 2 
        
        self._is_muted = False
        self._background_mute_factor = 1.0 
        self._is_speaking_confirmed = False 
        self._state_lock = threading.Lock() 
        print(f"Audio Processor: VAD initialized at {vad_rate}Hz (Level {self._vad_aggressiveness}).")

    def set_vad_aggressiveness(self, level: int):
        level = max(0, min(3, level))
        with self._state_lock:
            self._vad_aggressiveness = level
            self.vad = webrtcvad.Vad(level)
            print(f"🎵 VAD Aggressiveness set to Level {level}")
    
    def set_mute(self, mute: bool):
        with self._state_lock:
            if self._is_muted != mute:
                self._is_muted = mute
                print(f"🔊 Audio Mute set to: {self._is_muted}")

    def set_background_mute(self, factor: float):
        with self._state_lock:
            self._background_mute_factor = factor
            state = "ON" if factor > 1.0 else "OFF"
            print(f"🔇 Adaptive Background Muting set to: {state}")

    def is_muted(self):
        with self._state_lock:
            return self._is_muted
            
    def get_background_mute_factor(self):
        with self._state_lock:
            return self._background_mute_factor

    def process_chunk(self, audio_data_vad: bytes) -> bytes:
        with self._state_lock:
            background_mute_factor = self._background_mute_factor
            
        audio_np = np.frombuffer(audio_data_vad, dtype=np.int16)
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
        
        if is_speaking_confirmed:
            pass
        else:
            if background_mute_factor > 1.0:
                audio_np = np.zeros_like(audio_np)
            else:
                audio_np = np.zeros_like(audio_np)
            
        return audio_np.tobytes()

    def extract_voice_embedding(self, audio_content):
        return np.array([0, 0, 0])

# =================================================================
# Main Threading Loop & Public Control Functions 
# =================================================================

audio_processor = AudioProcessor(RATE_VAD) 

def find_vb_cable_index(p: pyaudio.PyAudio):
    """Searches for the VB-CABLE output device index."""
    global OUTPUT_DEVICE_INDEX
    
    for i in range(p.get_device_count()):
        dev_info = p.get_device_info_by_index(i)
        # Check if the device is an output device AND contains the CABLE name
        if dev_info.get('maxOutputChannels') > 0 and VB_CABLE_OUTPUT_NAME in dev_info.get('name', ''):
            OUTPUT_DEVICE_INDEX = i
            print(f"✅ Found VB-CABLE Output at Index: {OUTPUT_DEVICE_INDEX}")
            return True
    
    print(f"❌ VB-CABLE Output device ('{VB_CABLE_OUTPUT_NAME}') NOT found. Audio will be processed but discarded.")
    return False


def run_audio_distortion(stop_event: threading.Event):
    """
    Runs the audio processing loop, writing the final output to VB-CABLE.
    """
    p = pyaudio.PyAudio()
    input_stream = None
    output_stream = None
    
    # 1. Locate the VB-CABLE device
    find_vb_cable_index(p)
    
    try:
        # Open Input Stream (Microphone)
        input_stream = p.open(format=FORMAT,
                              channels=CHANNELS,
                              rate=RATE_HW,
                              input=True,
                              output=False, # Input stream must not output
                              frames_per_buffer=CHUNK_HW)

        # Open Output Stream (VB-CABLE)
        if OUTPUT_DEVICE_INDEX != -1:
            output_stream = p.open(format=FORMAT,
                                   channels=CHANNELS,
                                   rate=RATE_HW,
                                   output=True,
                                   output_device_index=OUTPUT_DEVICE_INDEX, # CRITICAL: Target VB-CABLE
                                   frames_per_buffer=CHUNK_HW)
            print(f"Audio Output routed to VB-CABLE (Index {OUTPUT_DEVICE_INDEX}).")
        else:
            print("Audio processed for VB-CABLE, but output stream is inactive.")

        while not stop_event.is_set():
            if audio_processor.is_muted():
                try:
                    data = input_stream.read(CHUNK_HW, exception_on_overflow=False) 
                except IOError:
                    continue
                
                # If muted, write silence to the cable to maintain the audio track
                if output_stream:
                    output_stream.write(b'\x00' * CHUNK_HW * 2) 
                continue

            # 1. Read from Hardware Stream
            data = None
            try:
                data = input_stream.read(CHUNK_HW, exception_on_overflow=False)
            except IOError as e:
                if e.errno == -9981: 
                    continue 
                raise e 
            
            audio_np_hw = np.frombuffer(data, dtype=np.int16)
            
            # 2. Downsample (44100Hz -> 16000Hz)
            num_samples_vad = int(len(audio_np_hw) * RATE_VAD / RATE_HW)
            audio_np_vad = signal.resample(audio_np_hw, num_samples_vad).astype(np.int16)
            
            # 3. Process at 16000Hz (VAD/Muting)
            processed_data_vad = audio_processor.process_chunk(audio_np_vad.tobytes())
            
            # 4. Upsample (16000Hz -> 44100Hz)
            processed_np_vad = np.frombuffer(processed_data_vad, dtype=np.int16)
            output_num_samples_hw = len(audio_np_hw) 
            processed_np_output = signal.resample(processed_np_vad, output_num_samples_hw).astype(np.int16)
            
            # 5. Write to VB-CABLE Output
            if output_stream:
                output_stream.write(processed_np_output.tobytes())
            pass 

    except Exception as e:
        if not stop_event.is_set():
            print(f"Audio Filter UNEXPECTED Error: {e}")
            stop_event.set()
    finally:
        if input_stream:
            input_stream.close()
        if output_stream:
            output_stream.close()
        if p:
            p.terminate()
        print("Audio Filter Thread Terminated.")

# --- Public Control Functions for main_app.py to call (Unchanged) ---
def set_audio_mute(mute: bool):
    audio_processor.set_mute(mute)
def get_audio_mute_state():
    return audio_processor.is_muted()
def set_background_mute_factor(factor: float): 
    audio_processor.set_background_mute(factor)
def get_background_mute_factor():
    return audio_processor.get_background_mute_factor()
def set_vad_aggressiveness(level: int):
    audio_processor.set_vad_aggressiveness(level)
