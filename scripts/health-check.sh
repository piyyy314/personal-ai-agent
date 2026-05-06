#!/bin/bash
# Health check script for monitoring and verification

set -e

HEALTH_ENDPOINT="${HEALTH_ENDPOINT:-http://localhost:8080/health}"
READY_ENDPOINT="${READY_ENDPOINT:-http://localhost:8080/ready}"
METRICS_ENDPOINT="${METRICS_ENDPOINT:-http://localhost:8080/metrics}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=== Personal AI Agent Health Check ==="
echo ""

# Check if curl is available
if ! command -v curl &> /dev/null; then
    echo -e "${RED}✗ curl not found${NC}"
    exit 1
fi

# 1. Liveness check
echo -n "Liveness (health): "
if curl -sf "${HEALTH_ENDPOINT}" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PASS${NC}"
    HEALTH_STATUS=$(curl -s "${HEALTH_ENDPOINT}" | jq -r '.status' 2>/dev/null || echo "unknown")
    echo "  Status: ${HEALTH_STATUS}"
else
    echo -e "${RED}✗ FAIL${NC}"
    exit 1
fi

# 2. Readiness check
echo -n "Readiness: "
if curl -sf "${READY_ENDPOINT}" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PASS${NC}"
    READY_STATUS=$(curl -s "${READY_ENDPOINT}" | jq -r '.status' 2>/dev/null || echo "unknown")
    echo "  Status: ${READY_STATUS}"
else
    echo -e "${YELLOW}⚠ WARNING${NC}"
    echo "  Agent may not be ready to accept traffic"
fi

# 3. Metrics check
echo -n "Metrics endpoint: "
if curl -sf "${METRICS_ENDPOINT}" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PASS${NC}"

    # Extract key metrics
    METRICS=$(curl -s "${METRICS_ENDPOINT}")

    UPTIME=$(echo "$METRICS" | grep "^agent_uptime_seconds" | awk '{print $2}' || echo "0")
    ACTIVE_SESSIONS=$(echo "$METRICS" | grep "^agent_active_sessions" | awk '{print $2}' || echo "0")

    # Calculate total and failed requests from agent_requests_total metric with status label
    REQUESTS_TOTAL=$(echo "$METRICS" | grep 'agent_requests_total{' | awk '{sum += $2} END {print sum+0}')
    REQUESTS_FAILED=$(echo "$METRICS" | grep 'agent_requests_total{.*status="error"' | awk '{print $2}' || echo "0")

    echo "  Uptime: ${UPTIME}s"
    echo "  Total Requests: ${REQUESTS_TOTAL}"
    echo "  Failed Requests: ${REQUESTS_FAILED}"
    echo "  Active Sessions: ${ACTIVE_SESSIONS}"

    # Calculate error rate
    if [ "$REQUESTS_TOTAL" != "0" ] && [ "$REQUESTS_TOTAL" != "" ]; then
        ERROR_RATE=$(echo "scale=2; $REQUESTS_FAILED * 100 / $REQUESTS_TOTAL" | bc)
        echo "  Error Rate: ${ERROR_RATE}%"

        # Warning if error rate > 5%
        if (( $(echo "$ERROR_RATE > 5.0" | bc -l) )); then
            echo -e "  ${YELLOW}⚠ High error rate detected${NC}"
        fi
    fi
else
    echo -e "${RED}✗ FAIL${NC}"
    exit 1
fi

# 4. Container/Pod check (if applicable)
echo ""
echo -n "Container status: "
if command -v docker &> /dev/null; then
    CONTAINER_STATUS=$(docker inspect -f '{{.State.Status}}' personal-ai-agent 2>/dev/null || echo "not_found")
    if [ "$CONTAINER_STATUS" = "running" ]; then
        echo -e "${GREEN}✓ Running${NC}"
    else
        echo -e "${RED}✗ ${CONTAINER_STATUS}${NC}"
    fi
elif command -v kubectl &> /dev/null; then
    POD_STATUS=$(kubectl get pods -n ai-agent -l app=ai-agent -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "not_found")
    if [ "$POD_STATUS" = "Running" ]; then
        echo -e "${GREEN}✓ Running${NC}"
    else
        echo -e "${RED}✗ ${POD_STATUS}${NC}"
    fi
else
    echo "N/A (not containerized)"
fi

echo ""
echo "=== Health Check Complete ==="

exit 0
