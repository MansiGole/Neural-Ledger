const supabase = require("../supabaseClient");

async function calculateMetrics() {

    const [
        transactionResult,
        eventResult,
        failureResult,
        anomalyResult,
        resolvedResult,
    ] = await Promise.all([

        // Total Transactions
        supabase
            .from("transactions")
            .select("*", {
                count: "exact",
                head: true,
            }),

        // Total Events
        supabase
            .from("events")
            .select("*", {
                count: "exact",
                head: true,
            }),

        // Failure Events
        supabase
            .from("events")
            .select("*", {
                count: "exact",
                head: true,
            })
            .eq("event_type", "failure"),

        // Fetch ALL anomaly transaction IDs
        supabase
            .from("anomalies")
            .select("transaction_id")
            .neq("status", "CLEAN"),

        // Fetch ALL resolved transaction IDs
        supabase
            .from("anomalies")
            .select("transaction_id")
            .eq("status", "RESOLVED"),

    ]);

    if (transactionResult.error) throw transactionResult.error;
    if (eventResult.error) throw eventResult.error;
    if (failureResult.error) throw failureResult.error;
    if (anomalyResult.error) throw anomalyResult.error;
    if (resolvedResult.error) throw resolvedResult.error;

    const totalTransactions = transactionResult.count || 0;
    const totalEvents = eventResult.count || 0;
    const failureEvents = failureResult.count || 0;

    // Count UNIQUE transactions with anomalies
    const uniqueAnomalyTransactions = new Set(
        (anomalyResult.data || []).map(
            row => row.transaction_id
        )
    );

    const totalAnomalies = uniqueAnomalyTransactions.size;

    // Count UNIQUE resolved transactions
    const uniqueResolvedTransactions = new Set(
        (resolvedResult.data || []).map(
            row => row.transaction_id
        )
    );

    const resolved = uniqueResolvedTransactions.size;

    const failureRate =
        totalEvents === 0
            ? 0
            : Number(
                (
                    failureEvents / totalEvents
                ).toFixed(4)
            );

    const anomalyRate =
        totalTransactions === 0
            ? 0
            : Number(
                (
                    totalAnomalies / totalTransactions
                ).toFixed(4)
            );

    const healSuccessRate =
        totalAnomalies === 0
            ? 0
            : Number(
                (
                    resolved / totalAnomalies
                ).toFixed(4)
            );


    //console.log("========== METRICS DEBUG ==========");
    //console.log("Transactions:", totalTransactions);
    //console.log("Events:", totalEvents);
    //console.log("Failures:", failureEvents);
    //console.log("Unique Anomalies:", totalAnomalies);
    //console.log("Unique Resolved:", resolved);
    //console.log("Failure Rate:", failureRate);
    //console.log("Anomaly Rate:", anomalyRate);
    //console.log("Heal Success Rate:", healSuccessRate);
    //console.log("===================================");

    return {
        total_transactions: totalTransactions,
        total_events: totalEvents,
        failure_rate: failureRate,
        anomaly_rate: anomalyRate,
        heal_success_rate: healSuccessRate,
    };
}

module.exports = {
    calculateMetrics,
};