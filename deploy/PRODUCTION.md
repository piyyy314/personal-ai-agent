# Production Deployment, Monitoring, and Response

This guide describes how to run the personal AI agent in a hardened, observable production environment with real-time alerts and emergency procedures.

## Prerequisites
- Docker + Docker Compose v2
- `.env` populated with secrets (`OPENAI_API_KEY`, optional `SERPAPI_API_KEY`, `API_AUTH_TOKEN`, alert SMTP/webhook credentials)
- Host firewall open only for required ports (defaults: 8000 API, 3000 Grafana, 9090 Prometheus, 9093 Alertmanager, 3100 Loki, 9000 metrics if using CLI mode)

## Deploy
```bash
cd deploy
docker compose -f docker-compose.prod.yml up -d --build
```
Services:
- `agent` (FastAPI on `:8000`, metrics at `/metrics`, health at `/healthz`)
- `prometheus` + `alertmanager` (metrics + alert routing)
- `grafana` (dashboards; default admin password set via `GRAFANA_ADMIN_PASSWORD`)
- `loki` + `promtail` (log aggregation)
- `cadvisor` (container/system health)

### Hardening
- Require API key header `x-api-key` by setting `API_AUTH_TOKEN` in `.env`.
- Keep `.env` outside source control; mount via Docker secrets if available.
- Restrict ingress to Prometheus/Alertmanager/Grafana to admin networks or behind SSO.
- Persist Grafana/Prometheus/Loki volumes for auditability (`grafana-data`, `prometheus-data`, `loki-data`).

## Observability
- Metrics: `http://<host>:8000/metrics` (agent), scraped by Prometheus via `deploy/monitoring/prometheus.yml`.
- Logs: shipped by Promtail to Loki with Docker labels for filtering by container/job.
- Health: `http://<host>:8000/healthz` for readiness/liveness checks.

### Alerting (deploy/monitoring/alert_rules.yml)
- **AgentUnavailable**: session gauge drops to 0.
- **HighErrorRate**: >5% failures over 5m.
- **SlowResponsesP95**: P95 latency > 5s over 5m.
- **SuspiciousAccessDetected**: any security/anomaly counter increase (e.g., suspicious prompt, unauthorized request).
- **Container CPU/Memory**: sustained high utilization for the agent container.

Alertmanager routes critical alerts to the `critical` receiver (webhook) and others to email (`deploy/monitoring/alertmanager.yml`). Set `ALERT_EMAIL`, `ALERT_WEBHOOK_URL`, and SMTP vars in the environment for delivery.

## Runbooks
### Incident / Emergency
1) **Acknowledge** alert in Alertmanager (record incident ID).  
2) **Containment**: scale agent replicas to 0 or revoke API key (rotate `API_AUTH_TOKEN`), block offending IP at firewall/WAF.  
3) **Triage**: review Grafana panels (latency/error/security), inspect recent Loki logs for `event="suspicious_query"` or `event="unauthorized_request"`.  
4) **Eradication**: patch configuration (secrets rotated, rules tightened), redeploy stack.  
5) **Recovery**: restart services, verify health (`/healthz`) and metrics ingestion, watch alerts for 30 minutes.  
6) **Post-incident**: export timelines, update runbooks, and attach Prometheus/Loki snapshots to the ticket.

### Forensics / Audit
- Preserve Loki/Prometheus volumes before redeploying.
- Export relevant log streams from Grafana Explore with time bounds and filters (`job="varlogs"`, `event` labels).
- Capture Prometheus snapshot (`/api/v1/admin/tsdb/snapshot`) for point-in-time metrics.
- Hash and archive `.env` and compose files used in the incident for chain of custody.
- Document access changes (rotated API tokens, firewall rules) in the ticket.

### Disaster Recovery
- Back up Grafana dashboards/config and Prometheus data directories regularly.
- Store `.env` secrets in a vault; ensure off-host copy of the compose files.
- Test restore quarterly: bring up stack from backups on an isolated host and validate alerts fire via smoke tests.

## Smoke Tests
After deploy:
1) `curl -H "x-api-key: $API_AUTH_TOKEN" -X POST http://localhost:8000/v1/chat -d '{"prompt":"ping"}' -H 'Content-Type: application/json'`
2) `curl http://localhost:8000/metrics | head` (verify Prometheus scrape).
3) Trigger a synthetic security event: send prompt containing “secret” and confirm `agent_security_events_total` increments and alert fires.

