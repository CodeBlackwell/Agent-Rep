import time
from openai import OpenAI, RateLimitError

from src.core import logger

NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
EMBED_DIMENSIONS = 1024


class NimClient:
    def __init__(self, api_key: str):
        self.client = OpenAI(base_url=NIM_BASE_URL, api_key=api_key)

    def chat(self, messages: list[dict], tools=None,
             model: str = "nvidia/llama-3.3-nemotron-super-49b-v1.5",
             purpose: str = ""):
        logger.debug("llm.request", provider="nim", model=model,
                      purpose=purpose, message_count=len(messages),
                      has_tools=bool(tools))
        try:
            kwargs = {"model": model, "messages": messages}
            if tools:
                kwargs["tools"] = tools
            t0 = time.perf_counter()
            response = self.client.chat.completions.create(**kwargs)
            latency = int((time.perf_counter() - t0) * 1000)

            usage = response.usage
            input_tokens = usage.prompt_tokens if usage else 0
            output_tokens = usage.completion_tokens if usage else 0
            tc_count = len(response.choices[0].message.tool_calls or []) if response.choices[0].message.tool_calls else 0

            logger.log_llm_call(
                provider="nim", model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency, purpose=purpose,
                tool_calls=tc_count,
            )
            return response
        except Exception as e:
            logger.log_llm_error(provider="nim", error=str(e), purpose=purpose)
            raise RuntimeError(f"NIM chat error ({NIM_BASE_URL}/chat/completions): {e}") from e

    def embed(self, texts: list[str], input_type: str = "passage",
              model: str = "nvidia/llama-3.2-nv-embedqa-1b-v2") -> list[list[float]]:
        for attempt in range(10):
            try:
                t0 = time.perf_counter()
                response = self.client.embeddings.create(
                    model=model, input=texts, encoding_format="float",
                    dimensions=EMBED_DIMENSIONS,
                    extra_body={"input_type": input_type, "truncate": "END"},
                )
                latency = int((time.perf_counter() - t0) * 1000)
                logger.log_embed_call(
                    provider="nim", model=model,
                    batch_size=len(texts), latency_ms=latency,
                    input_type=input_type,
                )
                return [item.embedding for item in response.data]
            except RateLimitError:
                wait = min(2 ** attempt * 5, 120)
                logger.log_embed_retry(provider="nim", attempt=attempt + 1, wait_s=wait)
                time.sleep(wait)
                if attempt == 9:
                    raise
            except Exception as e:
                logger.log_llm_error(provider="nim", error=str(e), purpose="embed")
                raise RuntimeError(f"NIM embed error ({NIM_BASE_URL}/embeddings): {e}") from e
