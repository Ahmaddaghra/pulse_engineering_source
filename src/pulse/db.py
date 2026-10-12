from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.orm import Session


def engine_for(url: str) -> Engine:
    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0,
        connect_args={"options": "-c timezone=UTC"},
    )
    if engine.dialect.name != "postgresql":
        raise ValueError("PostgreSQL is required for leases, fencing and visibility semantics")
    return engine


@contextmanager
def transaction(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session, session.begin():
        yield session


def db_now(session: Session) -> datetime:
    value = session.scalar(select(func.clock_timestamp()))
    assert isinstance(value, datetime)
    return value.astimezone(UTC)


def evidence_lock(session: Session) -> None:
    # Shared by evidence writers, retention/reconciliation and snapshot sealers.
    # Held through commit; a sequence allocation alone is NOT a visibility boundary.
    session.execute(text("SELECT pg_advisory_xact_lock(71001201)"))
