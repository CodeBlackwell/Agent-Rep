import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.core.claude_chat_client import (
    ClaudeChatClient,
    _convert_messages,
    _convert_tools,
    _shape_response,
)


def test_system_message_extraction():
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
    ]
    system, converted = _convert_messages(messages)
    assert system == "You are helpful."
    assert len(converted) == 1
    assert converted[0]["role"] == "user"
    assert converted[0]["content"] == "Hello"


def test_tool_definition_conversion():
    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": "search_code",
                "description": "Search code",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        }
    ]
    result = _convert_tools(openai_tools)
    assert len(result) == 1
    assert result[0]["name"] == "search_code"
    assert result[0]["description"] == "Search code"
    assert result[0]["input_schema"]["type"] == "object"
    assert "query" in result[0]["input_schema"]["properties"]


def test_tool_result_message_merging():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "tc1", "function": {"name": "search", "arguments": '{"q": "a"}'}},
            {"id": "tc2", "function": {"name": "search", "arguments": '{"q": "b"}'}},
        ]},
        {"role": "tool", "tool_call_id": "tc1", "content": "result1"},
        {"role": "tool", "tool_call_id": "tc2", "content": "result2"},
    ]
    system, converted = _convert_messages(messages)
    assert system == "sys"
    # user, assistant, user (merged tool results)
    assert len(converted) == 3
    # Last message should be user with two tool_result blocks
    tool_msg = converted[2]
    assert tool_msg["role"] == "user"
    assert len(tool_msg["content"]) == 2
    assert tool_msg["content"][0]["type"] == "tool_result"
    assert tool_msg["content"][0]["tool_use_id"] == "tc1"
    assert tool_msg["content"][1]["tool_use_id"] == "tc2"


def test_response_shaping_text_only():
    response = MagicMock()
    response.content = [MagicMock(type="text", text="Hello world")]
    shaped = _shape_response(response)
    assert shaped.choices[0].message.content == "Hello world"
    assert shaped.choices[0].message.tool_calls is None


def test_response_shaping_tool_calls_only():
    tool_block = SimpleNamespace(type="tool_use", id="tc_1", name="search", input={"query": "test"})
    response = MagicMock()
    response.content = [tool_block]
    shaped = _shape_response(response)
    assert shaped.choices[0].message.content is None
    assert len(shaped.choices[0].message.tool_calls) == 1
    tc = shaped.choices[0].message.tool_calls[0]
    assert tc.id == "tc_1"
    assert tc.function.name == "search"
    # arguments must be JSON string, not dict
    assert isinstance(tc.function.arguments, str)
    assert json.loads(tc.function.arguments) == {"query": "test"}


def test_response_shaping_mixed():
    text_block = SimpleNamespace(type="text", text="Let me search")
    tool_block = SimpleNamespace(type="tool_use", id="tc_2", name="get_evidence", input={"skill_name": "Python"})
    response = MagicMock()
    response.content = [text_block, tool_block]
    shaped = _shape_response(response)
    assert shaped.choices[0].message.content == "Let me search"
    assert len(shaped.choices[0].message.tool_calls) == 1
    assert shaped.choices[0].message.tool_calls[0].function.name == "get_evidence"


def test_arguments_is_json_string():
    """Verify that tool call arguments are serialized as JSON strings, not dicts."""
    tool_block = MagicMock(type="tool_use", id="tc_3", name="find", input={"skills_csv": "Python,Go"})
    response = MagicMock()
    response.content = [tool_block]
    shaped = _shape_response(response)
    args = shaped.choices[0].message.tool_calls[0].function.arguments
    assert isinstance(args, str)
    parsed = json.loads(args)
    assert parsed == {"skills_csv": "Python,Go"}


@patch("src.core.claude_chat_client.anthropic.Anthropic")
def test_chat_calls_api(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    text_block = MagicMock(type="text", text="response text")
    mock_response = MagicMock()
    mock_response.content = [text_block]
    mock_client.messages.create.return_value = mock_response

    client = ClaudeChatClient(api_key="test-key", model="claude-sonnet-4-20250514")
    result = client.chat([
        {"role": "system", "content": "Be helpful"},
        {"role": "user", "content": "Hi"},
    ])

    assert result.choices[0].message.content == "response text"
    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args[1]
    assert call_kwargs["system"] == "Be helpful"
    assert call_kwargs["model"] == "claude-sonnet-4-20250514"
