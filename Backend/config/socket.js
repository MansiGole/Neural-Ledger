let io = null;

const initializeSocket = (server) => {
    const { Server } = require("socket.io");

    io = new Server(server, {
        cors: {
            origin: "*",
            methods: ["GET", "POST"],
        },
    });

    io.on("connection", (socket) => {
        console.log(`🟢 Dashboard Connected: ${socket.id}`);

        socket.on("disconnect", () => {
            console.log(`🔴 Dashboard Disconnected: ${socket.id}`);
        });
    });

    return io;
};

const getIO = () => {
    if (!io) {
        throw new Error("Socket.io not initialized");
    }

    return io;
};

module.exports = {
    initializeSocket,
    getIO,
};