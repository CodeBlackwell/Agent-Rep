"""Re-embed all CodeSnippet nodes with contextual preambles. Idempotent.

Usage:
  uv run python scripts/reembed.py              # uses EMBED_PROVIDER from .env (default: nim)
  EMBED_PROVIDER=voyage uv run python scripts/reembed.py   # use Voyage embeddings
  EMBED_PROVIDER=nim uv run python scripts/reembed.py      # use NIM embeddings
"""

from tqdm import tqdm
from src.config.settings import Settings
from src.core.client_factory import build_clients
from src.ingestion.graph_builder import build_preamble

from src.core.voyage_client import VoyageClient

# Voyage handles up to 1,000 texts / 320K tokens per request; 128 is their
# recommended sweet spot.  NIM's hosted endpoint is slower, so keep batches
# smaller there to avoid timeouts.
BATCH_SIZE_VOYAGE = 128
BATCH_SIZE_NIM = 50

FETCH_QUERY = """
MATCH (r:Repository)-[:CONTAINS]->(:File)-[:CONTAINS]->(cs:CodeSnippet)
OPTIONAL MATCH (cs)-[:DEMONSTRATES]->(sk:Skill)
RETURN cs.name AS name, cs.file_path AS file_path, cs.content AS content,
       cs.language AS language, r.name AS repo, collect(DISTINCT sk.name) AS skills
"""


def main():
    settings = Settings.load()
    clients = build_clients(settings)
    neo = clients["neo4j_client"]
    embed_client = clients["embed_client"]
    embed_prop = neo.embed_property
    batch_size = BATCH_SIZE_VOYAGE if isinstance(embed_client, VoyageClient) else BATCH_SIZE_NIM

    # Ensure the vector index exists for this provider
    neo.init_schema()

    with neo.driver.session() as session:
        rows = list(session.run(FETCH_QUERY))

    print(f"Re-embedding {len(rows)} snippets into '{embed_prop}' in batches of {batch_size}")

    for i in tqdm(range(0, len(rows), batch_size)):
        batch = rows[i : i + batch_size]
        texts = [
            build_preamble(r["name"], r["language"], r["file_path"], r["repo"], r["skills"])
            + "\nCode:\n" + r["content"]
            for r in batch
        ]
        embeddings = embed_client.embed(texts)

        with neo.driver.session() as session:
            for row, emb in zip(batch, embeddings):
                session.run(
                    f"MATCH (cs:CodeSnippet {{name: $name, file_path: $fp}}) "
                    f"SET cs.{embed_prop} = $embedding",
                    name=row["name"], fp=row["file_path"], embedding=emb,
                )

    neo.close()
    print("Done.")


if __name__ == "__main__":
    main()
