"""
Property tests for Event_Store (database.py).
"""
import json
import tempfile
import os
from datetime import datetime, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.exc import IntegrityError

import database


def _make_db():
    """Create a fresh in-memory SQLite DB and return its URL."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    url = f"sqlite:///{tmp.name}"
    engine = database._engine_for(url)
    database.metadata.create_all(engine)
    return url, tmp.name


def _cleanup(path):
    try:
        os.unlink(path)
    except OSError:
        pass


valid_text = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=1,
    max_size=32,
)

valid_status = st.sampled_from(["initiated", "processing", "completed", "failed"])


@st.composite
def valid_event(draw):
    tid = draw(valid_text)
    status = draw(valid_status)
    ts = datetime.now(timezone.utc).isoformat()
    return {
        "idempotency_key": f"{tid}:{status}",
        "transaction_id": tid,
        "status": status,
        "timestamp": ts,
        "payload": json.dumps({"transaction_id": tid, "status": status}),
        "received_at": ts,
        "anomaly_score": draw(st.floats(min_value=-1.0, max_value=0.0, allow_nan=False)),
        "is_anomaly": draw(st.integers(min_value=0, max_value=1)),
        "is_healed": 0,
        "healed_at": None,
    }


# Feature: webhook-reconciliation-microservice, Property 4: Event persistence round-trip
@given(event=valid_event())
def test_property4_event_persistence_round_trip(event):
    """Validates: Requirements 2.1, 3.5"""
    url, path = _make_db()
    try:
        database.insert_event(event, db_url=url)
        engine = database._engine_for(url)
        from sqlalchemy import select
        with engine.connect() as conn:
            row = conn.execute(
                select(database.webhook_events).where(
                    database.webhook_events.c.idempotency_key == event["idempotency_key"]
                )
            ).mappings().fetchone()
        assert row is not None
        assert row["transaction_id"] == event["transaction_id"]
        assert row["status"] == event["status"]
        assert row["timestamp"] == event["timestamp"]
        assert row["payload"] == event["payload"]
        assert row["received_at"] == event["received_at"]
    finally:
        _cleanup(path)


# Feature: webhook-reconciliation-microservice, Property 5: Idempotent ingestion
@given(event=valid_event())
def test_property5_idempotent_ingestion_db(event):
    """Validates: Requirements 2.2"""
    url, path = _make_db()
    try:
        database.insert_event(event, db_url=url)
        try:
            database.insert_event(event, db_url=url)
        except IntegrityError:
            pass

        engine = database._engine_for(url)
        from sqlalchemy import select, func
        with engine.connect() as conn:
            count = conn.execute(
                select(func.count()).select_from(database.webhook_events).where(
                    database.webhook_events.c.idempotency_key == event["idempotency_key"]
                )
            ).scalar()
        assert count == 1
    finally:
        _cleanup(path)
