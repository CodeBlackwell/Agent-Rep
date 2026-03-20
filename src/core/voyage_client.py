import time

import voyageai
from voyageai.error import RateLimitError

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
                result = self.client.embed(
                    texts, model=model, input_type=voyage_input_type,
                    output_dimension=EMBED_DIMENSIONS,
                )
                return result.embeddings
            except RateLimitError:
                wait = min(2 ** attempt * 5, 120)
                print(f"  Voyage rate limited (attempt {attempt + 1}/10), waiting {wait}s...")
                time.sleep(wait)
                if attempt == 9:
                    raise
            except Exception as e:
                raise RuntimeError(f"Voyage embed error: {e}") from e
