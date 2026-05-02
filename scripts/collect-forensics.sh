#!/bin/bash
# Forensic data collection script
# Collects logs, metrics, and system state for incident investigation

set -e

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
FORENSICS_DIR="forensics-${TIMESTAMP}"

echo "Collecting forensic data..."
echo "Output directory: ${FORENSICS_DIR}"

mkdir -p "${FORENSICS_DIR}"/{logs,metrics,system,network}

# System information
echo "[1/6] Collecting system information..."
{
    echo "=== System Info ==="
    uname -a
    echo ""
    echo "=== Date/Time ==="
    date -Iseconds
    echo ""
    echo "=== Uptime ==="
    uptime
} > "${FORENSICS_DIR}/system/info.txt"

# Docker/Container state
echo "[2/6] Collecting container state..."
if command -v docker &> /dev/null; then
    docker ps -a > "${FORENSICS_DIR}/system/containers.txt" 2>&1 || true
    docker inspect personal-ai-agent > "${FORENSICS_DIR}/system/container-inspect.json" 2>&1 || true
    docker stats --no-stream > "${FORENSICS_DIR}/system/container-stats.txt" 2>&1 || true
fi

# Kubernetes state (if applicable)
if command -v kubectl &> /dev/null; then
    echo "[2b/6] Collecting Kubernetes state..."
    kubectl get pods -n ai-agent -o yaml > "${FORENSICS_DIR}/system/k8s-pods.yaml" 2>&1 || true
    kubectl get events -n ai-agent > "${FORENSICS_DIR}/system/k8s-events.txt" 2>&1 || true
    kubectl describe pods -n ai-agent > "${FORENSICS_DIR}/system/k8s-describe.txt" 2>&1 || true
fi

# Application logs
echo "[3/6] Collecting application logs..."
if [ -d "/var/log/agent" ]; then
    cp -r /var/log/agent "${FORENSICS_DIR}/logs/" 2>&1 || true
fi

# Docker logs
if command -v docker &> /dev/null; then
    docker logs personal-ai-agent > "${FORENSICS_DIR}/logs/docker-stdout.log" 2>&1 || true
fi

# Kubernetes logs
if command -v kubectl &> /dev/null; then
    kubectl logs -n ai-agent -l app=ai-agent --all-containers > "${FORENSICS_DIR}/logs/k8s-logs.log" 2>&1 || true
fi

# Metrics snapshot
echo "[4/6] Collecting metrics..."
curl -s http://localhost:8080/metrics > "${FORENSICS_DIR}/metrics/metrics-snapshot.txt" 2>&1 || true
curl -s http://localhost:8080/health > "${FORENSICS_DIR}/metrics/health.json" 2>&1 || true
curl -s http://localhost:8080/ready > "${FORENSICS_DIR}/metrics/ready.json" 2>&1 || true

# Prometheus data (if accessible)
if command -v promtool &> /dev/null; then
    promtool query instant http://localhost:9090 'agent_requests_total' > "${FORENSICS_DIR}/metrics/prometheus-requests.txt" 2>&1 || true
fi

# Network information
echo "[5/6] Collecting network information..."
{
    echo "=== Network Interfaces ==="
    ip addr show 2>/dev/null || ifconfig
    echo ""
    echo "=== Routing Table ==="
    ip route show 2>/dev/null || netstat -rn
    echo ""
    echo "=== Active Connections ==="
    netstat -an 2>/dev/null || ss -an
} > "${FORENSICS_DIR}/network/network-info.txt" 2>&1 || true

# Process information
echo "[6/6] Collecting process information..."
if command -v docker &> /dev/null; then
    docker exec personal-ai-agent ps aux > "${FORENSICS_DIR}/system/processes.txt" 2>&1 || true
fi

# Create manifest and checksums
echo "Creating evidence manifest..."
{
    echo "Forensic Evidence Collection"
    echo "============================"
    echo ""
    echo "Timestamp: ${TIMESTAMP}"
    echo "Collected by: $(whoami)"
    echo "Hostname: $(hostname)"
    echo ""
    echo "Files:"
    find "${FORENSICS_DIR}" -type f -exec ls -lh {} \;
} > "${FORENSICS_DIR}/MANIFEST.txt"

# Calculate checksums
find "${FORENSICS_DIR}" -type f -exec sha256sum {} \; > "${FORENSICS_DIR}/CHECKSUMS.sha256"

# Create tarball
echo "Creating archive..."
tar czf "${FORENSICS_DIR}.tar.gz" "${FORENSICS_DIR}"

echo ""
echo "Forensic data collection complete!"
echo "Archive: ${FORENSICS_DIR}.tar.gz"
echo ""
echo "To encrypt the evidence:"
echo "  gpg --encrypt --recipient security@example.com ${FORENSICS_DIR}.tar.gz"
echo ""
echo "To verify checksums:"
echo "  cd ${FORENSICS_DIR} && sha256sum -c CHECKSUMS.sha256"
