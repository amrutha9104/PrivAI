from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from src.database import PrivAIDatabase
from src.audio_processor import AudioProcessor
from src.video_processor import VideoProcessor
import cv2
import numpy as np
import os
import asyncio
import json
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaRelay
from av import VideoFrame

app = FastAPI(title="PrivAI Backend")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = PrivAIDatabase()
audio_proc = AudioProcessor()

pcs = set()
relay = MediaRelay()

class VideoTransformTrack(MediaStreamTrack):
    kind = "video"
    
    def __init__(self, track, user_id):
        super().__init__()
        self.track = track
        self.user_id = user_id
        self.processor = VideoProcessor()
        self.db = PrivAIDatabase()
        self.settings = self.db.get_privacy_settings(user_id) or {
            'blur_unknown_faces': True,
            'blur_objects': True,
            'background_mode': 'blur'
        }

    async def recv(self):
        frame = await self.track.recv()
        img = frame.to_ndarray(format="bgr24")
        
        processed_img, detections = self.processor.process_frame(
            img, self.user_id, self.db, self.settings
        )
        
        if detections.get('faces_blurred', 0) > 0 or detections.get('objects_blurred', 0) > 0:
            print(f"📊 Processed: {detections}")
        
        new_frame = VideoFrame.from_ndarray(processed_img, format="bgr24")
        new_frame.pts = frame.pts
        new_frame.time_base = frame.time_base
        return new_frame

@app.post("/webrtc/offer")
async def webrtc_offer(offer_data: dict):
    try:
        offer_sdp = offer_data["sdp"]
        user_id = offer_data.get("user_id", "anonymous")
        
        pc = RTCPeerConnection()
        pcs.add(pc)
        
        @pc.on("track")
        async def on_track(track):
            if track.kind == "video":
                print(f"🎥 Video track from {user_id} - AI processing active")
                pc.addTrack(VideoTransformTrack(relay.subscribe(track), user_id))
            elif track.kind == "audio":
                print(f"🎤 Audio track from {user_id}")
        
        await pc.setRemoteDescription(RTCSessionDescription(sdp=offer_sdp, type="offer"))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        
        return {"sdp": answer.sdp, "type": "answer"}
    except Exception as e:
        raise HTTPException(500, f"WebRTC error: {str(e)}")

@app.on_event("shutdown")
async def shutdown_event():
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open("index.html", "r") as f:
        return f.read()

@app.post("/register_user")
async def register_user(
    user_id: str = Form(...),
    name: str = Form("User"),
    face_image: UploadFile = File(...),
    audio_sample: UploadFile = File(...),
):
    try:
        face_content = await face_image.read()
        face_array = np.frombuffer(face_content, np.uint8)
        face_img = cv2.imdecode(face_array, cv2.IMREAD_COLOR)
        if face_img is None:
            raise HTTPException(400, "Invalid face image")
        face_embedding = cv2.mean(face_img)[:3]

        audio_content = await audio_sample.read()
        voice_embedding = audio_proc.extract_voice_embedding(audio_content)

        db.add_user(user_id, name, face_embedding, voice_embedding)
        return {"status": "success", "user_id": user_id}
    except Exception as e:
        raise HTTPException(500, f"Registration failed: {str(e)}")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "PrivAI Backend"}