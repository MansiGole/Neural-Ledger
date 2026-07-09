const axios = require("axios");
const crypto = require("crypto");
require("dotenv").config();

const BASE_URL = "http://localhost:3000/webhook";

const EVENT_SEQUENCES = [
  ["created", "captured", "success"],
  ["created", "success"],
  ["captured", "created"],
  ["created", "created", "captured"],
  ["created", "captured", "failure"],
  ["created", "captured", "success", "refund"]
];

const delay = (ms) => new Promise((r) => setTimeout(r, ms));

function generateSignature(payload) {

  return crypto
    .createHmac("sha256", process.env.WEBHOOK_SECRET)
    .update(JSON.stringify(payload))
    .digest("hex");

}

async function sendWebhook(txnId, eventType, amount) {

  const payload = {
    txn_id: txnId,
    event_type: eventType,
    amount
  };

  const signature = generateSignature(payload);

  try {

    await axios.post(BASE_URL, payload, {

      headers: {

        "Content-Type": "application/json",

        "x-webhook-signature": signature

      }

    });

    console.log(`✅ ${txnId} -> ${eventType}`);

  } catch (err) {

    console.log("\n========================");
    console.log(`FAILED : ${txnId} -> ${eventType}`);

    if (err.response) {
      console.log("Status :", err.response.status);
      console.log("Body   :", err.response.data);
    } else {
      console.log("Message:", err.message);
    }

    console.log("========================\n");

  }

}

async function runSimulation() {

  console.log("\n==============================");
  console.log("Starting Webhook Simulation...");
  console.log("==============================\n");

  for (let i = 1; i <= 500; i++) {

    const txnId = `TXN${String(i).padStart(5, "0")}`;

    const amount = Math.floor(Math.random() * 9000) + 1000;

    const sequence =
      EVENT_SEQUENCES[
      Math.floor(Math.random() * EVENT_SEQUENCES.length)
      ];

    for (const event of sequence) {

      await sendWebhook(
        txnId,
        event,
        amount
      );

      await delay(100);

    }

  }

  console.log("\nSimulation Complete.\n");

}

runSimulation();