from unittest.mock import MagicMock, patch
import json

from src.qa.tools import search_code, get_evidence, search_resume, get_repo_overview, get_connected_evidence
from src.qa.agent import QAAgent, format_response


class _FakeResult:
    """Mimics a Neo4j Result object supporting both .single() and iteration."""
    def __init__(self, records):
        self._records = records
    def single(self):
        return self._records[0] if self._records else None
    def __iter__(self):
        return iter(self._records)


def _mock_neo4j():
    client = MagicMock()
    client.vector_search.return_value = [
        {"props": {"file_path": "src/main.py", "start_line": 10, "end_line": 20, "content": "def hello():"}, "score": 0.95},
        {"props": {"file_path": "src/utils.py", "start_line": 1, "end_line": 5, "content": "import os"}, "score": 0.80},
    ]
    client.get_skill_evidence.return_value = [
        {"file_path": "src/app.py", "start_line": 5, "end_line": 15, "content": "class App:"},
    ]
    client.get_competency_map.return_value = [
        {"domain": "AI & Machine Learning", "category": "LLM & Generative AI",
         "skill": "LLM Integration", "proficiency": "extensive", "evidence_count": 42},
        {"domain": "Backend Engineering", "category": "Web Frameworks",
         "skill": "FastAPI", "proficiency": "extensive", "evidence_count": 38},
    ]
    client.get_repo_overview.return_value = {
        "name": "Agent_Blackwell", "path": "/repos/Agent_Blackwell",
        "file_count": 15,
        "sample_files": ["src/agent.py", "src/orchestrator.py"],
        "top_skills": [{"skill": "LLM Integration", "proficiency": "extensive",
                        "snippet_count": 12, "total_lines": 450}],
    }
    client.get_connected_snippets.return_value = [
        {"file_path": "src/agent.py", "snippet_name": "AgentBase", "start_line": 1, "end_line": 30,
         "content": "class AgentBase:", "proficiency": "extensive", "related_skills": ["Design Patterns"]},
    ]
    session = MagicMock()
    session.run.return_value = _FakeResult([
        {"name": "Chris", "labels": ["Engineer"], "props": {"name": "Chris", "email": "chris@test.com"}},
    ])
    client.driver.session.return_value.__enter__ = MagicMock(return_value=session)
    client.driver.session.return_value.__exit__ = MagicMock(return_value=False)
    return client


def _mock_chat():
    client = MagicMock()
    return client


def _mock_embed():
    client = MagicMock()
    client.embed.return_value = [[0.1] * 1024]
    return client


def _make_chat_response(content=None, tool_calls=None):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.choices[0].message.tool_calls = tool_calls
    return response


def _make_tool_call(name, arguments, call_id="call_1"):
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc


def test_search_tools():
    neo4j = _mock_neo4j()
    embed = _mock_embed()

    results = search_code("python async", neo4j, embed)
    assert len(results) == 2
    assert results[0]["file_path"] == "src/main.py"
    assert results[0]["score"] == 0.95
    embed.embed.assert_called_once_with(["python async"], input_type="query")
    neo4j.vector_search.assert_called_once()

    results = get_evidence("Python", neo4j)
    assert len(results) == 1
    assert results[0]["file_path"] == "src/app.py"
    neo4j.get_skill_evidence.assert_called_once_with("Python")

    results = search_resume("Chris", neo4j)
    assert len(results) == 1
    assert results[0]["labels"] == ["Engineer"]
    assert results[0]["name"] == "Chris"


def test_react_loop():
    neo4j = _mock_neo4j()
    chat = _mock_chat()
    embed = _mock_embed()

    tool_response = _make_chat_response(
        tool_calls=[_make_tool_call("search_code", {"query": "python"})]
    )
    final_response = _make_chat_response(content="The engineer demonstrates Python skills.")

    chat.chat = MagicMock(side_effect=[tool_response, final_response])

    agent = QAAgent(neo4j, chat, embed)
    result = agent.answer("Does this engineer know Python?")

    assert "The engineer demonstrates Python skills." in result
    # 2 ReAct calls + curate/annotate calls
    assert chat.chat.call_count >= 2
    first_call_kwargs = chat.chat.call_args_list[0]
    tools_arg = first_call_kwargs[0][1] if len(first_call_kwargs[0]) > 1 else first_call_kwargs[1].get("tools")
    assert tools_arg is not None


def test_react_loop_max_calls():
    neo4j = _mock_neo4j()
    chat = _mock_chat()
    embed = _mock_embed()

    tool_resp = _make_chat_response(
        tool_calls=[_make_tool_call("search_code", {"query": "test"}, f"call_1")]
    )
    final_resp = _make_chat_response(content="Final answer after max calls.")

    chat.chat = MagicMock(side_effect=[tool_resp, tool_resp, tool_resp, tool_resp, final_resp])

    agent = QAAgent(neo4j, chat, embed)
    result = agent.answer("complex question")

    assert "Final answer after max calls." in result
    # 5 ReAct calls + curate/annotate calls
    assert chat.chat.call_count >= 5


def test_response_formatting():
    evidence = [
        {"file_path": "src/a.py", "start_line": 1, "end_line": 10, "content": "class Foo:", "score": 0.9},
        {"file_path": "src/b.py", "start_line": 5, "end_line": 15, "content": "def bar():", "score": 0.8},
        {"file_path": "src/c.py", "start_line": 20, "end_line": 30, "content": "async def baz():", "score": 0.7},
    ]
    result = format_response("Engineer knows Python.", evidence)
    assert "`src/a.py:L1`" in result
    assert "`src/b.py:L5`" in result
    assert "Confidence: Strong (3 code examples)" in result

    result = format_response("Some skill.", evidence[:1])
    assert "Confidence: Partial (1 code example)" in result

    result = format_response("No evidence found for this claim.", [])
    assert "Confidence: None (0 code examples)" in result
    assert "No evidence found" in result


def test_response_formatting_with_curation():
    evidence = [
        {"file_path": "src/agent.py", "start_line": 1, "end_line": 50,
         "content": "class AgentOrchestrator:", "score": 0.9, "repo": "multi-agent"},
        {"file_path": "src/utils.py", "start_line": 5, "end_line": 10,
         "content": "def format():", "score": 0.8, "repo": "tools"},
    ]
    curation = [
        {"mode": "link", "explanation": "Orchestrates multi-agent coordination with fault tolerance"},
        {"mode": "inline", "explanation": "Clean utility pattern"},
    ]
    result = format_response("Strong engineer.", evidence, curation=curation)
    # Link mode: explanation but no code block for first item
    assert "Orchestrates multi-agent" in result
    # Inline mode: code block for second item
    assert "```\ndef format():\n```" in result
    assert "Confidence:" in result


def test_streaming():
    neo4j = _mock_neo4j()
    chat = _mock_chat()
    embed = _mock_embed()

    tool_response = _make_chat_response(
        tool_calls=[_make_tool_call("search_code", {"query": "python"})]
    )
    final_response = _make_chat_response(content="Streaming answer.")

    chat.chat = MagicMock(side_effect=[tool_response, final_response])

    agent = QAAgent(neo4j, chat, embed)
    chunks = list(agent.answer_stream("Does this engineer know Python?"))

    assert any("Searching for:" in c for c in chunks if isinstance(c, str))
    assert any("Streaming answer." in c for c in chunks if isinstance(c, str))
    assert any("Confidence:" in c for c in chunks if isinstance(c, str))


def test_skill_inventory_in_prompt():
    neo4j = _mock_neo4j()
    chat = _mock_chat()
    embed = _mock_embed()
    agent = QAAgent(neo4j, chat, embed)
    assert "LLM Integration" in agent.system_prompt
    assert "extensive" in agent.system_prompt
    assert "FastAPI" in agent.system_prompt
    neo4j.get_competency_map.assert_called_once()


def test_repo_overview_tool():
    neo4j = _mock_neo4j()
    result = get_repo_overview("Agent_Blackwell", neo4j)
    assert result["name"] == "Agent_Blackwell"
    assert len(result["top_skills"]) == 1
    assert result["top_skills"][0]["skill"] == "LLM Integration"
    neo4j.get_repo_overview.assert_called_once_with("Agent_Blackwell")


def test_repo_overview_not_found():
    neo4j = _mock_neo4j()
    neo4j.get_repo_overview.return_value = None
    result = get_repo_overview("nonexistent", neo4j)
    assert "error" in result


def test_connected_evidence_tool():
    neo4j = _mock_neo4j()
    result = get_connected_evidence("LLM Integration", "Agent_Blackwell", neo4j)
    assert len(result) == 1
    assert result[0]["file_path"] == "src/agent.py"
    assert result[0]["repo"] == "Agent_Blackwell"
    assert result[0]["related_skills"] == ["Design Patterns"]
    neo4j.get_connected_snippets.assert_called_once_with("LLM Integration", "Agent_Blackwell")


def test_dispatch_new_tools():
    neo4j = _mock_neo4j()
    chat = _mock_chat()
    embed = _mock_embed()
    agent = QAAgent(neo4j, chat, embed)

    result = json.loads(agent._execute_tool("get_repo_overview", {"repo_name": "Agent_Blackwell"}))
    assert result["name"] == "Agent_Blackwell"

    result = json.loads(agent._execute_tool("get_connected_evidence",
                                            {"skill_name": "LLM Integration", "repo_name": "Agent_Blackwell"}))
    assert isinstance(result, list)
    assert len(result) == 1


def test_curate_evidence():
    neo4j = _mock_neo4j()
    chat = _mock_chat()
    embed = _mock_embed()

    # Mock chat.chat() to return OpenAI-shaped response for curation
    curation_response = _make_chat_response(content=json.dumps([
        {"index": 0, "action": "keep", "mode": "inline", "explanation": "Impressive orchestration"},
        {"index": 1, "action": "drop", "mode": "inline", "explanation": ""},
    ]))
    chat.chat = MagicMock(return_value=curation_response)

    agent = QAAgent(neo4j, chat, embed)
    evidence = [
        {"file_path": "a.py", "content": "class Orchestrator:", "repo": "proj"},
        {"file_path": "b.py", "content": "x = 1", "repo": "proj"},
    ]
    curated, meta = agent._curate_evidence("question", evidence)
    assert len(curated) == 1
    assert curated[0]["file_path"] == "a.py"
    assert meta[0]["mode"] == "inline"
    assert "Impressive" in meta[0]["explanation"]
