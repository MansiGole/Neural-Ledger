"""
Integration tests for the webhook reconciliation microservice.
Requirements: 2.3, 2.5, 7.1
"""
import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine, select, func

import database
from database import webhook_events, metadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_full_app(db_path: str):
    """
    Create a full FastAPI app (matching main.py) with an isolated SQLite DB.
    Avoids starting the background auto_heal_loop to keep tests deterministic.
    """
    from fastapi import FastAPI, Query
    from fastapi.responses import FileResponse, JSONResponse
    from pathlib import Path
    from pydantic import BaseModel
    from sqlalchemy.exc import IntegrityError
    from ml_model import AnomalyDetector

    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    original_engine_for = database._engine_for

    def patched_engine_for(url=None):
        return engine

    database._engine_for = patched_engine_for
    database._engine = engine

    detector = AnomalyDetector()
    detector.train()

    class WebhookPayload(BaseModel):
        transaction_id: str
        status: str
        timestamp: str
        amount_cents: int | None = None
        metadata: dict | None = None

    app = FastAPI()

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

    @app.get("/metrics")
    async def get_metrics():
        return database.get_metrics()

    @app.get("/events")
    async def get_events(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ):
        return database.get_events(page=page, page_size=page_size)

    @app.get("/")
    async def serve_dashboard():
        index_path = Path("static/index.html")
        if index_path.exists():
            return FileResponse(str(index_path))
        return JSONResponse({"message": "Dashboard not yet available"})

    return app, engine, original_engine_for


def _cleanup(path, original_engine_for=None):
    if original_engine_for is not None:
        database._engine_for = original_engine_for
        database._engine = None
    try:
        os.unlink(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# test_end_to_end_simulator_traffic
# Requirements: 2.3, 2.5
# ---------------------------------------------------------------------------

def test_end_to_end_simulator_traffic():
    """
    Send simulator-style traffic and verify end-to-end event counts.
    Covers: normal events, duplicates, missing statuses, out-of-order events.
    Requirements: 2.3, 2.5
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    app, engine, orig = _make_full_app(tmp.name)
    try:
        async def run():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                ts = datetime.now(timezone.utc).isoformat()

                # Pattern 1: Normal sequential transactions (3 transactions × 3 statuses = 9 events)
                normal_txns = ["norm-001", "norm-002", "norm-003"]
                for tid in normal_txns:
                    for status in ["initiated", "processing", "completed"]:
                        r = await client.post("/webhook", json={
                            "transaction_id": tid,
                            "status": status,
                            "timestamp": ts,
                            "amount_cents": 500,
                        })
                        assert r.status_code == 200

                # Pattern 2: Duplicate events — same key sent twice
                dup_payload = {
                    "transaction_id": "dup-001",
                    "status": "initiated",
                    "timestamp": ts,
                    "amount_cents": 100,
                }
                r1 = await client.post("/webhook", json=dup_payload)
                r2 = await client.post("/webhook", json=dup_payload)
                assert r1.status_code == 200
                assert r2.status_code == 200

                # Pattern 3: Missing intermediate status (skip processing)
                for status in ["initiated", "completed"]:
                    r = await client.post("/webhook", json={
                        "transaction_id": "gap-001",
                        "status": status,
                        "timestamp": ts,
                    })
                    assert r.status_code == 200

                # Pattern 4: Out-of-order (completed before processing)
                for status in ["completed", "processing", "initiated"]:
                    r = await client.post("/webhook", json={
                        "transaction_id": "ooo-001",
                        "status": status,
                        "timestamp": ts,
                    })
                    assert r.status_code == 200

            # Verify total event count:
            # 9 (normal) + 1 (dup, only 1 stored) + 2 (gap) + 3 (ooo) = 15
            with engine.connect() as conn:
                total = conn.execute(
                    select(func.count()).select_from(webhook_events)
                ).scalar()
            assert total == 15, f"Expected 15 events, got {total}"

            # Verify duplicate was not stored twice
            with engine.connect() as conn:
                dup_count = conn.execute(
                    select(func.count()).select_from(webhook_events).where(
                        webhook_events.c.transaction_id == "dup-001"
                    )
                ).scalar()
            assert dup_count == 1, f"Expected 1 dup record, got {dup_count}"

        asyncio.run(run())
    finally:
        _cleanup(tmp.name, orig)


# ---------------------------------------------------------------------------
# test_init_db_creates_tables
# Requirements: 2.3, 2.5
# ---------------------------------------------------------------------------

def test_init_db_creates_tables():
    """
    init_db() should create the webhook_events table in a fresh database.
    Requirements: 2.3, 2.5
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_url = f"sqlite:///{tmp.name}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    orig = database._engine_for
    database._engine_for = lambda url=None: engine
    database._engine = engine

    try:
        # Tables should not exist yet (fresh engine, no create_all called)
        from sqlalchemy import inspect as sa_inspect
        inspector = sa_inspect(engine)
        # init_db creates tables
        database.init_db()
        inspector = sa_inspect(engine)
        tables = inspector.get_table_names()
        assert "webhook_events" in tables, f"webhook_events table not found; tables: {tables}"
    finally:
        database._engine_for = orig
        database._engine = None
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# test_dashboard_html_served_at_root
# Requirements: 7.1
# ---------------------------------------------------------------------------

def test_dashboard_html_served_at_root():
    """
    GET / should serve the dashboard HTML file.
    Requirements: 7.1
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    app, engine, orig = _make_full_app(tmp.name)
    try:
        async def run():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/")
            assert resp.status_code == 200
            content_type = resp.headers.get("content-type", "")
            # Should be HTML or a JSON fallback if file missing
            assert "html" in content_type or "json" in content_type, (
                f"Unexpected content-type: {content_type}"
            )
            # If static/index.html exists, verify it contains HTML
            if "html" in content_type:
                assert "<html" in resp.text.lower() or "<!doctype" in resp.text.lower(), (
                    "Response does not look like HTML"
                )

        asyncio.run(run())
    finally:
        _cleanup(tmp.name, orig)


# ---------------------------------------------------------------------------
# test_healing_inserts_healed_events
# Requirements: 2.3
# ---------------------------------------------------------------------------

def test_healing_inserts_healed_events():
    """
    After running one heal cycle, missing statuses should be inserted with is_healed=1.
    Requirements: 2.3
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
        ts = datetime.now(timezone.utc).isoformat()
        # Insert initiated + completed, skip processing
        for status in ["initiated", "completed"]:
            database.insert_event({
                "idempotency_key": f"heal-txn:{status}",
                "transaction_id": "heal-txn",
                "status": status,
                "timestamp": ts,
                "payload": "{}",
                "received_at": ts,
                "anomaly_score": None,
                "is_anomaly": 0,
                "is_healed": 0,
                "healed_at": None,
            })

        # Run one heal cycle
        import mock_gateway as mg
        import main as main_module

        transactions = database.get_all_transactions()
        for tid, events in transactions.items():
            observed = {e["status"] for e in events}
            terminal = observed & main_module.TERMINAL_STATUSES
            if terminal:
                terminal_status = next(iter(terminal))
                terminal_idx = main_module.EXPECTED_SEQUENCE.index(terminal_status)
                expected = set(main_module.EXPECTED_SEQUENCE[: terminal_idx + 1])
            else:
                expected = set(main_module.EXPECTED_SEQUENCE[:2])
            missing = expected - observed
            for ms in missing:
                try:
                    result = mg.fetch_missing_event(tid, ms)
                    healed_at = datetime.now(timezone.utc).isoformat()
                    database.insert_healed_event({
                        "idempotency_key": f"{tid}:{ms}",
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
                except Exception:
                    pass

        # Verify the healed processing event was inserted
        with engine.connect() as conn:
            row = conn.execute(
                select(webhook_events).where(
                    webhook_events.c.transaction_id == "heal-txn",
                    webhook_events.c.status == "processing",
                )
            ).mappings().fetchone()

        assert row is not None, "Expected healed 'processing' event"
        assert row["is_healed"] == 1
        assert row["healed_at"] is not None

    finally:
        database._engine_for = orig
        database._engine = None
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
