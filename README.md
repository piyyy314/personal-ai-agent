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

## 🚀 Two Ways to Run

### Option 1: Cloud-Based (OpenAI)
Uses OpenAI API - easy to set up but requires API key and sends data to cloud.

### Option 2: 100% Local & Private (Ollama) ⭐ RECOMMENDED
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
4. Copy `.env.example` to `.env` and add your keys.
5. Run:
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

2. Start the full stack:
   ```bash
   docker-compose up -d
   ```

3. Access monitoring:
   - Agent Health: http://localhost:8080/health
   - Metrics: http://localhost:8080/metrics
   - Grafana: http://localhost:3000 (admin/admin)
   - Prometheus: http://localhost:9090
   - AlertManager: http://localhost:9093

### Kubernetes Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for comprehensive deployment guide.

```bash
kubectl apply -f deploy/kubernetes/deployment.yml
```

## Monitoring Endpoints

- `/health` - Liveness probe (is the service running?)
- `/ready` - Readiness probe (is the service ready for traffic?)
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

## Compliance

The system supports:
- **GDPR**: Data privacy controls, right to access/erasure
- **SOC 2**: Security, availability, confidentiality controls
- **HIPAA**: Audit logging, encryption, access controls
- **ISO 27001**: Security management alignment

See [COMPLIANCE.md](COMPLIANCE.md) for details.

## Documentation

- [DEPLOYMENT.md](DEPLOYMENT.md) - Comprehensive deployment guide
- [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md) - Emergency procedures
- [COMPLIANCE.md](COMPLIANCE.md) - Compliance and security details
- [SETUP_LOCAL.md](SETUP_LOCAL.md) - Local Ollama setup

## Metrics Available

- `agent_requests_total` - Total requests processed
- `agent_requests_success` - Successful requests
- `agent_requests_failed` - Failed requests
- `agent_response_time_seconds` - Response time histogram
- `agent_active_sessions` - Current active sessions
- `agent_uptime_seconds` - Service uptime
- `agent_compliance_violations` - Compliance issues detected
- `agent_security_events` - Security events logged

## Alerting

Alerts are configured for:
- **Critical**: Agent down, high error rate, security/compliance violations
- **Warning**: High response time, resource constraints
- **Info**: Deployments, configuration changes

Alerts route to:
- Slack channels
- PagerDuty (for critical alerts)
- Email notifications

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
curl http://localhost:8080/health
```

### Check metrics
```bash
curl http://localhost:8080/metrics
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
