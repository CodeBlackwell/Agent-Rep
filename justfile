dev:
    -lsof -ti :7860 | xargs kill 2>/dev/null
    @docker compose up -d --wait 2>/dev/null || true
    CHAT_PROVIDER=anthropic EMBED_PROVIDER=voyage uv run uvicorn src.app:app --port 7860 --reload

optimize-svg:
    bash scripts/optimize-svg.sh

deploy:
    git push
    ssh root@5.78.198.79 'cd /opt/prove && git fetch origin && git reset --hard origin/main && git lfs pull && docker compose -f docker-compose.prod.yml up -d --build'

# Deploy code + Neo4j data: dumps local DB, uploads, restores on server
deploy-full:
    git push
    @echo "=== Dumping local Neo4j ==="
    -docker stop agent-rep-neo4j-1 2>/dev/null
    docker run --rm -v agent-rep_neo4j_data:/data -v $(pwd)/dump:/dump neo4j:5-community neo4j-admin database dump neo4j --to-path=/dump --overwrite-destination
    docker start agent-rep-neo4j-1
    @echo "=== Uploading dump to server ==="
    scp dump/neo4j.dump root@5.78.198.79:/opt/prove/dump/
    @echo "=== Deploying code + restoring DB ==="
    ssh root@5.78.198.79 'cd /opt/prove && git fetch origin && git reset --hard origin/main && git lfs pull && docker compose -f docker-compose.prod.yml stop neo4j && docker run --rm -v /opt/prove/dump:/dump -v prove_neo4j_data:/data neo4j:5-community neo4j-admin database load neo4j --from-path=/dump --overwrite-destination && docker compose -f docker-compose.prod.yml up -d --build'

backup tag="":
    ssh root@5.78.198.79 'cd /opt/prove && bash scripts/db-backup.sh {{tag}}'

restore tag="":
    ssh root@5.78.198.79 'cd /opt/prove && bash scripts/db-restore.sh {{tag}}'

backups:
    ssh root@5.78.198.79 'aws --endpoint-url https://hel1.your-objectstorage.com s3 ls s3://prove-backups/neo4j/'
