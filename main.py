from contextlib import asynccontextmanager

import httpx
from db.base import AsyncSessionLocal
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from kafka.storage_queue_manager import KafkaStorageQueueManager
from loguru import logger

from cache.cache_adapter import RedisCacheAdapter
from domain.excepts import SystemErrorType, User
from rag.qdrant_port import retriever
from routers import webhooks
from services.error_reporting_service import ErrorReportingService


# --- Application Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles application startup and shutdown events."""
    logger.info("Starting application...")

    # --- Initialize Clients ---
    app.state.http_client = httpx.AsyncClient(timeout=120.0)

    # --- Initialize cache ---
    try:
        app.state.cache_adapter = RedisCacheAdapter()
        # Clear the whole cache
        # await app.state.cache_adapter.clear_all_cache()
        await app.state.cache_adapter._initialise()
    except Exception as e:
        logger.critical(f"Failed to initialize cache: {e}")
        await ErrorReportingService.report_system_error(
            e,
            SystemErrorType.CACHE_ERROR,
            User(),
            "Failed to initialise cache",
        )
        raise

    # --- Initialize Kafka ---
    try:
        app.state.queue_manager = KafkaStorageQueueManager(
            cache_client=app.state.cache_adapter, session_factory=AsyncSessionLocal
        )
        await app.state.queue_manager.initialize()
    except Exception as e:
        logger.critical(f"Failed to initialize the queue_manager: {e}")
        await ErrorReportingService.report_system_error(
            e,
            SystemErrorType.QUEUE_ERROR,
            User(),
            "Failed to initialise the queue_manager",
        )
        raise

    # --- Initialise the Vector database ---
    try:
        # Await the knowledge vector_database init and setup
        collections = await retriever.initialize()

        # Check if collection already exists

        collection_names = [collection.name for collection in collections.collections]

        # Delete all collections if they exist
        # if collection_names:
        #    for collection in collection_names:
        #        await retriever.client.delete_collection(collection_name = collection)

        # --- Sync the Vector database ---
        yield {"retriever": retriever}
    except Exception as e:
        logger.critical(f"Failed to initialize Qdrant DB: {e}")
        await ErrorReportingService.report_system_error(
            e,
            SystemErrorType.VECTOR_DB_ERROR,
            User(),
            "Failed to initialise vector database",
        )
        raise

    # --- Shutdown logic ---

    logger.info("...Application shutdown complete.")
    await app.state.http_client.close()
    await app.state.cache_adapter.close()
    await retriever.close()
    logger.info("All connections closed.")


# --- FastAPI App Initialization ---
app = FastAPI(
    title="Jikinge Insurance Agent",
    description="Digital Insurance powered by AI.",
    version="1.0.0",
    lifespan=lifespan,
)


# Add logger for the main application
logger.add("./logs/main_app.log", rotation="1 week", level="INFO")

# --- Middleware Configuration ---
# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- API Routers ---

app.include_router(webhooks.router)


# --- Health Check Endpoint ---
@app.get("/health", tags=["Health"])
async def health_check():
    """Simple health check endpoint to confirm the API is running."""
    return {"status": "healthy"}
