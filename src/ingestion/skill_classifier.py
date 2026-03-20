import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.core.claude_chat_client import ClaudeChatClient
from src.ingestion.skill_taxonomy import ALL_SKILLS

BATCH_SIZE = 20
# Anthropic Tier 2+ can handle 1,000 RPM; NIM free tier caps at ~40 RPM.
CONCURRENCY_ANTHROPIC = 4
CONCURRENCY_NIM = 2
SECTION_LINES = 150
OVERLAP_LINES = 30  # shared context between sections
ALL_SKILLS_SET = set(ALL_SKILLS)

CLASSIFY_SYSTEM = (
    "You are a code skill classifier. Given code snippets, identify which skills "
    "from the provided list are demonstrated. Return ONLY valid JSON mapping "
    "snippet index to skill names. No explanation."
)


def _split_with_overlap(content: str) -> list[str]:
    """Split large content into overlapping sections so each has shared context."""
    lines = content.split("\n")
    if len(lines) <= SECTION_LINES:
        return [content]
    sections = []
    start = 0
    while start < len(lines):
        end = start + SECTION_LINES
        sections.append("\n".join(lines[start:end]))
        start = end - OVERLAP_LINES  # next section starts with overlap from this one
    return sections


def classify_chunks(chunks, chat_client) -> list[set[str]]:
    batches = [chunks[i:i + BATCH_SIZE] for i in range(0, len(chunks), BATCH_SIZE)]
    results = [None] * len(batches)
    concurrency = CONCURRENCY_ANTHROPIC if isinstance(chat_client, ClaudeChatClient) else CONCURRENCY_NIM

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(_classify_batch_full, b, chat_client): idx for idx, b in enumerate(batches)}
        for future in as_completed(futures):
            results[futures[future]] = future.result()

    return [skill for batch_result in results for skill in batch_result]


def _classify_batch_full(chunks, chat_client) -> list[set[str]]:
    """Classify a batch. Large snippets get split into overlapping sections, skills merged."""
    sections = []  # (chunk_index, section_text)
    for i, c in enumerate(chunks):
        for section in _split_with_overlap(c.content):
            sections.append((i, section))

    per_chunk_skills = [set() for _ in chunks]
    section_batches = [sections[j:j + BATCH_SIZE] for j in range(0, len(sections), BATCH_SIZE)]

    for sbatch in section_batches:
        batch_skills = _call_classifier(sbatch, chunks, chat_client)
        for (chunk_idx, _), skills in zip(sbatch, batch_skills):
            per_chunk_skills[chunk_idx] |= skills

    return per_chunk_skills


def _call_classifier(sections, chunks, chat_client) -> list[set[str]]:
    snippet_text = "\n\n".join(
        f"[{i}] ({chunks[idx].file_path if hasattr(chunks[idx], 'file_path') else ''}):\n{text}"
        for i, (idx, text) in enumerate(sections)
    )
    user_prompt = (
        f"Skills list: {json.dumps(ALL_SKILLS)}\n\n"
        f"Snippets:\n{snippet_text}\n\n"
        "Return JSON: {{\"0\": [\"Skill1\", ...], \"1\": [...], ...}}"
    )
    try:
        response = chat_client.chat([
            {"role": "system", "content": CLASSIFY_SYSTEM},
            {"role": "user", "content": user_prompt},
        ])
        raw = response.choices[0].message.content
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw.strip())
    except (json.JSONDecodeError, IndexError):
        return [set() for _ in sections]

    results = []
    for i in range(len(sections)):
        skills = parsed.get(str(i), [])
        results.append({s for s in skills if s in ALL_SKILLS_SET})
    return results
