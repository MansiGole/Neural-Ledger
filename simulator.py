"""
Traffic Simulator for the Webhook Reconciliation Microservice.

Sends four traffic patterns to POST /webhook:
  1. Normal sequential transactions (initiated → processing → completed)
  2. Duplicate events (same idempotency_key sent twice)
  3. Transactions with missing intermediate statuses (skip processing)
  4. Out-of-order events (send completed before processing)

Catches requests.ConnectionError per individual request; logs and continues.

Usage:
    python simulator.py
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _post(base_url: str, payload: dict) -> None:
    """POST a single webhook event; catch ConnectionError and log."""
    try:
        resp = requests.post(f"{base_url}/webhook", json=payload, timeout=5)
        logger.info(
            "POST /webhook status=%s transaction_id=%s event_status=%s",
            resp.status_code,
            payload.get("transaction_id"),
            payload.get("status"),
        )
    except requests.ConnectionError as exc:
        logger.error(
            "ConnectionError for transaction_id=%s status=%s: %s",
            payload.get("transaction_id"),
            payload.get("status"),
            exc,
        )


def run_simulation(base_url: str = "http://localhost:8000") -> None:
    """Run all four traffic patterns against base_url."""

    # Pattern 1: Normal sequential transactions (initiated → processing → completed)
    logger.info("=== Pattern 1: Normal sequential transactions ===")
    for i in range(3):
        tid = f"normal-{uuid.uuid4().hex[:8]}"
        base_ts = datetime.now(timezone.utc)
        for j, status in enumerate(["initiated", "processing", "completed"]):
            ts = (base_ts + timedelta(seconds=j * 5)).isoformat()
            _post(base_url, {
                "transaction_id": tid,
                "status": status,
                "timestamp": ts,
                "amount_cents": 1000 + i * 100,
            })

    # Pattern 2: Duplicate events (same idempotency_key sent twice)
    logger.info("=== Pattern 2: Duplicate events ===")
    for i in range(2):
        tid = f"dup-{uuid.uuid4().hex[:8]}"
        ts = _now_iso()
        payload = {
            "transaction_id": tid,
            "status": "initiated",
            "timestamp": ts,
            "amount_cents": 500,
        }
        _post(base_url, payload)
        _post(base_url, payload)  # exact duplicate

    # Pattern 3: Missing intermediate statuses (skip processing)
    logger.info("=== Pattern 3: Missing intermediate statuses ===")
    for i in range(2):
        tid = f"gap-{uuid.uuid4().hex[:8]}"
        base_ts = datetime.now(timezone.utc)
        for j, status in enumerate(["initiated", "completed"]):  # skip processing
            ts = (base_ts + timedelta(seconds=j * 10)).isoformat()
            _post(base_url, {
                "transaction_id": tid,
                "status": status,
                "timestamp": ts,
                "amount_cents": 750,
            })

    # Pattern 4: Out-of-order events (send completed before processing)
    logger.info("=== Pattern 4: Out-of-order events ===")
    for i in range(2):
        tid = f"ooo-{uuid.uuid4().hex[:8]}"
        base_ts = datetime.now(timezone.utc)
        # Timestamps reflect correct order, but we send completed first
        events_in_send_order = [
            ("completed",  (base_ts + timedelta(seconds=10)).isoformat()),
            ("processing", (base_ts + timedelta(seconds=5)).isoformat()),
            ("initiated",  base_ts.isoformat()),
        ]
        for status, ts in events_in_send_order:
            _post(base_url, {
                "transaction_id": tid,
                "status": status,
                "timestamp": ts,
                "amount_cents": 1250,
            })

    logger.info("=== Simulation complete ===")


if __name__ == "__main__":
    run_simulation()
