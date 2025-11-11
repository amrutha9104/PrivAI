import numpy as np
import io
import librosa
from scipy.signal import butter, filtfilt

class AudioProcessor:
    def __init__(self):
        print("🎤 Initializing AudioProcessor...")
        self.sample_rate = 16000
        print("✅ AudioProcessor initialized")

    def extract_voice_embedding(self, audio_bytes):
        try:
            audio, sr = librosa.load(io.BytesIO(audio_bytes), sr=self.sample_rate)
            mfcc = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=40)
            return np.mean(mfcc, axis=1)
        except Exception as e:
            print(f"❌ Voice embedding error: {e}")
            return np.random.rand(40)

    def cosine_similarity(self, vec1, vec2):
        try:
            dot = np.dot(vec1, vec2)
            norm1, norm2 = np.linalg.norm(vec1), np.linalg.norm(vec2)
            return dot / (norm1 * norm2 + 1e-8) if norm1 > 0 and norm2 > 0 else 0
        except:
            return 0