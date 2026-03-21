import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class Settings:
    nvidia_api_key: str
    anthropic_api_key: str
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    github_token: str
    embed_provider: str
    voyage_api_key: str
    chat_provider: str
    claude_model: str
    db_path: str
    show_private_code: bool
    github_owner: str

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()
        return cls(
            nvidia_api_key=os.getenv("NVIDIA_API_KEY", ""),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", "showmeoff"),
            github_token=os.getenv("GITHUB_TOKEN", ""),
            embed_provider=os.getenv("EMBED_PROVIDER", "nim"),
            voyage_api_key=os.getenv("VOYAGE_API_KEY", ""),
            chat_provider=os.getenv("CHAT_PROVIDER", "nim"),
            claude_model=os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
            db_path=os.getenv("DB_PATH", "data/showmeoff.db"),
            show_private_code=os.getenv("SHOW_PRIVATE_CODE", "false").lower() in ("true", "1", "yes"),
            github_owner=os.getenv("GITHUB_OWNER", "codeblackwell"),
        )
