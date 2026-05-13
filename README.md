# Personal AI Agent - Production Ready with Monitoring & Compliance

This project contains a production-ready personal AI agent using LangChain, featuring comprehensive monitoring, alerting, and compliance capabilities.

## ✨ Features

### Core Functionality
- Conversational memory (in-process)
- Optional web search via SerpAPI
- Calculator tool (LLM Math Chain)
- CLI loop for local use

### Production Features
- **Advanced Monitoring**: Prometheus metrics, Grafana dashboards, log aggregation
- **Multi-Channel Alerting**: Slack, PagerDuty, email notifications
- **Compliance**: Audit logging, GDPR/SOC2 alignment, data retention policies
- **Security**: Container hardening, encryption, access controls
- **High Availability**: Kubernetes deployment, health checks, auto-restart
- **Incident Response**: Forensic tools, emergency procedures, runbooks

## 🚀 Ways to Run

### Option 1: FastAPI service (production-ready, monitored)
- Requires OpenAI key (or swap LLM implementation).
- Exposes `/v1/chat`, `/healthz`, and `/metrics` for Prometheus.
- Set `API_AUTH_TOKEN` in `.env` to protect the API; set `AUTH_DISABLED=true` to opt out in dev.

### Option 2: Cloud-Based CLI (OpenAI)
Uses OpenAI API - easy to set up but requires API key and sends data to cloud.

### Option 3: 100% Local & Private (Ollama) ⭐ RECOMMENDED
✅ **Completely private** - no data leaves your computer
✅ **No restrictions** - use uncensored open-source models
✅ **No API costs** - free to run 24/7
✅ **Works offline** - no internet needed after setup

👉 **[See SETUP_LOCAL.md for full local setup guide](SETUP_LOCAL.md)**

## 📊 Monitoring Stack

The production deployment includes:
- **Prometheus**: Metrics collection and storage
- **Grafana**: Visualization dashboards
- **AlertManager**: Alert routing and notifications
- **Loki**: Log aggregation
- **Promtail**: Log shipping

## Requirements

- Python 3.8+
- pip
- If using OpenAI: OPENAI_API_KEY
- (Optional) SERPAPI_API_KEY for web search
- Docker 20.10+ (for containerized deployment)
- Docker Compose 2.0+ (for full monitoring stack)
- Kubernetes 1.21+ (for production deployment)

## Quick Start

### Local Development (CLI)

1. Create project folder and copy files from this repo.
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # macOS/Linux
   .venv\Scripts\activate      # Windows
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and add your keys (set `API_AUTH_TOKEN` to enable auth).
5. Run the API:
   ```bash
   uvicorn server:app --host 0.0.0.0 --port 8000
   ```
6. Test:
   ```bash
   curl -H "x-api-key: $API_AUTH_TOKEN" -H "Content-Type: application/json" \
     -d '{"prompt":"hello"}' http://localhost:8000/v1/chat
   ```

Or run in CLI mode:
   ```bash
   python main.py
   ```

### Production Deployment (Docker Compose)

1. Clone and configure:
   ```bash
   git clone https://github.com/piyyy314/personal-ai-agent.git
   cd personal-ai-agent
   cp .env.example .env
   # Edit .env with your configuration
   ```

2. Start the full monitoring stack:
   ```bash
   cd deploy
   docker-compose -f docker-compose.prod.yml up -d
   ```

3. Access monitoring:
   - Agent API: http://localhost:8000
   - Agent Metrics: http://localhost:8000/metrics
   - Agent Health: http://localhost:8000/healthz
   - Grafana: http://localhost:3000 (admin/admin)
   - Prometheus: http://localhost:9090
   - AlertManager: http://localhost:9093

### Kubernetes Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for comprehensive deployment guide.

```bash
kubectl apply -f deploy/kubernetes/deployment.yml
```

### Docker (standalone)

1. Build:
   ```bash
   docker build -t personal-ai-agent:latest .
   ```
2. Run API (must set env vars in host or docker run):
   ```bash
   docker run --env-file .env -p 8000:8000 personal-ai-agent:latest
   ```

## Monitoring Endpoints

- `/healthz` - Liveness probe
- `/metrics` - Prometheus metrics endpoint

## Health Check

Run the health check script:
```bash
./scripts/health-check.sh
```

## Security & Privacy

- Runs as non-root user in containers
- Comprehensive audit logging
- Encryption at rest and in transit
- No secrets in source control
- GDPR and SOC2 compliant design
- Incident response procedures documented
- Set `API_AUTH_TOKEN` to enforce API-key auth; rotate when incidents occur
- For higher privacy, swap the LLM wrapper to a local model (e.g., LlamaCPP) and remove cloud API keys
- Avoid adding tools that run arbitrary shell commands unless you add strict safeguards

## Security Operations Scenarios

These workflows are designed for authorized defensive operations. Think "Palantir-style visibility" rather than covert action: high-fidelity telemetry, quiet observation, and strict data handling.

### 1. Threat triage with minimal operator friction

- Protect `/v1/chat` with `API_AUTH_TOKEN` so every analyst request is authenticated
- Use the suspicious-query detector to flag credential probes, exfiltration language, and privilege-escalation attempts
- Review `/metrics`, `/healthz`, and the health probe service (`/health`, `/ready`, `/metrics` on port `8080`) for live operational status

### 2. Quiet investigation during incident response

- Prefer passive monitoring from the dedicated health/metrics service when you only need service state and Prometheus counters
- Use structured audit logs to reconstruct access attempts, suspicious classifications, and response timing without storing raw prompts
- Follow the read-only investigation flow in [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md) when you need "stealth" monitoring that avoids unnecessary changes to the running service

### 3. Privacy-first deployment and data safety

- Keep prompts and secrets out of logs; the default audit trail stores metadata such as query length, response length, status, and source
- Use `AUDIT_LOG_PATH` to persist JSON audit records for retention and forensics
- For the strongest data-boundary posture, use the local-model flow in [SETUP_LOCAL.md](SETUP_LOCAL.md) and remove cloud API keys
- Rotate API keys and review audit logs after any suspected misuse or break-glass event

## Compliance

The system supports:
- **GDPR**: Data privacy controls, right to access/erasure
- **SOC 2**: Security, availability, confidentiality controls
- **HIPAA**: Audit logging, encryption, access controls
- **ISO 27001**: Security management alignment

See [COMPLIANCE.md](COMPLIANCE.md) for details.

## Documentation

- [deploy/PRODUCTION.md](deploy/PRODUCTION.md) - Production deployment runbook
- [DEPLOYMENT.md](DEPLOYMENT.md) - Comprehensive deployment guide
- [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md) - Emergency procedures
- [COMPLIANCE.md](COMPLIANCE.md) - Compliance and security details
- [SETUP_LOCAL.md](SETUP_LOCAL.md) - Local Ollama setup

## Metrics Available

- `agent_requests_total` - Total requests by status and source
- `agent_request_latency_seconds` - Response time histogram
- `agent_security_events_total` - Security/anomaly events
- `agent_session_status` - 1 when running, 0 when stopped

## Alerting

Alerts are configured for:
- **Critical**: Agent down, security/compliance violations
- **Warning**: High error rate, high response time, resource constraints

Alerts route to email and webhook (configure via `ALERT_*` env vars in `.env`).

## Emergency Procedures

For incidents:
1. Check [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md)
2. Run forensic collection: `./scripts/collect-forensics.sh`
3. Review Grafana dashboards
4. Follow severity-based escalation procedures

## Backup and Recovery

```bash
# Backup metrics
docker cp prometheus:/prometheus ./backup/prometheus-$(date +%Y%m%d)

# Backup logs
docker cp loki:/loki ./backup/loki-$(date +%Y%m%d)
```

## Troubleshooting

### Agent won't start
```bash
docker-compose logs agent
curl http://localhost:8000/healthz
```

### Check metrics
```bash
curl http://localhost:8000/metrics
```

### View logs
```bash
docker-compose logs -f agent
```

## Next Steps / Enhancements

- Persistent memory (Chroma/Weaviate)
- RAG indexing personal documents
- Gradio/Streamlit web UI with auth
- Scheduler/background tasks
- Advanced anomaly detection
- Integration with SIEM systems

## Contributing

Please ensure:
- All changes include appropriate monitoring
- Security changes are documented
- Compliance implications are reviewed
- Tests are added for new features

## License

MIT License - See LICENSE file

## Support

- GitHub Issues: https://github.com/piyyy314/personal-ai-agent/issues
- Documentation: See docs/ directory
- Emergency Contact: See INCIDENT_RESPONSE.md
