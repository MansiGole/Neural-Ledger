const PDFDocument = require("pdfkit");

function generateComplianceReport(res, metrics, issues) {
    const doc = new PDFDocument({
        margin: 50,
    });

    res.setHeader("Content-Type", "application/pdf");
    res.setHeader(
        "Content-Disposition",
        'attachment; filename="Compliance_Report.pdf"'
    );

    doc.pipe(res);

    doc
        .fontSize(24)
        .text("Neural Ledger Compliance Report", {
            align: "center",
        });

    doc.moveDown();

    doc.fontSize(16).text("System Metrics");

    doc.moveDown(0.5);

    doc.fontSize(12);

    doc.text(`Total Transactions : ${metrics.total_transactions}`);
    doc.text(`Total Events       : ${metrics.total_events}`);
    doc.text(`Failure Rate       : ${(
        metrics.failure_rate * 100
    ).toFixed(2)} %`);
    doc.text(`Anomaly Rate       : ${(
        metrics.anomaly_rate * 100
    ).toFixed(2)} %`);

    //doc.text(`Heal Success Rate  : ${(
    //   metrics.heal_success_rate * 100
    //).toFixed(2)} %`);

    doc.moveDown();

    doc.fontSize(16).text("Recent Issues");

    doc.moveDown();

    issues.slice(0, 10).forEach((issue, index) => {
        doc.fontSize(12).text(`${index + 1}. ${issue.transaction_id}`);

        doc.text(`Issue      : ${issue.issue}`);
        doc.text(`Severity   : ${issue.severity}`);
        doc.text(`Resolved   : ${issue.resolved}`);
        doc.text(`Explanation: ${issue.explanation}`);

        doc.moveDown();
    });

    doc.end();
}

module.exports = {
    generateComplianceReport,
};