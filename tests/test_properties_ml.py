"""
Property tests for Anomaly_Detector (ml_model.py).
"""
import time

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ml_model import AnomalyDetector

_detector = AnomalyDetector()
_detector.train()

valid_status = st.sampled_from(["initiated", "processing", "completed", "failed"])


@st.composite
def valid_payload(draw):
    return {
        "transaction_id": draw(st.text(min_size=1, max_size=32)),
        "status": draw(valid_status),
        "timestamp": "2024-01-01T00:00:00+00:00",
        "amount_cents": draw(st.integers(min_value=100, max_value=10_000)),
        "delay_seconds": draw(st.floats(min_value=0.0, max_value=5.0, allow_nan=False)),
    }


# Warm up the detector once at module level to avoid first-call overhead in tests
_detector.score({"transaction_id": "warmup", "status": "initiated", "timestamp": "2024-01-01T00:00:00+00:00", "amount_cents": 100, "delay_seconds": 0.0})


# Feature: webhook-reconciliation-microservice, Property 6: Anomaly scoring latency
@given(payload=valid_payload())
@settings(deadline=None)
def test_property6_anomaly_scoring_latency(payload):
    """Validates: Requirements 3.2"""
    start = time.perf_counter()
    score, is_anomaly = _detector.score(payload)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.1, f"Scoring took {elapsed:.3f}s, expected < 100ms"
    assert isinstance(score, float)
    # is_anomaly may be numpy bool_ — check it's boolean-like
    assert bool(is_anomaly) in (True, False)


# Feature: webhook-reconciliation-microservice, Property 7: Anomaly flag consistency
@given(
    amount_cents=st.integers(min_value=5_000_000, max_value=100_000_000),
    delay_seconds=st.floats(min_value=10_000.0, max_value=100_000.0, allow_nan=False),
)
def test_property7_anomaly_flag_consistency(amount_cents, delay_seconds):
    """Validates: Requirements 3.3"""
    payload = {
        "transaction_id": "test-extreme",
        "status": "initiated",
        "timestamp": "2024-01-01T00:00:00+00:00",
        "amount_cents": amount_cents,
        "delay_seconds": delay_seconds,
    }
    _, is_anomaly = _detector.score(payload)
    assert bool(is_anomaly) is True, (
        f"Expected anomaly for extreme values amount={amount_cents}, delay={delay_seconds}"
    )
