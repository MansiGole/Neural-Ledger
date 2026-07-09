# 🚀 Neural Ledger
### AI-Powered Self-Healing Webhook Reconciliation Engine

> An intelligent middleware platform that securely processes payment webhooks, detects reconciliation anomalies using AI, autonomously repairs inconsistent transaction histories, and provides real-time operational insights.

![React](https://img.shields.io/badge/Frontend-React-61DAFB?logo=react)
![Node.js](https://img.shields.io/badge/Backend-Node.js-339933?logo=node.js)
![Express](https://img.shields.io/badge/Express.js-000000?logo=express)
![Supabase](https://img.shields.io/badge/Database-Supabase-3ECF8E?logo=supabase)
![Redis](https://img.shields.io/badge/Redis-DC382D?logo=redis)
![Python](https://img.shields.io/badge/AI-Python-3776AB?logo=python)
![License](https://img.shields.io/badge/License-MIT-blue)

---

## 🌐 Live Demo

**Frontend:** https://neural-ledger-git-main-mansigoles-projects.vercel.app/

---

# 📌 Overview

Modern payment gateways such as **Razorpay**, **Stripe**, and **Cashfree** communicate transaction updates using asynchronous webhooks.

In real-world distributed systems, webhook events may:

- Arrive out of order
- Be duplicated
- Be delayed
- Fail to arrive entirely

These inconsistencies often result in:

- Incorrect transaction states
- Ledger mismatches
- Manual reconciliation efforts
- Financial reporting issues
- Compliance risks

**Neural Ledger** introduces an intelligent reconciliation layer between the payment gateway and the merchant database to validate, analyze, repair, and monitor every webhook before it reaches the final ledger.

---

# 💡 Key Features

### 🔐 Secure Webhook Processing

- HMAC Signature Verification
- Payload Validation
- Event Authentication
- Request Integrity Checks

---

### 📥 Reliable Event Processing

- Redis-based Idempotency
- Duplicate Event Detection
- Ordered Event Storage
- BullMQ Queue Processing

---

### ⚙ Intelligent State Machine

Validates complete payment lifecycle:

```text
Created
   │
Captured
   │
Success
 ├────────► Refund
 └────────► Failure
```

Automatically detects:

- Missing Events
- Invalid State Transitions
- Duplicate Events
- Out-of-Order Webhooks

---

### 🤖 AI-Powered Anomaly Detection

The AI engine continuously analyzes transaction behavior using statistical anomaly detection.

Monitored signals include:

- Transaction Amount
- Event Delay
- Event Frequency
- Retry Behaviour
- Gateway Latency
- Transaction Flow

The model dynamically identifies abnormal webhook behaviour without relying solely on static thresholds.

---

### 🩹 Autonomous Ledger Healing

When inconsistencies are detected, Neural Ledger can:

- Query the payment gateway
- Reconstruct missing transaction events
- Repair incomplete event histories
- Synchronize the final ledger automatically

---

### 🛡 AI Replay Attack Detection

The middleware distinguishes between:

- Legitimate webhook retries
- Malicious replay attacks

using Redis-based timing analysis and AI-assisted fraud scoring.

---

### 🧠 AI Explainability

Generates human-readable explanations for detected anomalies including:

- Root Cause Analysis
- Incident Summary
- Manual Review Guidance
- Recovery Recommendation

---

### 📊 Real-Time Dashboard

Interactive dashboard providing:

- Live Webhook Monitoring
- Transaction Explorer
- Gateway Inspector
- Manual Review Queue
- Strategic Intervention Logs
- Compliance Report Export

---

# 🏗 System Architecture

```text
                   Payment Gateway
                          │
                    Incoming Webhooks
                          │
          ─────────────────────────────────

             🔐 Signature Verification

                          │

               📥 Webhook Ingestion

                          │

              🛡 Idempotency Check

                          │

               📚 Event Persistence

                          │

             ⚙ Transaction State Machine

                          │

          🤖 AI Anomaly Detection Engine

                          │

          🩹 Autonomous Ledger Healing

                          │

          🧠 AI Explainability Engine

                          │

          📊 Monitoring Dashboard

                          │

            📒 Reconciled Ledger
```

---

# 🛠 Tech Stack

## Frontend

- React
- Vite
- Tailwind CSS

## Backend

- Node.js
- Express.js

## Database

- Supabase (PostgreSQL)

## Queue & Cache

- Redis
- BullMQ

## AI & Machine Learning

- Python
- Scikit-learn
- Isolation Forest

## Security

- HMAC Signature Verification
- Replay Attack Detection
- Redis Idempotency

## Deployment

- Docker
- Vercel
- Render

---

# 📷 Screenshots

- Dashboard
-
<img width="1847" height="908" alt="image" src="https://github.com/user-attachments/assets/74823285-e9c3-48c6-9af8-2d535e91f4c2" />


- Compliance Report
-
  <img width="503" height="660" alt="image" src="https://github.com/user-attachments/assets/c463e629-9852-4867-b514-dbf507e9892d" />


---

# 🚀 Future Enhancements

- Multi-Gateway Support
- Kafka Event Streaming
- Predictive Risk Forecasting
- Graph-based Transaction Analysis
- Multi-Tenant Support
- Kubernetes Deployment

---

# 👨‍💻 Team

This project was developed during a hackathon by:

🌟 My Contribution — Mansi Gole

As the **Backend Developer**, I was responsible for designing and implementing the core reconciliation engine, including:
- Designing the backend architecture using **Node.js**, **Express.js**, and **Supabase**
- Developing the complete **Webhook Ingestion Pipeline**
- Implementing **HMAC Signature Verification** for secure webhook authentication
- Building **Redis-based Idempotency** to prevent duplicate webhook processing
- Designing the **Transaction State Machine** for lifecycle validation
- Integrating the **Python AI Anomaly Detection Engine**
- Implementing **AI-powered Replay Attack Detection**
- Developing the **Autonomous Ledger Healing** workflow
- Building the backend APIs powering the monitoring dashboard
- Implementing **Compliance Report (PDF) Generation**
- Integrating **Redis**, **BullMQ**, and **Docker** into the backend infrastructure
- Backend testing, debugging, and deployment
Special thanks to the team for collaborating on the frontend, integration, testing, and presentation throughout the hackathon.

---

# 📄 License

This project is licensed under the **MIT License**.

---

⭐ If you found this project interesting, consider giving it a star!
