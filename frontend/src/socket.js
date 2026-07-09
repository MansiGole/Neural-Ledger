import { io } from "socket.io-client";

const socket = io("http://localhost:3000", {
    transports: ["websocket"],
    autoConnect: true,
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,
    timeout: 10000,
});

socket.on("connect", () => {
    console.log("🟢 Connected to Webhook Reconciliation Engine");
    console.log("Socket ID:", socket.id);
});

socket.on("disconnect", (reason) => {
    console.log("🔴 Socket Disconnected:", reason);
});

socket.on("connect_error", (err) => {
    console.error("❌ Socket Connection Error:", err.message);
});

export default socket;