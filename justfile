dev:
    -lsof -ti :7860 | xargs kill 2>/dev/null
    @docker compose up -d --wait 2>/dev/null || true
    CHAT_PROVIDER=anthropic EMBED_PROVIDER=voyage uv run uvicorn src.app:app --port 7860 --reload

optimize-svg:
    bash scripts/optimize-svg.sh

deploy:
    git push
    ssh root@5.78.198.79 'cd /opt/prove && git fetch origin && git reset --hard origin/main && git lfs pull && docker compose -f docker-compose.prod.yml up -d --build'

backup tag="":
    ssh root@5.78.198.79 'cd /opt/prove && bash scripts/db-backup.sh {{tag}}'

restore tag="":
    ssh root@5.78.198.79 'cd /opt/prove && bash scripts/db-restore.sh {{tag}}'

backups:
    ssh root@5.78.198.79 'aws --endpoint-url https://hel1.your-objectstorage.com s3 ls s3://prove-backups/neo4j/'
