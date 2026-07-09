// middleware/signatureVerification.js
// Verifies incoming webhook requests using HMAC-SHA256.
// Reads the signature from the `x-webhook-signature` header,
// recomputes it from the raw request body, and rejects mismatches with 401.
//
// IMPORTANT: Requires req.rawBody to be populated. This is done in server.js
// via the express.json({ verify }) callback — no extra packages needed.

const crypto = require('crypto');

const verifySignature = (req, res, next) => {
  const secret = process.env.WEBHOOK_SECRET;

  if (!secret) {
    console.error('[SIGNATURE] WEBHOOK_SECRET is not set in environment variables.');
    return res.status(500).json({ error: 'Server misconfiguration: missing WEBHOOK_SECRET.' });
  }

  const receivedSig = req.headers['x-webhook-signature'];

  if (!receivedSig) {
    console.warn('[SIGNATURE] Rejected: missing x-webhook-signature header.');
    return res.status(401).json({ error: 'Unauthorized: missing webhook signature.' });
  }

  // req.rawBody is attached in server.js via express.json verify callback
  const rawBody = req.rawBody;
  if (!rawBody) {
    console.error('[SIGNATURE] rawBody not available — check server.js express.json({ verify }) setup.');
    return res.status(500).json({ error: 'Internal error: raw body unavailable for signature verification.' });
  }

  // Compute expected HMAC-SHA256 signature
  const expectedSig = crypto
    .createHmac('sha256', secret)
    .update(rawBody)
    .digest('hex');

  // Use timingSafeEqual to prevent timing attacks
  try {
    const receivedBuf = Buffer.from(receivedSig, 'hex');
    const expectedBuf = Buffer.from(expectedSig, 'hex');

    if (
      receivedBuf.length !== expectedBuf.length ||
      !crypto.timingSafeEqual(receivedBuf, expectedBuf)
    ) {
      console.warn('[SIGNATURE] Rejected: invalid signature.');
      return res.status(401).json({ error: 'Unauthorized: invalid webhook signature.' });
    }
  } catch (err) {
    // Buffer conversion can fail if signature is not valid hex
    console.warn('[SIGNATURE] Rejected: malformed signature value.', err.message);
    return res.status(401).json({ error: 'Unauthorized: malformed signature header.' });
  }

  console.log('[SIGNATURE] Verified successfully.');
  next();
};

module.exports = { verifySignature };
