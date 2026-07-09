// services/autoHealService.js
// Auto-Healing module for the Webhook Reconciliation Engine.
//
// When an anomaly is detected, this service:
//  1. Fetches the "correct" transaction history from the mock gateway.
//  2. Compares it against what's already in the DB.
//  3. Reconstructs any missing events.
//  4. Updates the transaction reconciliation_status to RESOLVED or UNRESOLVABLE.

const http  = require('http');
const { insertEvent } = require('./eventService');
const supabase = require('../supabaseClient');

// ─── Config ───────────────────────────────────────────────────────────────────

const GATEWAY_HOST = 'localhost';
const GATEWAY_PORT = process.env.PORT || 3000;

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Fetches the canonical transaction history from the mock gateway.
 * Uses Node's built-in http module to avoid circular require issues with express.
 *
 * @param {string} txn_id
 * @returns {Promise<Array>} canonical event list
 */
const fetchFromMockGateway = (txn_id) => {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: GATEWAY_HOST,
      port:     GATEWAY_PORT,
      path:     `/mock-gateway/${encodeURIComponent(txn_id)}`,
      method:   'GET',
    };

    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', (chunk) => (body += chunk));
      res.on('end', () => {
        try {
          const parsed = JSON.parse(body);
          resolve(parsed.events || []);
        } catch (e) {
          reject(new Error(`Failed to parse mock gateway response: ${e.message}`));
        }
      });
    });

    req.on('error', (err) => reject(new Error(`Mock gateway request failed: ${err.message}`)));
    req.setTimeout(5000, () => {
      req.destroy();
      reject(new Error('Mock gateway request timed out.'));
    });
    req.end();
  });
};

/**
 * Fetches all existing events for a transaction from Supabase.
 * @param {string} txn_id
 * @returns {Promise<Array>}
 */
const fetchExistingEvents = async (txn_id) => {
  const { data, error } = await supabase
    .from('events')
    .select('event_type, created_at')
    .eq('txn_id', txn_id)
    .order('created_at', { ascending: true });

  if (error) throw new Error(`Failed to fetch events for healing: ${error.message}`);
  return data || [];
};

/**
 * Updates the reconciliation_status (and optionally healed_at) on the transactions table.
 * @param {string} txn_id
 * @param {string} status - 'RESOLVED' | 'UNRESOLVABLE'
 */
const updateHealStatus = async (txn_id, status) => {
  const update = {
    reconciliation_status: status,
    updated_at: new Date().toISOString(),
  };
  if (status === 'RESOLVED') {
    update.healed_at = new Date().toISOString();
  }

  const { error } = await supabase
    .from('transactions')
    .update(update)
    .eq('id', txn_id);

  if (error) throw new Error(`Failed to update heal status: ${error.message}`);
};

// ─── Main Export ─────────────────────────────────────────────────────────────

/**
 * Attempts to heal a transaction by fetching canonical event history from the
 * mock gateway and reconstructing any missing events in the DB.
 *
 * @param {string} txn_id - The transaction ID to heal.
 * @returns {Promise<{ result: 'RESOLVED'|'UNRESOLVABLE', reconstructed: string[], reason?: string }>}
 */
const healTransaction = async (txn_id) => {
  console.log(`[AUTO_HEAL] Starting heal attempt for txn_id="${txn_id}"`);

  let canonicalEvents;
  try {
    canonicalEvents = await fetchFromMockGateway(txn_id);
  } catch (err) {
    console.error(`[AUTO_HEAL] Could not reach mock gateway: ${err.message}`);
    await updateHealStatus(txn_id, 'UNRESOLVABLE');
    return { result: 'UNRESOLVABLE', reconstructed: [], reason: err.message };
  }

  if (!canonicalEvents || canonicalEvents.length === 0) {
    console.warn(`[AUTO_HEAL] No canonical events returned for txn_id="${txn_id}". Marking UNRESOLVABLE.`);
    await updateHealStatus(txn_id, 'UNRESOLVABLE');
    return { result: 'UNRESOLVABLE', reconstructed: [], reason: 'Mock gateway returned empty event list.' };
  }

  // Compare with existing DB events
  const existingEvents = await fetchExistingEvents(txn_id);
  const existingTypes  = new Set(existingEvents.map((e) => e.event_type));
  const missingEventTypes = canonicalEvents
    .map((e) => e.event_type)
    .filter((et) => !existingTypes.has(et));

  if (missingEventTypes.length === 0) {
    console.log(`[AUTO_HEAL] No missing events for txn_id="${txn_id}". Marking RESOLVED.`);
    await updateHealStatus(txn_id, 'RESOLVED');
    return { result: 'RESOLVED', reconstructed: [] };
  }

  // Reconstruct missing events
  const reconstructed = [];
  for (const eventType of missingEventTypes) {
    try {
      await insertEvent({
        txn_id,
        event_type: eventType,
        raw_payload: {
          _source:    'auto_heal',
          event_type: eventType,
          txn_id,
          _note:      'Reconstructed by auto-heal service from mock gateway data',
        },
      });
      reconstructed.push(eventType);
      console.log(`[AUTO_HEAL] Reconstructed missing event "${eventType}" for txn_id="${txn_id}"`);
    } catch (insertErr) {
      console.error(`[AUTO_HEAL] Failed to insert "${eventType}" for txn_id="${txn_id}":`, insertErr.message);
    }
  }

  // Mark RESOLVED if we successfully reconstructed all missing events
  const healResult = reconstructed.length === missingEventTypes.length ? 'RESOLVED' : 'UNRESOLVABLE';
  await updateHealStatus(txn_id, healResult);

  console.log(`[AUTO_HEAL] Heal complete for txn_id="${txn_id}" — result: ${healResult}, reconstructed: [${reconstructed.join(', ')}]`);
  return { result: healResult, reconstructed };
};

module.exports = { healTransaction };
