dev:
    -lsof -ti :7860 | xargs kill 2>/dev/null && sleep 1
    CHAT_PROVIDER=anthropic EMBED_PROVIDER=voyage uv run uvicorn src.app:app --port 7860 --reload

deploy:
    git push
    ssh root@5.78.198.79 'cd /opt/showmeoff && git fetch origin && git reset --hard origin/main && git lfs pull && docker compose -f docker-compose.prod.yml up -d --build'
