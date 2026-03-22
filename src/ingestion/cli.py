import argparse
import subprocess
from pathlib import Path

from src.config.settings import Settings
from src.core import logger
from src.core.client_factory import build_clients
from src.ingestion.graph_builder import build_graph
from src.ingestion.resume_parser import parse_resume
from src.ingestion.skill_taxonomy import TAXONOMY

REPOS_DIR = Path(__file__).resolve().parent.parent.parent / "repos"


def clone_repo(github_url: str, token: str = "") -> Path:
    REPOS_DIR.mkdir(exist_ok=True)
    repo_name = github_url.rstrip("/").split("/")[-1].removesuffix(".git")
    dest = REPOS_DIR / repo_name

    if dest.exists():
        logger.info("ingestion.clone_skip", repo=repo_name, path=str(dest))
        return dest

    clone_url = github_url
    if token and clone_url.startswith("https://"):
        clone_url = clone_url.replace("https://", f"https://{token}@")

    logger.info("ingestion.clone_start", repo=repo_name, url=github_url)
    subprocess.run(["git", "clone", "--depth=1", clone_url, str(dest)], check=True)
    logger.info("ingestion.clone_done", repo=repo_name)
    return dest


def fetch_github_repos(username: str, token: str = "") -> tuple[list[str], dict[str, bool]]:
    """Fetch all public (+ private if token provided) repo URLs for a GitHub user.

    Returns (clone_urls, visibility) where visibility maps repo name -> is_private.
    """
    import json, urllib.request

    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    repos: list[str] = []
    visibility: dict[str, bool] = {}
    page = 1
    while True:
        url = f"https://api.github.com/users/{username}/repos?per_page=100&page={page}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            batch = json.loads(resp.read())
        if not batch:
            break
        for r in batch:
            if r.get("fork"):
                continue
            repos.append(r["clone_url"])
            visibility[r["name"]] = r.get("private", False)
        page += 1

    logger.info("ingestion.github_repos", username=username, count=len(repos))
    return repos, visibility


def ingest(resume_path: str, repo_sources: list[str], github_user: str = ""):
    settings = Settings.load()
    clients = build_clients(settings)
    neo4j_client = clients["neo4j_client"]
    embed_client = clients["embed_client"]
    chat_client = clients["ingestion_chat_client"]
    token = settings.github_token

    logger.start_session(source="ingestion")
    logger.info("ingestion.start", resume=resume_path,
                repo_count=len(repo_sources), github_user=github_user or None,
                chat_provider=settings.chat_provider,
                embed_provider=settings.embed_provider)

    neo4j_client.init_schema()
    neo4j_client.ensure_taxonomy(TAXONOMY)

    # Check if engineer already exists (skip re-parsing resume)
    with neo4j_client.driver.session() as session:
        existing = session.run("MATCH (e:Engineer) RETURN e.name AS name LIMIT 1").single()
    if existing:
        engineer_name = existing["name"]
        logger.info("ingestion.engineer_cached", name=engineer_name)
    else:
        engineer_name = parse_resume(resume_path, neo4j_client, chat_client)
        logger.info("ingestion.engineer_parsed", name=engineer_name)

    sources = list(repo_sources)
    visibility: dict[str, bool] = {}
    if github_user:
        logger.info("ingestion.fetch_github", username=github_user)
        gh_urls, visibility = fetch_github_repos(github_user, token)
        sources.extend(gh_urls)

    for source in sources:
        name = source.rstrip("/").split("/")[-1]
        logger.log_ingestion_step(step="repo_start", detail=name, source=source)
        try:
            if source.startswith("https://") or source.startswith("git@"):
                repo_path = clone_repo(source, token)
            else:
                repo_path = Path(source)
            build_graph(repo_path, neo4j_client, embed_client, chat_client)
            # Link engineer to repo and store visibility
            is_private = visibility.get(repo_path.name, False)
            with neo4j_client.driver.session() as session:
                session.run(
                    "MATCH (e:Engineer {name: $eng}), (r:Repository {name: $repo}) "
                    "MERGE (e)-[:OWNS]->(r) "
                    "SET r.private = $private",
                    eng=engineer_name, repo=repo_path.name, private=is_private,
                )
            logger.log_ingestion_step(step="repo_done", detail=name)
        except Exception as e:
            logger.error("ingestion.repo_error", repo=name, error=str(e))

    neo4j_client.close()
    summary = logger.end_session()
    logger.info("ingestion.complete", repos_processed=len(sources))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest resume and repos into PROVE")
    parser.add_argument("--resume", required=True)
    parser.add_argument("--repos", nargs="*", default=[], help="Local paths or GitHub URLs")
    parser.add_argument("--github-user", default="", help="Fetch all repos for this GitHub username")
    args = parser.parse_args()
    ingest(args.resume, args.repos, args.github_user)
