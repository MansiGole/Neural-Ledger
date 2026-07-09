const { getIO } = require("../config/socket");

function emitWebhookReceived(data) {
    getIO().emit("webhook_received", data);
}

function emitAnomaly(data) {
    getIO().emit("anomaly_detected", data);
}

function emitHealingStarted(data) {
    getIO().emit("healing_started", data);
}

function emitHealingCompleted(data) {
    getIO().emit("healing_completed", data);
}

function emitMetricsUpdate(data) {
    getIO().emit("metrics_updated", data);
}

function emitPrediction(data) {
    getIO().emit("prediction_updated", data);
}

module.exports = {
    emitWebhookReceived,
    emitAnomaly,
    emitHealingStarted,
    emitHealingCompleted,
    emitMetricsUpdate,
    emitPrediction,
};