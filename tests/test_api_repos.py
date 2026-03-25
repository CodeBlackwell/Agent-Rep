"""Tests for repository detail and repo-scoped skill snippet endpoints."""

from unittest.mock import MagicMock, patch


def _mock_neo4j():
    """Build a mock Neo4j client with a programmable session.run."""
    client = MagicMock()
    session = MagicMock()
    client.driver.session.return_value.__enter__ = MagicMock(return_value=session)
    client.driver.session.return_value.__exit__ = MagicMock(return_value=False)
    return client, session


def _patch_app(neo4j, session):
    """Patch src.app module globals so we can import without real infra."""
    mock_db = MagicMock()
    mock_db.check_rate_limit.return_value = (True, 99)
    mock_db.cleanup_rate_limits.return_value = None

    clients = {
        "neo4j_client": neo4j,
        "chat_client": MagicMock(),
        "embed_client": MagicMock(),
        "ingestion_chat_client": MagicMock(),
        "db": mock_db,
    }
    return clients, mock_db


# ---------------------------------------------------------------------------
# Helpers to build fake Cypher result rows
# ---------------------------------------------------------------------------

STATIC_FILE_ROW = {
    "domain": "Frontend",
    "skill": "DOM Manipulation",
    "snippets": 3,
    "files": [{"file": "src/static/graph.js", "start": 10, "branch": "main"}],
}

NORMAL_FILE_ROW = {
    "domain": "AI & Machine Learning",
    "skill": "LLM Integration",
    "snippets": 5,
    "files": [{"file": "src/qa/agent.py", "start": 42, "branch": "main"}],
}

VENDOR_FILE_ROW = {
    "domain": "Frontend",
    "skill": "Charting",
    "snippets": 1,
    "files": [{"file": "vendor/d3.min.js", "start": 1, "branch": "main"}],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAssetPathFilter:
    """Verify _SKIP_ASSET_PATHS is present in the right Cypher queries."""

    def test_filter_string_excludes_static(self):
        from src.app import _SKIP_ASSET_PATHS
        assert "'static'" in _SKIP_ASSET_PATHS
        assert "'public'" in _SKIP_ASSET_PATHS
        assert "'vendor'" in _SKIP_ASSET_PATHS
        assert "'generated'" in _SKIP_ASSET_PATHS
        assert "'assets'" in _SKIP_ASSET_PATHS
        assert ".min.js" in _SKIP_ASSET_PATHS
        assert ".min.css" in _SKIP_ASSET_PATHS


class TestRepoSkillSnippetsEndpoint:
    """Test GET /api/repositories/{repo}/skills/{skill}/snippets."""

    def test_returns_snippets(self):
        neo4j, session = _mock_neo4j()
        session.run.return_value.data.return_value = [
            {
                "branch": "main", "private": False,
                "path": "src/qa/agent.py", "snippet_name": "answer_stream",
                "context": "Streams answers via SSE", "content": "def answer_stream(): pass",
                "start_line": 10, "end_line": 25, "lang": "py",
            },
        ]
        clients, mock_db = _patch_app(neo4j, session)

        with patch.dict("src.app.clients", clients):
            from src.app import _repo_skill_snippets
            _repo_skill_snippets.cache_clear()
            result = _repo_skill_snippets("PROVE", "LLM Integration")

        assert len(result) == 1
        assert result[0]["path"] == "src/qa/agent.py"
        assert result[0]["snippet_name"] == "answer_stream"
        assert result[0]["content"] == "def answer_stream(): pass"
        assert "github.com" in result[0]["url"]

    def test_private_repo_redacts_content(self):
        neo4j, session = _mock_neo4j()
        session.run.return_value.data.return_value = [
            {
                "branch": "main", "private": True,
                "path": "src/core/secret.py", "snippet_name": "decrypt",
                "context": "Decrypts tokens", "content": "def decrypt(): secret",
                "start_line": 1, "end_line": 5, "lang": "py",
            },
        ]
        clients, _ = _patch_app(neo4j, session)

        with patch.dict("src.app.clients", clients):
            from src.app import _repo_skill_snippets
            _repo_skill_snippets.cache_clear()
            result = _repo_skill_snippets("gateway", "Security")

        assert result[0]["content"] == ""
        assert result[0]["private"] is True

    def test_cache_hit_skips_neo4j(self):
        neo4j, session = _mock_neo4j()
        session.run.return_value.data.return_value = [
            {
                "branch": "main", "private": False,
                "path": "src/app.py", "snippet_name": "main",
                "context": "Entry point", "content": "app = FastAPI()",
                "start_line": 1, "end_line": 1, "lang": "py",
            },
        ]
        clients, _ = _patch_app(neo4j, session)

        with patch.dict("src.app.clients", clients):
            from src.app import _repo_skill_snippets
            _repo_skill_snippets.cache_clear()
            _repo_skill_snippets("CacheTest", "Python")
            _repo_skill_snippets("CacheTest", "Python")

        assert session.run.call_count == 1

    def test_cypher_includes_asset_filter(self):
        neo4j, session = _mock_neo4j()
        session.run.return_value.data.return_value = []
        clients, _ = _patch_app(neo4j, session)

        with patch.dict("src.app.clients", clients):
            from src.app import _repo_skill_snippets
            _repo_skill_snippets.cache_clear()
            _repo_skill_snippets("PROVE", "Testing")

        cypher = session.run.call_args[0][0]
        assert "static" in cypher
        assert ".min.js" in cypher
