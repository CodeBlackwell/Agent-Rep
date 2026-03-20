import json
import time
from types import SimpleNamespace

import anthropic


class ClaudeChatClient:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> SimpleNamespace:
        system, converted = _convert_messages(messages)
        kwargs = {"model": self.model, "max_tokens": 4096, "messages": converted}
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = _convert_tools(tools)
        for attempt in range(10):
            try:
                response = self.client.messages.create(**kwargs)
                return _shape_response(response)
            except anthropic.RateLimitError:
                wait = min(2 ** attempt * 5, 120)
                print(f"  Claude rate limited (attempt {attempt + 1}/10), waiting {wait}s...")
                time.sleep(wait)
                if attempt == 9:
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
