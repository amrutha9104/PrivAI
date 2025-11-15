const socket = io("http://localhost:3000");

// Identify as web client
socket.emit('client-type', 'web');

// --- DOM Elements ---
const localVideo = document.getElementById('localVideo');
const remoteVideo = document.getElementById('remoteVideo');
const startCallBtn = document.getElementById('startCall');
const statusMessage = document.getElementById('statusMessage');
const detectionPopup = document.getElementById('detectionPopup');
const cameraSelect = document.getElementById('cameraSelect');

// --- State Variables ---
let localStream;
let peer;

// =================================================================
// 1. Robust Camera Discovery (The Fix)
// =================================================================

async function getCameras() {
    statusMessage.textContent = "Requesting camera access...";
    cameraSelect.innerHTML = '<option>Loading...</option>';

    try {
        // 1. Try standard access. 
        // If this fails (e.g., Default Cam is busy), we catch the error.
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
        
        // If successful, stop this temporary stream immediately
        stream.getTracks().forEach(t => t.stop());
        
        // Now we have permission to list labels
        enumerateAndSelect();

    } catch (err) {
        console.warn("Default camera blocked/busy. Trying recovery...", err);
        
        // 2. RECOVERY MODE:
        // If default is busy (Python has it), we try to find the Virtual Camera blindly.
        try {
            const devices = await navigator.mediaDevices.enumerateDevices();
            const videoDevices = devices.filter(d => d.kind === 'videoinput');
            
            // Try to find a specific Virtual Camera ID even without labels if possible,
            // or just try opening the SECOND device (index 1) which is often the Virtual Cam.
            if (videoDevices.length > 1) {
                console.log("Attempting to bypass busy camera by selecting secondary device...");
                startCameraStream(videoDevices[1].deviceId); // Try the next camera
                
                // Refresh list after a short delay to get labels
                setTimeout(enumerateAndSelect, 1000);
            } else {
                throw new Error("No alternative camera found.");
            }
        } catch (recoveryErr) {
            console.error("Recovery failed:", recoveryErr);
            statusMessage.textContent = "⚠️ Camera Locked. Stop Python, Refresh Page, then Start Python.";
            statusMessage.style.color = "orange";
            
            // Add a manual retry button for user
            cameraSelect.innerHTML = '<option>⚠️ Camera Busy</option>';
        }
    }
}

async function enumerateAndSelect() {
    try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const videoDevices = devices.filter(device => device.kind === 'videoinput');

        cameraSelect.innerHTML = '<option value="" disabled>Select Camera Source</option>';
        
        let virtualCamId = null;

        videoDevices.forEach(device => {
            const option = document.createElement('option');
            option.value = device.deviceId;
            option.text = device.label || `Camera ${cameraSelect.length}`;
            
            // Smart Auto-Select Logic
            const label = device.label.toLowerCase();
            if (label.includes('virtual') || label.includes('obs') || label.includes('unity')) {
                virtualCamId = device.deviceId;
                option.selected = true;
            }
            
            cameraSelect.appendChild(option);
        });

        // If we found a virtual camera, start it. Otherwise use the first one.
        const targetId = virtualCamId || (videoDevices.length > 0 ? videoDevices[0].deviceId : null);
        
        if (targetId) {
            startCameraStream(targetId);
        }

    } catch (e) {
        console.error("Enumeration error:", e);
    }
}

async function startCameraStream(deviceId) {
    if (localStream) {
        localStream.getTracks().forEach(track => track.stop());
    }

    try {
        const constraints = {
            video: { 
                deviceId: { exact: deviceId },
                width: { ideal: 1280 },
                height: { ideal: 720 }
            },
            audio: true 
        };

        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        localStream = stream;
        localVideo.srcObject = stream;
        statusMessage.textContent = "✅ System Ready. Waiting for call...";
        statusMessage.style.color = "#4CAF50";
        
    } catch (err) {
        console.error("Stream error for ID " + deviceId, err);
        statusMessage.textContent = "❌ Selected camera is busy or unavailable.";
    }
}

// Listen for dropdown changes
cameraSelect.onchange = () => {
    startCameraStream(cameraSelect.value);
};

// Initialize
getCameras();

// =================================================================
// 2. Detection Alert Logic (Standard)
// =================================================================

socket.on('new-detection', data => {
    const { objectId, className } = data;
    detectionPopup.style.display = 'flex';
    detectionPopup.innerHTML = `
        <div class="popup-content">
            <h3>🚨 New Detection</h3>
            <p>A <strong>${className}</strong> was detected.</p>
            <div class="button-group">
                <button onclick="handleDetectionChoice(${objectId}, 'retain', '${className}')" style="background:#4CAF50">✅ Reveal</button>
                <button onclick="handleDetectionChoice(${objectId}, 'blur', '${className}')" style="background:#ff9800">🔒 Keep Blurred</button>
            </div>
        </div>
    `;
});

window.handleDetectionChoice = function(objectId, choice, className) {
    socket.emit('detection-choice', { objectId, choice, className });
    detectionPopup.style.display = 'none';
    statusMessage.textContent = `Action: ${choice === 'retain' ? 'Revealed' : 'Blurred'} ${className}`;
    setTimeout(() => statusMessage.textContent = "Secure call active", 3000);
};

// =================================================================
// 3. WebRTC Call Logic (Standard)
// =================================================================

function createPeerConnection() {
    peer = new RTCPeerConnection({
        iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
    });

    peer.ontrack = event => {
        remoteVideo.srcObject = event.streams[0];
        statusMessage.textContent = "✅ Call Connected";
    };

    peer.onicecandidate = event => {
        if (event.candidate) socket.emit('ice-candidate', event.candidate);
    };

    if (localStream) {
        localStream.getTracks().forEach(track => peer.addTrack(track, localStream));
    }
}

startCallBtn.onclick = async () => {
    if (!localStream) return alert("Please wait for camera connection.");
    statusMessage.textContent = "⏳ Calling...";
    createPeerConnection();
    const offer = await peer.createOffer();
    await peer.setLocalDescription(offer);
    socket.emit('offer', offer);
};

socket.on('offer', async offer => {
    createPeerConnection();
    await peer.setRemoteDescription(offer);
    const answer = await peer.createAnswer();
    await peer.setLocalDescription(answer);
    socket.emit('answer', answer);
    statusMessage.textContent = "⏳ Answering...";
});

socket.on('answer', async answer => {
    await peer.setRemoteDescription(answer);
});

socket.on('ice-candidate', async candidate => {
    if (peer) await peer.addIceCandidate(candidate);
});