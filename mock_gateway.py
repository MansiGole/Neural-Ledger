import random
import time
from datetime import datetime, timezone

VALID_STATUSES = {"initiated", "processing", "completed", "failed"}


def fetch_missing_event(transaction_id: str, missing_status: str) -> dict:
    if missing_status not in VALID_STATUSES:
        raise ValueError(
            f"Unrecognised missing_status '{missing_status}'. "
            f"Expected one of: {sorted(VALID_STATUSES)}"
        )
    time.sleep(random.uniform(0.05, 0.2))
    ts = datetime.now(timezone.utc).isoformat()
    return {
        "transaction_id": transaction_id,
        "status": missing_status,
        "timestamp": ts,
        "payload": f'{{"transaction_id": "{transaction_id}", "status": "{missing_status}", "timestamp": "{ts}"}}',
    }
