// middleware/validation.js
// Validates that incoming webhook payloads contain required fields.
// Rejects invalid payloads early before any DB interaction.

const validatePayload = (req, res, next) => {
  const { txn_id, event_type } = req.body;

  if (!txn_id || typeof txn_id !== 'string' || txn_id.trim() === '') {
    console.warn('[VALIDATION] Rejected: missing or invalid txn_id');
    return res.status(400).json({
      error: 'Invalid payload: txn_id is required and must be a non-empty string.',
    });
  }

  if (!event_type || typeof event_type !== 'string' || event_type.trim() === '') {
    console.warn('[VALIDATION] Rejected: missing or invalid event_type');
    return res.status(400).json({
      error: 'Invalid payload: event_type is required and must be a non-empty string.',
    });
  }

  next();
};

module.exports = { validatePayload };
