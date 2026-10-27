import asyncio
from asyncio.locks import Semaphore
from typing import Any
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", env_file=".env", env_file_encoding="utf-8"
    )

    # AI API config
    VLLM_HOST: str
    VLLM_AGENT_HOST: str
    LLM_MODEL_ID: str = "Qwen/Qwen3-8B-FP8"
    VISION_MODEL_ID: str = "Qwen/Qwen2.5-VL-7B-Instruct"
    AGGREGATOR_SEM: Semaphore = asyncio.Semaphore(5)

    # Vector DB (Qdrant) Configuration
    EMBEDDING_MODEL: str
    OLLAMA_HOST: str
    QDRANT_HOST: str
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION_NAME: str = "lane_data_collection"
    REFERRAL_COLLECTION: str = "lane_referral_collection"
    OIL_FINDERS_COLLECTION: str = "oil_finders_collection"
    FAQ_COLLECTION: str = "faq_collection"
    DIMENSION: int = 768
    CHUNK_SIZE: int = 100
    SEARCH_LIMIT: int = 20

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
    KAFKA_GROUP_ID: str = "lane-storage-consumer"
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
    DB_PASSWORD: str

    # Jikinge API
    INVENTORY_API: str
    PLACE_ORDER_API_URL: str
    INTERVENTION_API: str
    REFERRAL_CODE_API: str
    CONFIRM_ORDER_API: str
    FALLBACK_PRODUCT_IMAGE: str
    WEB_API_CHAT: str

    # Intervention settings. To be sent a Whatsapp message hence no +.
    HUMAN_INTERVENTION_NUMBER: str

    # Neo4j (Graph Knowledge)
    NEO4J_URI: str
    NEO4J_USER: str
    NEO4J_PASSWORD: str
    KNOWLEDGE_GRAPH_SEARCH_LIMIT: int = 10

    # --- Uniform Timezone
    NAIROBI_TZ: ZoneInfo = ZoneInfo("Africa/Nairobi")

    # Default referral code
    DEFAULT_REFERRAL_CODE: str = "8CCSYOR5"

    # Messaging Universal settings
    MAX_ALLOWED_CAROUSEL_CARD_INDEX: int = 10


settings = AppSettings()

# Qwen agent configuration
llm_configuration: dict[str, Any] = {
    "model": settings.LLM_MODEL_ID,
    "model_server": settings.VLLM_AGENT_HOST,
    "generate_cfg": {
        "top_p": 0.8,
        "temperature": 0,
        "max_input_tokens": 9900,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    },
}

WHATSAPP_URL: str = f"https://graph.facebook.com/{settings.API_VERSION}/{settings.PHONE_NUMBER_ID}/messages"

WHATSAPP_MEDIA_URL: str = f"https://graph.facebook.com/{settings.API_VERSION}"

WHATSAPP_HEADERS: dict[str, str] = {
    "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
    "Content-Type": "application/json",
}
