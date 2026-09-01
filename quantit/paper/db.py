"""SQLite (or other SQLAlchemy URL) session helpers."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from quantit.paper.models import Base
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
    return engine


def create_session(url: str | None = None, engine: Engine | None = None) -> Session:
    eng = engine or create_engine_for(url)
    factory = sessionmaker(eng, expire_on_commit=False, future=True)
    return factory()
