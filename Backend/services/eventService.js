// services/eventService.js
// Contains all database interaction logic.
// Keeps controller thin by isolating Supabase queries here.

const supabase = require('../supabaseClient');

/**
 * Inserts a new event record into the "events" table.
 * @param {object} event - { txn_id, event_type, raw_payload }
 * @returns {object} inserted data or throws error
 */
const insertEvent = async ({ txn_id, event_type, raw_payload }) => {
  const { data, error } = await supabase
    .from('events')
    .insert([
      {
        txn_id,
        event_type,
        raw_payload,
        created_at: new Date().toISOString(),
      },
    ])
    .select();

  if (error) {
    throw new Error(`Failed to insert event: ${error.message}`);
  }

  return data;
};

/**
 * Upserts a transaction record.
 * If the transaction already exists, updates its status and optionally amount.
 * Uses "id" (txn_id) as the unique conflict key.
 * @param {object} txn - { txn_id, event_type, amount }
 */
const upsertTransaction = async ({ txn_id, event_type, amount }) => {
  const record = {
    id: txn_id,
    status: event_type,
    created_at: new Date().toISOString(),
  };

  // Only include amount if it was provided in the payload
  if (amount !== undefined && amount !== null) {
    record.amount = amount;
  }

  const { data, error } = await supabase
    .from('transactions')
    .upsert([record], { onConflict: 'id' })
    .select();

  if (error) {
    throw new Error(`Failed to upsert transaction: ${error.message}`);
  }

  return data;
};

/**
 * Fetches all transactions, ordered by most recent first.
 */
const getAllTransactions = async () => {
  const { data, error } = await supabase
    .from('transactions')
    .select('*')
    .order('created_at', { ascending: false });

  if (error) {
    throw new Error(`Failed to fetch transactions: ${error.message}`);
  }

  return data;
};

/**
 * Fetches all events for a given transaction ID, ordered by most recent first.
 * @param {string} txn_id
 */
const getEventsByTxnId = async (txn_id) => {
  const { data, error } = await supabase
    .from('events')
    .select('*')
    .eq('txn_id', txn_id)
    .order('created_at', { ascending: false });

  if (error) {
    throw new Error(`Failed to fetch events for txn_id=${txn_id}: ${error.message}`);
  }

  return data;
};

/**
 * Fetches all issues from the "issues" table.
 */
const getAllIssues = async () => {
  const { data, error } = await supabase
    .from('issues')
    .select('*')
    .order('created_at', { ascending: false });

  if (error) {
    throw new Error(`Failed to fetch issues: ${error.message}`);
  }

  return data;
};

// ─── State Machine ────────────────────────────────────────────────────────────

/**
 * Defines the expected linear lifecycle for a payment transaction.
 * Each step is a required waypoint before the next.
 *
 * Terminal states (success, failure, refund) close the lifecycle.
 */
const STATE_MACHINE = {
  lifecycle: ['created', 'captured'],
  terminals: ['success', 'failure', 'refund'],
};

/**
 * Runs state machine analysis on all events for a given transaction.
 * Detects:
 *  - Missing events: a required step was skipped
 *  - Out-of-order events: events arrived in wrong chronological order
 *
 * @param {string} txn_id
 * @returns {object} { status: 'CLEAN'|'ANOMALY', anomalyType: string|null, details: object }
 */
const runStateMachine = async (txn_id) => {
  // Fetch events ordered by DB insertion time (creation order)
  const { data: events, error } = await supabase
    .from('events')
    .select('event_type, created_at')
    .eq('txn_id', txn_id)
    .order('created_at', { ascending: true });

  if (error) {
    throw new Error(`State machine failed to fetch events for txn_id=${txn_id}: ${error.message}`);
  }

  if (!events || events.length === 0) {
    return { status: 'CLEAN', anomalyType: null, details: { message: 'No events found.' } };
  }

  const receivedTypes = events.map((e) => e.event_type);

  // ── 1. Check for out-of-order events ─────────────────────────────────────
  // The full expected order is: lifecycle steps + exactly one terminal
  const fullOrder = [...STATE_MACHINE.lifecycle, ...STATE_MACHINE.terminals];
  let lastIndex = -1;
  for (const eventType of receivedTypes) {
    const idx = fullOrder.indexOf(eventType);
    if (idx === -1) continue; // Unknown event type — skip
    if (idx < lastIndex) {
      return {
        status: 'ANOMALY',
        anomalyType: 'OUT_OF_ORDER',
        details: {
          message:        `Event "${eventType}" arrived out of expected order.`,
          receivedOrder:  receivedTypes,
          expectedOrder:  fullOrder,
        },
      };
    }
    lastIndex = idx;
  }

  // ── 2. Check for missing lifecycle events ─────────────────────────────────
  // If a terminal state exists, all lifecycle steps before it should be present
  const hasTerminal = receivedTypes.some((t) => STATE_MACHINE.terminals.includes(t));
  if (hasTerminal) {
    const missingSteps = STATE_MACHINE.lifecycle.filter((step) => !receivedTypes.includes(step));
    if (missingSteps.length > 0) {
      return {
        status: 'ANOMALY',
        anomalyType: 'MISSING_EVENT',
        details: {
          message:       `Expected lifecycle event(s) missing before terminal state.`,
          missingEvents: missingSteps,
          receivedOrder: receivedTypes,
        },
      };
    }
  }

  return {
    status: 'CLEAN',
    anomalyType: null,
    details: { message: 'Transaction lifecycle is healthy.', receivedOrder: receivedTypes },
  };
};

// ─── Additional DB Helpers ────────────────────────────────────────────────────

/**
 * Saves an anomaly detection record to the anomalies table.
 * @param {object} anomalyData - { transaction_id, status, anomaly_reason, explanation, details }
 * @returns {object} inserted record
 */
const saveAnomalyRecord = async ({ transaction_id, status, anomaly_reason, explanation, details }) => {
  const { data, error } = await supabase
    .from('anomalies')
    .insert([
      {
        transaction_id,
        status,
        anomaly_reason: anomaly_reason || null,
        explanation:    explanation    || null,
        details:        details        || null,
        created_at:     new Date().toISOString(),
      },
    ])
    .select();

  if (error) {
    throw new Error(`Failed to save anomaly record: ${error.message}`);
  }
  return data;
};

/**
 * Updates reconciliation-related fields on a transaction record.
 * @param {string} txn_id
 * @param {object} fields - Partial fields to update (reconciliation_status, anomaly_reason, explanation, healed_at, etc.)
 */
const updateTransactionStatus = async (txn_id, fields) => {
  const { error } = await supabase
    .from('transactions')
    .update({ ...fields, updated_at: new Date().toISOString() })
    .eq('id', txn_id);

  if (error) {
    throw new Error(`Failed to update transaction status for ${txn_id}: ${error.message}`);
  }
};

/**
 * Fetches the most recent N events from the DB (used by AI detection for baseline).
 * @param {number} limit
 * @returns {Array}
 */
const getRecentEvents = async (limit = 100) => {
  const { data, error } = await supabase
    .from('events')
    .select('event_type, txn_id, created_at')
    .order('created_at', { ascending: false })
    .limit(limit);

  if (error) {
    throw new Error(`Failed to fetch recent events: ${error.message}`);
  }
  return data || [];
};

module.exports = {
  insertEvent,
  upsertTransaction,
  getAllTransactions,
  getEventsByTxnId,
  getAllIssues,
  // State machine
  runStateMachine,
  STATE_MACHINE,
  // DB helpers
  saveAnomalyRecord,
  updateTransactionStatus,
  getRecentEvents,
};
