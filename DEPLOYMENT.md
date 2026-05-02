# Deployment Guide - Personal AI Agent

## Overview

This guide provides comprehensive instructions for deploying the Personal AI Agent to production with advanced monitoring, alerting, and compliance features.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Production Environment                    │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  AI Agent    │───▶│  Prometheus  │───▶│   Grafana    │  │
│  │  Container   │    │   (Metrics)  │    │ (Dashboard)  │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│         │                     │                              │
│         │                     ▼                              │
│         │            ┌──────────────┐                        │
│         │            │ AlertManager │                        │
│         │            │  (Alerts)    │                        │
│         │            └──────────────┘                        │
│         │                     │                              │
│         │                     ├──▶ Slack                     │
│         │                     ├──▶ PagerDuty                 │
│         │                     └──▶ Email                     │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────┐    ┌──────────────┐                       │
│  │     Loki     │◀───│   Promtail   │                       │
│  │    (Logs)    │    │ (Log Agent)  │                       │
│  └──────────────┘    └──────────────┘                       │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Deployment Options

### Option 1: Docker Compose (Recommended for Development/Testing)

#### Prerequisites
- Docker 20.10+
- Docker Compose 2.0+
- 4GB RAM minimum
- 10GB disk space

#### Steps

1. **Clone and prepare environment**
   ```bash
   git clone https://github.com/piyyy314/personal-ai-agent.git
   cd personal-ai-agent
   cp .env.example .env
   ```

2. **Configure environment variables**
   Edit `.env` and set required variables:
   ```bash
   # Required
   OPENAI_API_KEY=sk-your-key-here

   # Optional
   SERPAPI_API_KEY=your-serpapi-key
   HEALTH_PORT=8080
   LOG_LEVEL=INFO

   # Alerting (optional)
   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
   PAGERDUTY_SERVICE_KEY=your-pagerduty-key
   ALERT_EMAIL_TO=alerts@example.com
   ALERT_EMAIL_FROM=noreply@example.com
   SMTP_SMARTHOST=smtp.gmail.com:587
   SMTP_USERNAME=your-email@gmail.com
   SMTP_PASSWORD=your-app-password
   ```

3. **Start the stack**
   ```bash
   docker-compose up -d
   ```

4. **Verify deployment**
   ```bash
   # Check all containers are running
   docker-compose ps

   # Check agent health
   curl http://localhost:8080/health

   # Check metrics
   curl http://localhost:8080/metrics
   ```

5. **Access monitoring dashboards**
   - Grafana: http://localhost:3000 (admin/admin)
   - Prometheus: http://localhost:9090
   - AlertManager: http://localhost:9093

### Option 2: Kubernetes (Production)

#### Prerequisites
- Kubernetes 1.21+
- kubectl configured
- Helm 3.0+ (optional)
- Storage provisioner

#### Steps

1. **Create namespace and apply manifests**
   ```bash
   kubectl apply -f deploy/kubernetes/deployment.yml
   ```

2. **Configure secrets**
   ```bash
   # Update the secret with actual values
   kubectl create secret generic agent-secrets \
     --from-literal=OPENAI_API_KEY=your-key \
     --from-literal=SERPAPI_API_KEY=your-key \
     -n ai-agent
   ```

3. **Verify deployment**
   ```bash
   kubectl get pods -n ai-agent
   kubectl get svc -n ai-agent
   kubectl logs -n ai-agent -l app=ai-agent
   ```

4. **Check health**
   ```bash
   kubectl port-forward -n ai-agent svc/ai-agent 8080:8080
   curl http://localhost:8080/health
   ```

## Monitoring Setup

### Metrics Available

The agent exposes the following Prometheus metrics at `/metrics`:

- `agent_requests_total` - Total number of requests
- `agent_requests_success` - Successful requests
- `agent_requests_failed` - Failed requests
- `agent_response_time_seconds` - Response time histogram
- `agent_active_sessions` - Number of active sessions
- `agent_uptime_seconds` - Agent uptime
- `agent_compliance_violations` - Compliance violations detected
- `agent_security_events` - Security events detected

### Grafana Dashboards

1. Access Grafana at http://localhost:3000
2. Login with admin/admin
3. The "AI Agent - Production Monitoring" dashboard is pre-configured
4. Dashboard includes:
   - System health status
   - Request rate and response time
   - Error rates
   - Security and compliance metrics
   - Log viewer

### Log Aggregation

Logs are collected by Promtail and stored in Loki:
- Structured JSON logs with full context
- Audit logs for compliance
- Security event logs
- Error tracking

View logs in Grafana using the Loki data source.

## Alerting Configuration

### Alert Severity Levels

1. **Critical** - Immediate action required
   - Agent down
   - High error rate (>10%)
   - Compliance violations
   - Security events
   - Routes to: PagerDuty, Slack, Email

2. **Warning** - Attention needed
   - High response time
   - High resource usage
   - Routes to: Slack

3. **Info** - Informational
   - New deployments
   - Routes to: Slack (info channel)

### Configuring Alert Channels

#### Slack Integration
1. Create a Slack webhook URL
2. Set `SLACK_WEBHOOK_URL` in AlertManager config
3. Configure channels:
   - `#ai-agent-critical` - Critical alerts
   - `#ai-agent-warnings` - Warning alerts
   - `#ai-agent-info` - Info alerts
   - `#security-alerts` - Security events
   - `#compliance-alerts` - Compliance violations

#### PagerDuty Integration
1. Create a PagerDuty service integration
2. Get the integration key
3. Set `PAGERDUTY_SERVICE_KEY` in AlertManager config

#### Email Alerts
Configure SMTP settings in AlertManager config:
```yaml
SMTP_SMARTHOST: smtp.gmail.com:587
SMTP_USERNAME: your-email@gmail.com
SMTP_PASSWORD: your-app-password
```

## Security Hardening

### Container Security
- Runs as non-root user (UID 1000)
- Read-only root filesystem where possible
- Dropped all unnecessary capabilities
- Multi-stage build for minimal attack surface

### Network Security
- Health check endpoint on separate port
- No external exposure required for agent
- TLS/SSL for external communications

### Secrets Management
- Environment variables for secrets
- Kubernetes secrets integration
- Support for external secret managers (Vault, AWS Secrets Manager)

## Compliance Features

### Audit Logging
All actions are logged with:
- Timestamp
- User/session ID
- Action type
- Resource accessed
- Outcome
- Metadata

Audit logs are stored in `/var/log/agent/audit.log` in JSON format.

### Data Retention
- Metrics: 30 days (configurable in Prometheus)
- Logs: 31 days (configurable in Loki)
- Audit logs: Retained according to compliance requirements

### Access Control
- Role-based access control (RBAC) in Kubernetes
- Service account with minimal permissions
- Network policies to restrict traffic

## Troubleshooting

### Agent Won't Start
```bash
# Check logs
docker-compose logs agent
# or
kubectl logs -n ai-agent -l app=ai-agent

# Verify environment variables
docker-compose exec agent env | grep -i api

# Check health endpoint
curl http://localhost:8080/health
```

### High Memory Usage
```bash
# Check resource usage
docker stats
# or
kubectl top pods -n ai-agent

# Scale down if needed
kubectl scale deployment ai-agent --replicas=1 -n ai-agent
```

### Missing Metrics
```bash
# Verify metrics endpoint
curl http://localhost:8080/metrics

# Check Prometheus targets
# Visit http://localhost:9090/targets
```

### Alerts Not Firing
```bash
# Check AlertManager
curl http://localhost:9093/api/v2/alerts

# Verify alert rules
curl http://localhost:9090/api/v1/rules

# Check AlertManager logs
docker-compose logs alertmanager
```

## Scaling

### Horizontal Scaling
```bash
# Kubernetes
kubectl scale deployment ai-agent --replicas=3 -n ai-agent

# Docker Compose
docker-compose up -d --scale agent=3
```

### Resource Tuning
Adjust in Kubernetes deployment:
```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "200m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

## Backup and Recovery

### Backup Metrics
```bash
# Prometheus data
docker cp prometheus:/prometheus ./backup/prometheus-$(date +%Y%m%d)
```

### Backup Logs
```bash
# Loki data
docker cp loki:/loki ./backup/loki-$(date +%Y%m%d)
```

### Disaster Recovery
1. Restore data volumes
2. Redeploy using same configuration
3. Verify health checks
4. Review audit logs for gaps

## Maintenance

### Updates
```bash
# Pull latest images
docker-compose pull

# Rolling update
docker-compose up -d --no-deps --build agent

# Kubernetes rolling update
kubectl set image deployment/ai-agent agent=personal-ai-agent:v1.1.0 -n ai-agent
```

### Log Rotation
Logs are automatically rotated by Loki based on retention policy.

## Support and Resources

- GitHub Issues: https://github.com/piyyy314/personal-ai-agent/issues
- Documentation: README.md, SETUP_LOCAL.md
- Runbooks: See `/docs/runbooks/` directory
- Emergency Contacts: See INCIDENT_RESPONSE.md
