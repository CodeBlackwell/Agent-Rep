import subprocess
from pathlib import Path

from src.core import logger
from src.ingestion.code_parser import parse_file
from src.ingestion.context_generator import generate_contexts
from src.ingestion.git_dates import get_chunk_dates
from src.ingestion.skill_classifier import classify_chunks
from src.ingestion.skill_taxonomy import ALL_SKILLS

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".env", "dist", "build", ".next"}
CODE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".rb", ".cpp", ".c", ".h"}
LANG_LABELS = {
    "py": "Python", "js": "JavaScript", "ts": "TypeScript", "tsx": "TypeScript",
    "jsx": "JavaScript", "java": "Java", "go": "Go", "rs": "Rust",
    "rb": "Ruby", "cpp": "C++", "c": "C", "h": "C/C++",
}


def build_preamble(name, language, file_path, repo_name, skills):
    lang_label = LANG_LABELS.get(language, language)
    parts = [f"{lang_label} function '{name}' in repo {repo_name} ({file_path})"]
    if skills:
        parts.append(f"Skills: {', '.join(skills)}")
    return "\n".join(parts)


def _detect_default_branch(repo_path: Path) -> str:
    """Detect the default branch of a cloned repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path, capture_output=True, text=True, timeout=5,
        )
        branch = result.stdout.strip()
        if branch and branch != "HEAD":
            return branch
    except Exception:
        pass
    return "main"


def build_graph(repo_path, neo4j_client, embed_client, chat_client):
    repo_path = Path(repo_path)
    repo_name = repo_path.name
    file_count = 0

    logger.info("graph.build_start", repo=repo_name)

    default_branch = _detect_default_branch(repo_path)

    with neo4j_client.driver.session() as session:
        session.run(
            "MERGE (r:Repository {name: $name}) SET r.path = $path, r.default_branch = $branch",
            name=repo_name, path=str(repo_path), branch=default_branch,
        )

        for file_path in _walk_code_files(repo_path):
            rel_path = str(file_path.relative_to(repo_path))
            session.run(
                "MATCH (r:Repository {name: $repo}) "
                "MERGE (f:File {path: $path}) "
                "MERGE (r)-[:CONTAINS]->(f)",
                repo=repo_name, path=rel_path,
            )

            chunks = parse_file(file_path)
            if not chunks:
                continue

            # Skip file if all chunks already embedded for this provider
            embed_prop = neo4j_client.embed_property
            existing = session.run(
                f"MATCH (cs:CodeSnippet {{file_path: $fp}}) WHERE cs.{embed_prop} IS NOT NULL "
                "RETURN count(cs) AS c",
                fp=rel_path,
            ).single()["c"]
            if existing >= len(chunks):
                file_count += 1
                logger.debug("graph.file_skip", file=rel_path, reason="already_embedded",
                              chunk_count=len(chunks))
                # Still classify skills for existing chunks
                skills_per_chunk = classify_chunks(chunks, chat_client)
                for chunk, chunk_skills in zip(chunks, skills_per_chunk):
                    _link_chunk_skills(session, chunk, rel_path, chunk_skills, repo_path)
                continue

            # Classify first so skills are available for preamble
            logger.debug("graph.classify", file=rel_path, chunk_count=len(chunks))
            skills_per_chunk = classify_chunks(chunks, chat_client)

            # Generate contextual descriptions (reuse existing if available)
            existing_contexts = session.run(
                "MATCH (cs:CodeSnippet {file_path: $fp}) "
                "RETURN cs.name AS name, cs.context AS context",
                fp=rel_path,
            ).data()
            ctx_map = {r["name"]: r["context"] for r in existing_contexts if r["context"]}

            needs_context = [
                (i, c, skills)
                for i, (c, skills) in enumerate(zip(chunks, skills_per_chunk))
                if c.name not in ctx_map
            ]

            contexts = [ctx_map.get(c.name, "") for c in chunks]

            if needs_context:
                snippet_dicts = [
                    {"name": c.name, "file_path": rel_path, "content": c.content,
                     "language": c.language, "repo": repo_name, "skills": list(skills)}
                    for _, c, skills in needs_context
                ]
                new_contexts = generate_contexts(snippet_dicts, chat_client,
                                                 skills_list=", ".join(ALL_SKILLS))
                for (i, _, _), ctx in zip(needs_context, new_contexts):
                    contexts[i] = ctx

            # Embed with context + metadata preamble + code
            texts = [
                (ctx + "\n" if ctx else "")
                + build_preamble(c.name, c.language, rel_path, repo_name, list(skills))
                + "\nCode:\n" + c.content
                for c, skills, ctx in zip(chunks, skills_per_chunk, contexts)
            ]
            embeddings = embed_client.embed(texts)

            for chunk, embedding, chunk_skills, ctx in zip(chunks, embeddings, skills_per_chunk, contexts):
                session.run(
                    "MATCH (f:File {path: $file_path}) "
                    "MERGE (cs:CodeSnippet {name: $name, file_path: $file_path}) "
                    "SET cs.content = $content, cs.start_line = $start, "
                    f"    cs.end_line = $end, cs.language = $lang, "
                    f"    cs.{embed_prop} = $embedding, cs.context = $ctx "
                    "MERGE (f)-[:CONTAINS]->(cs)",
                    file_path=rel_path, name=chunk.name,
                    content=chunk.content, start=chunk.start_line,
                    end=chunk.end_line, lang=chunk.language,
                    embedding=embedding, ctx=ctx,
                )
                _link_chunk_skills(session, chunk, rel_path, chunk_skills, repo_path)

            file_count += 1
            if file_count % 25 == 0:
                logger.info("graph.progress", repo=repo_name, files_processed=file_count)

    logger.info("graph.build_done", repo=repo_name, files_total=file_count)
    neo4j_client.compute_repo_rollups(repo_name)
    neo4j_client.compute_proficiency()


def _link_chunk_skills(session, chunk, rel_path, chunk_skills, repo_path):
    snippet_lines = chunk.end_line - chunk.start_line + 1
    first_seen, last_seen = get_chunk_dates(repo_path, rel_path, chunk.start_line, chunk.end_line)
    for skill in chunk_skills:
        session.run(
            "MERGE (s:Skill {name: $skill}) WITH s "
            "MATCH (cs:CodeSnippet {name: $name, file_path: $fp}) "
            "MERGE (cs)-[d:DEMONSTRATES]->(s) "
            "SET d.snippet_lines = $lines, "
            "    d.first_seen = $first, d.last_seen = $last",
            skill=skill, name=chunk.name, fp=rel_path,
            lines=snippet_lines,
            first=str(first_seen) if first_seen else None,
            last=str(last_seen) if last_seen else None,
        )


def _walk_code_files(repo_path: Path):
    for item in sorted(repo_path.rglob("*")):
        if any(skip in item.parts for skip in SKIP_DIRS):
            continue
        if item.is_file() and item.suffix.lower() in CODE_EXTENSIONS:
            yield item
