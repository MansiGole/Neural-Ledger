const { transactions, anomalies } = require('./mockData');

// This is the canonical correct order of events
const CORRECT_ORDER = ['CREATED', 'CAPTURED', 'SETTLED'];

// ── Helper: build a MANUAL_REVIEW response ──────────────────────────────────
function manualReviewResponse(id, anomalyType, originalEvents, reason) {
  return {
    transactionId: id,
    anomalyType,
    originalEvents,
    healedEvents: [],
    status: 'MANUAL_REVIEW',
    reason,
  };
}

// ── Main heal function ───────────────────────────────────────────────────────
function healTransaction(id) {

  // 1. Find the broken transaction in our anomaly list
  const brokenTransaction = anomalies.find((item) => item.transactionId === id);

  if (!brokenTransaction) {
    // ID not found at all → manual review
    return manualReviewResponse(id, null, [], 'Transaction ID not found in anomaly records');
  }

  const receivedEvents = brokenTransaction.receivedEvents;

  // 2. Empty events → can't do anything → manual review
  if (!Array.isArray(receivedEvents) || receivedEvents.length === 0) {
    return manualReviewResponse(
      brokenTransaction.transactionId,
      brokenTransaction.anomalyType,
      [],
      'No events received — cannot determine transaction state'
    );
  }

  // 3. Check for invalid event names (events not in our known set)
  //    If we find unknown events, we can't trust the payload at all
  const invalidEvents = receivedEvents.filter((e) => !CORRECT_ORDER.includes(e));
  if (invalidEvents.length > 0) {
    return manualReviewResponse(
      brokenTransaction.transactionId,
      brokenTransaction.anomalyType,
      receivedEvents,
      `Unknown event types found: ${invalidEvents.join(', ')} — cannot safely heal`
    );
  }

  // 4. Remove duplicates (handles DUPLICATE_EVENT anomaly)
  //    e.g. ['CREATED', 'CAPTURED', 'CAPTURED'] → ['CREATED', 'CAPTURED']
  const uniqueEvents = [];
  for (const event of receivedEvents) {
    if (!uniqueEvents.includes(event)) {
      uniqueEvents.push(event);
    }
  }

  // 5. Reorder according to canonical order (handles OUT_OF_ORDER anomaly)
  //    e.g. ['CAPTURED', 'CREATED'] → ['CREATED', 'CAPTURED']
  //    We only keep events that were actually received — we do NOT invent new ones
  const reorderedEvents = CORRECT_ORDER.filter((e) => uniqueEvents.includes(e));

  // 6. Check if reordering actually produced a usable sequence
  if (reorderedEvents.length === 0) {
    return manualReviewResponse(
      brokenTransaction.transactionId,
      brokenTransaction.anomalyType,
      receivedEvents,
      'No valid events remain after processing — transaction data too inconsistent'
    );
  }

  // ✅ 7. Healed successfully
  //    Note: healedEvents may be INCOMPLETE (e.g. only ['CREATED', 'CAPTURED'])
  //    That is intentional — we do NOT fabricate events that never happened.
  //    Person 2's state machine will flag it as still-in-progress, not fully settled.
  return {
    transactionId: brokenTransaction.transactionId,
    anomalyType: brokenTransaction.anomalyType,
    originalEvents: receivedEvents,
    healedEvents: reorderedEvents,
    status: 'RESOLVED',
    note: reorderedEvents.length < CORRECT_ORDER.length
      ? `Partial sequence recovered. Missing: ${CORRECT_ORDER.filter(e => !reorderedEvents.includes(e)).join(', ')}`
      : 'Full sequence recovered',
  };
}

module.exports = { healTransaction };