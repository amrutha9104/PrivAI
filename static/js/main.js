// PrivAI - Main JavaScript Controller
// Handles user registration, WebRTC connection, and video processing UI

const API_URL = 'http://127.0.0.1:8000';
const GALENE_SERVER = 'http://127.0.0.1:8443';

let pc; // Global peer connection
let currentUserId; // Current user identifier
let localStream; // Local media stream

// Register user with face and voice samples
async function registerUser() {
    const userId = document.getElementById('userId').value;
    const faceFile = document.getElementById('faceImage').files[0];
    const audioFile = document.getElementById('audioSample').files[0];
    
    // Validate input
    if (!userId || !faceFile || !audioFile) {
        alert('Please fill all fields: User ID, Face Image, and Voice Sample');
        return false;
    }
    
    // Show loading status
    document.getElementById('status').innerHTML = 
        '<span style="color:blue;">⏳ Registering user profile...</span>';
    
    const formData = new FormData();
    formData.append('user_id', userId);
    formData.append('name', userId);
    formData.append('face_image', faceFile);
    formData.append('audio_sample', audioFile);
    
    try {
        const response = await fetch(`${API_URL}/register_user`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error(`Registration failed: HTTP ${response.status}`);
        }
        
        const result = await response.json();
        document.getElementById('status').innerHTML = 
            `<span style="color:green;">✅ Registered: ${result.user_id}</span>`;
        return true;
    } catch (err) {
        console.error('Registration error:', err);
        document.getElementById('status').innerHTML = 
            `<span style="color:red;">❌ Error: ${err.message}</span>`;
        return false;
    }
}

// Update UI with detection status
function updateDetectionStatus(detections) {
    const statusDiv = document.getElementById('status');
    let html = '<div style="font-size:12px; margin-top:10px; padding:10px; background:#f0f0f0; border-radius:4px;">';
    html += '<strong>🔍 Detection Status:</strong><br>';
    
    if (detections.faces_blurred > 0) {
        html += `<span style="color:red;">🎭 ${detections.faces_blurred} unauthorized face(s) blurred</span><br>`;
    }
    if (detections.objects_blurred > 0) {
        html += `<span style="color:orange;">📦 ${detections.objects_blurred} sensitive object(s) blurred: ${detections.object_classes.join(', ')}</span><br>`;
    }
    if (detections.faces_blurred === 0 && detections.objects_blurred === 0) {
        html += '<span style="color:green;">✅ No privacy threats detected</span><br>';
    }
    
    html += '</div>';
    statusDiv.innerHTML = html;
}

// Join video room and start AI processing
async function joinRoom() {
    // Generate or get user ID
    currentUserId = document.getElementById('userId').value || 'user' + Math.floor(Math.random() * 1000);
    document.getElementById('userId').value = currentUserId;
    
    // Register if files provided
    const faceFile = document.getElementById('faceImage').files[0];
    const audioFile = document.getElementById('audioSample').files[0];
    if (faceFile && audioFile) {
        const registered = await registerUser();
        if (!registered) return;
    }
    
    // Show connecting status
    document.getElementById('status').innerHTML = 
        '<span style="color:blue;">⏳ Connecting camera and starting AI processing...</span>';
    
    try {
        // Request camera and microphone
        localStream = await navigator.mediaDevices.getUserMedia({ 
            video: true, 
            audio: true 
        });
        
        // Create peer connection to Python backend
        pc = new RTCPeerConnection({
            iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
        });
        
        // Add local tracks to peer connection
        localStream.getTracks().forEach(track => {
            pc.addTrack(track, localStream);
        });
        
        // Create data channel for detection updates (optional)
        const dataChannel = pc.createDataChannel('detections');
        dataChannel.onmessage = (event) => {
            try {
                const detections = JSON.parse(event.data);
                updateDetectionStatus(detections);
            } catch (e) {
                console.warn('Failed to parse detection data:', e);
            }
        };
        
        // Handle connection state changes
        pc.onconnectionstatechange = () => {
            console.log('Connection state:', pc.connectionState);
        };
        
        // Create and send offer
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        
        console.log('Sending WebRTC offer to backend...');
        const response = await fetch(`${API_URL}/webrtc/offer`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({
                sdp: offer.sdp,
                user_id: currentUserId
            })
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Backend error: HTTP ${response.status} - ${errorText}`);
        }
        
        const answer = await response.json();
        await pc.setRemoteDescription(answer);
        
        console.log('WebRTC connection established. Displaying video...');
        
        // Display local video with processing
        const videoContainer = document.getElementById('video-container');
        const video = document.createElement('video');
        video.srcObject = localStream;
        video.autoplay = true;
        video.playsInline = true;
        video.muted = true;
        video.style.width = '100%';
        video.style.border = '2px solid #667eea';
        video.style.borderRadius = '8px';
        
        // Clear container and add video
        videoContainer.innerHTML = '';
        videoContainer.appendChild(video);
        
        // Update status
        document.getElementById('status').innerHTML = 
            `<span style="color:green;">✅ Connected as ${currentUserId}. AI processing active.</span>`;
        
        // Open Galène in new tab for SFU/multiplexing (after 1.5 seconds)
        setTimeout(() => {
            const galeneUrl = `${GALENE_SERVER}/group/privai?username=${currentUserId}`;
            window.open(galeneUrl, '_blank');
            console.log('Opened Galène in new tab:', galeneUrl);
        }, 1500);
        
    } catch (err) {
        console.error('❌ WebRTC error:', err);
        document.getElementById('status').innerHTML = 
            `<span style="color:red;">❌ WebRTC Error: ${err.message}</span>`;
        
        // Cleanup on error
        if (localStream) {
            localStream.getTracks().forEach(track => track.stop());
        }
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    currentUserId = 'user' + Math.floor(Math.random() * 1000);
    document.getElementById('userId').value = currentUserId;
    console.log('PrivAI initialized with user ID:', currentUserId);
});