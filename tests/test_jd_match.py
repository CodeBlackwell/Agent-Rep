import json
from unittest.mock import MagicMock

from src.jd_match.parser import parse_requirements
from src.jd_match.matcher import MatchResult, match_requirement
from src.jd_match.agent import JDMatchAgent, MatchReport


def _mock_chat(chat_content="[]"):
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = chat_content
    client.chat.return_value = response
    return client


def _mock_embed(embed_result=None):
    client = MagicMock()
    client.embed.return_value = [embed_result or [0.1] * 1024]
    return client


def _mock_neo4j(vector_results=None):
    client = MagicMock()
    client.vector_search.return_value = vector_results or []
    return client


def test_parse_requirements():
    reqs = json.dumps(["Python 3+", "Kubernetes", "REST API design", "Python 3+"])
    chat = _mock_chat(chat_content=reqs)

    result = parse_requirements("We need a Python developer with K8s experience.", chat)

    assert isinstance(result, list)
    assert "Python 3+" in result
    assert "Kubernetes" in result
    assert "REST API design" in result
    # Deduplication: "Python 3+" appears only once
    assert result.count("Python 3+") == 1
    chat.chat.assert_called_once()


def test_parse_requirements_markdown_fenced():
    fenced = '```json\n["React", "TypeScript"]\n```'
    chat = _mock_chat(chat_content=fenced)

    result = parse_requirements("Frontend role", chat)
    assert result == ["React", "TypeScript"]


def test_match_requirement():
    vector_hits = [
        {"props": {"file_path": "src/a.py", "start_line": 1, "end_line": 10, "content": "async def fetch():"}, "score": 0.9},
        {"props": {"file_path": "src/b.py", "start_line": 5, "end_line": 15, "content": "async def process():"}, "score": 0.8},
        {"props": {"file_path": "src/c.py", "start_line": 20, "end_line": 30, "content": "async def stream():"}, "score": 0.7},
    ]
    neo4j = _mock_neo4j(vector_results=vector_hits)
    embed = _mock_embed()

    result = match_requirement("Python async programming", neo4j, embed)

    assert isinstance(result, MatchResult)
    assert result.requirement == "Python async programming"
    assert result.confidence == "Strong"
    assert len(result.evidence) == 3
    assert result.evidence[0]["file_path"] == "src/a.py"
    embed.embed.assert_called_once_with(["Python async programming"], input_type="query")
    neo4j.vector_search.assert_called_once()


def test_match_requirement_partial():
    neo4j = _mock_neo4j(vector_results=[
        {"props": {"file_path": "src/x.py", "start_line": 1, "end_line": 5, "content": "code"}, "score": 0.9},
    ])
    embed = _mock_embed()

    result = match_requirement("Go concurrency", neo4j, embed)
    assert result.confidence == "Partial"
    assert len(result.evidence) == 1


def test_match_requirement_none():
    neo4j = _mock_neo4j(vector_results=[])
    embed = _mock_embed()

    result = match_requirement("Haskell monads", neo4j, embed)
    assert result.confidence == "None"
    assert len(result.evidence) == 0


def test_match_report():
    reqs_json = json.dumps(["Python", "Docker", "GraphQL"])
    vector_hits = [
        {"props": {"file_path": f"src/{i}.py", "start_line": i, "end_line": i + 10, "content": f"code_{i}"}, "score": 0.9}
        for i in range(3)
    ]
    neo4j = _mock_neo4j(vector_results=vector_hits)

    # First chat call returns parsed requirements, subsequent calls return summary
    responses = []
    for content in [reqs_json, reqs_json, reqs_json, reqs_json, "The candidate matches 100% of requirements."]:
        r = MagicMock()
        r.choices = [MagicMock()]
        r.choices[0].message.content = content
        responses.append(r)

    chat = _mock_chat()
    chat.chat.side_effect = responses
    embed = _mock_embed()

    agent = JDMatchAgent(neo4j, chat, embed)
    report = agent.match("Looking for a Python Docker GraphQL developer")

    assert isinstance(report, MatchReport)
    assert len(report.requirements) == 3
    assert all(isinstance(r, MatchResult) for r in report.requirements)
    # All 3 reqs have 3 evidence items each → all Strong → 100%
    assert report.match_percentage == 100.0
    assert isinstance(report.summary, str)
    assert len(report.summary) > 0
