"""SQLite (or other SQLAlchemy URL) session helpers."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from quantit.paper.models import Base, Position, PositionLot
from quantit.utils.config import get_config


def default_db_url() -> str:
    path = get_config().cache_dir.parent / "paper.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


def create_engine_for(url: str | None = None) -> Engine:
    url = url or default_db_url()
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    Base.metadata.create_all(engine)
    _ensure_columns(engine)
    return engine


def session_on(engine: Engine) -> Session:
    """Open another session on an existing engine (separate from the broker session)."""
    factory = sessionmaker(engine, expire_on_commit=False, future=True)
    return factory()


_ORDER_EXTRAS = (("rationale", "TEXT"),)


def _ensure_columns(engine: Engine) -> None:
    """Add columns introduced after the first paper.db was created."""
    insp = inspect(engine)
    if "orders" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("orders")}
    missing = [(name, ddl) for name, ddl in _ORDER_EXTRAS if name not in cols]
    if not missing:
        return
    with engine.begin() as conn:
        for name, ddl in missing:
            conn.execute(text(f"ALTER TABLE orders ADD COLUMN {name} {ddl}"))


def create_session(url: str | None = None, engine: Engine | None = None) -> Session:
    eng = engine or create_engine_for(url)
    factory = sessionmaker(eng, expire_on_commit=False, future=True)
    return factory()


def purge_zero_quantity_positions(session: Session, *, commit: bool = True) -> dict[str, int]:
    """Drop leftover qty<=0 positions and lots with no live parent. Idempotent.

    Isolation-migration residue (and fully flattened rows) stay in ``positions``
    because sells zero the quantity instead of deleting the row. Safe for cash
    and orders: those tables are not touched.
    """
    zero_ids = [row[0] for row in session.query(Position.id).filter(Position.quantity <= 0).all()]
    lots_deleted = 0
    if zero_ids:
        lots_deleted += (
            session.query(PositionLot)
            .filter(PositionLot.position_id.in_(zero_ids))
            .delete(synchronize_session=False)
            or 0
        )
        session.query(Position).filter(Position.id.in_(zero_ids)).delete(synchronize_session=False)

    live_ids = [row[0] for row in session.query(Position.id).all()]
    orphan_q = session.query(PositionLot)
    if live_ids:
        orphan_q = orphan_q.filter(~PositionLot.position_id.in_(live_ids))
    lots_deleted += orphan_q.delete(synchronize_session=False) or 0

    if commit:
        session.commit()
        session.expire_all()
    return {"positions": len(zero_ids), "lots": int(lots_deleted)}
