from src.config.settings import Settings
from src.core.claude_chat_client import ClaudeChatClient
from src.core.db import Database
from src.core.neo4j_client import Neo4jClient
from src.core.nim_client import NimClient
from src.core.voyage_client import VoyageClient


def build_clients(settings: Settings) -> dict:
    """Build all clients based on provider settings.

    Returns dict with keys: neo4j_client, embed_client, chat_client, ingestion_chat_client, db.
    """
    neo4j_client = Neo4jClient(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        embed_provider=settings.embed_provider,
    )

    # Embed client: Voyage or NIM
    if settings.embed_provider == "voyage":
        if not settings.voyage_api_key:
            raise ValueError("VOYAGE_API_KEY is required when EMBED_PROVIDER=voyage")
        embed_client = VoyageClient(settings.voyage_api_key)
    else:
        embed_client = NimClient(settings.nvidia_api_key)

    # Chat client: Claude or NIM
    if settings.chat_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when CHAT_PROVIDER=anthropic")
        chat_client = ClaudeChatClient(settings.anthropic_api_key, model=settings.claude_model)
    else:
        chat_client = NimClient(settings.nvidia_api_key)

    # Ingestion chat client: always Sonnet (quality matters for context generation
    # and skill classification that permanently affect embeddings), with NIM fallback
    if settings.anthropic_api_key:
        ingestion_chat_client = ClaudeChatClient(settings.anthropic_api_key, model="claude-sonnet-4-20250514")
    else:
        ingestion_chat_client = NimClient(settings.nvidia_api_key)

    return {
        "neo4j_client": neo4j_client,
        "embed_client": embed_client,
        "chat_client": chat_client,
        "ingestion_chat_client": ingestion_chat_client,
        "db": Database(settings.db_path),
    }
