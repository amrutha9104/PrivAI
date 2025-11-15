const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const path = require('path');

const app = express();
const server = http.createServer(app);
const io = new Server(server, {
  cors: { origin: "*" }
});

app.use(express.static(path.join(__dirname, '..', 'client')));

app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, '..', 'client', 'index.html'));
});

// NEW: Store Python client socket
let pythonClient = null;
let webClient = null;

io.on('connection', socket => {
  console.log('✅ User connected:', socket.id);
  
  // Identify client type
  socket.on('client-type', type => {
    if (type === 'python') {
      pythonClient = socket;
      console.log('Python backend connected');
    } else if (type === 'web') {
      webClient = socket;
      console.log('Web client connected');
    }
  });

  // Forward detection alerts from Python to web
  socket.on('new-detection', data => {
    if (webClient && webClient.connected) {
      webClient.emit('new-detection', data);
    }
  });

  // Forward user choices from web to Python
  socket.on('detection-choice', data => {
    if (pythonClient && pythonClient.connected) {
      pythonClient.emit('detection-choice', data);
    }
  });

  // WebRTC signaling (existing)
  socket.on('offer', data => {
    socket.broadcast.emit('offer', data);
  });

  socket.on('answer', data => {
    socket.broadcast.emit('answer', data);
  });

  socket.on('ice-candidate', data => {
    socket.broadcast.emit('ice-candidate', data);
  });

  socket.on('disconnect', () => {
    console.log('❌ User disconnected:', socket.id);
    if (socket === pythonClient) pythonClient = null;
    if (socket === webClient) webClient = null;
  });
});

const PORT = 3000;
server.listen(PORT, () => {
  console.log(`🚀 Signaling server running on port ${PORT}`);
  console.log(`📡 Forwarding detection alerts between Python and Web clients`);
});