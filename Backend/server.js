// server.js
// Entry point for the Webhook Reconciliation Engine

require("dotenv").config();

// Start BullMQ Worker
require("./workers/webhookWorker");

const express = require("express");
const cors = require("cors");
const http = require("http");

const webhookRoutes = require("./routes/webhook");
const { initializeSocket } = require("./config/socket");

const app = express();
const server = http.createServer(app);

const PORT = process.env.PORT || 3000;

// -----------------------------------------------------------------------------
// Socket.IO
// -----------------------------------------------------------------------------

initializeSocket(server);

// -----------------------------------------------------------------------------
// Middleware
// -----------------------------------------------------------------------------

app.use(cors());

app.use(
  express.json({
    verify: (req, res, buf) => {
      req.rawBody = buf;
    },
  })
);

// Simple Request Logger
app.use((req, res, next) => {
  console.log(
    `[REQUEST] ${new Date().toISOString()} ${req.method} ${req.originalUrl}`
  );
  next();
});

// -----------------------------------------------------------------------------
// Routes
// -----------------------------------------------------------------------------

app.use("/", webhookRoutes);

// -----------------------------------------------------------------------------
// Health Check
// -----------------------------------------------------------------------------

app.get("/health", (req, res) => {
  res.json({
    status: "ok",
    socket: "connected",
    timestamp: new Date().toISOString(),
  });
});

// -----------------------------------------------------------------------------
// 404
// -----------------------------------------------------------------------------

app.use((req, res) => {
  res.status(404).json({
    error: `Route not found: ${req.method} ${req.originalUrl}`,
  });
});

// -----------------------------------------------------------------------------
// Global Error Handler
// -----------------------------------------------------------------------------

app.use((err, req, res, next) => {
  console.error("[SERVER ERROR]", err);

  res.status(500).json({
    success: false,
    error: "Internal Server Error",
  });
});

// -----------------------------------------------------------------------------
// Start Server
// -----------------------------------------------------------------------------

server.listen(PORT, () => {
  console.log("");
  console.log("==============================================");
  console.log("🚀 Neural Ledger Backend Started");
  console.log("==============================================");
  console.log(`Server      : http://localhost:${PORT}`);
  console.log(`Health      : GET  /health`);
  console.log(`Webhook     : POST /webhook`);
  console.log(`Socket.IO   : Enabled`);
  console.log(`BullMQ      : Enabled`);
  console.log(`Redis       : Enabled`);
  console.log("==============================================");
  console.log("");
});