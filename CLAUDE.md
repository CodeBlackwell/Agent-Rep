# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Prerequisites
docker compose up -d          # Start Neo4j (required for app + tests)
uv sync                       # Install dependencies

# Development
just dev                      # Run FastAPI dev server on :7860
uv run pytest tests/ -v       # Run all tests (43 tests, ~0.2s)
uv run pytest tests/test_qa.py::test_react_loop -v  # Run single test

# Ingestion
uv run python -m src.ingestion.cli --resume path/to/resume.pdf --repos https://github.com/user/repo
uv run python -m src.ingestion.cli --resume path/to/resume.pdf --github-user username

# Re-embed (context generation + embeddings, idempotent, all providers in parallel)
uv run python scripts/reembed.py                        # auto-detects: nim + voyage if keys set
uv run python scripts/reembed.py --providers voyage      # just voyage
uv run python scripts/reembed.py --providers nim voyage   # explicit both

# Provider overrides
CHAT_PROVIDER=anthropic EMBED_PROVIDER=voyage just dev    # Anthropic pipeline
LOG_LEVEL=DEBUG just dev                                  # Verbose logging
```

## Architecture

**Dual-provider system** toggled via env vars (`CHAT_PROVIDER`, `EMBED_PROVIDER`). NIM is default (free). Anthropic+Voyage is the quality path. `build_clients(settings)` in `src/core/client_factory.py` returns all four clients as a dict.

### Model Selection Strategy

The system deliberately uses different models at different stages:

- **Ingestion always uses Sonnet** — Context generation and skill classification run once per snippet and permanently affect embedding quality. `ingestion_chat_client` is hardcoded to Sonnet in `client_factory.py` (falls back to Nemotron if no Anthropic key). This is the highest-leverage LLM work: better context descriptions → better vector search for every future query.
- **Queries use Haiku 4.5** — ReAct loop, evidence curation, and answer generation run per request. A/B tested against Sonnet across multi-turn conversations: Haiku matches quality while being 4.8x cheaper and 2.1x faster. The embedding pipeline does the heavy lifting; the query model just orchestrates tools and synthesizes.
- **`CLAUDE_MODEL` env var controls query model only** — ingestion is always Sonnet regardless of this setting.

**Provider matrix:**

| Stage | NIM Pipeline | Anthropic Pipeline |
|---|---|---|
| Query chat (ReAct, curation) | Nemotron 49B | Claude Haiku 4.5 |
| Embeddings | EmbedQA 1B | Voyage-3.5 |
| Ingestion chat (classify, context) | Sonnet → fallback Nemotron | Claude Sonnet |

**All chat clients share the same interface:** `.chat(messages, tools=None, purpose="")` returning OpenAI-shaped `SimpleNamespace` with `.choices[0].message.content` and `.tool_calls`. `ClaudeChatClient` adapts Anthropic's format internally. The `purpose` kwarg is for logger tagging — clients that don't support it ignore it via `**kwargs`.

### Ingestion Pipeline

`cli.py` → `graph_builder.py` per repo:

1. **Parse** — tree-sitter extracts CodeChunks (functions/classes) from source files
2. **Classify** — Sonnet maps each chunk to skills from the taxonomy (`skill_taxonomy.py`)
3. **Generate context** — Sonnet writes a dense paragraph per snippet for embedding augmentation, stored as `cs.context` on the node
4. **Embed** — `(context + metadata preamble + code)` → vector, stored per provider (`embedding_nim` / `embedding_voyage`)
5. **Link** — Cypher creates graph edges (File→CodeSnippet→Skill) with git dates

### Knowledge Graph (Neo4j)

```
Engineer -[:OWNS]-> Repository -[:CONTAINS]-> File -[:CONTAINS]-> CodeSnippet -[:DEMONSTRATES]-> Skill
Domain -[:CONTAINS]-> Category -[:CONTAINS]-> Skill
Engineer -[:CLAIMS]-> Skill  (from resume)
Engineer -[:HELD]-> Role -[:AT]-> Company
```

Each `CodeSnippet` node has: `content`, `context` (Sonnet description), `embedding_nim`, `embedding_voyage`, `start_line`, `end_line`, `language`.

Proficiency levels computed from evidence counts: extensive (≥10 snippets + ≥2 repos), moderate (≥3), minimal (≥1).

### Query Pipeline

`QAAgent` runs a ReAct loop (up to 4 tool calls) with 6 tools: `search_code` (vector search), `get_evidence` (skill lookup), `search_resume`, `find_gaps`, `get_repo_overview`, `get_connected_evidence`. After the loop, `_curate_evidence` selects the most impressive snippets with inline/link display modes. Responses stream via SSE at `/api/chat`.

**Conversation history:** `answer_stream(question, history=)` accepts prior turns. The app stores condensed Q&A pairs (answer text only, no evidence/tool internals) per session, keyed by session ID. The frontend sends `session_id` on follow-up requests. History is injected between the system prompt and the new question so the model can resolve references like "tell me more about that." Server-side LRU eviction at 200 sessions, max 20 turns per session.

The stored `context` field flows through the entire query path — tool results include it, the curator sees it, and it's used as fallback explanation in the final display.

### JD Match Pipeline

`JDMatchAgent` extracts requirements from job description text, embeds each requirement for vector search, computes per-requirement confidence (Strong/Partial/None) boosted by proficiency, then summarizes.

### SQLite Persistence (`src/core/db.py`)

`Database` class provides persistent storage for conversations and logs at `data/showmeoff.db` (configurable via `DB_PATH`). Two tables:

- **`conversations`** — individual messages (session_id, role, content, metadata JSON, created_at). Keyed by session_id for multi-turn history retrieval.
- **`logs`** — structured log entries (timestamp, level, event, session_id, fields JSON). Mirrors the JSONL output with indexed columns for querying.

Thread-safe via `threading.local()` per-thread connections with WAL mode. Created by `build_clients()` and returned in the clients dict as `"db"`.

**API endpoints:**
- `GET /api/sessions` — list past conversations (paginated)
- `GET /api/sessions/{session_id}` — full message history for a session
- `GET /api/logs?session_id=&event=&level=` — query logs with filters

### Structured Logger

`src/core/logger.py` provides structured logging with session auditing:

- **Session context** via `ContextVar` — each request gets a `session_id` with accumulated cost, tokens, latency
- **Cost estimation** from per-model pricing tables (Sonnet $3/$15, Haiku $1/$5, Voyage $0.06, NIM free)
- **Three outputs**: colored console + JSON lines at `logs/app.jsonl` + SQLite (attached via `logger.attach_db(db)` at startup)
- **Log levels**: `DEBUG` (raw payloads, tool results), `INFO` (LLM calls, sessions, tools), `WARNING` (retries, fallbacks), `ERROR` (API failures)
- All clients log automatically — `log_llm_call()`, `log_embed_call()`, `log_tool_call()` etc.
- Use `logger.start_session()` / `logger.end_session()` to wrap request handlers
- Import as `from src.core import logger` then call `logger.info("event.name", key=value)`

## Key Conventions

- **Client params are split:** `chat_client` for LLM calls, `embed_client` for embeddings. Never pass a single "nim_client" for both.
- **`ingestion_chat_client`** is always Sonnet when `ANTHROPIC_API_KEY` is set, regardless of `CLAUDE_MODEL`. Falls back to NIM. This is separate from `chat_client` which follows `CHAT_PROVIDER` + `CLAUDE_MODEL`.
- **Concurrency is provider-aware:** `ClaudeChatClient` gets higher thread pools (4-8 workers) vs NIM (2 workers) because of rate limit differences.
- **Embeddings are provider-namespaced:** Neo4j stores `embedding_nim` and `embedding_voyage` as separate properties with separate vector indices. Switching `EMBED_PROVIDER` requires running `reembed.py`.
- **No embedding without context:** `reembed.py` only embeds snippets that have a Sonnet-generated `context` field. Phase 1 generates missing contexts, Phase 2 embeds in parallel across providers.
- **No print statements:** All output goes through `src/core/logger`. Use `logger.info()`, `logger.warning()`, etc.

## Environment Variables

| Var | Default | Notes |
|---|---|---|
| `CHAT_PROVIDER` | `nim` | `nim` or `anthropic` |
| `EMBED_PROVIDER` | `nim` | `nim` or `voyage` |
| `NVIDIA_API_KEY` | — | Required for NIM |
| `ANTHROPIC_API_KEY` | — | Required when `CHAT_PROVIDER=anthropic`; also enables Sonnet for ingestion |
| `VOYAGE_API_KEY` | — | Required when `EMBED_PROVIDER=voyage` |
| `CLAUDE_MODEL` | `claude-haiku-4-5-20251001` | Query model only — ingestion always uses Sonnet |
| `DB_PATH` | `data/showmeoff.db` | SQLite database for conversations and logs |
| `NEO4J_URI` | `bolt://localhost:7687` | |
| `NEO4J_PASSWORD` | `showmeoff` | |
| `GITHUB_TOKEN` | — | For private repo access |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
