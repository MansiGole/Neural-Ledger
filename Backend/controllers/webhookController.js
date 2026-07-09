// controllers/webhookController.js
// -----------------------------------------------------------------------------
// Webhook Reconciliation Controller
// -----------------------------------------------------------------------------
// Handles:
//
// POST /webhook
// GET  /transactions
// GET  /events/:txn_id
// GET  /issues
// GET  /metrics
// -----------------------------------------------------------------------------

const {
  insertEvent,
  upsertTransaction,
  getAllTransactions,
  getEventsByTxnId,
  getAllIssues,
  runStateMachine,
  saveAnomalyRecord,
  updateTransactionStatus,
} = require("../services/eventService");

const { calculateMetrics } = require("../services/metricsService");
const { detectPatternAnomaly } = require("../services/aiDetection");
const { healTransaction } = require("../services/autoHealService");
const { generateExplanation } = require("../utils/explanationGenerator");
const { createIssue } = require("../services/issueService");

const supabase = require("../supabaseClient");

const {
  emitWebhookReceived,
  emitAnomaly,
  emitHealingStarted,
  emitHealingCompleted,
  emitMetricsUpdate,
  emitPrediction,
} = require("../services/socketService");

// -----------------------------------------------------------------------------
// POST /webhook
// -----------------------------------------------------------------------------

const handleWebhook = async (req, res) => {
  const { txn_id, event_type, amount } = req.body;

  console.log(
    `[WEBHOOK] ${txn_id} | ${event_type} | ${amount ?? "N/A"}`
  );

  // ---------------------------------------------------------------------------
  // Live Dashboard
  // ---------------------------------------------------------------------------

  emitWebhookReceived({
    txn_id,
    event_type,
    timestamp: new Date().toISOString(),
  });

  try {
    // -------------------------------------------------------------------------
    // STEP 1
    // Store Raw Event
    // -------------------------------------------------------------------------

    await upsertTransaction({
      txn_id,
      event_type,
      amount,
    });

    console.log(`[DB] Transaction upserted: ${txn_id}`);

    // -------------------------------------------------------------------------
    // STEP 2
    // Upsert Transaction
    // -------------------------------------------------------------------------

    await insertEvent({
      txn_id,
      event_type,
      raw_payload: req.body,
    });

    console.log(`[DB] Event inserted: ${txn_id} -> ${event_type}`);

    // -------------------------------------------------------------------------
    // STEP 3
    // State Machine
    // -------------------------------------------------------------------------

    const smResult = await runStateMachine(txn_id);

    console.log(
      `[STATE MACHINE]`,
      smResult
    );

    // -------------------------------------------------------------------------
    // STEP 4
    // Load Transaction History
    // -------------------------------------------------------------------------

    const { data: txnEvents } = await supabase
      .from("events")
      .select("event_type, created_at")
      .eq("txn_id", txn_id)
      .order("created_at", {
        ascending: true,
      });

    // -------------------------------------------------------------------------
    // STEP 5
    // AI Detection
    // -------------------------------------------------------------------------

    const aiResult = await detectPatternAnomaly({
      txn_id,
      amount,
      events: txnEvents || [],
      receiveTime: new Date().toISOString(),
    });

    console.log("[AI]", aiResult);

    emitPrediction({
      txn_id,
      prediction: aiResult,
    });

    // -------------------------------------------------------------------------
    // STEP 6
    // Determine Status
    // -------------------------------------------------------------------------

    const isAnomaly =
      smResult.status === "ANOMALY" ||
      aiResult.isAnomaly;

    const anomalyType =
      smResult.anomalyType ||
      aiResult.reason ||
      null;

    let finalStatus =
      isAnomaly ? "ANOMALY" : "CLEAN";

    let explanation = null;

    let healResult = null;

    // -------------------------------------------------------------------------
    // STEP 7
    // Handle Anomaly
    // -------------------------------------------------------------------------

    if (isAnomaly) {

      explanation =
        await generateExplanation(
          anomalyType || "UNKNOWN",
          txn_id,
          txnEvents?.map(e => e.event_type) || []
        );

      emitAnomaly({
        txn_id,
        anomalyType,
        explanation,
      });

      try {

        emitHealingStarted({
          txn_id,
        });

        healResult =
          await healTransaction(txn_id);

        finalStatus = healResult.result;

        emitHealingCompleted({
          txn_id,
          result: healResult.result,
          reconstructed: healResult.reconstructed,
        });

      } catch (healError) {

        console.error(
          "[AUTO HEAL]",
          healError.message
        );

        finalStatus = "UNRESOLVABLE";

      }

      await updateTransactionStatus(
        txn_id,
        {
          reconciliation_status: finalStatus,
          anomaly_reason: anomalyType,
          explanation,
        }
      );

      // -----------------------------------------------------
      // Save Issue into issues table
      // -----------------------------------------------------
      try {

        await createIssue({
          transaction_id: txn_id,

          severity:
            anomalyType === "REPLAY_ATTACK"
              ? "CRITICAL"
              : anomalyType === "OUT_OF_ORDER"
                ? "MEDIUM"
                : "HIGH",

          issue: anomalyType,

          explanation,

          resolved: finalStatus === "RESOLVED",

          metadata: {
            stateMachine: smResult.details,
            aiDetection: aiResult,
            healResult,
          },
        });

        console.log(`[ISSUES] Saved issue for ${txn_id}`);

      } catch (err) {

        console.error("[ISSUES]", err.message);

      }

    } else {

      await updateTransactionStatus(
        txn_id,
        {
          reconciliation_status: "CLEAN",
        }
      );

    }

    // -------------------------------------------------------------------------
    // STEP 8
    // Save Anomaly Record
    // -------------------------------------------------------------------------

    await saveAnomalyRecord({

      transaction_id: txn_id,

      status: finalStatus,

      anomaly_reason: anomalyType,

      explanation,

      details: {

        stateMachine:
          smResult.details,

        aiDetection: {

          reason:
            aiResult.reason,

          metrics:
            aiResult.metrics,

        },

        healResult,

      },

    });

    // -------------------------------------------------------------------------
    // STEP 9
    // Dashboard Metrics
    // -------------------------------------------------------------------------

    emitMetricsUpdate({

      txn_id,

      event_type,

      status: finalStatus,

      anomaly: anomalyType,

    });

    // -------------------------------------------------------------------------
    // Response
    // -------------------------------------------------------------------------

    return res.status(200).json({

      success: true,

      message:
        "Webhook processed successfully.",

      txn_id,

      reconciliation_status:
        finalStatus,

      anomaly_type:
        anomalyType,

      explanation,

      heal_result:
        healResult?.result || null,

    });

  } catch (err) {

    console.error(
      "[WEBHOOK ERROR]",
      err
    );

    return res.status(500).json({

      success: false,

      error:
        "Webhook processing failed.",

    });

  }

};

// -----------------------------------------------------------------------------
// GET /transactions
// -----------------------------------------------------------------------------

const getTransactions = async (req, res) => {
  try {
    const transactions = await getAllTransactions();

    console.log(
      `[TRANSACTIONS] Returned ${transactions.length} records`
    );

    return res.status(200).json(transactions);

  } catch (err) {

    console.error(
      "[GET /transactions]",
      err.message
    );

    return res.status(500).json({
      success: false,
      error: "Failed to fetch transactions.",
    });

  }
};

// -----------------------------------------------------------------------------
// GET /events/:txn_id
// -----------------------------------------------------------------------------

const getEvents = async (req, res) => {

  const { txn_id } = req.params;

  try {

    const events =
      await getEventsByTxnId(txn_id);

    console.log(
      `[EVENTS] ${txn_id} -> ${events.length} events`
    );

    return res.status(200).json(events);

  } catch (err) {

    console.error(
      `[GET /events/${txn_id}]`,
      err.message
    );

    return res.status(500).json({
      success: false,
      error: "Failed to fetch transaction events.",
    });

  }

};

// -----------------------------------------------------------------------------
// GET /issues
// -----------------------------------------------------------------------------

const getIssues = async (req, res) => {

  try {

    const issues =
      await getAllIssues();

    console.log(
      `[ISSUES] ${issues.length} issue(s)`
    );

    return res.status(200).json(issues);

  } catch (err) {

    console.error(
      "[GET /issues]",
      err.message
    );

    return res.status(500).json({
      success: false,
      error: "Failed to fetch issues.",
    });

  }

};

// -----------------------------------------------------------------------------
// GET /metrics
// -----------------------------------------------------------------------------

const getMetrics = async (req, res) => {
  try {

    const metrics = await calculateMetrics();

    emitMetricsUpdate(metrics);

    return res.status(200).json(metrics);

  } catch (err) {

    console.error("[GET /metrics]", err);

    return res.status(500).json({
      success: false,
      error: "Failed to fetch metrics.",
    });

  }
};

// -----------------------------------------------------------------------------
// Exports
// -----------------------------------------------------------------------------

module.exports = {
  handleWebhook,
  getTransactions,
  getEvents,
  getIssues,
  getMetrics,

};