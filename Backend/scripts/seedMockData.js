// scripts/seedMockData.js
require('dotenv').config();
const { createClient } = require('@supabase/supabase-js');
const crypto = require('crypto');

const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_KEY);

// AES-256-GCM Encryption Setup
// If no encryption key is set, we use a 32-byte hash of the webhook secret for testing
const ENCRYPTION_KEY = crypto.createHash('sha256').update(process.env.WEBHOOK_SECRET || 'fallback-super-secret-key-12345').digest();

function encryptPayload(payloadObj) {
  const text = JSON.stringify(payloadObj);
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', ENCRYPTION_KEY, iv);
  
  let encrypted = cipher.update(text, 'utf8', 'hex');
  encrypted += cipher.final('hex');
  const authTag = cipher.getAuthTag().toString('hex');
  
  return {
    iv: iv.toString('hex'),
    encryptedData: encrypted,
    authTag: authTag
  };
}

async function seed() {
  console.log(`[SEED] Initializing Mock Dataset Seeding...`);
  
  const events = [];
  const transactions = [];
  const anomalies = [];
  const replayEvents = [];

  let txnCounter = 1000;
  function getTxnId() { return `txn_mock_${txnCounter++}`; }

  function pushEvent(txn_id, type, delayMs = 0) {
    const ts = new Date(Date.now() - 10000000 + delayMs).toISOString(); // spread out over past hours
    const payload = { txn_id, event_type: type, amount: 5000, timestamp: ts };
    events.push({
      txn_id,
      event_type: type,
      raw_payload: encryptPayload(payload),
      created_at: ts
    });
  }

  // 1. 40 Clean Transactions: created → captured → success
  for (let i = 0; i < 40; i++) {
    const tx = getTxnId();
    pushEvent(tx, 'created', 0);
    pushEvent(tx, 'captured', 500);
    pushEvent(tx, 'success', 1000);
    transactions.push({ txn_id: tx, latest_event: 'success', reconciliation_status: 'CLEAN' });
  }

  // 2. 10 Missing-event: captured → success (no created)
  for (let i = 0; i < 10; i++) {
    const tx = getTxnId();
    pushEvent(tx, 'captured', 500);
    pushEvent(tx, 'success', 1000);
    transactions.push({ txn_id: tx, latest_event: 'success', reconciliation_status: 'ANOMALY' });
    anomalies.push({ transaction_id: tx, status: 'AUTO_HEALED', anomaly_reason: 'MISSING_CREATED', explanation: 'AI injected missing CREATED event natively.' });
  }

  // 3. 10 Out-of-order: success before captured
  for (let i = 0; i < 10; i++) {
    const tx = getTxnId();
    pushEvent(tx, 'created', 0);
    pushEvent(tx, 'success', 500); // Early
    pushEvent(tx, 'captured', 1000);
    transactions.push({ txn_id: tx, latest_event: 'success', reconciliation_status: 'ANOMALY' });
    anomalies.push({ transaction_id: tx, status: 'AUTO_HEALED', anomaly_reason: 'OUT_OF_ORDER', explanation: 'Advanced timeline vector realignment successful.' });
  }

  // 4. 10 Duplicate retries (harmless)
  for (let i = 0; i < 10; i++) {
    const tx = getTxnId();
    pushEvent(tx, 'created', 0);
    pushEvent(tx, 'captured', 500);
    pushEvent(tx, 'captured', 505); // Duplicate! Only 5ms exactly (harmless)
    pushEvent(tx, 'success', 1000);
    transactions.push({ txn_id: tx, latest_event: 'success', reconciliation_status: 'CLEAN' });
  }

  // 5. 10 Refund transactions
  for (let i = 0; i < 10; i++) {
    const tx = getTxnId();
    pushEvent(tx, 'created', 0);
    pushEvent(tx, 'captured', 500);
    pushEvent(tx, 'success', 1000);
    pushEvent(tx, 'refund', 5000);
    transactions.push({ txn_id: tx, latest_event: 'refund', reconciliation_status: 'CLEAN' });
  }

  // 6. 5 Failure transactions
  for (let i = 0; i < 5; i++) {
    const tx = getTxnId();
    pushEvent(tx, 'created', 0);
    pushEvent(tx, 'captured', 500);
    pushEvent(tx, 'failure', 1000);
    transactions.push({ txn_id: tx, latest_event: 'failure', reconciliation_status: 'CLEAN' });
  }

  // 7. 5 Suspicious Replays (fraud blocked)
  for (let i = 0; i < 5; i++) {
    const tx = getTxnId();
    pushEvent(tx, 'created', 0);
    pushEvent(tx, 'captured', 500);
    pushEvent(tx, 'success', 1000);
    // Huge delay (1 million ms) implies malicious replay
    replayEvents.push({
      transaction_id: tx,
      event_type: 'success',
      fraud_probability: 0.98 + (Math.random() * 0.01),
      is_blocked: true,
      timing_delta_ms: 1000000
    });
    transactions.push({ txn_id: tx, latest_event: 'success', reconciliation_status: 'ANOMALY' });
    anomalies.push({ transaction_id: tx, status: 'MANUAL_REVIEW', anomaly_reason: 'REPLAY_ATTACK_BLOCKED', explanation: 'AI Firewall Intercepted Malicious Duplicate. Fraud Probability: 98.7%.' });
  }

  // --- Insertion Push ---
  console.log(`[SEED] Attempting to insert mock records via REST...`);
  try {
    if (events.length) await supabase.from('events').insert(events);
    if (transactions.length) await supabase.from('transactions').upsert(transactions, { onConflict: 'txn_id' });
    if (anomalies.length) await supabase.from('anomalies').insert(anomalies);
    // Try to insert replay events. If migration hasn't been run, this might fail, hence the try/catch wrapper
    if (replayEvents.length) await supabase.from('replay_events').insert(replayEvents);
    
    console.log(`[SEED] Success! Uploaded: \n- ${events.length} Events\n- ${transactions.length} Transactions\n- ${anomalies.length} Anomalies\n- ${replayEvents.length} Replay Blocks`);
  } catch (err) {
    console.error(`[SEED] Error inserting data:`, err.message);
  }
}

seed();
