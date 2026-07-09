// utils/explanationGenerator.js
const { GoogleGenerativeAI } = require("@google/generative-ai");

/**
 * Connects to the Gemini API to write a highly specific, unique explanation 
 * for the dashboard. Falls back to static rules if API key is missing.
 */
const generateExplanation = async (anomalyType, transactionId, rawEvents) => {
  const fallbackExplanations = {
    OUT_OF_ORDER: 'An event was received out of the expected transaction lifecycle order. This may indicate a webhook drop, replay attack, or upstream system reordering.',
    MISSING_EVENT: 'One or more expected events are absent from the transaction sequence. The webhook may have been lost in transit, timed out, or silently dropped by the gateway.',
    HIGH_FAILURE_RATE: 'The failure rate for this transaction significantly exceeds the recent system baseline. This could indicate a payment processor issue, network instability, or a misconfigured merchant account.',
    HIGH_REFUND_RATE: 'The refund rate is abnormally high compared to baseline levels. This may signal a fraud pattern, unusual dispute activity, or a product/service quality issue.',
    HIGH_DUPLICATE_RATE: 'An unusually high number of duplicate events were detected beyond the normal retry rate. This could be a retry storm, misconfigured webhook endpoint, or a bug in the sending system.',
    SLOW_EVENT_DELAY: 'Events are arriving significantly slower than the baseline average. This may indicate network degradation, queue backlogs, or processing bottlenecks upstream.',
    UNKNOWN: 'An unclassified anomaly was detected in this transaction. Manual review is recommended to determine the root cause.'
  };

  const fallbackText = fallbackExplanations[anomalyType] || fallbackExplanations['UNKNOWN'];

  if (!process.env.GEMINI_API_KEY) {
    return fallbackText;
  }

  try {
    const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
    const model = genAI.getGenerativeModel({ model: "gemini-1.5-flash" });
    
    const prompt = `You are a strict, professional Fintech System Monitor Agent auditing a Webhook Reconciliation Ledger.
Transaction ID: ${transactionId}
Anomaly Detected: ${anomalyType}
Captured Events So Far: ${JSON.stringify(rawEvents)}

Write a concise, 2-sentence institutional-grade brief explaining why this transaction is statistically problematic and what a human auditor should inspect. 
Return ONLY the text itself (no conversational filler, no quotation marks).`;

    const result = await model.generateContent(prompt);
    return result.response.text().trim();
  } catch (err) {
    console.error("[LLM ERROR] Falling back to algorithmic expert system:", err.message);
    return fallbackText;
  }
};

module.exports = { generateExplanation };
