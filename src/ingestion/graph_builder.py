import hashlib
import subprocess
from pathlib import Path

from src.core import logger
from src.ingestion.code_parser import parse_file
from src.ingestion.context_generator import generate_contexts
from src.ingestion.git_dates import get_chunk_dates
from src.ingestion.skill_classifier import classify_chunks
from src.ingestion.skill_taxonomy import ALL_SKILLS

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".env", "dist", "build", ".next", "portfolio"}
CODE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".rb", ".cpp", ".c", ".h", ".ipynb"}
LANG_LABELS = {
    "py": "Python", "js": "JavaScript", "ts": "TypeScript", "tsx": "TypeScript",
    "jsx": "JavaScript", "java": "Java", "go": "Go", "rs": "Rust",
    "rb": "Ruby", "cpp": "C++", "c": "C", "h": "C/C++",
}


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


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


def _diff_file_chunks(session, rel_path: str, chunks, embed_prop: str):
    """Compare parsed chunks against Neo4j and return what changed.

    Returns (changed, unchanged, orphaned) where:
      - changed: list of chunks whose content hash differs or are new
      - unchanged: list of chunks that match existing hashes
      - orphaned: set of snippet names in Neo4j that no longer exist in source
    """
    # Fetch existing snippets with their content hashes
    existing = session.run(
        "MATCH (cs:CodeSnippet {file_path: $fp}) "
        "RETURN cs.name AS name, cs.content_hash AS hash, "
        f"       cs.context AS context, cs.{embed_prop} IS NOT NULL AS embedded",
        fp=rel_path,
    ).data()
    existing_map = {r["name"]: r for r in existing}

    changed = []
    unchanged = []
    current_names = set()

    for chunk in chunks:
        current_names.add(chunk.name)
        new_hash = _content_hash(chunk.content)
        prev = existing_map.get(chunk.name)

        if prev and prev["hash"] == new_hash and prev["embedded"]:
            unchanged.append(chunk)
        else:
            changed.append(chunk)

    orphaned = set(existing_map.keys()) - current_names
    return changed, unchanged, orphaned


def _delete_orphaned_snippets(session, rel_path: str, orphaned_names: set):
    """Remove snippets from Neo4j that no longer exist in the source file."""
    if not orphaned_names:
        return
    session.run(
        "MATCH (cs:CodeSnippet {file_path: $fp}) "
        "WHERE cs.name IN $names "
        "DETACH DELETE cs",
        fp=rel_path, names=list(orphaned_names),
    )
    logger.info("graph.orphan_cleanup", file=rel_path, removed=len(orphaned_names),
                names=list(orphaned_names))


def build_graph(repo_path, neo4j_client, embed_client, chat_client):
    repo_path = Path(repo_path)
    repo_name = repo_path.name
    file_count = 0

    all_files = list(_walk_code_files(repo_path))
    total_files = len(all_files)
    logger.info("graph.build_start", repo=repo_name, total_files=total_files)

    default_branch = _detect_default_branch(repo_path)

    embed_prop = neo4j_client.embed_property

    with neo4j_client.driver.session() as session:
        session.run(
            "MERGE (r:Repository {name: $name}) SET r.path = $path, r.default_branch = $branch",
            name=repo_name, path=str(repo_path), branch=default_branch,
        )

    stats = {"skipped_files": 0, "unchanged_snippets": 0, "changed_snippets": 0, "orphaned_snippets": 0}

    for file_path in all_files:
        rel_path = str(file_path.relative_to(repo_path))

        with neo4j_client.driver.session() as session:
            session.run(
                "MATCH (r:Repository {name: $repo}) "
                "MERGE (f:File {path: $path}) "
                "MERGE (r)-[:CONTAINS]->(f)",
                repo=repo_name, path=rel_path,
            )

            chunks = parse_file(file_path)
            if not chunks:
                continue

            # Diff against existing snippets by content hash
            changed, unchanged, orphaned = _diff_file_chunks(session, rel_path, chunks, embed_prop)

            # Clean up orphaned snippets (deleted/renamed functions)
            _delete_orphaned_snippets(session, rel_path, orphaned)
            stats["orphaned_snippets"] += len(orphaned)
            stats["unchanged_snippets"] += len(unchanged)

            # If nothing changed in this file, just update skill links for unchanged chunks
            if not changed:
                file_count += 1
                stats["skipped_files"] += 1
                logger.debug("graph.file_skip", file=rel_path, reason="no_changes",
                              unchanged=len(unchanged))
                continue

            stats["changed_snippets"] += len(changed)
            logger.debug("graph.file_diff", file=rel_path,
                          changed=len(changed), unchanged=len(unchanged), orphaned=len(orphaned))

        # Only classify and embed the changed chunks
        logger.debug("graph.classify", file=rel_path, chunk_count=len(changed))
        skills_per_chunk = classify_chunks(changed, chat_client)

        # Generate contextual descriptions for changed chunks only
        with neo4j_client.driver.session() as session:
            existing_contexts = session.run(
                "MATCH (cs:CodeSnippet {file_path: $fp}) "
                "RETURN cs.name AS name, cs.context AS context",
                fp=rel_path,
            ).data()
        ctx_map = {r["name"]: r["context"] for r in existing_contexts if r["context"]}

        needs_context = [
            (i, c, skills)
            for i, (c, skills) in enumerate(zip(changed, skills_per_chunk))
            if c.name not in ctx_map
        ]

        contexts = [ctx_map.get(c.name, "") for c in changed]

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

        # Embed only changed chunks
        texts = [
            (ctx + "\n" if ctx else "")
            + build_preamble(c.name, c.language, rel_path, repo_name, list(skills))
            + "\nCode:\n" + c.content
            for c, skills, ctx in zip(changed, skills_per_chunk, contexts)
        ]
        embeddings = embed_client.embed(texts)

        with neo4j_client.driver.session() as session:
            for chunk, embedding, chunk_skills, ctx in zip(changed, embeddings, skills_per_chunk, contexts):
                content_hash = _content_hash(chunk.content)
                session.run(
                    "MATCH (f:File {path: $file_path}) "
                    "MERGE (cs:CodeSnippet {name: $name, file_path: $file_path}) "
                    "SET cs.content = $content, cs.start_line = $start, "
                    f"    cs.end_line = $end, cs.language = $lang, "
                    f"    cs.{embed_prop} = $embedding, cs.context = $ctx, "
                    "    cs.content_hash = $hash "
                    "MERGE (f)-[:CONTAINS]->(cs)",
                    file_path=rel_path, name=chunk.name,
                    content=chunk.content, start=chunk.start_line,
                    end=chunk.end_line, lang=chunk.language,
                    embedding=embedding, ctx=ctx, hash=content_hash,
                )
                _link_chunk_skills(session, chunk, rel_path, chunk_skills, repo_path)

        file_count += 1
        pct = int(file_count / total_files * 100) if total_files else 0
        logger.info("graph.progress", repo=repo_name,
                    files_processed=file_count, total_files=total_files,
                    percent=pct)

    logger.info("graph.build_done", repo=repo_name, files_total=file_count,
                skipped_files=stats["skipped_files"],
                changed_snippets=stats["changed_snippets"],
                unchanged_snippets=stats["unchanged_snippets"],
                orphaned_snippets=stats["orphaned_snippets"])
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
    import os
    for dirpath, dirnames, filenames in os.walk(repo_path, topdown=True):
        # Prune skipped dirs and nested git repos in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS
            and not (Path(dirpath) / d / ".git").exists()
        ]
        for fname in sorted(filenames):
            if Path(fname).suffix.lower() in CODE_EXTENSIONS:
                yield Path(dirpath) / fname
