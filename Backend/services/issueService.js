const supabase = require("../supabaseClient");

async function createIssue({
    transaction_id,
    severity = "HIGH",
    issue = "Unknown Issue",
    explanation = "",
    resolved = false,
    metadata = {},
}) {
    const { data, error } = await supabase
        .from("issues")
        .insert([
            {
                transaction_id,
                severity,
                issue,
                explanation,
                resolved,
                metadata,
            },
        ])
        .select()
        .single();

    if (error) {
        throw new Error(`Failed to insert issue: ${error.message}`);
    }

    console.log(`[DB] Issue inserted: ${transaction_id} -> ${issue}`);

    return data;
}

module.exports = {
    createIssue,
};