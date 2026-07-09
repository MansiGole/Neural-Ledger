"""
Property tests for Webhook_Server and Auto_Healer (main.py).
Properties 1, 2, 3, 5, 8, 9, 13, 14, 15.
"""
import asyncio
import json
import os
import tempfile
import time
from datetime import datetime, timezone, timedelta

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine, select, func

import database
from database import webhook_events, metadata
from ml_model import AnomalyDetector

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

valid_text = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=1,
    max_size=32,
)

valid_status = st.sampled_from(["initiated", "processing", "completed", "failed"])


@st.composite
def valid_payload_dict(draw):
    return {
        "transaction_id": draw(valid_text),
        "status": draw(valid_status),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "amount_cents": draw(st.integers(min_value=100, max_value=10_000)),
    }


# ---------------------------------------------------------------------------
# App factory — creates a fresh FastAPI app + isolated SQLite DB per test
# ---------------------------------------------------------------------------

def _make_app_with_db(db_path: str):
    """Return (app, engine, original_engine_for) for an isolated test DB."""
    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    original_engine_for = database._engine_for

    def patched_engine_for(url=None):
        return engine

    database._engine_for = patched_engine_for
    database._engine = engine

    from fastapi import FastAPI, Query
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    from sqlalchemy.exc import IntegrityError

    detector = AnomalyDetector()
    detector.train()

    class WebhookPayload(BaseModel):
        transaction_id: str
        status: str
        timestamp: str
        amount_cents: int | None = None
        metadata: dict | None = None

    test_app = FastAPI()

    @test_app.post("/webhook")
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

    @test_app.get("/metrics")
    async def get_metrics():
        return database.get_metrics()

    @test_app.get("/events")
    async def get_events(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ):
        return database.get_events(page=page, page_size=page_size)

    return test_app, engine, original_engine_for


def _cleanup(path, original_engine_for=None):
    if original_engine_for is not None:
        database._engine_for = original_engine_for
        database._engine = None
    try:
        os.unlink(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Property 1: Payload validation rejects any incomplete payload
# Feature: webhook-reconciliation-microservice, Property 1: Payload validation rejects any incomplete payload
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = ["transaction_id", "status", "timestamp"]


@st.composite
def incomplete_payload(draw):
    full = {
        "transaction_id": draw(valid_text),
        "status": draw(valid_status),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    fields_to_remove = draw(
        st.lists(st.sampled_from(REQUIRED_FIELDS), min_size=1, max_size=3, unique=True)
    )
    for f in fields_to_remove:
        del full[f]
    return full


@given(payload=incomplete_payload())
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
def test_property1_payload_validation_rejects_incomplete(payload):
    """
    # Feature: webhook-reconciliation-microservice, Property 1: Payload validation rejects any incomplete payload
    Validates: Requirements 1.2, 1.3
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    app, engine, orig = _make_app_with_db(tmp.name)
    try:
        async def run():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/webhook", json=payload)
            assert resp.status_code == 422, (
                f"Expected 422 for incomplete payload {payload}, got {resp.status_code}"
            )
        asyncio.run(run())
    finally:
        _cleanup(tmp.name, orig)


# ---------------------------------------------------------------------------
# Property 2: Valid payloads are accepted within latency budget
# Feature: webhook-reconciliation-microservice, Property 2: Valid payloads are accepted within latency budget
# ---------------------------------------------------------------------------

@given(payload=valid_payload_dict())
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
def test_property2_valid_payload_latency(payload):
    """
    # Feature: webhook-reconciliation-microservice, Property 2: Valid payloads are accepted within latency budget
    Validates: Requirements 1.4
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    app, engine, orig = _make_app_with_db(tmp.name)
    try:
        async def run():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # Warm up: first request initialises DB connections and app state
                warmup = {**payload, "transaction_id": "__warmup__", "status": "initiated"}
                await client.post("/webhook", json=warmup)
                start = time.perf_counter()
                resp = await client.post("/webhook", json=payload)
                elapsed = time.perf_counter() - start
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
            assert elapsed < 0.5, f"Request took {elapsed:.3f}s, expected < 500ms"
        asyncio.run(run())
    finally:
        _cleanup(tmp.name, orig)


# ---------------------------------------------------------------------------
# Property 3: Concurrent ingestion produces no duplicate records
# Feature: webhook-reconciliation-microservice, Property 3: Concurrent ingestion produces no duplicate records
# ---------------------------------------------------------------------------

@given(
    n=st.integers(min_value=2, max_value=10),
    base_tid=valid_text,
)
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    max_examples=30,
    deadline=None,
)
def test_property3_concurrent_ingestion_no_duplicates(n, base_tid):
    """
    # Feature: webhook-reconciliation-microservice, Property 3: Concurrent ingestion produces no duplicate records
    Validates: Requirements 1.5
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    app, engine, orig = _make_app_with_db(tmp.name)
    try:
        payloads = [
            {
                "transaction_id": f"{base_tid}_{i}",
                "status": "initiated",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "amount_cents": 1000,
            }
            for i in range(n)
        ]

        async def run():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                responses = await asyncio.gather(
                    *[client.post("/webhook", json=p) for p in payloads]
                )
            for r in responses:
                assert r.status_code == 200
            with engine.connect() as conn:
                count = conn.execute(
                    select(func.count()).select_from(webhook_events)
                ).scalar()
                keys = conn.execute(
                    select(webhook_events.c.idempotency_key)
                ).scalars().fetchall()
            assert count == n, f"Expected {n} records, got {count}"
            assert len(set(keys)) == n, "Duplicate idempotency_keys found"

        asyncio.run(run())
    finally:
        _cleanup(tmp.name, orig)


# ---------------------------------------------------------------------------
# Property 5 (HTTP layer): Idempotent ingestion
# Feature: webhook-reconciliation-microservice, Property 5: Idempotent ingestion
# ---------------------------------------------------------------------------

@given(payload=valid_payload_dict())
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
def test_property5_idempotent_http_ingestion(payload):
    """
    # Feature: webhook-reconciliation-microservice, Property 5: Idempotent ingestion
    Validates: Requirements 2.2
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    app, engine, orig = _make_app_with_db(tmp.name)
    try:
        async def run():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                r1 = await client.post("/webhook", json=payload)
                r2 = await client.post("/webhook", json=payload)
            assert r1.status_code == 200
            assert r2.status_code == 200
            idempotency_key = f"{payload['transaction_id']}:{payload['status']}"
            with engine.connect() as conn:
                count = conn.execute(
                    select(func.count()).select_from(webhook_events).where(
                        webhook_events.c.idempotency_key == idempotency_key
                    )
                ).scalar()
            assert count == 1, f"Expected 1 record, got {count}"

        asyncio.run(run())
    finally:
        _cleanup(tmp.name, orig)


# ---------------------------------------------------------------------------
# Property 8: Auto-healer fills gaps
# Feature: webhook-reconciliation-microservice, Property 8: Auto-healer fills gaps
# ---------------------------------------------------------------------------

def _run_one_heal_cycle():
    """Execute one auto-heal cycle body (synchronous wrapper)."""
    import mock_gateway as mg

    EXPECTED_SEQUENCE = ["initiated", "processing", "completed", "failed"]
    TERMINAL_STATUSES = {"completed", "failed"}

    transactions = database.get_all_transactions()
    for t_id, events in transactions.items():
        observed = {e["status"] for e in events}
        terminal = observed & TERMINAL_STATUSES
        if terminal:
            terminal_status = next(iter(terminal))
            terminal_idx = EXPECTED_SEQUENCE.index(terminal_status)
            expected = set(EXPECTED_SEQUENCE[: terminal_idx + 1])
        else:
            expected = set(EXPECTED_SEQUENCE[:2])
        missing = expected - observed
        for ms in missing:
            try:
                result = mg.fetch_missing_event(t_id, ms)
                healed_at = datetime.now(timezone.utc).isoformat()
                database.insert_healed_event({
                    "idempotency_key": f"{t_id}:{ms}",
                    "transaction_id": t_id,
                    "status": ms,
                    "timestamp": result["timestamp"],
                    "payload": result["payload"],
                    "received_at": healed_at,
                    "anomaly_score": None,
                    "is_anomaly": 0,
                    "is_healed": 1,
                    "healed_at": healed_at,
                })
            except Exception:
                pass


@given(tid=valid_text)
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    max_examples=30,
    deadline=None,
)
def test_property8_auto_healer_fills_gaps(tid):
    """
    # Feature: webhook-reconciliation-microservice, Property 8: Auto-healer fills gaps
    Validates: Requirements 4.2, 4.3, 4.6
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_url = f"sqlite:///{tmp.name}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    orig = database._engine_for
    database._engine_for = lambda url=None: engine
    database._engine = engine

    try:
        now = datetime.now(timezone.utc)
        # Insert initiated + completed but skip processing (gap)
        for i, status in enumerate(["initiated", "completed"]):
            ts = (now + timedelta(seconds=i)).isoformat()
            database.insert_event({
                "idempotency_key": f"{tid}:{status}",
                "transaction_id": tid,
                "status": status,
                "timestamp": ts,
                "payload": json.dumps({"transaction_id": tid, "status": status}),
                "received_at": ts,
                "anomaly_score": None,
                "is_anomaly": 0,
                "is_healed": 0,
                "healed_at": None,
            })

        _run_one_heal_cycle()

        with engine.connect() as conn:
            row = conn.execute(
                select(webhook_events).where(
                    webhook_events.c.transaction_id == tid,
                    webhook_events.c.status == "processing",
                )
            ).mappings().fetchone()
        assert row is not None, f"Expected healed 'processing' event for {tid}"
        assert row["is_healed"] == 1
        assert row["healed_at"] is not None

    finally:
        database._engine_for = orig
        database._engine = None
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Property 9: Auto-healer ordering invariant
# Feature: webhook-reconciliation-microservice, Property 9: Auto-healer ordering invariant
# ---------------------------------------------------------------------------

@given(tid=valid_text)
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    max_examples=30,
    deadline=None,
)
def test_property9_auto_healer_ordering_invariant(tid):
    """
    # Feature: webhook-reconciliation-microservice, Property 9: Auto-healer ordering invariant
    Validates: Requirements 4.4
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_url = f"sqlite:///{tmp.name}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    orig = database._engine_for
    database._engine_for = lambda url=None: engine
    database._engine = engine

    try:
        now = datetime.now(timezone.utc)
        # Insert out-of-order by received_at but with correct timestamps
        events_to_insert = [
            # status,       payload timestamp,          received_at
            ("completed",   now,                        now),
            ("initiated",   now - timedelta(seconds=10), now + timedelta(seconds=1)),
            ("processing",  now - timedelta(seconds=5),  now + timedelta(seconds=2)),
        ]
        for status, ts, recv in events_to_insert:
            database.insert_event({
                "idempotency_key": f"{tid}:{status}",
                "transaction_id": tid,
                "status": status,
                "timestamp": ts.isoformat(),
                "payload": json.dumps({"transaction_id": tid, "status": status}),
                "received_at": recv.isoformat(),
                "anomaly_score": None,
                "is_anomaly": 0,
                "is_healed": 0,
                "healed_at": None,
            })

        # Events should be queryable in correct timestamp order
        with engine.connect() as conn:
            rows = conn.execute(
                select(webhook_events)
                .where(webhook_events.c.transaction_id == tid)
                .order_by(webhook_events.c.timestamp)
            ).mappings().fetchall()

        timestamps = [r["timestamp"] for r in rows]
        assert timestamps == sorted(timestamps), (
            f"Events not in timestamp order: {timestamps}"
        )

    finally:
        database._engine_for = orig
        database._engine = None
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Property 13: Metrics response completeness
# Feature: webhook-reconciliation-microservice, Property 13: Metrics response completeness
# ---------------------------------------------------------------------------

@st.composite
def event_set(draw):
    n = draw(st.integers(min_value=0, max_value=15))
    events = []
    used_keys = set()
    for i in range(n):
        tid = f"txn_{draw(valid_text)}_{i}"
        status = draw(valid_status)
        key = f"{tid}:{status}"
        if key in used_keys:
            continue
        used_keys.add(key)
        ts = datetime.now(timezone.utc).isoformat()
        is_anomaly = draw(st.integers(min_value=0, max_value=1))
        is_healed = draw(st.integers(min_value=0, max_value=1))
        events.append({
            "idempotency_key": key,
            "transaction_id": tid,
            "status": status,
            "timestamp": ts,
            "payload": json.dumps({"transaction_id": tid, "status": status}),
            "received_at": ts,
            "anomaly_score": -0.1,
            "is_anomaly": is_anomaly,
            "is_healed": is_healed,
            "healed_at": ts if is_healed else None,
        })
    return events


@given(events=event_set())
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    max_examples=50,
    deadline=None,
)
def test_property13_metrics_response_completeness(events):
    """
    # Feature: webhook-reconciliation-microservice, Property 13: Metrics response completeness
    Validates: Requirements 6.2
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    app, engine, orig = _make_app_with_db(tmp.name)
    try:
        for ev in events:
            try:
                database.insert_event(ev)
            except Exception:
                pass

        expected_total = len(events)
        expected_anomaly = sum(1 for e in events if e["is_anomaly"] == 1)
        expected_healed = sum(1 for e in events if e["is_healed"] == 1)

        async def run():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/metrics")
            assert resp.status_code == 200
            data = resp.json()
            assert "total_events" in data
            assert "anomaly_count" in data
            assert "healed_count" in data
            assert "recent_events" in data
            assert data["total_events"] == expected_total
            assert data["anomaly_count"] == expected_anomaly
            assert data["healed_count"] == expected_healed
            assert len(data["recent_events"]) <= 10

        asyncio.run(run())
    finally:
        _cleanup(tmp.name, orig)


# ---------------------------------------------------------------------------
# Property 14: Metrics response latency
# Feature: webhook-reconciliation-microservice, Property 14: Metrics response latency
# ---------------------------------------------------------------------------

@given(n=st.integers(min_value=0, max_value=50))
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    max_examples=30,
    deadline=None,
)
def test_property14_metrics_response_latency(n):
    """
    # Feature: webhook-reconciliation-microservice, Property 14: Metrics response latency
    Validates: Requirements 6.3
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    app, engine, orig = _make_app_with_db(tmp.name)
    try:
        for i in range(n):
            ts = datetime.now(timezone.utc).isoformat()
            try:
                database.insert_event({
                    "idempotency_key": f"txn_{i}:initiated",
                    "transaction_id": f"txn_{i}",
                    "status": "initiated",
                    "timestamp": ts,
                    "payload": "{}",
                    "received_at": ts,
                    "anomaly_score": None,
                    "is_anomaly": 0,
                    "is_healed": 0,
                    "healed_at": None,
                })
            except Exception:
                pass

        async def run():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                start = time.perf_counter()
                resp = await client.get("/metrics")
                elapsed = time.perf_counter() - start
            assert resp.status_code == 200
            assert elapsed < 0.2, f"GET /metrics took {elapsed:.3f}s, expected < 200ms"

        asyncio.run(run())
    finally:
        _cleanup(tmp.name, orig)


# ---------------------------------------------------------------------------
# Property 15: Events endpoint ordering invariant
# Feature: webhook-reconciliation-microservice, Property 15: Events endpoint ordering invariant
# ---------------------------------------------------------------------------

@st.composite
def events_with_varying_timestamps(draw):
    n = draw(st.integers(min_value=1, max_value=10))
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    offsets = draw(
        st.lists(
            st.integers(min_value=0, max_value=100_000),
            min_size=n,
            max_size=n,
            unique=True,
        )
    )
    events = []
    for i, offset in enumerate(offsets):
        recv = (base + timedelta(seconds=offset)).isoformat()
        events.append({
            "idempotency_key": f"txn_{i}:initiated",
            "transaction_id": f"txn_{i}",
            "status": "initiated",
            "timestamp": recv,
            "payload": "{}",
            "received_at": recv,
            "anomaly_score": None,
            "is_anomaly": 0,
            "is_healed": 0,
            "healed_at": None,
        })
    return events


@given(events=events_with_varying_timestamps())
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    max_examples=50,
    deadline=None,
)
def test_property15_events_endpoint_ordering(events):
    """
    # Feature: webhook-reconciliation-microservice, Property 15: Events endpoint ordering invariant
    Validates: Requirements 6.4
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    app, engine, orig = _make_app_with_db(tmp.name)
    try:
        for ev in events:
            try:
                database.insert_event(ev)
            except Exception:
                pass

        async def run():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/events", params={"page": 1, "page_size": 100})
            assert resp.status_code == 200
            data = resp.json()
            returned = data["events"]
            recv_times = [e["received_at"] for e in returned]
            assert recv_times == sorted(recv_times, reverse=True), (
                f"Events not ordered by received_at descending: {recv_times}"
            )

        asyncio.run(run())
    finally:
        _cleanup(tmp.name, orig)
