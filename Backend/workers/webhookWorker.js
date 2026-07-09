const { Worker } = require("bullmq");
const redis = require("../config/redis");

const worker = new Worker(
  "webhook-processing",

  async (job) => {
    console.log(
      `📦 Processing Webhook Job ${job.id} | ${job.data.txn_id}`
    );

    /*
      NEXT STEP

      Everything inside your current

      handleWebhook()

      will move here.

      We are NOT writing it yet.
    */

    return true;
  },

  {
    connection: redis,
  }
);

worker.on("completed", (job) => {
  console.log(`✅ Job ${job.id} Completed`);
});

worker.on("failed", (job, err) => {
  console.error(`❌ Job ${job.id} Failed`, err.message);
});

module.exports = worker;