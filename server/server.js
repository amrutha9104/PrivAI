const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const path = require('path');

const app = express();
const server = http.createServer(app);
const io = new Server(server, {
  cors: { origin: "*" } // allow all origins for now
});

// --- CRITICAL FIX 1: Serve Static Files ---
// This middleware tells the server to look in the '../client' directory 
// whenever it receives a request for a file (like /script.js or /style.css).
app.use(express.static(path.join(__dirname, '..', 'client')));


// --- CRITICAL FIX 2: Handle Root Route ---
// This route tells the server to send the main HTML page when the user navigates to http://localhost:3000/
app.get('/', (req, res) => {
    // Assuming the client folder is one level up from the server.js file
    res.sendFile(path.join(__dirname, '..', 'client', 'index.html')); 
});


// Handle connections (Signaling Logic)
io.on('connection', socket => {
  console.log('✅ User connected:', socket.id);

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
  });
});

const PORT = 3000;
server.listen(PORT, () => console.log(`🚀 Signaling server running on port ${PORT}`));