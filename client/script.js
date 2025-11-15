const socket = io("http://localhost:3000");

const localVideo = document.getElementById('localVideo');
const remoteVideo = document.getElementById('remoteVideo');
const startCallBtn = document.getElementById('startCall');

let localStream;
let peer;

// Define the names of the devices we expect from the filter setup
const VIRTUAL_CAMERA_LABEL = "OBS Virtual Camera";
const PHYSICAL_MIC_LABEL_PARTIAL = "Microphone"; 

// --------------------------------------------------------
// 1. Get User Media (MODIFIED FOR FILTER INTEGRATION)
// --------------------------------------------------------

async function getFilteredMedia() {
    try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        
        let virtualCamera = devices.find(
            // 1. Try to find the device by its full, standard label
            d => d.kind === 'videoinput' && d.label.includes(VIRTUAL_CAMERA_LABEL)
        );

        // 2. CRITICAL FIX: If standard name fails, search for the device with an empty label
        if (!virtualCamera) {
            virtualCamera = devices.find(
                d => d.kind === 'videoinput' && d.label === ''
            );
        }
        
        // 3. Find the physical microphone
        const physicalMic = devices.find(
            d => d.kind === 'audioinput' && d.label.includes(PHYSICAL_MIC_LABEL_PARTIAL) && !d.label.includes('Virtual')
        );

        if (!virtualCamera) {
            console.error(`ERROR: Virtual Camera not found! No device found with label '${VIRTUAL_CAMERA_LABEL}' OR empty label.`);
            alert(`Filter Error: Could not find '${VIRTUAL_CAMERA_LABEL}'. Is main_app.py running?`);
            return;
        }

        // B. Define Constraints using the found device IDs
        const constraints = {
            video: {
                // CRITICAL: Request the video stream from the Virtual Camera (filtered output)
                deviceId: { ideal: virtualCamera.deviceId },
                width: 1280, 
                height: 720
            },
            audio: {
                // CRITICAL: Request the audio stream from the physical mic (raw input for filter)
                deviceId: { ideal: physicalMic ? physicalMic.deviceId : 'default' }
            }
        };

        // C. Request the stream
        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        
        localStream = stream;
        localVideo.srcObject = stream;
        console.log("SUCCESS: Filtered media stream acquired.");
        
    } catch (err) {
        console.error("Error accessing media devices:", err);
        alert("Media Error: Check console and ensure all competing apps are closed. Error: " + err.name);
    }
}

// Start the media acquisition process immediately
getFilteredMedia();

// --------------------------------------------------------
// 2-4. WebRTC Setup and Signaling 
// --------------------------------------------------------

// 2. Setup peer connection
function createPeerConnection() {
    peer = new RTCPeerConnection();

    peer.ontrack = event => {
        remoteVideo.srcObject = event.streams[0];
    };

    peer.onicecandidate = event => {
        if (event.candidate) {
            socket.emit('ice-candidate', event.candidate);
        }
    };

    if (localStream) {
        localStream.getTracks().forEach(track => peer.addTrack(track, localStream));
    } else {
        console.error("Cannot add tracks: localStream is not yet defined.");
    }
}

// 3. Handle call start
startCallBtn.onclick = async () => {
    // Check localStream status before proceeding
    if (!localStream) {
        alert("Media stream not ready yet. Please wait.");
        return;
    }
    
    // Check if the stream has tracks (to prevent silent failure)
    if (localStream.getTracks().length === 0) {
        alert("Media stream acquired but no tracks found. Check camera/mic permissions.");
        return;
    }

    createPeerConnection();

    const offer = await peer.createOffer();
    await peer.setLocalDescription(offer);
    
    console.log("Attempting to send offer to signaling server."); 
    socket.emit('offer', offer);
};

// 4. Listen for offer, answer, ICE
socket.on('offer', async offer => {
    // Ensure localStream is available before starting the peer connection process as responder
    if (!localStream) {
        console.error("Local media stream not available. Cannot respond to offer.");
        return;
    }
    
    createPeerConnection();
    await peer.setRemoteDescription(offer);
    const answer = await peer.createAnswer();
    await peer.setLocalDescription(answer);
    socket.emit('answer', answer);
});

socket.on('answer', async answer => {
    await peer.setRemoteDescription(answer);
});

socket.on('ice-candidate', async candidate => {
    try {
        await peer.addIceCandidate(candidate);
    } catch (e) {
        console.error("Error adding received ICE candidate", e);
    }
});