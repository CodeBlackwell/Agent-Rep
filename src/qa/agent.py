import json
import re
import time
from dataclasses import dataclass, field
from typing import Generator

from src.core import logger
from src.core.neo4j_client import Neo4jClient
from src.qa.tools import search_code, get_evidence, search_resume, find_gaps, get_repo_overview, get_connected_evidence
from src.ui.competency_map import build_query_subgraph


@dataclass
class EntityRef:
    name: str
    status: str  # demonstrated | claimed_only | not_found_but_related | not_found | inferred
    related: list[str] = field(default_factory=list)


STATUS_PRIORITY = {
    "demonstrated": 5, "not_found_but_related": 4,
    "claimed_only": 3, "inferred": 2, "not_found": 1,
}


def _merge_entity(entities: dict[str, EntityRef], ref: EntityRef):
    existing = entities.get(ref.name)
    if existing is None:
        entities[ref.name] = ref
    elif STATUS_PRIORITY.get(ref.status, 0) > STATUS_PRIORITY.get(existing.status, 0):
        existing.status = ref.status
        existing.related = list(set(existing.related + ref.related))

SYSTEM_PROMPT_TEMPLATE = (
    "You are a QA agent representing {name}'s software engineering portfolio. "
    "You have access to their resume data and code repositories indexed with vector embeddings.\n\n"
    "Skills use a 3-tier hierarchy (Domain > Category > Skill) with proficiency levels "
    "(extensive, moderate, minimal, none) based on code evidence.\n\n"
    "{skill_inventory}\n\n"
    "STRATEGY:\n"
    "- For broad questions ('what skills?', 'strengths?'), highlight the STRONGEST skills "
    "(extensive proficiency, highest evidence counts) using get_evidence.\n"
    "- For specific skill questions, use get_evidence for that skill, then search_code for depth.\n"
    "- For architecture/system-design questions, use get_repo_overview to see how a repo is "
    "structured, then get_connected_evidence to show multi-file implementations.\n"
    "- For work history, use search_resume.\n"
    "- For gap analysis, use find_gaps.\n"
    "- Prefer skills with 'extensive' proficiency and high evidence counts.\n"
    "- Always make at least 2 tool calls before answering.\n\n"
    "ANSWER FORMAT (STRICT):\n"
    "Write EXACTLY 2-3 short sentences. Name specific repos. No bullet points, no headers, "
    "no code, no lists, no categories, no subsections. Never write the engineer's name in ALL CAPS. "
    "A curated evidence section is appended automatically — do NOT preview or summarize it. "
    "Your ONLY job: a brief narrative of what was built and where. "
    "If no evidence exists, say so."
)


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _trim_answer(text: str, max_sentences: int = 4) -> str:
    """Trim verbose LLM answers to the first paragraph or max_sentences.

    If the LLM ignores the brevity instruction and produces headers, bullets,
    or multiple paragraphs, keep only the opening narrative.
    """
    if not text:
        return text
    # If it contains markdown headers or bullet lists, take only the first paragraph
    if "\n#" in text or "\n-" in text or "\n*" in text:
        first_para = text.split("\n\n")[0].strip()
        if len(first_para) > 50:
            return first_para
    # Otherwise cap by sentence count
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if len(sentences) > max_sentences:
        return " ".join(sentences[:max_sentences])
    return text


def _compute_confidence(evidence: list[dict]) -> str:
    count = len(evidence)
    if count == 0:
        return "None"
    proficiencies = [e.get("proficiency") for e in evidence if e.get("proficiency")]
    if "extensive" in proficiencies:
        return "Strong"
    scores = [e["score"] for e in evidence if "score" in e]
    avg = sum(scores) / len(scores) if scores else 0
    if count >= 3 and avg >= 0.5:
        return "Strong"
    if avg >= 0.3:
        return "Partial"
    return "None"

MAX_EVIDENCE_SHOWN = 3

PROFICIENCY_WEIGHT = {"extensive": 3, "moderate": 2, "minimal": 1, "none": 0}


def _sort_evidence(evidence: list[dict]) -> list[dict]:
    """Sort evidence by quality, then diversify across repos and files.

    First ranks by proficiency + score, deduplicates by file path (keeps
    best per file), then interleaves results from different repos so the
    curator sees variety rather than 20 snippets from the same skill.
    """
    ranked = sorted(evidence, key=lambda e: (
        PROFICIENCY_WEIGHT.get(e.get("proficiency", ""), 0),
        e.get("score", 0),
    ), reverse=True)

    # Deduplicate by file — keep best snippet per file
    seen_files: set[str] = set()
    deduped = []
    for e in ranked:
        fp = e.get("file_path", "")
        if fp not in seen_files:
            seen_files.add(fp)
            deduped.append(e)

    # Interleave by repo to ensure diversity
    by_repo: dict[str, list[dict]] = {}
    for e in deduped:
        by_repo.setdefault(e.get("repo", "unknown"), []).append(e)

    diversified = []
    queues = list(by_repo.values())
    idx = 0
    while queues:
        queue = queues[idx % len(queues)]
        diversified.append(queue.pop(0))
        if not queue:
            queues.remove(queue)
        else:
            idx += 1

    return diversified


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search indexed code repositories by semantic similarity. Use this to find code examples for any topic.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_evidence",
            "description": "Get code snippets demonstrating a specific skill, including proficiency level and date range.",
            "parameters": {
                "type": "object",
                "properties": {"skill_name": {"type": "string", "description": "Skill name"}},
                "required": ["skill_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_resume",
            "description": "Search resume data: engineer name, job roles/titles, companies, dates. Use for work history questions.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_gaps",
            "description": "Check which skills have code evidence with proficiency levels, which are only resume claims, and which are missing. Returns hierarchy-aware results with domain/category context.",
            "parameters": {
                "type": "object",
                "properties": {"skills_csv": {"type": "string", "description": "Comma-separated skill names to check"}},
                "required": ["skills_csv"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_repo_overview",
            "description": "Get a high-level overview of a repository: file structure, top demonstrated skills with proficiency levels, and snippet counts. Use this to understand how a project is organized before diving into specific code.",
            "parameters": {
                "type": "object",
                "properties": {"repo_name": {"type": "string", "description": "Repository name"}},
                "required": ["repo_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_connected_evidence",
            "description": "Get multi-file code evidence showing how a skill is demonstrated across files within a specific repository. Use this to show system-level engineering and how components work together, not just individual functions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string", "description": "Skill name to find evidence for"},
                    "repo_name": {"type": "string", "description": "Repository to search within"},
                },
                "required": ["skill_name", "repo_name"],
            },
        },
    },
]

MAX_TOOL_CALLS = 4
MAX_TOOL_RESULT_CHARS = 4000


def _github_link(e: dict) -> str:
    repo = e.get("repo", "")
    fp = e.get("file_path", "unknown")
    start = e.get("start_line", 0)
    if repo:
        return f"[{repo}/{fp}#L{start}](https://github.com/codeblackwell/{repo}/blob/main/{fp}#L{start})"
    return f"`{fp}:L{start}`"


def format_response(answer: str, evidence: list[dict], annotations: list[str] | None = None,
                     curation: list[dict] | None = None, total_count: int | None = None) -> str:
    shown = evidence[:MAX_EVIDENCE_SHOWN]
    total = total_count if total_count is not None else len(evidence)
    lines = [answer, ""]
    if shown:
        lines.append("\n**Evidence:**")
        for i, e in enumerate(shown):
            link = _github_link(e)
            cur = curation[i] if curation and i < len(curation) else None

            if cur and cur.get("mode") == "link":
                lines.append(f"\n{link}")
                lines.append(f"> {cur['explanation']}")
            else:
                content = e.get("content", "")
                ctx = e.get("context", "")
                explanation = cur["explanation"] if cur else (annotations[i] if annotations and i < len(annotations) else "")
                if not explanation and ctx:
                    explanation = ctx
                lines.append(f"\n{link}")
                if explanation:
                    lines.append(f"> {explanation}")
                lines.append(f"```\n{content}\n```")
    confidence = _compute_confidence(evidence)
    lines.append(f"\nConfidence: {confidence} ({total} code example{'s' if total != 1 else ''})")
    return "\n".join(lines)


ANNOTATE_PROMPT = (
    "You will receive a user question and numbered code snippets. "
    "For each snippet, write 1-2 sentences explaining how it is relevant to the question. "
    "Reply ONLY with a JSON array of strings, one per snippet. No markdown, no explanation."
)

CURATE_PROMPT = (
    "You are selecting the most IMPRESSIVE code evidence for a software portfolio.\n"
    "You will receive a question and numbered code snippets with metadata.\n\n"
    "RULES:\n"
    "1. KEEP at least 3 snippets. Prefer diversity across different repos — "
    "showing range is more impressive than depth in one project.\n"
    "2. DROP only truly trivial code (simple getters, one-line configs, bare imports). "
    "When in doubt, KEEP.\n"
    "3. For each KEEP, assign a display mode:\n"
    "   - 'inline': Show the code — it is self-contained and impressive on its own.\n"
    "   - 'link': The snippet is part of a larger system — provide an architectural "
    "explanation of how it fits the bigger picture.\n"
    "4. For each KEEP, write 1-2 sentences explaining WHY it is impressive, "
    "not just what it does.\n\n"
    "Reply ONLY with a JSON array. Each element:\n"
    '{{"index": 0, "action": "keep", "mode": "inline", "explanation": "..."}}\n'
    "No markdown, no extra text."
)


class QAAgent:
    def __init__(self, neo4j_client: Neo4jClient, chat_client, embed_client):
        self.neo4j = neo4j_client
        self.chat = chat_client
        self.embed = embed_client
        self.system_prompt = self._resolve_prompt()

    def _resolve_prompt(self) -> str:
        with self.neo4j.driver.session() as session:
            result = session.run("MATCH (e:Engineer) RETURN e.name AS name LIMIT 1")
            record = result.single()
            name = record["name"] if record else "a software engineer"
        inventory = self._build_skill_inventory()
        return SYSTEM_PROMPT_TEMPLATE.format(name=name, skill_inventory=inventory)

    def _build_skill_inventory(self) -> str:
        skills = self.neo4j.get_competency_map()
        if not skills:
            return "SKILL INVENTORY: No skills indexed yet."
        by_domain: dict[str, list[dict]] = {}
        for s in skills:
            by_domain.setdefault(s["domain"], []).append(s)
        lines = ["SKILL INVENTORY (strongest first):"]
        for domain, entries in sorted(by_domain.items()):
            top = sorted(entries, key=lambda e: (
                PROFICIENCY_WEIGHT.get(e["proficiency"], 0), e["evidence_count"]
            ), reverse=True)[:5]
            skills_str = ", ".join(
                f"{e['skill']} ({e['proficiency']}, {e['evidence_count']} examples)"
                for e in top
            )
            lines.append(f"  {domain}: {skills_str}")
        return "\n".join(lines)

    def _execute_tool(self, name: str, args: dict) -> str:
        t0 = time.perf_counter()
        dispatch = {
            "search_code": lambda: search_code(args["query"], self.neo4j, self.embed),
            "get_evidence": lambda: get_evidence(args["skill_name"], self.neo4j),
            "search_resume": lambda: search_resume(args["query"], self.neo4j),
            "find_gaps": lambda: find_gaps(args["skills_csv"], self.neo4j),
            "get_repo_overview": lambda: get_repo_overview(args["repo_name"], self.neo4j),
            "get_connected_evidence": lambda: get_connected_evidence(args["skill_name"], args["repo_name"], self.neo4j),
        }
        result = dispatch.get(name, lambda: {"error": f"Unknown tool: {name}"})()
        serialized = json.dumps(result)
        latency = int((time.perf_counter() - t0) * 1000)

        result_count = len(result) if isinstance(result, list) else 1
        logger.log_tool_call(tool_name=name, args=args,
                             result_size=len(serialized), latency_ms=latency)
        logger.log_tool_result(tool_name=name, result_count=result_count)

        return serialized

    def _collect_entities(self, tool_name: str, args: dict, tool_result: str,
                          entities: dict[str, EntityRef]):
        if tool_name == "get_evidence":
            try:
                parsed = json.loads(tool_result)
                status = "demonstrated" if parsed else "inferred"
            except (json.JSONDecodeError, TypeError):
                status = "inferred"
            _merge_entity(entities, EntityRef(args.get("skill_name", ""), status))
        elif tool_name == "search_code":
            try:
                for item in json.loads(tool_result):
                    for skill in item.get("skills", []):
                        _merge_entity(entities, EntityRef(skill, "demonstrated"))
            except (json.JSONDecodeError, TypeError):
                pass
        elif tool_name == "find_gaps":
            try:
                for item in json.loads(tool_result):
                    skill = item.get("skill", "")
                    if not skill:
                        continue
                    status = item.get("status", "not_found")
                    related = item.get("related_demonstrated", [])
                    _merge_entity(entities, EntityRef(skill, status, related))
                    for rel in related:
                        _merge_entity(entities, EntityRef(rel, "demonstrated"))
            except (json.JSONDecodeError, TypeError):
                pass
        elif tool_name == "get_repo_overview":
            try:
                data = json.loads(tool_result)
                for skill_info in data.get("top_skills", []):
                    if skill_info.get("skill"):
                        _merge_entity(entities, EntityRef(skill_info["skill"], "demonstrated"))
            except (json.JSONDecodeError, TypeError):
                pass
        elif tool_name == "get_connected_evidence":
            _merge_entity(entities, EntityRef(args.get("skill_name", ""), "demonstrated"))
            try:
                for item in json.loads(tool_result):
                    for skill in item.get("related_skills", []):
                        _merge_entity(entities, EntityRef(skill, "demonstrated"))
            except (json.JSONDecodeError, TypeError):
                pass

    def _collect_evidence(self, tool_result: str, evidence: list[dict]):
        try:
            parsed = json.loads(tool_result)
            if isinstance(parsed, list):
                new = [item for item in parsed if "file_path" in item]
                evidence.extend(new)
        except (json.JSONDecodeError, TypeError):
            pass

    def _annotate_evidence(self, question: str, evidence: list[dict]) -> list[str] | None:
        if not evidence:
            return None
        logger.debug("agent.annotate", evidence_count=len(evidence))
        snippets = []
        for i, e in enumerate(evidence):
            fp = e.get("file_path", "?")
            ctx = e.get("context", "")
            preview = "\n".join(e.get("content", "").split("\n")[:8])
            header = f"{i + 1}. {fp}"
            if ctx:
                header += f"\nContext: {ctx}"
            snippets.append(f"{header}\n{preview}")
        user_msg = f"Question: {question}\n\nSnippets:\n" + "\n\n".join(snippets)
        try:
            response = self.chat.chat([
                {"role": "system", "content": ANNOTATE_PROMPT},
                {"role": "user", "content": user_msg},
            ], purpose="annotate_evidence")
            raw = _strip_think(response.choices[0].message.content)
            raw = re.sub(r"^```\w*\n|```$", "", raw.strip())
            return json.loads(raw)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("agent.annotate_failed", error=str(e))
            return None

    def _curate_evidence(self, question: str, evidence: list[dict]) -> tuple[list[dict], list[dict] | None]:
        """Select the most impressive evidence and assign display modes (inline/link)."""
        if not evidence:
            return [], None

        logger.info("agent.curate_start", evidence_count=len(evidence))

        summaries = []
        for i, e in enumerate(evidence):
            fp = e.get("file_path", "?")
            repo = e.get("repo", "?")
            prof = e.get("proficiency", "?")
            skill = e.get("skill_name", "")
            ctx = e.get("context", "")
            preview = "\n".join(e.get("content", "").split("\n")[:15])
            header = f"[{i}] {repo}/{fp} (proficiency: {prof}{', skill: ' + skill if skill else ''})"
            if ctx:
                header += f"\nContext: {ctx}"
            summaries.append(f"{header}\n{preview}")
        user_msg = f"Question: {question}\n\nSnippets:\n\n" + "\n\n".join(summaries)

        try:
            response = self.chat.chat([
                {"role": "system", "content": CURATE_PROMPT},
                {"role": "user", "content": user_msg},
            ], purpose="curate_evidence")
            raw = _strip_think(response.choices[0].message.content)
            raw = re.sub(r"^```\w*\n|```$", "", raw.strip())
            parsed = json.loads(raw)
            keeps = [item for item in parsed if item.get("action") == "keep"]
            dropped = len(parsed) - len(keeps)
            if not keeps:
                logger.log_curation(kept=0, dropped=len(parsed), total=len(evidence))
                return evidence[:MAX_EVIDENCE_SHOWN], None
            curated = []
            meta = []
            for k in keeps[:MAX_EVIDENCE_SHOWN]:
                idx = k.get("index", 0)
                if 0 <= idx < len(evidence):
                    curated.append(evidence[idx])
                    meta.append({"mode": k.get("mode", "inline"), "explanation": k.get("explanation", "")})
            logger.log_curation(kept=len(curated), dropped=dropped, total=len(evidence))
            return curated or evidence[:MAX_EVIDENCE_SHOWN], meta or None
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("agent.curate_failed", error=str(e), fallback="annotate")
            shown = evidence[:MAX_EVIDENCE_SHOWN]
            annotations = self._annotate_evidence(question, shown)
            if annotations:
                logger.log_curation(kept=len(shown), dropped=0,
                                    total=len(evidence), fallback=True)
                return shown, [{"mode": "inline", "explanation": a} for a in annotations]
            return shown, None

    def _assistant_msg(self, choice) -> dict:
        msg = {"role": "assistant", "content": choice.message.content}
        if choice.message.tool_calls:
            msg["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in choice.message.tool_calls
            ]
        return msg

    def answer(self, question: str) -> str:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": question},
        ]
        all_evidence = []

        for step in range(MAX_TOOL_CALLS):
            logger.info("agent.react_step", step=step + 1, max_steps=MAX_TOOL_CALLS)
            response = self.chat.chat(messages, tools=TOOL_DEFINITIONS, purpose="react_loop")
            choice = response.choices[0]
            if not choice.message.tool_calls:
                logger.info("agent.react_done", step=step + 1, reason="final_answer")
                sorted_ev = _sort_evidence(all_evidence)
                curated, curation_meta = self._curate_evidence(question, sorted_ev)
                return format_response(_trim_answer(_strip_think(choice.message.content or "")), curated, curation=curation_meta, total_count=len(all_evidence))
            messages.append(self._assistant_msg(choice))
            for tc in choice.message.tool_calls:
                result = self._execute_tool(tc.function.name, json.loads(tc.function.arguments))
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result[:MAX_TOOL_RESULT_CHARS]})
                self._collect_evidence(result, all_evidence)

        logger.info("agent.react_done", step=MAX_TOOL_CALLS, reason="max_calls_reached")
        response = self.chat.chat(messages, purpose="react_final")
        sorted_ev = _sort_evidence(all_evidence)
        curated, curation_meta = self._curate_evidence(question, sorted_ev)

        # Log evidence summary
        repos = {e.get("repo") for e in all_evidence if e.get("repo")}
        skills = {e.get("skill_name") for e in all_evidence if e.get("skill_name")}
        logger.log_evidence(collected=len(all_evidence),
                            unique_repos=len(repos), unique_skills=len(skills))

        return format_response(_trim_answer(_strip_think(response.choices[0].message.content or "")), curated, curation=curation_meta, total_count=len(all_evidence))

    def answer_stream(self, question: str,
                       history: list[dict] | None = None) -> Generator[str | dict, None, None]:
        """Run the ReAct loop and yield status messages, graph data, and the final response.

        Args:
            question: The user's current question.
            history: Prior conversation turns as [{"role": "user"/"assistant", "content": "..."}].
                     Injected between the system prompt and the new question so the model
                     can resolve references like "tell me more about that".
        """
        messages = [{"role": "system", "content": self.system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": question})
        all_evidence = []
        entities: dict[str, EntityRef] = {}

        for step in range(MAX_TOOL_CALLS):
            logger.info("agent.react_step", step=step + 1, max_steps=MAX_TOOL_CALLS)
            response = self.chat.chat(messages, tools=TOOL_DEFINITIONS, purpose="react_loop")
            choice = response.choices[0]
            if not choice.message.tool_calls:
                logger.info("agent.react_done", step=step + 1, reason="final_answer")
                break
            messages.append(self._assistant_msg(choice))
            for tc in choice.message.tool_calls:
                yield f"Searching for: {tc.function.name}..."
                args = json.loads(tc.function.arguments)
                result = self._execute_tool(tc.function.name, args)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result[:MAX_TOOL_RESULT_CHARS]})
                self._collect_evidence(result, all_evidence)
                self._collect_entities(tc.function.name, args, result, entities)
                # Emit intermediate subgraph for progressive reveal
                if entities:
                    intermediate = build_query_subgraph(self.neo4j, entities)
                    if intermediate["nodes"]:
                        yield intermediate
        else:
            logger.info("agent.react_done", step=MAX_TOOL_CALLS, reason="max_calls_reached")
            response = self.chat.chat(messages, purpose="react_final")
            choice = response.choices[0]

        if entities:
            subgraph = build_query_subgraph(self.neo4j, entities)
            if subgraph["nodes"]:
                logger.debug("agent.subgraph", node_count=len(subgraph["nodes"]),
                              edge_count=len(subgraph["edges"]))
                yield subgraph

        # Log evidence summary
        repos = {e.get("repo") for e in all_evidence if e.get("repo")}
        skills = {e.get("skill_name") for e in all_evidence if e.get("skill_name")}
        logger.log_evidence(collected=len(all_evidence),
                            unique_repos=len(repos), unique_skills=len(skills))

        sorted_ev = _sort_evidence(all_evidence)
        curated, curation_meta = self._curate_evidence(question, sorted_ev)
        yield format_response(_trim_answer(_strip_think(choice.message.content or "")), curated, curation=curation_meta, total_count=len(all_evidence))
