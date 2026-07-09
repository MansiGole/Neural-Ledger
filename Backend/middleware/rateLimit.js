// middleware/rateLimit.js
// Dynamic memory-based token bucket for surges to prevent DB overloading.

const WINDOW_MS = 1000; // 1 second
const MAX_REQUESTS = 50; // max requests per second

let currentWindowStart = Date.now();
let requestCount = 0;

const dynamicRateLimiter = (req, res, next) => {
  const now = Date.now();
  if (now - currentWindowStart > WINDOW_MS) {
    currentWindowStart = now;
    requestCount = 0;
  }

  requestCount++;

  if (requestCount > MAX_REQUESTS) {
    console.warn('[RATE_LIMIT] Surge detected! Blocking request.');
    return res.status(429).json({ error: 'Too Many Requests - Surge Protection Active' });
  }

  next();
};

module.exports = { dynamicRateLimiter };
