from typing import Any

from loguru import logger
from models import CacheMessage
from ollama import AsyncClient
from qdrant_client import AsyncQdrantClient, models

from config import settings

from .rag_port import RagRetrieverPort

TIMEOUT: float = 60.0


class HybridRetriever(RagRetrieverPort):
    """
    Vector Database object to create and search through collections
    """

    def __init__(
        self,
        collection_name: str = settings.QDRANT_COLLECTION_NAME,
        dimension: int = settings.DIMENSION,
        chunk_size: int = settings.CHUNK_SIZE,
    ):
        self.collection_name = collection_name
        self.dimension = dimension
        self.chunk_size = chunk_size
        self.client = None
        self.embedding_client = AsyncClient(
            host=settings.OLLAMA_HOST,
        )
        self.vector_cache: dict[str, list[CacheMessage]] = {}

    async def initialize(self):
        """Initialize the Qdrant client connection"""
        try:
            # Increased timeout for robustness during startup
            self.client = AsyncQdrantClient(
                url=settings.QDRANT_HOST, port=settings.QDRANT_PORT, timeout=TIMEOUT
            )
            # Test the connection
            logger.info("Qdrant client initialized successfully")

            return await self.client.get_collections()

        except ValueError as e:
            logger.error(f"Failed to initialize Qdrant client: {e}")
            raise

    async def _get_embedding(self, text: str | list[str]) -> list[float]:
        """Helper method to get embeddings for text"""
        try:
            response = await self.embedding_client.embeddings(
                model=settings.EMBEDDING_MODEL, prompt=text
            )
            return response["embedding"]
        except ValueError as e:
            logger.debug(f"Embedding error for text: {e!s}")
            raise

    async def initialize_knowledge_base(
        self, knowledge_paths
    ) -> list[dict[str, int | str | list[float]]]:
        """Process files and create chunks with embeddings"""
        chunks = []
        chunk_id = 0
        logger.info("Knowledge base chunking has began....")
        for path in knowledge_paths:
            try:
                with open(file=path, mode="r", encoding="UTF-8") as file:
                    text = file.read()
                    for i in range(0, len(text), self.chunk_size):
                        chunk_content: str = text[i : i + self.chunk_size]
                        embedding: list[float] = await self._get_embedding(
                            chunk_content
                        )

                        chunks.append(
                            {
                                "id": chunk_id,
                                "text": chunk_content,
                                "vector": embedding,
                                "source_file": path,
                            }
                        )
                        chunk_id += 1
            except ValueError as e:
                logger.ValueError(f"Error processing {path}: {e!s}")
                continue
        return chunks

    async def process_inventory_api_to_chunks(
        self, inventory_data: list[dict]
    ) -> list[dict]:
        """
        Converts API JSON response into structured chunks for the Vector DB.
        Each product is treated as a single 'Document' (Chunk).
        """
        chunks = []
        logger.info(f"Processing {len(inventory_data)} inventory items into vectors...")

        for item in inventory_data:
            try:
                # 1. Create the descriptive text (The 'Document')
                # We repeat key terms like Brand and Name to boost their weight
                brand = item.get("brand_name", {}).get("name", "Unknown")
                item_name = item.get("item_name", "Unknown Part")

                text_content = (
                    f"PRODUCT: {item_name}. BRAND: {brand}. "
                    f"Specs: {item.get('specification')}. "
                    f"Code: {item.get('product_code')}. "
                    f"Price: KSh {item.get('retail_selling_price')}. "
                    f"Description: {item.get('description')}"
                )

                # 2. Generate the embedding
                embedding = await self._get_embedding(text_content)

                # 3. Build the chunk object
                chunks.append(
                    {
                        "id": item.get("id"),  # Use API ID for idempotency
                        "text": text_content,
                        "vector": embedding,
                        "metadata": item,  # Store the whole JSON for the LLM to use later
                    }
                )
            except Exception as e:
                logger.error(f"Error processing item {item.get('id')}: {e}")
                continue

        return chunks

    async def create_collection(self, collection_name: str, chunks: list) -> None:
        """
        Atomically re-creates the collection and uploads points.
        This is a robust method to ensure a fresh state on each startup.
        """
        try:
            if self.client is None:
                await self.initialize()

            logger.info(f"Initialise '{collection_name}' to ensure it is fresh.")
            await self.client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=self.dimension, distance=models.Distance.COSINE, on_disk=True
                ),
                timeout=TIMEOUT,
            )
            logger.info(f"Collection '{collection_name}' created successfully.")

            points = [
                models.PointStruct(
                    id=chunk["id"],
                    vector=chunk["vector"],
                    payload={
                        "text": chunk["text"],
                        "metadata": chunk.get("metadata", {}),
                        "source": collection_name,  # Track where this came from
                    },
                )
                for chunk in chunks
            ]
            # Upload points in batches
            batch_size = 100
            logger.info(f"Uploading {len(points)} points in batches of {batch_size}...")
            for i in range(0, len(points), batch_size):
                batch: list[Any] = points[i : i + batch_size]
                self.client.upload_points(
                    collection_name=collection_name,
                    points=batch,
                    wait=True,
                    parallel=6,
                )
                logger.info(f"Uploaded batch {i // batch_size + 1}")

            logger.success(f"Successfully inserted {len(chunks)} chunks into Qdrant")

        except ValueError as e:
            logger.critical(f"Failed to setup Qdrant collection: {e}", exc_info=True)
            raise

    async def search(
        self, question: str, collection_name: str, limit: int = settings.SEARCH_LIMIT
    ) -> list[dict]:
        """Perform vector similarity search"""

        if self.client is None:
            await self.initialize()  # Ensure client exists

        # Check cache first
        if question in self.vector_cache:
            return self.vector_cache[question]

        embedded_question: list[float] = await self._get_embedding(text=question)

        search_res: list = await self.client.query_points(
            collection_name=collection_name,
            query=embedded_question,
            limit=limit,
            score_threshold=0.4,
        )

        return search_res

    def _generate_searchable_text(self, item: dict[str, Any]) -> str:
        """
        Converts the API payload into a dense, descriptive string for the vector DB.
        This ensures all relevant search terms (brand, size, code) are in the embedding.
        """
        category = item.get("category", {}).get("name", "General Part")

        return (
            f"Product: {item.get('item_name')}. "
            f"Brand: {item.get('item_name')}. "
            f"Category: {category}. "
            f"Code: {item.get('product_code')}. "
            f"Specs: {item.get('specification')}. "
            f"Description: {item.get('description')}. "
            f"Price: KSh {item.get('retail_selling_price')}. "
            f"Stock: {item.get('units')} units available."
        )

    async def upsert_inventory_item(self, item: dict[str, Any]):
        """Upserts a single item. Used by Webhooks."""
        if self.client is None:
            await self.initialize()

        text = self._generate_searchable_text(item)
        vector = await self._get_embedding(text)

        await self.client.upsert(
            collection_name=self.collection_name,
            points=[
                models.PointStruct(
                    id=item.get("id"),  # Use API ID as Qdrant ID for idempotency
                    vector=vector,
                    payload={
                        "text": text,
                        "metadata": item,
                        "updated_at": item.get("updated_at"),
                    },
                )
            ],
        )
        logger.info(f"Updated Vector DB for product ID: {item.get('id')}")

    async def sync_full_inventory(self, inventory_list: list[dict[str, Any]]):
        """Processes and uploads the entire inventory in batches."""
        if self.client is None:
            await self.initialize()

        points = []
        logger.info(f"Starting batch sync for {len(inventory_list)} items...")

        for item in inventory_list:
            text = self._generate_searchable_text(item)
            vector = await self._get_embedding(text)
            points.append(
                models.PointStruct(
                    id=item.get("id"),
                    vector=vector,
                    payload={"text": text, "metadata": item},
                )
            )

            # Upload in batches of 50 to avoid memory bottlenecks
            if len(points) >= 50:
                await self.client.upsert(
                    collection_name=self.collection_name, points=points
                )
                points = []

        if points:  # Final partial batch
            await self.client.upsert(
                collection_name=self.collection_name, points=points
            )

        logger.success("Full inventory sync complete.")

    async def close(self):
        """Clean up resources"""
        if self.client:
            try:
                await self.client.close()
            except ValueError as e:
                logger.warning(f"Error closing Qdrant client: {e}")
            finally:
                self.client = None


# Create a single, shared instance of the retriever
standard_retriever: HybridRetriever = HybridRetriever()
