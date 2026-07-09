const express = require('express');
const { transactions, anomalies } = require('./mockData');
const { healTransaction } = require('./healService');

const router = express.Router();

// Mock Gateway: fetch a known-good transaction
router.get('/mock-gateway/transaction/:id', (req, res) => {
  const transaction = transactions.find((item) => item.transactionId === req.params.id);

  if (!transaction) {
    return res.status(404).json({ message: 'Transaction not found in gateway' });
  }

  res.json(transaction);
});

// List all anomaly records
router.get('/anomalies', (req, res) => {
  res.json(anomalies);
});

// Heal a transaction (GET for browser testing)
router.get('/heal/:id', (req, res) => {
  const result = healTransaction(req.params.id);

  if (result.status === 'MANUAL_REVIEW' && !result.anomalyType) {
    return res.status(404).json(result);
  }

  res.json(result);
});

// Heal a transaction (POST for integration with Person 1/2)
router.post('/heal/:id', (req, res) => {
  const result = healTransaction(req.params.id);

  if (result.status === 'MANUAL_REVIEW' && !result.anomalyType) {
    return res.status(404).json(result);
  }

  res.json(result);
});

// Full pipeline simulation (GET so you can test in browser)
router.get('/process/:id', (req, res) => {
  const id = req.params.id;

  const isAnomaly = anomalies.find(a => a.transactionId === id);

  if (!isAnomaly) {
    const clean = transactions.find(t => t.transactionId === id);
    if (clean) {
      return res.json({
        transactionId: id,
        pipeline: 'PASSED_THROUGH',
        status: 'CLEAN',
        events: clean.events
      });
    }
    return res.status(404).json({ message: 'Transaction not found anywhere' });
  }

  const result = healTransaction(id);

  res.json({
    transactionId: id,
    pipeline: 'HEALED',
    anomalyDetected: isAnomaly.anomalyType,
    ...result
  });
});

module.exports = router;