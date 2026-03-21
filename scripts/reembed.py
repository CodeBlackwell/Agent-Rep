"""Re-embed all CodeSnippet nodes with LLM-generated contextual descriptions. Idempotent.

Three-phase pipeline:
  1. Generate contextual descriptions via chat_client (stored on node as `context`)
  2. Embed for each configured provider (only snippets WITH context are embedded)
  3. Runs all providers in a single invocation — no need to call separately

Context generation is concurrent — auto-scales based on provider:
  - Anthropic (ClaudeChatClient): 8 concurrent workers (Tier 2: 1,000 RPM)
  - NIM: 2 concurrent workers (~40 RPM free tier)

Usage:
  uv run python scripts/reembed.py                    # all configured providers
  uv run python scripts/reembed.py --providers voyage  # only voyage
  uv run python scripts/reembed.py --providers nim     # only nim
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm
from src.config.settings import Settings
from src.core.claude_chat_client import ClaudeChatClient
from src.core.neo4j_client import Neo4jClient, EMBED_PROVIDERS
from src.core.nim_client import NimClient
from src.core.voyage_client import VoyageClient
from src.ingestion.context_generator import (
    CONTEXT_BATCH_SIZE, CONCURRENCY_ANTHROPIC, CONCURRENCY_NIM,
    _generate_batch,
)
from src.ingestion.graph_builder import build_preamble
from src.ingestion.skill_taxonomy import ALL_SKILLS

# Embedding batch sizes — tuned per provider's rate limits and throughput.
EMBED_BATCH = {"voyage": 128, "nim": 50}

FETCH_QUERY = """
MATCH (r:Repository)-[:CONTAINS]->(:File)-[:CONTAINS]->(cs:CodeSnippet)
OPTIONAL MATCH (cs)-[:DEMONSTRATES]->(sk:Skill)
RETURN cs.name AS name, cs.file_path AS file_path, cs.content AS content,
       cs.language AS language, r.name AS repo, collect(DISTINCT sk.name) AS skills,
       cs.context AS context
"""

SKILLS_LIST = ", ".join(ALL_SKILLS)


def _build_embed_client(provider: str, settings: Settings):
    """Build an embed client for the given provider."""
    if provider == "voyage":
        if not settings.voyage_api_key:
            raise ValueError("VOYAGE_API_KEY is required for voyage provider")
        return VoyageClient(settings.voyage_api_key)
    else:
        return NimClient(settings.nvidia_api_key)


def _build_chat_client(settings: Settings):
    """Build the ingestion chat client (Anthropic preferred, NIM fallback)."""
    if settings.anthropic_api_key:
        return ClaudeChatClient(settings.anthropic_api_key, model=settings.claude_model)
    return NimClient(settings.nvidia_api_key)


def _build_embed_text(row) -> str:
    """Assemble the full text to embed: context + metadata preamble + code."""
    preamble = build_preamble(
        row["name"], row["language"], row["file_path"],
        row["repo"], row["skills"],
    )
    context = row["context"] or ""
    parts = []
    if context:
        parts.append(context)
    parts.append(preamble)
    parts.append("Code:\n" + row["content"])
    return "\n".join(parts)


def _phase_context(rows, chat_client, neo: Neo4jClient):
    """Phase 1: Generate contextual descriptions for snippets that lack them."""
    needs_context = [r for r in rows if not r["context"]]
    if not needs_context:
        print(f"All {len(rows)} snippets already have context")
        return

    concurrency = (CONCURRENCY_ANTHROPIC if isinstance(chat_client, ClaudeChatClient)
                   else CONCURRENCY_NIM)
    print(f"Generating context for {len(needs_context)} snippets "
          f"({len(rows) - len(needs_context)} already have context) "
          f"[concurrency={concurrency}]")

    batches = []
    for i in range(0, len(needs_context), CONTEXT_BATCH_SIZE):
        batches.append(needs_context[i : i + CONTEXT_BATCH_SIZE])

    progress = tqdm(total=len(batches), desc="Context")

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(_generate_batch, [dict(r) for r in batch],
                        chat_client, SKILLS_LIST): batch
            for batch in batches
        }
        for future in as_completed(futures):
            batch = futures[future]
            progress.update(1)
            try:
                descriptions = future.result()
            except Exception as e:
                print(f"  Context batch failed: {e}")
                continue
            with neo.driver.session() as session:
                for row, desc in zip(batch, descriptions):
                    if desc:
                        session.run(
                            "MATCH (cs:CodeSnippet {name: $name, file_path: $fp}) "
                            "SET cs.context = $ctx",
                            name=row["name"], fp=row["file_path"], ctx=desc,
                        )

    progress.close()


def _phase_embed(rows, provider: str, embed_client, neo: Neo4jClient):
    """Phase 2: Embed snippets that have context for a given provider."""
    embed_prop = f"embedding_{provider}"
    batch_size = EMBED_BATCH.get(provider, 50)

    # Only embed snippets that have context
    eligible = [r for r in rows if r["context"]]
    if not eligible:
        print(f"  {provider}: No snippets with context to embed")
        return

    print(f"  {provider}: Embedding {len(eligible)} snippets into '{embed_prop}' "
          f"(batch size {batch_size})")

    for i in tqdm(range(0, len(eligible), batch_size),
                  desc=f"Embed [{provider}]"):
        batch = eligible[i : i + batch_size]
        texts = [_build_embed_text(r) for r in batch]
        embeddings = embed_client.embed(texts)

        with neo.driver.session() as session:
            for row, emb in zip(batch, embeddings):
                session.run(
                    f"MATCH (cs:CodeSnippet {{name: $name, file_path: $fp}}) "
                    f"SET cs.{embed_prop} = $embedding",
                    name=row["name"], fp=row["file_path"], embedding=emb,
                )


def main():
    parser = argparse.ArgumentParser(description="Re-embed code snippets with contextual descriptions")
    parser.add_argument("--providers", nargs="*", default=None,
                        help="Embed providers to run (default: all available). Options: nim, voyage")
    args = parser.parse_args()

    settings = Settings.load()

    # Determine which providers to run
    if args.providers:
        providers = args.providers
    else:
        # Auto-detect: always include nim, include voyage if key is set
        providers = ["nim"]
        if settings.voyage_api_key:
            providers.append("voyage")

    print(f"Providers: {', '.join(providers)}")

    neo = Neo4jClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    neo.init_schema()
    chat_client = _build_chat_client(settings)

    with neo.driver.session() as session:
        rows = list(session.run(FETCH_QUERY))

    print(f"Total snippets: {len(rows)}")

    # --- Phase 1: Context generation (shared across all providers) ---
    _phase_context(rows, chat_client, neo)

    # Refresh rows to pick up new contexts
    with neo.driver.session() as session:
        rows = list(session.run(FETCH_QUERY))

    # --- Phase 2: Embed all providers in parallel ---
    if len(providers) > 1:
        embed_threads = []
        with ThreadPoolExecutor(max_workers=len(providers)) as pool:
            for provider in providers:
                embed_client = _build_embed_client(provider, settings)
                embed_threads.append(
                    pool.submit(_phase_embed, rows, provider, embed_client, neo)
                )
            for future in as_completed(embed_threads):
                try:
                    future.result()
                except Exception as e:
                    print(f"  Embed failed: {e}")
    else:
        for provider in providers:
            embed_client = _build_embed_client(provider, settings)
            _phase_embed(rows, provider, embed_client, neo)

    neo.close()
    print("Done.")


if __name__ == "__main__":
    main()
