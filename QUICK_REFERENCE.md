# Quick Reference Guide - Monitoring & Compliance

## 🚀 Quick Start Commands

### Deploy Full Stack
```bash
./scripts/quick-deploy.sh
```

### Check System Health
```bash
./scripts/health-check.sh
```

### Collect Forensic Data
```bash
./scripts/collect-forensics.sh
```

## 📊 Monitoring Endpoints

| Endpoint | URL | Purpose |
|----------|-----|---------|
| Agent Health | http://localhost:8080/health | Liveness probe |
| Agent Ready | http://localhost:8080/ready | Readiness probe |
| Metrics | http://localhost:8080/metrics | Prometheus metrics |
| Grafana | http://localhost:3000 | Dashboards (admin/admin) |
| Prometheus | http://localhost:9090 | Metrics storage |
| AlertManager | http://localhost:9093 | Alert management |

## 🔔 Alert Severity Levels

| Severity | Response Time | Channels | Example |
|----------|--------------|----------|---------|
| Critical | < 15 min | PagerDuty, Slack, Email | Agent down, security breach |
| Warning | < 1 hour | Slack | High latency, resource constraints |
| Info | Next day | Slack (info channel) | Deployments, config changes |

## 📈 Key Metrics

```promql
# Request rate
rate(agent_requests_total[5m])

# Error rate percentage
100 * rate(agent_requests_failed[5m]) / rate(agent_requests_total[5m])

# Average response time
agent_response_time_seconds_sum / agent_response_time_seconds_count

# Active sessions
agent_active_sessions

# Security events
increase(agent_security_events[5m])

# Compliance violations
increase(agent_compliance_violations[5m])
```

## 🔧 Common Operations

### View Logs
```bash
# Docker Compose
docker-compose logs -f agent

# Kubernetes
kubectl logs -n ai-agent -l app=ai-agent -f
```

### Restart Service
```bash
# Docker Compose
docker-compose restart agent

# Kubernetes
kubectl rollout restart deployment/ai-agent -n ai-agent
```

### Scale Service
```bash
# Docker Compose
docker-compose up -d --scale agent=3

# Kubernetes
kubectl scale deployment ai-agent --replicas=3 -n ai-agent
```

### Check Container Status
```bash
# Docker
docker ps | grep agent
docker stats personal-ai-agent

# Kubernetes
kubectl get pods -n ai-agent
kubectl top pods -n ai-agent
```

## 🚨 Emergency Procedures

### Agent Down
1. Check health: `curl http://localhost:8080/health`
2. View logs: `docker-compose logs agent`
3. Restart: `docker-compose restart agent`
4. Escalate if not resolved in 15 minutes

### High Error Rate
1. Check metrics dashboard in Grafana
2. Review error logs: `docker-compose logs agent | grep -i error`
3. Identify pattern (API issues, resource constraints, etc.)
4. Apply mitigation based on root cause

### Security Event
1. Run forensic collection: `./scripts/collect-forensics.sh`
2. Review security logs: `grep security_event /var/log/agent/audit.log`
3. Isolate if necessary: `docker-compose stop agent`
4. Follow incident response procedures in INCIDENT_RESPONSE.md

### Compliance Violation
1. Review audit logs for violation details
2. Document the incident
3. Notify compliance team
4. Implement corrective measures
5. Update policies if needed

## 📋 Pre-Deployment Checklist

- [ ] `.env` file configured with API keys
- [ ] Alerting channels configured (Slack, email, PagerDuty)
- [ ] SMTP settings for email alerts
- [ ] Backup procedures tested
- [ ] Incident response team contacts updated
- [ ] Grafana dashboards reviewed
- [ ] Alert rules tested
- [ ] Health checks verified
- [ ] Log retention policies configured
- [ ] Compliance requirements reviewed

## 📝 Daily Operations Checklist

- [ ] Review Grafana dashboard for anomalies
- [ ] Check AlertManager for active alerts
- [ ] Verify backup completion
- [ ] Review security and compliance metrics
- [ ] Check system resource usage
- [ ] Scan logs for errors

## 📞 Emergency Contacts

| Role | Contact | When to Escalate |
|------|---------|------------------|
| On-Call Engineer | [Phone/Slack] | All SEV-1/SEV-2 incidents |
| Security Lead | [Phone/Email] | Security events, breaches |
| Compliance Officer | [Phone/Email] | Compliance violations |
| Engineering Manager | [Phone/Email] | SEV-1 incidents after 30 min |

## 🔐 Security Best Practices

1. **Never commit secrets** - Use `.env` files (gitignored)
2. **Rotate keys regularly** - API keys, passwords every 90 days
3. **Review access logs** - Check audit logs daily
4. **Update dependencies** - Security patches within 7 days
5. **Encrypt sensitive data** - Both at rest and in transit
6. **Least privilege** - Minimal permissions for service accounts
7. **Monitor continuously** - 24/7 alerting enabled

## 📚 Documentation Index

| Document | Purpose | When to Use |
|----------|---------|-------------|
| README.md | Getting started | Initial setup |
| DEPLOYMENT.md | Production deployment | Deploying to production |
| INCIDENT_RESPONSE.md | Emergency procedures | During incidents |
| COMPLIANCE.md | Compliance & security | Audits, certifications |
| SETUP_LOCAL.md | Local Ollama setup | Privacy-focused deployment |

## 🛠️ Troubleshooting Quick Fixes

### "Connection refused" on health endpoint
- Check if container is running: `docker ps`
- Check port mapping: `docker port personal-ai-agent`
- Restart service: `docker-compose restart agent`

### Prometheus not scraping metrics
- Verify agent health endpoint works
- Check Prometheus targets: http://localhost:9090/targets
- Review Prometheus logs: `docker-compose logs prometheus`

### Grafana shows no data
- Verify Prometheus datasource in Grafana
- Check time range in dashboard (top-right)
- Ensure metrics are being generated (run some queries)

### Alerts not firing
- Check AlertManager configuration: http://localhost:9093
- Verify alert rules in Prometheus: http://localhost:9090/rules
- Test alert with: `curl -X POST http://localhost:9093/api/v1/alerts`

### High memory usage
- Check active sessions metric
- Review for memory leaks in logs
- Restart service to clear memory
- Consider increasing resource limits

## 🎯 Performance Targets

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Uptime | 99.9% | < 99.5% |
| Response Time | < 2s avg | > 5s avg |
| Error Rate | < 1% | > 10% |
| CPU Usage | < 50% | > 80% |
| Memory Usage | < 60% | > 80% |
| Disk Usage | < 70% | > 85% |

## 📦 Backup Schedule

| Item | Frequency | Retention | Location |
|------|-----------|-----------|----------|
| Metrics (Prometheus) | Daily | 30 days | ./backup/ |
| Logs (Loki) | Daily | 31 days | ./backup/ |
| Audit Logs | Daily | 7 years | ./backup/ |
| Configuration | On change | Forever | Git |

## 🔄 Update Procedures

### Application Updates
1. Test in development environment
2. Review changes for monitoring impact
3. Update documentation if needed
4. Deploy during maintenance window
5. Monitor for 1 hour post-deployment
6. Rollback if issues detected

### Monitoring Stack Updates
1. Check compatibility with current setup
2. Test in non-production first
3. Backup current configuration
4. Update one component at a time
5. Verify all dashboards still work
6. Update alert rules if needed

## 💡 Tips

- Use `./scripts/health-check.sh` regularly to verify system health
- Keep Grafana dashboards open during deployments
- Set up Slack notifications for immediate awareness
- Review audit logs weekly for compliance
- Test backup restoration quarterly
- Update runbooks based on incident learnings
- Document all configuration changes

---

**Last Updated:** 2026-04-17
**Version:** 1.0.0
