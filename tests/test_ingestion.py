import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.code_parser import CodeChunk, parse_file

FIXTURES = Path(__file__).parent / "fixtures"


# --- US-010: Tree-sitter code parser ---

def test_parse_python_file():
    chunks = parse_file(FIXTURES / "sample.py")
    names = [c.name for c in chunks]
    assert "greet" in names
    assert "Calculator" in names
    for c in chunks:
        assert c.language == "py"
        assert c.file_path.endswith("sample.py")
        assert c.start_line >= 1
        assert c.end_line >= c.start_line
        assert len(c.content) > 0


def test_parse_js_file():
    chunks = parse_file(FIXTURES / "sample.js")
    names = [c.name for c in chunks]
    assert "greet" in names
    assert "Animal" in names
    for c in chunks:
        assert c.language == "js"


def test_fallback_parse(tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("block one\nline two\n\nblock two\nline four")
    chunks = parse_file(f)
    assert len(chunks) == 2
    assert chunks[0].language == "txt"


# --- US-011: Neo4j graph builder ---

def test_build_graph(tmp_path):
    from src.ingestion.graph_builder import build_graph

    # Create a mini repo
    (tmp_path / "hello.py").write_text("def hello():\n    pass\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("junk")

    mock_neo4j = MagicMock()
    mock_neo4j.driver.session.return_value.__enter__ = MagicMock()
    mock_neo4j.driver.session.return_value.__exit__ = MagicMock(return_value=False)

    mock_nim = MagicMock()
    mock_nim.embed.return_value = [[0.1] * 1024]

    build_graph(tmp_path, mock_neo4j, mock_nim)

    # Verify session was used to run Cypher
    session = mock_neo4j.driver.session.return_value.__enter__.return_value
    assert session.run.call_count >= 2  # At least repo + file + snippet nodes


# --- US-012: Skill extraction ---

def test_extract_skills():
    from src.ingestion.skill_extractor import extract_skills

    mock_nim = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "FastAPI\nPydantic\nAsync Python"
    mock_nim.chat.return_value = mock_response

    chunk = CodeChunk(
        content="async def get_users():\n    return await db.fetch_all()",
        file_path="app.py",
        start_line=1,
        end_line=2,
        language="py",
        name="get_users",
    )

    skills = extract_skills(chunk, mock_nim)
    assert len(skills) == 3
    assert "FastAPI" in skills
    assert "Async Python" in skills


# --- US-013: Resume parser ---

def test_parse_resume():
    from src.ingestion.resume_parser import parse_resume

    mock_neo4j = MagicMock()
    mock_neo4j.driver.session.return_value.__enter__ = MagicMock()
    mock_neo4j.driver.session.return_value.__exit__ = MagicMock(return_value=False)

    structured = {
        "name": "Jane Smith",
        "roles": [
            {"title": "Senior Software Engineer", "company": "Acme Corp", "dates": "2020-Present"},
            {"title": "Software Engineer", "company": "StartupXYZ", "dates": "2017-2019"},
        ],
        "skills": ["Python", "FastAPI", "Kafka", "React"],
    }

    mock_nim = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps(structured)
    mock_nim.chat.return_value = mock_response

    parse_resume(FIXTURES / "sample_resume.txt", mock_neo4j, mock_nim)

    session = mock_neo4j.driver.session.return_value.__enter__.return_value
    assert session.run.call_count >= 3  # Engineer + roles + skills
