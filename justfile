set dotenv-load

# Server config — set PROVE_SERVER and PROVE_APP_DIR in .env
SERVER := env("PROVE_SERVER", "root@your-server")
APP_DIR := env("PROVE_APP_DIR", "/opt/prove")

build:
    bash scripts/build-static.sh

dev:
    -lsof -ti :7860 | xargs kill 2>/dev/null
    @echo "Starting Neo4j..."
    @docker compose up -d --wait || echo "⚠ Neo4j failed to start — is Docker running?"
    @echo "Neo4j ready."
    DEV_MODE=1 CHAT_PROVIDER=anthropic EMBED_PROVIDER=voyage uv run uvicorn src.app:app --port 7860 --reload

optimize-svg:
    bash scripts/optimize-svg.sh

deploy: build
    git push
    ssh {{SERVER}} 'cd {{APP_DIR}} && git fetch origin && git reset --hard origin/main && git lfs pull && docker compose -f docker-compose.prod.yml up -d --build'

# Deploy code + Neo4j data: dumps local DB, uploads, restores on server
deploy-full:
    git push
    @echo "=== Dumping local Neo4j ==="
    -docker stop agent-rep-neo4j-1 2>/dev/null
    rm -f dump/neo4j.dump
    docker run --rm -v agent-rep_neo4j_data:/data -v $(pwd)/dump:/dump neo4j:5-community neo4j-admin database dump neo4j --to-path=/dump
    docker start agent-rep-neo4j-1
    @echo "=== Uploading dump to server ==="
    scp dump/neo4j.dump {{SERVER}}:{{APP_DIR}}/dump/
    @echo "=== Deploying code + restoring DB ==="
    ssh {{SERVER}} 'cd {{APP_DIR}} && git fetch origin && git reset --hard origin/main && git lfs pull && docker compose -f docker-compose.prod.yml stop neo4j && docker run --rm -v {{APP_DIR}}/dump:/dump -v prove_neo4j_data:/data neo4j:5-community neo4j-admin database load neo4j --from-path=/dump --overwrite-destination && docker compose -f docker-compose.prod.yml up -d --build'

backup tag="":
    ssh {{SERVER}} 'cd {{APP_DIR}} && bash scripts/db-backup.sh {{tag}}'

restore tag="":
    ssh {{SERVER}} 'cd {{APP_DIR}} && bash scripts/db-restore.sh {{tag}}'

# Sync local Neo4j repos to prod (MERGE-based, skips existing data)
sync *args="":
    uv run python scripts/sync-to-prod.py {{args}}
