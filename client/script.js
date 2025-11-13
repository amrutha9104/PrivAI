const socket = io("http://localhost:3000");

const localVideo = document.getElementById('localVideo');
const remoteVideo = document.getElementById('remoteVideo');
const startCallBtn = document.getElementById('startCall');

let localStream;
let peer;

// 1. Get user media
navigator.mediaDevices.getUserMedia({ video: true, audio: true })
  .then(stream => {
    localStream = stream;
    localVideo.srcObject = stream;
  })
  .catch(err => console.error("Error accessing media devices:", err));

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

  localStream.getTracks().forEach(track => peer.addTrack(track, localStream));
}

// 3. Handle call start
startCallBtn.onclick = async () => {
  createPeerConnection();

  const offer = await peer.createOffer();
  await peer.setLocalDescription(offer);
  socket.emit('offer', offer);
};

// 4. Listen for offer, answer, ICE
socket.on('offer', async offer => {
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
