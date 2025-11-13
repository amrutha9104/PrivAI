const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const path = require('path');

const app = express();
const server = http.createServer(app);
const io = new Server(server, {
  cors: { origin: "*" } // allow all origins for now
});

// Handle connections
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
