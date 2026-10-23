from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from daily_agent.config import Settings, get_settings
from daily_agent.db_admission import (
    acquire_session_lease,
    attach_lease,
    install_admission,
    release_session,
)


class Base(DeclarativeBase):
    pass


def build_engine(settings: Settings) -> Engine:
    connect_args: dict[str, object] = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    if settings.database_url.startswith("postgresql"):
        connect_args["connect_timeout"] = settings.database_connect_timeout
        engine = create_engine(
            settings.database_url,
            connect_args=connect_args,
            pool_pre_ping=True,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout,
            pool_recycle=settings.database_pool_recycle_seconds,
            # LIFO reuses the most recently returned connection, so idle connections age out
            # and the pooler sees fewer live sessions under bursty load.
            pool_use_lifo=True,
            hide_parameters=True,
        )
    else:
        engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
    if settings.database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_foreign_keys(dbapi_connection: object, _record: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    # Admission slots equal pool capacity: a request waits for a slot instead of queueing inside
    # the pool, so SQLAlchemy's pool timeout is a backstop rather than the normal failure path.
    install_admission(
        engine,
        capacity=settings.database_pool_size + settings.database_max_overflow,
        wait_seconds=settings.database_admission_wait_seconds,
    )
    return engine


# Lazy: building the engine at import time would run get_settings() (and its
# sqlite data_dir side effect) on every import — tests and CLI tools included.
_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = build_engine(get_settings())
    return _engine


SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    if SessionLocal.kw.get("bind") is None:
        SessionLocal.configure(bind=get_engine())
    engine = SessionLocal.kw["bind"]
    # The slot is held until the handler calls ``release_session`` or the request ends. Streaming
    # handlers release before returning, so no slot or connection is held while SSE streams.
    lease = acquire_session_lease(engine)
    session = SessionLocal()
    attach_lease(session, lease)
    try:
        yield session
    finally:
        release_session(session)


def create_schema(target_engine: Engine | None = None) -> None:
    from daily_agent import models  # noqa: F401

    engine = target_engine or get_engine()
    if engine.dialect.name != "sqlite":
        raise ValueError("automatic schema creation is SQLite-only; review and apply Alembic migrations")
    Base.metadata.create_all(engine)
