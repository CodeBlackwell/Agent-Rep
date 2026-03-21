import json
import time
from types import SimpleNamespace

import anthropic

from src.core import logger


class ClaudeChatClient:
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             purpose: str = "") -> SimpleNamespace:
        system, converted = _convert_messages(messages)
        kwargs = {"model": self.model, "max_tokens": 4096, "messages": converted}
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = _convert_tools(tools)

        logger.debug("llm.request", provider="anthropic", model=self.model,
                      purpose=purpose, message_count=len(converted),
                      has_tools=bool(tools))

        for attempt in range(10):
            try:
                t0 = time.perf_counter()
                response = self.client.messages.create(**kwargs)
                latency = int((time.perf_counter() - t0) * 1000)

                shaped = _shape_response(response)
                tc_count = len(shaped.choices[0].message.tool_calls or [])

                logger.log_llm_call(
                    provider="anthropic", model=self.model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    latency_ms=latency, purpose=purpose,
                    tool_calls=tc_count,
                    stop_reason=response.stop_reason,
                )
                return shaped

            except anthropic.RateLimitError:
                wait = min(2 ** attempt * 5, 120)
                logger.log_llm_retry(provider="anthropic", attempt=attempt + 1,
                                     wait_s=wait)
                time.sleep(wait)
                if attempt == 9:
                    raise
            except Exception as e:
                logger.log_llm_error(provider="anthropic", error=str(e),
                                     purpose=purpose)
                raise


def _convert_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """Extract system message and convert OpenAI-shaped messages to Anthropic format."""
    system = ""
    converted = []
    pending_tool_results = []

    for msg in messages:
        role = msg.get("role")

        if role == "system":
            system = msg["content"]

        elif role == "tool":
            pending_tool_results.append({
                "type": "tool_result",
                "tool_use_id": msg["tool_call_id"],
                "content": msg["content"],
            })

        else:
            # Flush any pending tool results as a user message
            if pending_tool_results:
                converted.append({"role": "user", "content": pending_tool_results})
                pending_tool_results = []

            if role == "assistant":
                content_blocks = []
                if msg.get("content"):
                    content_blocks.append({"type": "text", "text": msg["content"]})
                for tc in msg.get("tool_calls", []):
                    fn = tc["function"]
                    arguments = fn["arguments"]
                    if isinstance(arguments, str):
                        arguments = json.loads(arguments)
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": fn["name"],
                        "input": arguments,
                    })
                converted.append({"role": "assistant", "content": content_blocks})

            elif role == "user":
                converted.append({"role": "user", "content": msg["content"]})

    # Flush trailing tool results
    if pending_tool_results:
        converted.append({"role": "user", "content": pending_tool_results})

    return system, converted


def _convert_tools(tools: list[dict]) -> list[dict]:
    """Convert OpenAI tool definitions to Anthropic format."""
    result = []
    for tool in tools:
        fn = tool.get("function", tool)
        result.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return result


def _shape_response(response) -> SimpleNamespace:
    """Shape Anthropic response into OpenAI-compatible SimpleNamespace."""
    content_text = None
    tool_calls = []

    for block in response.content:
        if block.type == "text":
            content_text = block.text
        elif block.type == "tool_use":
            tool_calls.append(SimpleNamespace(
                id=block.id,
                function=SimpleNamespace(
                    name=block.name,
                    arguments=json.dumps(block.input),
                ),
            ))

    message = SimpleNamespace(
        content=content_text,
        tool_calls=tool_calls or None,
    )
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])
