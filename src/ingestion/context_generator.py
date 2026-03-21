"""Generate LLM contextual descriptions for code snippets to improve embedding quality.

The descriptions bridge the vocabulary gap between natural-language queries
("Does this engineer know Kubernetes?") and raw source code. Each description
is prepended to the snippet before embedding so vector search can match on
concepts the code demonstrates but never names explicitly.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.core import logger
from src.core.claude_chat_client import ClaudeChatClient

# 10 snippets per LLM call — balances throughput against prompt size.
CONTEXT_BATCH_SIZE = 10

# Anthropic Tier 2+ (1,000 RPM) can handle heavy concurrency.
# NIM free tier (~40 RPM) and Anthropic Tier 1 (50 RPM) need to stay conservative.
# We probe the actual limit via rate-limit response headers when available,
# but fall back to these safe defaults.
CONCURRENCY_ANTHROPIC = 8
CONCURRENCY_NIM = 2

CONTEXT_SYSTEM = """\
You annotate code snippets for a software-engineering portfolio search engine.

For each numbered snippet, write a **single dense paragraph** (2-4 sentences) that a \
recruiter or hiring manager's query would match against. Include:

1. **What it does** — the business / system purpose (e.g. "handles OAuth refresh token rotation").
2. **Engineering patterns** — name the design patterns, paradigms, or techniques \
   (e.g. "repository pattern", "exponential backoff", "decorator-based middleware").
3. **Skill keywords** — restate the demonstrated skills using standard industry vocabulary \
   matching this list when applicable: {skills_list}
4. **Quality signals** — note production-quality traits if present \
   (error handling, idempotency, concurrency safety, test coverage, type safety).

Do NOT describe syntax or line-by-line logic. Focus on *what the code proves the \
engineer can build*.

Reply ONLY with a JSON object mapping snippet index (as string) to description string. \
No markdown fences, no explanation.\
"""


def generate_contexts(snippets: list[dict], chat_client,
                      skills_list: str = "",
                      concurrency: int | None = None) -> list[str]:
    """Generate contextual descriptions for a list of snippets.

    Each snippet dict should have: name, file_path, content, language, repo, skills.
    Returns a list of description strings, one per snippet.

    Concurrency is auto-detected from the chat_client type if not provided.
    """
    if concurrency is None:
        concurrency = (CONCURRENCY_ANTHROPIC if isinstance(chat_client, ClaudeChatClient)
                       else CONCURRENCY_NIM)

    # Build all batches
    batches = []
    for i in range(0, len(snippets), CONTEXT_BATCH_SIZE):
        batches.append((i, snippets[i : i + CONTEXT_BATCH_SIZE]))

    descriptions = [""] * len(snippets)

    if concurrency <= 1 or len(batches) <= 1:
        # Sequential path
        for offset, batch in batches:
            batch_descs = _generate_batch(batch, chat_client, skills_list)
            for j, desc in enumerate(batch_descs):
                descriptions[offset + j] = desc
    else:
        # Concurrent path
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {
                pool.submit(_generate_batch, batch, chat_client, skills_list): offset
                for offset, batch in batches
            }
            for future in as_completed(futures):
                offset = futures[future]
                try:
                    batch_descs = future.result()
                except Exception as e:
                    logger.error("context.batch_failed", error=str(e))
                    batch_descs = [""] * CONTEXT_BATCH_SIZE
                for j, desc in enumerate(batch_descs):
                    if offset + j < len(descriptions):
                        descriptions[offset + j] = desc

    return descriptions


def _generate_batch(snippets: list[dict], chat_client,
                    skills_list: str) -> list[str]:
    parts = []
    for idx, s in enumerate(snippets):
        preview = "\n".join(s.get("content", "").split("\n")[:30])
        skills = s.get("skills", [])
        skill_str = f" | Skills: {', '.join(skills)}" if skills else ""
        parts.append(
            f"[{idx}] {s.get('repo', '?')}/{s.get('file_path', '?')} "
            f"— {s.get('name', '?')}{skill_str}\n{preview}"
        )

    user_prompt = "Snippets:\n\n" + "\n\n".join(parts)
    system = CONTEXT_SYSTEM.format(skills_list=skills_list)

    try:
        t0 = time.perf_counter()
        response = chat_client.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ], purpose="context_generation")
        raw = response.choices[0].message.content
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw.strip())
        descs = [parsed.get(str(i), "") for i in range(len(snippets))]
        latency = int((time.perf_counter() - t0) * 1000)
        success = sum(1 for d in descs if d)
        logger.log_context_gen(batch_size=len(snippets), success=success,
                               failed=len(snippets) - success, latency_ms=latency)
        return descs
    except (json.JSONDecodeError, Exception) as e:
        logger.error("context.generation_failed", error=str(e),
                      batch_size=len(snippets))
        return [""] * len(snippets)
