const transactions = [
  {
    transactionId: 'txn_101',
    events: ['CREATED', 'CAPTURED', 'SETTLED'],
  },
  {
    transactionId: 'txn_102',
    events: ['CREATED', 'CAPTURED', 'SETTLED'],
  },
  {
    transactionId: 'txn_103',
    events: ['CREATED', 'CAPTURED', 'SETTLED'],
  },
];

const anomalies = [
  {
    transactionId: 'txn_2001',
    receivedEvents: ['CAPTURED'],
    anomalyType: 'MISSING_CREATED',
  },
  {
    transactionId: 'txn_2002',
    receivedEvents: ['CAPTURED', 'CREATED'],
    anomalyType: 'OUT_OF_ORDER',
  },
  {
    transactionId: 'txn_2003',
    receivedEvents: ['CREATED', 'CAPTURED', 'CAPTURED'],
    anomalyType: 'DUPLICATE_EVENT',
  },
  {
    transactionId: 'txn_2004',
    receivedEvents: [],
    anomalyType: 'EMPTY_EVENTS',
  },
  {
    transactionId: 'txn_2005',
    receivedEvents: ['FAILED', 'UNKNOWN'],
    anomalyType: 'INVALID_EVENTS',
  },
];

module.exports = { transactions, anomalies };
