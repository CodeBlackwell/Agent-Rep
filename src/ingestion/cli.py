import argparse
import subprocess
from pathlib import Path

from src.config.settings import Settings
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
        print(f"  Skipping clone (already exists): {dest}")
        return dest

    clone_url = github_url
    if token and clone_url.startswith("https://"):
        clone_url = clone_url.replace("https://", f"https://{token}@")

    subprocess.run(["git", "clone", "--depth=1", clone_url, str(dest)], check=True)
    return dest


def fetch_github_repos(username: str, token: str = "") -> list[str]:
    """Fetch all public (+ private if token provided) repo URLs for a GitHub user."""
    import json, urllib.request

    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    repos, page = [], 1
    while True:
        url = f"https://api.github.com/users/{username}/repos?per_page=100&page={page}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            batch = json.loads(resp.read())
        if not batch:
            break
        repos.extend(r["clone_url"] for r in batch if not r.get("fork"))
        page += 1
    return repos


def ingest(resume_path: str, repo_sources: list[str], github_user: str = ""):
    settings = Settings.load()
    clients = build_clients(settings)
    neo4j_client = clients["neo4j_client"]
    embed_client = clients["embed_client"]
    chat_client = clients["ingestion_chat_client"]
    token = settings.github_token

    neo4j_client.init_schema()
    neo4j_client.ensure_taxonomy(TAXONOMY)

    # Check if engineer already exists (skip re-parsing resume)
    with neo4j_client.driver.session() as session:
        existing = session.run("MATCH (e:Engineer) RETURN e.name AS name LIMIT 1").single()
    if existing:
        engineer_name = existing["name"]
        print(f"Engineer (cached): {engineer_name}")
    else:
        engineer_name = parse_resume(resume_path, neo4j_client, chat_client)
        print(f"Engineer: {engineer_name}")

    sources = list(repo_sources)
    if github_user:
        print(f"Fetching repos for GitHub user: {github_user}")
        sources.extend(fetch_github_repos(github_user, token))

    for source in sources:
        name = source.rstrip("/").split("/")[-1]
        print(f"=== {name} ===")
        try:
            if source.startswith("https://") or source.startswith("git@"):
                repo_path = clone_repo(source, token)
            else:
                repo_path = Path(source)
            build_graph(repo_path, neo4j_client, embed_client, chat_client)
            # Link engineer to repo
            with neo4j_client.driver.session() as session:
                session.run(
                    "MATCH (e:Engineer {name: $eng}), (r:Repository {name: $repo}) "
                    "MERGE (e)-[:OWNS]->(r)",
                    eng=engineer_name, repo=repo_path.name,
                )
            print(f"  Done: {name}")
        except Exception as e:
            print(f"  Error: {e}")

    neo4j_client.close()
    print("=== ALL DONE ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest resume and repos into ShowMeOff")
    parser.add_argument("--resume", required=True)
    parser.add_argument("--repos", nargs="*", default=[], help="Local paths or GitHub URLs")
    parser.add_argument("--github-user", default="", help="Fetch all repos for this GitHub username")
    args = parser.parse_args()
    ingest(args.resume, args.repos, args.github_user)
