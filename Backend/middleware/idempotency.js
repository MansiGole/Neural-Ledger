const redis = require("../config/redis");
const axios = require("axios");
const supabase = require("../supabaseClient");

const AI_SERVICE_URL =
  process.env.AI_SERVICE_URL || "http://localhost:8000";

const LOCK_TTL_SECONDS = 60 * 60 * 24; // 24 hours
const checkIdempotency = async (req, res, next) => {
  const { txn_id, event_type, amount } = req.body;

  if (!txn_id || !event_type) {
    return res.status(400).json({
      error: "txn_id and event_type are required.",
    });
  }

  const key = `${txn_id}:${event_type}`;
  const now = Date.now();

  try {
    // ==========================================================
    // STEP 1: Check if this webhook was already seen
    // ==========================================================

    const firstSeenTime = await redis.get(key);

    if (firstSeenTime) {
      const timingDeltaMs = now - Number(firstSeenTime);

      console.log(
        `[IDEMPOTENCY] Duplicate detected for ${key} (${timingDeltaMs} ms)`
      );

      try {
        const { data } = await axios.post(
          `${AI_SERVICE_URL}/api/security-score`,
          {
            transaction_id: txn_id,
            event_type,
            amount_cents: amount,
            timing_delta_ms: timingDeltaMs,
          }
        );

        const { is_malicious, fraud_score, reason } = data;

        if (is_malicious === 1) {
          console.error(
            `[SECURITY_AI] Replay attack detected for ${txn_id} | Score: ${fraud_score}`
          );

          await supabase.from("anomalies").insert({
            transaction_id: txn_id,
            status: "MANUAL_REVIEW",
            anomaly_reason: "REPLAY_ATTACK_BLOCKED",
            explanation: `AI Firewall detected a suspected replay attack.
Fraud Score: ${(fraud_score * 100).toFixed(1)}%.
Reason: ${reason}`,
          });

          req.security = {
            replayAttack: true,
            fraud_score,
            reason,
          };

          console.log(
            `[SECURITY_AI] Continuing webhook processing despite replay detection.`
          );

          return next();
        }

        console.log(
          `[SECURITY_AI] Harmless retry detected for ${txn_id}. Continuing processing.`
        );

        req.security = {
          replayAttack: false,
        };

        return next();

      } catch (aiErr) {
        console.error(
          "[SECURITY_AI] Python AI unavailable:",
          aiErr.message
        );

        console.warn(
          "[SECURITY_AI] AI unavailable. Continuing webhook processing."
        );

        return next();
      }
    }

    // ==========================================================
    // STEP 3: Acquire Redis Lock
    // ==========================================================

    const lockAcquired = await redis.set(
      key,
      now.toString(),
      "EX",
      LOCK_TTL_SECONDS,
      "NX"
    );

    if (!lockAcquired) {
      return res.status(200).json({
        success: true,
        duplicate: true,
        message: "Duplicate request blocked.",
      });
    }

    // ==========================================================
    // STEP 4: Continue processing
    // ==========================================================

    next();

  } catch (err) {
    console.error("[IDEMPOTENCY]", err);

    return res.status(500).json({
      success: false,
      error: "Internal Server Error",
    });
  }
};

module.exports = {
  checkIdempotency,
};