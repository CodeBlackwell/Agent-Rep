#!/usr/bin/env bash
set -euo pipefail

# PROVE deployment script for a fresh VPS (Ubuntu 22.04+)
# Usage: ssh root@your-server 'bash -s' < scripts/deploy.sh

REPO="https://github.com/CodeBlackwell/Agent-Rep.git"
APP_DIR="/opt/prove"

echo "=== 1. Install Docker ==="
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
fi

echo "=== 2. Clone repo ==="
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR" && git pull
else
    git clone "$REPO" "$APP_DIR"
    cd "$APP_DIR"
fi

echo "=== 3. Configure ==="
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "  >>> EDIT .env WITH YOUR API KEYS AND DOMAIN <<<"
    echo "  >>> Then re-run this script or run: docker compose -f docker-compose.prod.yml up -d"
    echo ""
    exit 0
fi

echo "=== 4. Restore Neo4j data ==="
# If dump exists and neo4j_data volume is empty, restore it
if [ -f dump/neo4j.dump ]; then
    VOLUME_EMPTY=$(docker volume ls -q | grep -c "prove_neo4j_data" || true)
    if [ "$VOLUME_EMPTY" -eq 0 ]; then
        echo "Restoring Neo4j dump..."
        docker compose -f docker-compose.prod.yml up -d neo4j
        sleep 10  # wait for neo4j to init
        docker compose -f docker-compose.prod.yml stop neo4j

        docker run --rm \
            -v "$(pwd)/dump:/dump" \
            -v "prove_neo4j_data:/data" \
            neo4j:5-community \
            neo4j-admin database load neo4j --from-path=/dump --overwrite-destination

        echo "Neo4j data restored."
    fi
fi

echo "=== 5. Build and start ==="
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d

echo ""
echo "=== Done! ==="
docker compose -f docker-compose.prod.yml ps
echo ""
echo "Logs: docker compose -f docker-compose.prod.yml logs -f"
