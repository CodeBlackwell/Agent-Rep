# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Prerequisites
docker compose up -d          # Start Neo4j (required for app + tests)
uv sync                       # Install dependencies

# Development
just dev                      # Run FastAPI dev server on :7860
uv run pytest tests/ -v       # Run all tests (33 tests, ~0.2s)
uv run pytest tests/test_qa.py::test_react_loop -v  # Run single test

# Ingestion
uv run python -m src.ingestion.cli --resume path/to/resume.pdf --repos https://github.com/user/repo
uv run python -m src.ingestion.cli --resume path/to/resume.pdf --github-user username

# Re-embed (generates LLM context descriptions + embeddings, idempotent)
uv run python scripts/reembed.py                              # default providers
EMBED_PROVIDER=voyage CHAT_PROVIDER=anthropic uv run python scripts/reembed.py  # Anthropic stack
```

## Architecture

**Dual-provider system** toggled via env vars (`CHAT_PROVIDER`, `EMBED_PROVIDER`). NIM is default (free). Anthropic+Voyage is the quality path. `build_clients(settings)` in `src/core/client_factory.py` returns all four clients as a dict.

**Provider matrix:**

| Capability | NIM Pipeline | Anthropic Pipeline |
|---|---|---|
| Chat (ReAct, curation, summaries) | Nemotron 49B | Claude Sonnet |
| Embeddings | EmbedQA 1B | Voyage-3.5 |
| Ingestion chat (classify, parse) | Sonnet → fallback Nemotron | Claude Sonnet |

**All chat clients share the same interface:** `.chat(messages, tools=None)` returning OpenAI-shaped `SimpleNamespace` with `.choices[0].message.content` and `.tool_calls`. `ClaudeChatClient` adapts Anthropic's format internally.

### Ingestion Pipeline

`cli.py` → `graph_builder.py` per repo:

1. **Parse** — tree-sitter extracts CodeChunks (functions/classes) from source files
2. **Classify** — LLM maps each chunk to skills from the taxonomy (`skill_taxonomy.py`)
3. **Generate context** — LLM writes a dense paragraph per snippet for embedding augmentation, stored as `cs.context` on the node
4. **Embed** — `(context + metadata preamble + code)` → vector, stored per provider (`embedding_nim` / `embedding_voyage`)
5. **Link** — Cypher creates graph edges (File→CodeSnippet→Skill) with git dates

### Knowledge Graph (Neo4j)

```
Engineer -[:OWNS]-> Repository -[:CONTAINS]-> File -[:CONTAINS]-> CodeSnippet -[:DEMONSTRATES]-> Skill
Domain -[:CONTAINS]-> Category -[:CONTAINS]-> Skill
Engineer -[:CLAIMS]-> Skill  (from resume)
Engineer -[:HELD]-> Role -[:AT]-> Company
```

Each `CodeSnippet` node has: `content`, `context` (LLM description), `embedding_nim`, `embedding_voyage`, `start_line`, `end_line`, `language`.

Proficiency levels computed from evidence counts: extensive (≥10 snippets + ≥2 repos), moderate (≥3), minimal (≥1).

### Query Pipeline

`QAAgent` runs a ReAct loop (up to 4 tool calls) with 6 tools: `search_code` (vector search), `get_evidence` (skill lookup), `search_resume`, `find_gaps`, `get_repo_overview`, `get_connected_evidence`. After the loop, `_curate_evidence` selects the most impressive snippets with inline/link display modes. Responses stream via SSE at `/api/chat`.

The stored `context` field flows through the entire query path — tool results include it, the curator sees it, and it's used as fallback explanation in the final display.

### JD Match Pipeline

`JDMatchAgent` extracts requirements from job description text, embeds each requirement for vector search, computes per-requirement confidence (Strong/Partial/None) boosted by proficiency, then summarizes.

## Key Conventions

- **Client params are split:** `chat_client` for LLM calls, `embed_client` for embeddings. Never pass a single "nim_client" for both.
- **`ingestion_chat_client`** prefers Anthropic (Sonnet) when `ANTHROPIC_API_KEY` is set, falls back to NIM. This is separate from `chat_client` which follows `CHAT_PROVIDER`.
- **Concurrency is provider-aware:** `ClaudeChatClient` gets higher thread pools (4-8 workers) vs NIM (2 workers) because of rate limit differences.
- **Embeddings are provider-namespaced:** Neo4j stores `embedding_nim` and `embedding_voyage` as separate properties with separate vector indices. Switching `EMBED_PROVIDER` requires running `reembed.py`.
- **`reembed.py` is two-phase:** Phase 1 generates `context` (LLM, concurrent, persisted per-batch for resumability). Phase 2 embeds (context + preamble + code). Phase 1 is skipped if contexts already exist.

## Environment Variables

| Var | Default | Notes |
|---|---|---|
| `CHAT_PROVIDER` | `nim` | `nim` or `anthropic` |
| `EMBED_PROVIDER` | `nim` | `nim` or `voyage` |
| `NVIDIA_API_KEY` | — | Required for NIM |
| `ANTHROPIC_API_KEY` | — | Required when `CHAT_PROVIDER=anthropic`; also enables Sonnet for ingestion |
| `VOYAGE_API_KEY` | — | Required when `EMBED_PROVIDER=voyage` |
| `CLAUDE_MODEL` | `claude-sonnet-4-20250514` | Any Claude model ID |
| `NEO4J_URI` | `bolt://localhost:7687` | |
| `NEO4J_PASSWORD` | `showmeoff` | |
| `GITHUB_TOKEN` | — | For private repo access |
