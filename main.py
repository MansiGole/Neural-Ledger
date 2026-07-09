import asyncio
import json
import logging
import math
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

import database
import mock_gateway
from ml_model import AnomalyDetector, STATUS_ORDINAL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

detector = AnomalyDetector()

EXPECTED_SEQUENCE = ["initiated", "processing", "completed", "failed"]
TERMINAL_STATUSES = {"completed", "failed"}


class WebhookPayload(BaseModel):
    transaction_id: str
    status: str
    timestamp: str
    amount_cents: int | None = None
    metadata: dict | None = None

# ── /api/score ── request model (sent by Express aiDetection.js) ──────────────
class ScoreRequest(BaseModel):
    transaction_id: str
    amount: float | None = None          # dollar amount (e.g. 99.99)
    events: list[dict[str, Any]] | None = None  # [{event_type, created_at}]
    receiveTime: str | None = None


# ── /api/security-score ── request model (sent by Express idempotency.js) ─────
class SecurityScoreRequest(BaseModel):
    transaction_id: str
    event_type: str
    amount_cents: float | None = None    # raw amount from webhook body
    timing_delta_ms: int                 # ms between first & duplicate arrival


async def auto_heal_loop(interval_seconds: int = 30) -> None:
    while True:
        try:
            transactions = database.get_all_transactions()
            for tid, events in transactions.items():
                observed = {e["status"] for e in events}
                terminal = observed & TERMINAL_STATUSES
                if terminal:
                    terminal_status = next(iter(terminal))
                    terminal_idx = EXPECTED_SEQUENCE.index(terminal_status)
                    expected = set(EXPECTED_SEQUENCE[: terminal_idx + 1])
                else:
                    expected = set(EXPECTED_SEQUENCE[:2])  # at least initiated+processing

                missing = expected - observed
                for ms in missing:
                    try:
                        result = mock_gateway.fetch_missing_event(tid, ms)
                        healed_at = datetime.now(timezone.utc).isoformat()
                        idempotency_key = f"{tid}:{ms}"
                        database.insert_healed_event({
                            "idempotency_key": idempotency_key,
                            "transaction_id": tid,
                            "status": ms,
                            "timestamp": result["timestamp"],
                            "payload": result["payload"],
                            "received_at": healed_at,
                            "anomaly_score": None,
                            "is_anomaly": 0,
                            "is_healed": 1,
                            "healed_at": healed_at,
                        })
                    except Exception as exc:
                        logger.error("Auto-healer failed for %s/%s: %s", tid, ms, exc)

                # Detect out-of-order events
                sorted_by_ts = sorted(events, key=lambda e: e["timestamp"])
                sorted_by_recv = sorted(events, key=lambda e: e["received_at"])
                if [e["id"] for e in sorted_by_ts] != [e["id"] for e in sorted_by_recv]:
                    logger.info("Out-of-order events detected for transaction %s", tid)

        except Exception as exc:
            logger.error("Auto-heal cycle error: %s", exc)

        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    detector.train()
    task = asyncio.create_task(auto_heal_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(lifespan=lifespan)

# Allow the Express backend (localhost:3000) and the Vite frontend (localhost:5173)
# to reach this service without CORS blocks.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/webhook")
async def ingest_webhook(payload: WebhookPayload):
    idempotency_key = f"{payload.transaction_id}:{payload.status}"

    if database.event_exists(idempotency_key):
        return JSONResponse(status_code=200, content={"status": "duplicate"})

    anomaly_score, is_anomaly = detector.score(payload.model_dump())
    received_at = datetime.now(timezone.utc).isoformat()

    event = {
        "idempotency_key": idempotency_key,
        "transaction_id": payload.transaction_id,
        "status": payload.status,
        "timestamp": payload.timestamp,
        "payload": json.dumps(payload.model_dump()),
        "received_at": received_at,
        "anomaly_score": anomaly_score,
        "is_anomaly": int(is_anomaly),
        "is_healed": 0,
        "healed_at": None,
    }

    try:
        database.insert_event(event)
    except IntegrityError:
        return JSONResponse(status_code=200, content={"status": "duplicate"})

    return JSONResponse(status_code=200, content={"status": "ok"})


# ─────────────────────────────────────────────────────────────────────────────
# Bridge endpoints — consumed exclusively by the Express/Node.js backend.
# These were previously missing, causing silent AI failures on every webhook.
# ─────────────────────────────────────────────────────────────────────────────

# Node.js event vocabulary → Python STATUS_ORDINAL mapping.
# The two services use different status names for the same lifecycle stages.
_NODE_TO_PY_STATUS: dict[str, str] = {
    "created": "initiated",
    "captured": "processing",
    "success": "completed",
    "failure": "failed",
    "refund": "failed",   # treated as terminal; ordinal same as failed
}

# Anomaly type labels that map to each detection trigger.
_REASON_TEMPLATES: dict[str, str] = {
    "high_amount": "Transaction amount is {amount_cents} cents, far exceeding the normal range (100–10 000 cents). Possible large-value fraud or erroneous charge.",
    "high_delay":  "Event ingestion delay of {delay_seconds:.1f}s is abnormally high. Possible stale replay, queue backlog, or upstream latency spike.",
    "combined":    "Both transaction amount ({amount_cents} cents) and event delay ({delay_seconds:.1f}s) are statistical outliers. Manual verification recommended.",
    "pattern":     "IsolationForest detected a low-density region for this transaction. The feature vector deviates significantly from the trained normal distribution.",
}


def _compute_event_delay(events: list[dict[str, Any]] | None, receive_time: str | None) -> float:
    """
    Compute the delay (in seconds) between the earliest event timestamp in the
    sequence and the time the webhook was received by the Node.js backend.
    Returns 0.0 when timestamps are unavailable or unparseable.
    """
    if not events:
        return 0.0

    timestamps: list[datetime] = []
    for e in events:
        raw = e.get("created_at") or e.get("timestamp")
        if not raw:
            continue
        try:
            # Handle both offset-aware and naive ISO strings.
            ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            timestamps.append(ts)
        except ValueError:
            continue

    if not timestamps:
        return 0.0

    earliest = min(timestamps)

    if receive_time:
        try:
            recv = datetime.fromisoformat(str(receive_time).replace("Z", "+00:00"))
            if recv.tzinfo is None:
                recv = recv.replace(tzinfo=timezone.utc)
            return max(0.0, (recv - earliest).total_seconds())
        except ValueError:
            pass

    # Fallback: spread across the event list itself.
    latest = max(timestamps)
    return max(0.0, (latest - earliest).total_seconds())


def _build_agent_reason(amount_cents: float, delay_seconds: float, raw_score: float) -> str:
    """
    Return a human-readable anomaly reason string based on which features
    pushed the IsolationForest into anomaly territory.
    """
    high_amount = amount_cents > 50_000   # > $500 in cents
    high_delay  = delay_seconds > 60      # > 1 minute

    if high_amount and high_delay:
        return _REASON_TEMPLATES["combined"].format(
            amount_cents=int(amount_cents), delay_seconds=delay_seconds
        )
    if high_amount:
        return _REASON_TEMPLATES["high_amount"].format(amount_cents=int(amount_cents))
    if high_delay:
        return _REASON_TEMPLATES["high_delay"].format(delay_seconds=delay_seconds)
    return _REASON_TEMPLATES["pattern"]


@app.post("/api/score")
async def score_transaction(payload: ScoreRequest):
    """
    Pattern anomaly scoring endpoint.
    Called by Express Backend/services/aiDetection.js on every webhook event.

    Response contract (must not change — read by aiDetection.js):
      { is_anomaly: 0|1, agent_reason: str|null,
        raw_metrics: {...}, baseline_score: {...} }
    """
    # ── 1. Feature engineering ────────────────────────────────────────────────

    # amount: Express sends a float dollar value (e.g. 99.99).
    # IsolationForest was trained on *cents* → multiply by 100.
    dollar_amount: float = float(payload.amount or 0)
    amount_cents: float = dollar_amount * 100

    # Compute delay from the event sequence + receiveTime.
    delay_seconds: float = _compute_event_delay(payload.events, payload.receiveTime)

    # Translate Node.js event_type vocabulary to Python status vocabulary.
    last_event_type: str = "initiated"
    if payload.events:
        last_raw = payload.events[-1].get("event_type", "created")
        last_event_type = _NODE_TO_PY_STATUS.get(last_raw, "initiated")

    # ── 2. IsolationForest scoring (reuse existing AnomalyDetector) ───────────
    score_payload = {
        "amount_cents":  amount_cents,
        "delay_seconds": delay_seconds,
        "status":        last_event_type,
    }
    raw_score, is_anomaly = detector.score(score_payload)

    # ── 3. Build response ─────────────────────────────────────────────────────
    agent_reason: str | None = None
    if is_anomaly:
        agent_reason = _build_agent_reason(amount_cents, delay_seconds, raw_score)

    raw_metrics = {
        "amount_cents":       amount_cents,
        "delay_seconds":      round(delay_seconds, 4),
        "status_ordinal":     STATUS_ORDINAL.get(last_event_type, 0),
        "isolation_score":    round(raw_score, 6),
        "event_count":        len(payload.events) if payload.events else 0,
    }
    baseline_score = {
        "normal_amount_range":  [100, 10_000],
        "normal_delay_range":   [0, 5],
        "contamination_rate":   0.1,
    }

    logger.info(
        "[/api/score] txn=%s | amount_cents=%.0f | delay=%.2fs | "
        "is_anomaly=%d | score=%.4f",
        payload.transaction_id, amount_cents, delay_seconds,
        int(is_anomaly), raw_score,
    )

    return JSONResponse(content={
        "is_anomaly":    int(is_anomaly),
        "agent_reason":  agent_reason,
        "raw_metrics":   raw_metrics,
        "baseline_score": baseline_score,
    })


def _compute_fraud_score(timing_delta_ms: int, amount_cents: float) -> tuple[float, str]:
    """
    Deterministic fraud scoring for replay attack classification.

    Core heuristic:
      - Harmless network retries arrive within milliseconds of the original
        (TCP keepalive, load-balancer retry, provider retry logic).
      - Malicious replay attacks arrive minutes to hours later, exploiting
        session windows or attempting double-charge.

    Returns (fraud_score ∈ [0, 1], human_readable_reason).
    """
    # ── Timing signal ─────────────────────────────────────────────────────────
    # Map timing_delta_ms to a 0..1 signal using a sigmoid centred at 30 000ms
    # (30 seconds).  Deltas below ~100 ms score near 0; above ~5 min score near 1.
    #
    #   sigmoid(x) = 1 / (1 + e^(-k*(x - x0)))
    #   k     = 0.00015  (controls steepness)
    #   x0    = 30 000   (inflection at 30 seconds)
    k, x0 = 0.00015, 30_000.0
    timing_signal: float = 1.0 / (1.0 + math.exp(-k * (timing_delta_ms - x0)))

    # ── Amount signal (secondary) ─────────────────────────────────────────────
    # Large amounts increase suspicion slightly (capped at +0.10).
    amount_bonus: float = 0.0
    if amount_cents and amount_cents > 0:
        # Normalise: $1 000 (100 000 cents) → +0.05;  $10 000 → +0.10
        amount_bonus = min(0.10, (amount_cents / 1_000_000.0))

    fraud_score: float = min(1.0, timing_signal + amount_bonus)

    # ── Human-readable reason ─────────────────────────────────────────────────
    delta_sec = timing_delta_ms / 1000.0
    if timing_delta_ms < 100:
        reason = (
            f"Duplicate arrived {timing_delta_ms}ms after original — "
            "consistent with a harmless provider retry or TCP re-transmission."
        )
    elif timing_delta_ms < 2_000:
        reason = (
            f"Duplicate arrived {delta_sec:.2f}s after original — "
            "within normal retry window; likely benign."
        )
    elif timing_delta_ms < 60_000:
        reason = (
            f"Duplicate arrived {delta_sec:.1f}s after original — "
            "delay exceeds typical retry interval; borderline suspicious."
        )
    elif timing_delta_ms < 600_000:
        reason = (
            f"Duplicate arrived {delta_sec:.0f}s ({timing_delta_ms // 60000}m) "
            "after original — significantly delayed; possible session-replay attempt."
        )
    else:
        minutes = timing_delta_ms // 60_000
        reason = (
            f"Duplicate arrived {minutes}m after original — "
            "far outside any legitimate retry window; high probability of malicious replay."
        )

    return fraud_score, reason


@app.post("/api/security-score")
async def security_score(payload: SecurityScoreRequest):
    """
    Replay-attack classification endpoint.
    Called by Express Backend/middleware/idempotency.js when an in-memory lock
    collision is detected (i.e., the same txn_id:event_type arrives twice).

    Response contract (must not change — read by idempotency.js):
      { is_malicious: 0|1, fraud_score: float, reason: str }
    """
    amount_cents: float = float(payload.amount_cents or 0)
    fraud_score, reason = _compute_fraud_score(payload.timing_delta_ms, amount_cents)

    # Threshold: score > 0.70 → malicious replay; ≤ 0.70 → harmless retry.
    is_malicious: int = 1 if fraud_score > 0.70 else 0

    logger.info(
        "[/api/security-score] txn=%s | event=%s | delta=%dms | "
        "fraud_score=%.4f | is_malicious=%d",
        payload.transaction_id, payload.event_type,
        payload.timing_delta_ms, fraud_score, is_malicious,
    )

    return JSONResponse(content={
        "is_malicious": is_malicious,
        "fraud_score":  round(fraud_score, 4),
        "reason":       reason,
    })


@app.get("/metrics")
async def get_metrics():
    return database.get_metrics()


@app.get("/events")
async def get_events(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    return database.get_events(page=page, page_size=page_size)


@app.get("/")
async def serve_dashboard():
    index_path = Path("static/index.html")
    if index_path.exists():
        return FileResponse(str(index_path))
    return JSONResponse({"message": "Dashboard not yet available"})
