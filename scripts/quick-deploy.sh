#!/bin/bash
# Quick deploy script for the Personal AI Agent with monitoring stack

set -e

echo "==================================="
echo "Personal AI Agent - Quick Deploy"
echo "==================================="
echo ""

# Check prerequisites
echo "Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose not found. Please install Docker Compose first."
    exit 1
fi

echo "✓ Docker found"
echo "✓ Docker Compose found"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  No .env file found. Creating from .env.example..."
    cp .env.example .env
    echo ""
    echo "📝 Please edit .env and add your API keys:"
    echo "   - OPENAI_API_KEY (required for cloud mode)"
    echo "   - SERPAPI_API_KEY (optional, for web search)"
    echo "   - Alerting configuration (optional)"
    echo ""
    read -p "Press Enter to continue once you've configured .env, or Ctrl+C to exit..."
fi

# Create necessary directories
echo "Creating directories..."
mkdir -p data
mkdir -p logs
mkdir -p backup

# Build and start services
echo ""
echo "Building and starting services..."
echo "This may take a few minutes on first run..."
echo ""

docker-compose up -d --build

echo ""
echo "Waiting for services to be ready..."
sleep 10

# Check health
echo ""
echo "Checking service health..."

MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -sf http://localhost:8080/health > /dev/null 2>&1; then
        echo "✓ Agent is healthy!"
        break
    fi
    echo "  Waiting for agent to be ready... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
    RETRY_COUNT=$((RETRY_COUNT + 1))
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "❌ Agent failed to start within expected time."
    echo "   Check logs with: docker-compose logs agent"
    exit 1
fi

echo ""
echo "==================================="
echo "✅ Deployment Complete!"
echo "==================================="
echo ""
echo "Access your services:"
echo "  • Agent Health:    http://localhost:8080/health"
echo "  • Metrics:         http://localhost:8080/metrics"
echo "  • Grafana:         http://localhost:3000 (admin/admin)"
echo "  • Prometheus:      http://localhost:9090"
echo "  • AlertManager:    http://localhost:9093"
echo ""
echo "Useful commands:"
echo "  • View logs:       docker-compose logs -f agent"
echo "  • Stop services:   docker-compose down"
echo "  • Restart:         docker-compose restart agent"
echo "  • Health check:    ./scripts/health-check.sh"
echo ""
echo "Documentation:"
echo "  • Deployment:      DEPLOYMENT.md"
echo "  • Incidents:       INCIDENT_RESPONSE.md"
echo "  • Compliance:      COMPLIANCE.md"
echo ""
