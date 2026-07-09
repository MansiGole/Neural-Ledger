// routes/webhook.js
// Defines all API routes and applies relevant middleware.

const supabase = require("../supabaseClient");
const { generateComplianceReport } = require("../utils/reportGenerator");
const express = require("express");
const router = express.Router();

const { verifySignature } = require("../middleware/signatureVerification");
const { validatePayload } = require("../middleware/validation");
const { checkIdempotency } = require("../middleware/idempotency");
const { dynamicRateLimiter } = require("../middleware/rateLimit");
const { calculateMetrics } = require("../services/metricsService");

const {
  handleWebhook,
  getTransactions,
  getEvents,
  getIssues,
  getMetrics,
} = require("../controllers/webhookController");

// -----------------------------------------------------------------------------
// WEBHOOK INGESTION
// -----------------------------------------------------------------------------
// Middleware execution order:
//
// 1. Rate Limiter
// 2. HMAC Signature Verification
// 3. Payload Validation
// 4. Redis Idempotency + AI Replay Detection
// 5. Webhook Processing
// -----------------------------------------------------------------------------

router.post(
  "/webhook",
  dynamicRateLimiter,
  verifySignature,
  validatePayload,
  checkIdempotency,
  handleWebhook
);

// -----------------------------------------------------------------------------
// DASHBOARD APIs
// -----------------------------------------------------------------------------

router.get("/transactions", getTransactions);

router.get("/events/:txn_id", getEvents);

router.get("/issues", getIssues);

router.get("/metrics", getMetrics);


// -----------------------------------------------------------------------------
// EXPORT COMPLIANCE REPORT
// -----------------------------------------------------------------------------

router.get("/export-report", async (req, res) => {
  // console.log("🔥 EXPORT ROUTE HIT");
  try {
    //const { data: metrics } = await supabase.rpc("get_dashboard_metrics");
    const metrics = await calculateMetrics();
    // console.log("========== METRICS ==========");
    // console.dir(metrics, { depth: null });
    // console.log("=============================");

    const { data: issues } = await supabase
      .from("issues")
      .select("*")
      .order("created_at", { ascending: false });

    generateComplianceReport(
      res,
      metrics || {},
      issues || []
    );
  } catch (err) {
    console.error(err);

    res.status(500).json({
      error: "Unable to generate report",
    });
  }
});


// -----------------------------------------------------------------------------
// MOCK PAYMENT GATEWAY
// Used by Auto-Heal Engine to reconstruct missing events
// -----------------------------------------------------------------------------

router.get("/mock-gateway/:transaction_id", (req, res) => {
  const { transaction_id } = req.params;

  const canonicalEvents = [
    {
      event_type: "created",
      txn_id: transaction_id,
      simulated: true,
    },
    {
      event_type: "captured",
      txn_id: transaction_id,
      simulated: true,
    },
    {
      event_type: "success",
      txn_id: transaction_id,
      simulated: true,
    },
  ];

  console.log(
    `[MOCK_GATEWAY] Returning canonical event history for ${transaction_id}`
  );

  return res.status(200).json({
    transaction_id,
    source: "mock-gateway",
    events: canonicalEvents,
    note: "Simulated canonical transaction history for autonomous healing.",
  });
});

module.exports = router;