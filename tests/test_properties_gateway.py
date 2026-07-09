"""
Property tests for Mock_Gateway (mock_gateway.py).
"""
import time

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import mock_gateway

VALID_STATUSES = ["initiated", "processing", "completed", "failed"]

valid_text = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=1,
    max_size=32,
)

valid_status = st.sampled_from(VALID_STATUSES)

invalid_status = st.text(min_size=1, max_size=32).filter(
    lambda s: s not in mock_gateway.VALID_STATUSES
)


# Feature: webhook-reconciliation-microservice, Property 10: Mock_Gateway output structure
@given(transaction_id=valid_text, status=valid_status)
def test_property10_mock_gateway_output_structure(transaction_id, status):
    """Validates: Requirements 5.2"""
    result = mock_gateway.fetch_missing_event(transaction_id, status)
    assert "transaction_id" in result
    assert "status" in result
    assert "timestamp" in result
    assert "payload" in result
    assert result["transaction_id"] == transaction_id
    assert result["status"] == status


# Feature: webhook-reconciliation-microservice, Property 11: Mock_Gateway rejects unknown statuses
@given(status=invalid_status)
def test_property11_mock_gateway_rejects_unknown_statuses(status):
    """Validates: Requirements 5.3"""
    try:
        mock_gateway.fetch_missing_event("txn-test", status)
        assert False, f"Expected ValueError for status '{status}'"
    except ValueError:
        pass


# Feature: webhook-reconciliation-microservice, Property 12: Mock_Gateway latency bounds
@settings(max_examples=10)
@given(transaction_id=valid_text, status=valid_status)
def test_property12_mock_gateway_latency_bounds(transaction_id, status):
    """Validates: Requirements 5.4"""
    start = time.perf_counter()
    mock_gateway.fetch_missing_event(transaction_id, status)
    elapsed = time.perf_counter() - start
    assert elapsed >= 0.05, f"Call completed too fast: {elapsed:.3f}s"
    assert elapsed <= 0.5, f"Call took too long: {elapsed:.3f}s"
