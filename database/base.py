import contextlib
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from loguru import logger
from orm_schema import Base
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from domain.excepts import DatabaseConnectionStringException


# Get connection to DB
def get_async_connection_string() -> str:
    """Construct the ASYNCHRONOUS database connection string."""
    connection_string: str = (
        f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}@"
        f"{settings.DB_HOST}:{settings.DB_PORT}/"
        f"{settings.DB_NAME}"
    )
    if not connection_string:
        raise DatabaseConnectionStringException
    return connection_string


# Create async database engine with connection pooling
async_engine = create_async_engine(
    get_async_connection_string(),
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=10,
    max_overflow=20,
    echo=True,
)

# Create an async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# initialise the DB
async def init_db() -> None:
    """Initialize the database by creating all tables"""
    async with async_engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise


@contextlib.asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Provide a transactional scope around a series of operations"""
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"Session rollback due to error: {e}")
        raise
    finally:
        await session.close()


async def shutdown_session() -> None:
    """Properly close all database connections"""
    await async_engine.dispose()
    logger.info("Database connections closed")


@contextlib.asynccontextmanager
async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Dependency for FastAPI to get async database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def current_time() -> datetime:
    """Get current time (synchronous utility function)"""
    return datetime.now(settings.NAIROBI_TZ)


async def execute_query(
    query: str, params: dict[str, Any] | None = None
) -> list[dict[Any, Any]]:
    """Execute a query and return results as list of dictionaries"""
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(text(query), params or {})
            columns = result.keys()
            return [dict(zip(columns, row)) for row in result.fetchall()]

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


async def execute_command(query: str, params: dict[str, Any] | None = None) -> None:
    """
    Execute a command (INSERT, UPDATE, DELETE) that does not return rows.
    """
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(text(query), params or {})
            await session.commit()
            logger.debug("Command executed successfully")
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()
