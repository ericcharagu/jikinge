import asyncio
from asyncio.locks import Semaphore
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict
from tavily import TavilyClient


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", env_file=".env", env_file_encoding="utf-8"
    )

    # AI API config
    LLM_API_KEY: str
    AGGREGATOR_SEM: Semaphore = asyncio.Semaphore(5)

    # Vector DB (Qdrant) Configuration
    EMBEDDING_MODEL: str
    OLLAMA_HOST: str
    QDRANT_HOST: str
    QDRANT_PORT: int = 6333
    DIMENSION: int = 768
    CHUNK_SIZE: int = 100
    SEARCH_LIMIT: int = 20
    QDRANT_COLLECTION_NAME: str = "jikinge_vector_collection"
    # Tavily API
    TAVILY_KEY: str
    TAVILY_MAX_RESULTS: int = 5

    # Whatsapp security
    WHATSAPP_WEBHOOK_TOKEN: str
    REQUEST_TOKEN: str
    API_VERSION: str = "v26.0"
    PHONE_NUMBER_ID: int
    WHATSAPP_ACCESS_TOKEN: str
    WHATSAPP_FERNET_KEY: str

    # Kafka settings
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    KAFKA_GROUP_ID: str = "jikinge-storage-consumer"
    KAFKA_STORAGE_TOPIC: str = "storage-operations"
    KAFKA_ERROR_TOPIC: str = "error-logs"
    KAFKA_HEALTH_TOPIC: str = "health-checks"
    KAFKA_MAX_POLL_INTERVAL_MS: int = 600000  # 10 min

    # Consumer settings
    KAFKA_CONSUMER_COUNT: int = 2
    KAFKA_AUTO_OFFSET_RESET: str = "earliest"
    KAFKA_ENABLE_AUTO_COMMIT: bool = True
    KAFKA_AUTO_COMMIT_INTERVAL_MS: int = 5000
    KAFKA_SESSION_TIMEOUT_MS: int = 45000
    KAFKA_MAX_POLL_RECORDS: int = 10

    # Producer settings
    KAFKA_ACKS: str = "all"
    KAFKA_RETRIES: int = 3
    KAFKA_LINGER_MS: int = 100
    KAFKA_BATCH_SIZE_KB: int = 999

    # Error handling
    KAFKA_PRODUCER_TIMEOUT: int = 30
    KAFKA_CONSUMER_TIMEOUT: int = 30

    # Valkey Redis Cache
    VALKEY_HOST: str
    VALKEY_PORT: int

    # Persistant database config
    DB_HOST: str
    DB_PORT: str
    DB_NAME: str
    DB_USER: str

    # Jikinge API
    DASHBOARD_API: str
    FRONTEND_API: str
    NOTIFICATION_API: str
    ERROR_API: str
    # Intervention settings. To be sent a Whatsapp message hence no +.
    HUMAN_INTERVENTION_NUMBER: str

    # --- Uniform Timezone
    NAIROBI_TZ: ZoneInfo = ZoneInfo("Africa/Nairobi")

    # Messaging Universal settings
    MAX_ALLOWED_CAROUSEL_CARD_INDEX: int = 10


settings = AppSettings()

USER_SESSION_TTL: int = 3600

WHATSAPP_URL: str = f"https://graph.facebook.com/{settings.API_VERSION}/{settings.PHONE_NUMBER_ID}/messages"

WHATSAPP_MEDIA_URL: str = f"https://graph.facebook.com/{settings.API_VERSION}"

# --- Shared Tavily Client ---


TAVILY_CLIENT = TavilyClient(api_key=settings.TAVILY_KEY)


WHATSAPP_HEADERS: dict[str, str] = {
    "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
    "Content-Type": "application/json",
}
