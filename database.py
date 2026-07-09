import json
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Index,
    Integer,
    MetaData,
    Float,
    String,
    Table,
    Text,
    create_engine,
    func,
    select,
)
from sqlalchemy.exc import IntegrityError

_DEFAULT_DB_URL = "sqlite:///reconciliation.db"

metadata = MetaData()

webhook_events = Table(
    "webhook_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("idempotency_key", Text, nullable=False, unique=True),
    Column("transaction_id", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("timestamp", Text, nullable=False),
    Column("payload", Text, nullable=False),
    Column("received_at", Text, nullable=False),
    Column("anomaly_score", Float),
    Column("is_anomaly", Integer, nullable=False, default=0),
    Column("is_healed", Integer, nullable=False, default=0),
    Column("healed_at", Text),
)

Index("idx_transaction_id", webhook_events.c.transaction_id)
Index("idx_received_at", webhook_events.c.received_at)

_engine = None


def _get_engine(db_url: str = _DEFAULT_DB_URL):
    global _engine
    if _engine is None:
        _engine = create_engine(db_url, connect_args={"check_same_thread": False})
    return _engine


def init_db(db_url: str = _DEFAULT_DB_URL) -> None:
    engine = _get_engine(db_url)
    metadata.create_all(engine)


def _engine_for(db_url: str | None):
    if db_url is None:
        return _get_engine()
    return create_engine(db_url, connect_args={"check_same_thread": False})


def event_exists(idempotency_key: str, db_url: str | None = None) -> bool:
    engine = _engine_for(db_url)
    with engine.connect() as conn:
        result = conn.execute(
            select(webhook_events.c.id).where(
                webhook_events.c.idempotency_key == idempotency_key
            )
        ).fetchone()
        return result is not None


def insert_event(event: dict, db_url: str | None = None) -> None:
    engine = _engine_for(db_url)
    with engine.begin() as conn:
        conn.execute(webhook_events.insert().values(**event))


def get_metrics(db_url: str | None = None) -> dict:
    engine = _engine_for(db_url)
    with engine.connect() as conn:
        total = conn.execute(
            select(func.count()).select_from(webhook_events)
        ).scalar()
        anomaly_count = conn.execute(
            select(func.count()).select_from(webhook_events).where(
                webhook_events.c.is_anomaly == 1
            )
        ).scalar()
        healed_count = conn.execute(
            select(func.count()).select_from(webhook_events).where(
                webhook_events.c.is_healed == 1
            )
        ).scalar()
        recent = conn.execute(
            select(webhook_events)
            .order_by(webhook_events.c.received_at.desc())
            .limit(10)
        ).mappings().fetchall()
    return {
        "total_events": total,
        "anomaly_count": anomaly_count,
        "healed_count": healed_count,
        "recent_events": [dict(r) for r in recent],
    }


def get_events(page: int = 1, page_size: int = 20, db_url: str | None = None) -> dict:
    engine = _engine_for(db_url)
    offset = (page - 1) * page_size
    with engine.connect() as conn:
        total = conn.execute(
            select(func.count()).select_from(webhook_events)
        ).scalar()
        rows = conn.execute(
            select(webhook_events)
            .order_by(webhook_events.c.received_at.desc())
            .limit(page_size)
            .offset(offset)
        ).mappings().fetchall()
    return {
        "events": [dict(r) for r in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def get_all_transactions(db_url: str | None = None) -> dict:
    engine = _engine_for(db_url)
    with engine.connect() as conn:
        rows = conn.execute(
            select(webhook_events).order_by(webhook_events.c.received_at)
        ).mappings().fetchall()
    result: dict = {}
    for row in rows:
        tid = row["transaction_id"]
        result.setdefault(tid, []).append(dict(row))
    return result


def insert_healed_event(event: dict, db_url: str | None = None) -> None:
    engine = _engine_for(db_url)
    with engine.begin() as conn:
        try:
            conn.execute(webhook_events.insert().values(**event))
        except IntegrityError:
            pass  # already healed
