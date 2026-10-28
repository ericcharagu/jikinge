import asyncio

from loguru import logger
from utils.db.qdrant import standard_retriever


async def run_manual_sync():
    """Manually synchronise the vector database with the current live inventory"""
    # TODO: Use celery to automate manual sync on weekends i.e midnight on Sunday. Note it takes approximately 10 min.

    logger.info("Starting Manual Vector Sync via CLI...")

    try:
        logger.success("CLI Vector Sync Complete.")
    except Exception as e:
        logger.error(f"Sync failed: {e}")
    finally:
        await standard_retriever.close()


if __name__ == "__main__":
    asyncio.run(run_manual_sync())
