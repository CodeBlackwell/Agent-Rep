import time

import voyageai
from voyageai.error import RateLimitError

from src.core import logger

EMBED_DIMENSIONS = 1024
INPUT_TYPE_MAP = {"passage": "document", "query": "query"}


class VoyageClient:
    def __init__(self, api_key: str):
        self.client = voyageai.Client(api_key=api_key)

    def embed(self, texts: list[str], input_type: str = "passage",
              model: str = "voyage-3.5") -> list[list[float]]:
        voyage_input_type = INPUT_TYPE_MAP.get(input_type, input_type)
        for attempt in range(10):
            try:
                t0 = time.perf_counter()
                result = self.client.embed(
                    texts, model=model, input_type=voyage_input_type,
                    output_dimension=EMBED_DIMENSIONS,
                )
                latency = int((time.perf_counter() - t0) * 1000)
                logger.log_embed_call(
                    provider="voyage", model=model,
                    batch_size=len(texts), latency_ms=latency,
                    input_type=input_type,
                    total_tokens=result.total_tokens if hasattr(result, "total_tokens") else None,
                )
                return result.embeddings
            except RateLimitError:
                wait = min(2 ** attempt * 5, 120)
                logger.log_embed_retry(provider="voyage", attempt=attempt + 1, wait_s=wait)
                time.sleep(wait)
                if attempt == 9:
                    raise
            except Exception as e:
                logger.log_llm_error(provider="voyage", error=str(e), purpose="embed")
                raise RuntimeError(f"Voyage embed error: {e}") from e
