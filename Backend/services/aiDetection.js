const axios = require('axios');

const detectPatternAnomaly = async (transactionData) => {
  try {
    const aiResponse = await axios.post('http://localhost:8000/api/score', {
      transaction_id: transactionData.txn_id,
      amount: transactionData.amount,
      events: transactionData.events,
      receiveTime: transactionData.receiveTime
    });

    const isAnomaly = aiResponse.data.is_anomaly === 1;
    
    console.log(`[PYTHON_AI_BRAIN] txn_id="${transactionData.txn_id}" | Result:`, aiResponse.data);

    return {
      isAnomaly: isAnomaly,
      reason: isAnomaly ? aiResponse.data.agent_reason : null,
      metrics: aiResponse.data.raw_metrics || {},
      baseline: aiResponse.data.baseline_score || {}
    };

  } catch (err) {
    console.error('[AI_DETECTION_ERROR] Failed to reach Python AI Microservice:', err.message);
    return { isAnomaly: false };
  }
};

module.exports = { detectPatternAnomaly };
