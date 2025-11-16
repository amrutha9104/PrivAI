const socket = io("http://localhost:3000");

// Identify this client as the Web Interface
socket.emit('client-type', 'web');

// --- DOM Elements ---
const localVideo = document.getElementById('localVideo');
const remoteVideo = document.getElementById('remoteVideo');
const startCallBtn = document.getElementById('startCall');
const statusMessage = document.getElementById('statusMessage');
const cameraSelect = document.getElementById('cameraSelect');
const toggleMicBtn = document.getElementById('toggleMicBtn');
const toggleCamBtn = document.getElementById('toggleCamBtn');

// Create Toast Container if it doesn't exist (Fail-safe)
let toastContainer = document.getElementById('toast-container');
if (!toastContainer) {
    toastContainer = document.createElement('div');
    toastContainer.id = 'toast-container';
    toastContainer.className = 'toast-container';
    document.body.appendChild(toastContainer);
}

// --- State Variables ---
let localStream;
let peer;
let isMicOn = true;
let isCamOn = true;
const activeAlerts = new Set(); // Prevents spamming the same alert

// =================================================================
// 1. Camera & Media Logic
// =================================================================

async function getCameras() {
    try {
        // Request permission first to see device labels
        await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
        enumerateAndSelect();
    } catch (err) {
        console.warn("Access needed for enumeration", err);
        cameraSelect.innerHTML = '<option>⚠️ Allow Camera Access</option>';
    }
}

async function enumerateAndSelect() {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const videoDevices = devices.filter(d => d.kind === 'videoinput');
    
    cameraSelect.innerHTML = '<option value="" disabled>Select Input</option>';
    
    let virtualId = null;
    
    videoDevices.forEach((d, index) => {
        const opt = document.createElement('option');
        opt.value = d.deviceId;
        opt.text = d.label || `Camera ${index + 1}`;
        
        // Auto-select Virtual Camera if found
        if (d.label.includes('Virtual') || d.label.includes('OBS') || d.label.includes('Unity')) {
            virtualId = d.deviceId;
            opt.selected = true;
        }
        cameraSelect.appendChild(opt);
    });
    
    // Start stream with Virtual Cam if found, else first available
    if (virtualId || videoDevices.length > 0) {
        startCameraStream(virtualId || videoDevices[0].deviceId);
    }
}

async function startCameraStream(deviceId) {
    if (localStream) {
        localStream.getTracks().forEach(t => t.stop());
    }
    
    try {
        console.log("Starting stream with device:", deviceId);
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { 
                deviceId: { exact: deviceId }, 
                width: { ideal: 1280 }, 
                height: { ideal: 720 } 
            },
            audio: true
        });
        
        localStream = stream;
        localVideo.srcObject = stream;
        statusMessage.textContent = "✅ Stream Active";
        statusMessage.style.color = "#4CAF50";
        
        // Reset UI state
        isMicOn = true;
        isCamOn = true;
        updateButtonUI(toggleMicBtn, true, 'fa-microphone', 'fa-microphone-slash');
        updateButtonUI(toggleCamBtn, true, 'fa-video', 'fa-video-slash');
        
    } catch (e) {
        console.error("Camera Error:", e);
        statusMessage.textContent = "❌ Camera Error (Check Console)";
        statusMessage.style.color = "#f44336";
    }
}

cameraSelect.onchange = () => startCameraStream(cameraSelect.value);

// Initialize
getCameras();

// =================================================================
// 2. Detection & Notification Logic ( The Fix )
// =================================================================

socket.on('new-detection', data => {
    const { objectId, className } = data;
    
    // Check local spam prevention
    if (activeAlerts.has(className)) return;
    activeAlerts.add(className);

    console.log(`🚨 Popup for: ${className}`);

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `
        <div class="toast-content">
            <h4>🔒 Privacy Alert</h4>
            <p><strong>${className}</strong> detected & blurred</p>
        </div>
        <div class="toast-actions">
            <button class="toast-btn btn-dismiss" onclick="dismissToast(this, '${className}')">Dismiss</button>
            <button class="toast-btn btn-reveal" onclick="revealObject(this, ${objectId}, '${className}')">Reveal</button>
        </div>
    `;
    toastContainer.appendChild(toast);
    
    // Auto dismiss
    setTimeout(() => {
        if (toast.parentElement) closeToast(toast, className);
    }, 8000);
});

window.revealObject = function(btnElement, objectId, className) {
    console.log(`Sending Reveal for Class: ${className}`);
    
    // Send specific command to backend
    socket.emit('detection-choice', {
        objectId: objectId,
        choice: 'retain', 
        className: className // This is what shared_state uses now
    });

    const toast = btnElement.closest('.toast');
    toast.classList.add('success');
    toast.innerHTML = `
        <div class="toast-content">
            <h4 style="color: #4CAF50">✅ Revealing...</h4>
            <p>${className} visible</p>
        </div>`;
        
    setTimeout(() => closeToast(toast, className), 1500);
};
window.dismissToast = function(btnElement, className) {
    const toast = btnElement.closest('.toast');
    closeToast(toast, className);
};

function closeToast(toast, className) {
    // Animation
    toast.style.animation = 'fadeOut 0.3s ease-in forwards';
    
    // Wait for animation, then remove
    setTimeout(() => {
        if (toast.parentElement) toast.remove();
        // Allow this class to trigger alerts again later if it re-appears
        // (Optional: Remove this line if you want to mute alerts for this class forever)
        activeAlerts.delete(className); 
    }, 300);
}

// =================================================================
// 3. Media Controls (Mic/Cam)
// =================================================================

window.toggleMic = function() {
    if (localStream) {
        const audioTrack = localStream.getAudioTracks()[0];
        if (audioTrack) {
            isMicOn = !isMicOn;
            audioTrack.enabled = isMicOn;
            updateButtonUI(toggleMicBtn, isMicOn, 'fa-microphone', 'fa-microphone-slash');
        }
    }
};

window.toggleCam = function() {
    if (localStream) {
        const videoTrack = localStream.getVideoTracks()[0];
        if (videoTrack) {
            isCamOn = !isCamOn;
            videoTrack.enabled = isCamOn;
            updateButtonUI(toggleCamBtn, isCamOn, 'fa-video', 'fa-video-slash');
        }
    }
};

function updateButtonUI(btn, isActive, iconActive, iconInactive) {
    const icon = btn.querySelector('i');
    if (isActive) {
        btn.style.backgroundColor = '#444';
        btn.style.color = '#fff';
        if(icon) icon.className = `fas ${iconActive}`;
    } else {
        btn.style.backgroundColor = '#f44336'; // Red
        btn.style.color = '#fff';
        if(icon) icon.className = `fas ${iconInactive}`;
    }
}

// =================================================================
// 4. WebRTC Logic (Standard)
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
        if (event.candidate) {
            socket.emit('ice-candidate', event.candidate);
        }
    };

    if (localStream) {
        localStream.getTracks().forEach(track => peer.addTrack(track, localStream));
    }
}

startCallBtn.onclick = async () => {
    if (!localStream) return alert("Camera not ready");
    
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
    statusMessage.textContent = "⏳ Connecting...";
});

socket.on('answer', async answer => {
    await peer.setRemoteDescription(answer);
});

socket.on('ice-candidate', async candidate => {
    if (peer) await peer.addIceCandidate(candidate);
});