# Incident Response and Forensic Procedures

## Overview

This document provides emergency response procedures, forensic investigation guidelines, and stealth access protocols for the Personal AI Agent system.

## Incident Response Team

### Roles and Responsibilities

1. **Incident Commander**
   - Overall incident coordination
   - Decision making authority
   - Communication with stakeholders

2. **Security Lead**
   - Security event analysis
   - Threat assessment
   - Containment strategies

3. **Compliance Officer**
   - Regulatory compliance verification
   - Audit trail preservation
   - Legal coordination

4. **Technical Lead**
   - System diagnostics
   - Recovery procedures
   - Post-incident analysis

### Contact Information

```
Incident Commander: [Name] - [Phone] - [Email]
Security Lead: [Name] - [Phone] - [Email]
Compliance Officer: [Name] - [Phone] - [Email]
Technical Lead: [Name] - [Phone] - [Email]

Emergency Hotline: [Number]
Security Operations Center: [Email]
```

## Incident Severity Levels

### SEV-1: Critical
- **Description**: Complete system outage, data breach, active attack
- **Response Time**: Immediate (< 15 minutes)
- **Escalation**: All stakeholders notified
- **Examples**:
  - Agent completely unavailable
  - Unauthorized data access detected
  - Active security compromise
  - Compliance violation with legal implications

### SEV-2: High
- **Description**: Significant degradation, potential security issue
- **Response Time**: < 1 hour
- **Escalation**: Technical and security teams
- **Examples**:
  - High error rates (>25%)
  - Suspicious access patterns
  - Performance degradation affecting users
  - Failed compliance checks

### SEV-3: Medium
- **Description**: Minor issues, degraded performance
- **Response Time**: < 4 hours
- **Escalation**: Technical team
- **Examples**:
  - Elevated error rates (10-25%)
  - Resource constraints
  - Minor monitoring gaps

### SEV-4: Low
- **Description**: Minimal impact, informational
- **Response Time**: Next business day
- **Escalation**: None required
- **Examples**:
  - Configuration changes needed
  - Documentation updates
  - Proactive maintenance

## Emergency Response Procedures

### Step 1: Detection and Triage (0-5 minutes)

1. **Identify the incident**
   - Alert notification received
   - User report
   - Monitoring detection

2. **Initial assessment**
   ```bash
   # Check system status
   curl http://localhost:8080/health

   # Review recent logs
   docker-compose logs --tail=100 agent

   # Check metrics
   curl http://localhost:8080/metrics | grep -E "(failed|error|security|compliance)"
   ```

3. **Determine severity level**
   - Use severity criteria above
   - Document initial findings

### Step 2: Notification (5-15 minutes)

1. **Alert incident response team**
   - Based on severity level
   - Use emergency contact list
   - Document notification times

2. **Create incident ticket**
   - Include severity, description, impact
   - Assign incident commander
   - Set up communication channels

3. **Stakeholder notification**
   - For SEV-1/SEV-2: Immediate notification
   - For SEV-3/SEV-4: During business hours

### Step 3: Containment (15-60 minutes)

#### For Security Incidents

1. **Isolate affected systems**
   ```bash
   # Kubernetes: Scale down to stop accepting traffic
   kubectl scale deployment ai-agent --replicas=0 -n ai-agent

   # Docker: Stop container
   docker-compose stop agent
   ```

2. **Preserve evidence**
   ```bash
   # Capture current state
   kubectl get pods -n ai-agent -o yaml > incident-pods-$(date +%Y%m%d-%H%M%S).yaml

   # Export logs
   kubectl logs -n ai-agent -l app=ai-agent --all-containers > incident-logs-$(date +%Y%m%d-%H%M%S).log

   # Snapshot metrics
   curl http://prometheus:9090/api/v1/query?query=agent_requests_total > incident-metrics-$(date +%Y%m%d-%H%M%S).json
   ```

3. **Block suspicious access**
   ```bash
   # Update network policies
   kubectl apply -f emergency-network-policy.yml
   ```

#### For Availability Incidents

1. **Attempt quick recovery**
   ```bash
   # Restart service
   kubectl rollout restart deployment/ai-agent -n ai-agent

   # Or with Docker
   docker-compose restart agent
   ```

2. **Scale resources if needed**
   ```bash
   # Increase replicas
   kubectl scale deployment ai-agent --replicas=3 -n ai-agent

   # Increase resource limits
   kubectl set resources deployment ai-agent --limits=memory=1Gi,cpu=1000m -n ai-agent
   ```

### Step 4: Investigation (Parallel with containment)

1. **Collect forensic data**
   ```bash
   # Full system snapshot
   ./scripts/collect-forensics.sh
   ```

2. **Analyze logs for root cause**
   ```bash
   # Search for errors
   grep -i "error\|failed\|exception" /var/log/agent/audit.log

   # Check for security events
   grep -i "security_event\|unauthorized\|violation" /var/log/agent/audit.log

   # Timeline analysis
   cat /var/log/agent/audit.log | jq -r '.timestamp + " " + .event_type + " " + .message' | sort
   ```

3. **Review metrics**
   - Check Grafana dashboards
   - Analyze Prometheus queries
   - Identify anomalies

### Step 5: Recovery (1-4 hours)

1. **Implement fix**
   - Apply patches
   - Update configurations
   - Deploy hotfixes

2. **Restore service**
   ```bash
   # Deploy fixed version
   kubectl set image deployment/ai-agent agent=personal-ai-agent:hotfix-$(date +%Y%m%d) -n ai-agent

   # Verify health
   kubectl wait --for=condition=ready pod -l app=ai-agent -n ai-agent --timeout=300s
   ```

3. **Verify resolution**
   ```bash
   # Run health checks
   curl http://localhost:8080/health
   curl http://localhost:8080/ready

   # Monitor for 15 minutes
   watch -n 10 'curl -s http://localhost:8080/metrics | grep agent_requests'
   ```

### Step 6: Communication (Ongoing)

1. **Status updates**
   - Every 30 minutes for SEV-1
   - Every 2 hours for SEV-2
   - Daily for SEV-3/SEV-4

2. **Final notification**
   - Incident resolved message
   - Summary of impact
   - Next steps

### Step 7: Post-Incident Review (24-48 hours after resolution)

1. **Conduct post-mortem**
   - Timeline of events
   - Root cause analysis
   - Impact assessment
   - Response effectiveness

2. **Document lessons learned**
   - What went well
   - What could be improved
   - Action items

3. **Implement improvements**
   - Update runbooks
   - Enhance monitoring
   - Improve alerts
   - Train team

## Forensic Investigation

### Evidence Collection

1. **System snapshots**
   ```bash
   # Container state
   docker inspect personal-ai-agent > forensics/container-state.json

   # Environment variables (sanitized)
   docker exec personal-ai-agent env | grep -v -i "key\|password\|secret" > forensics/env-vars.txt

   # Process list
   docker exec personal-ai-agent ps aux > forensics/processes.txt
   ```

2. **Log collection**
   ```bash
   # All application logs
   cp -r /var/log/agent forensics/logs-$(date +%Y%m%d)/

   # System logs
   journalctl -u docker > forensics/docker-journal.log
   ```

3. **Network traffic**
   ```bash
   # Active connections
   docker exec personal-ai-agent netstat -an > forensics/network-connections.txt

   # Recent traffic (if packet capture enabled)
   tcpdump -r /var/log/packets.pcap > forensics/traffic-analysis.txt
   ```

4. **Metrics snapshot**
   ```bash
   # Export all metrics
   curl http://localhost:8080/metrics > forensics/metrics-snapshot.txt

   # Prometheus data export
   promtool tsdb dump /prometheus > forensics/prometheus-dump.txt
   ```

### Chain of Custody

1. **Document evidence**
   - Create manifest of all collected files
   - Calculate checksums
   - Timestamp collection

   ```bash
   # Create evidence manifest
   find forensics/ -type f -exec sha256sum {} \; > forensics/MANIFEST.sha256
   echo "Collected by: $(whoami)" >> forensics/MANIFEST.txt
   echo "Timestamp: $(date -Iseconds)" >> forensics/MANIFEST.txt
   ```

2. **Secure storage**
   - Compress and encrypt
   - Store in secure location
   - Restrict access

   ```bash
   # Encrypt evidence
   tar czf - forensics/ | gpg --encrypt --recipient security@example.com > evidence-$(date +%Y%m%d-%H%M%S).tar.gz.gpg
   ```

3. **Access log**
   - Maintain record of who accessed evidence
   - Document when and why

### Analysis Tools

1. **Log analysis**
   ```bash
   # Find suspicious patterns
   jq 'select(.event_type == "security_event")' /var/log/agent/audit.log

   # Timeline of events
   jq -r '.timestamp + " " + .user_id + " " + .action + " " + .outcome' /var/log/agent/audit.log | sort

   # Failed access attempts
   jq 'select(.outcome == "error" or .outcome == "unauthorized")' /var/log/agent/audit.log
   ```

2. **Metrics analysis**
   ```bash
   # Anomaly detection
   # Look for sudden spikes or drops
   promtool query instant http://localhost:9090 'rate(agent_requests_failed[5m])'
   ```

## Stealth Access Protocols

The goal of "stealth" mode is quiet, read-only observation for authorized defenders. It is not meant to suppress audit trails or bypass approval requirements.

### Emergency Access

For critical incidents requiring immediate access without triggering normal alerting:

1. **Break-glass access**
   ```bash
   # Use emergency service account
   kubectl --as=system:serviceaccount:ai-agent:emergency-admin get pods -n ai-agent

   # Access is logged separately
   # Review: kubectl get events --all-namespaces | grep emergency-admin
   ```

2. **Forensic mode**
   ```bash
   # Start agent in forensic mode (read-only, enhanced logging)
   kubectl set env deployment/ai-agent FORENSIC_MODE=true -n ai-agent
   ```

### Monitoring During Investigation

1. **Silent monitoring**
   ```bash
   # Review recent logs directly; reading logs is passive, and visible output helps preserve operator awareness
   kubectl logs -n ai-agent -l app=ai-agent --tail=100

   # Query metrics from the dedicated health/metrics service
   curl -s http://localhost:8080/metrics | grep -v "scrape"
   ```

2. **Passive observation**
   - Use read-only Grafana dashboards
   - Prefer stored Prometheus data over ad-hoc changes to alert rules
   - Review stored audit logs and incident timelines

## Compliance and Legal Considerations

### Data Breach Response

1. **Immediate actions**
   - Contain the breach
   - Assess scope
   - Preserve evidence

2. **Notification requirements**
   - GDPR: 72 hours
   - State laws: Varies
   - Industry regulations: Per requirements

3. **Documentation**
   - Incident timeline
   - Data affected
   - Individuals impacted
   - Mitigation steps

### Audit Trail

All incident response actions are logged in:
- `/var/log/agent/incident-response.log`
- Incident tracking system
- Compliance management system

### Regulatory Reporting

File reports with:
- Data Protection Authority (if applicable)
- Industry regulators
- Law enforcement (if criminal activity)

## Training and Drills

### Quarterly Drills

1. **Tabletop exercises**
   - Simulated incidents
   - Decision-making practice
   - Process verification

2. **Technical drills**
   - Practice recovery procedures
   - Test backup restoration
   - Verify monitoring

### Annual Review

- Update contact information
- Review and update procedures
- Incorporate lessons learned
- Compliance verification

## Appendix: Quick Reference

### Critical Commands

```bash
# Health check
curl http://localhost:8080/health

# Stop service immediately
kubectl scale deployment ai-agent --replicas=0 -n ai-agent

# Collect logs
kubectl logs -n ai-agent -l app=ai-agent --all-containers > incident-logs.txt

# Start forensic collection
./scripts/collect-forensics.sh

# Emergency contact
emergency-hotline: [NUMBER]
```

### Escalation Matrix

| Severity | Initial Contact | Escalate After | Final Escalation |
|----------|----------------|----------------|------------------|
| SEV-1    | On-call + Security | 15 minutes | Executive team |
| SEV-2    | On-call | 1 hour | Security lead |
| SEV-3    | On-call | 4 hours | Team lead |
| SEV-4    | Ticket | Next day | None |

### Useful Links

- Monitoring Dashboard: http://localhost:3000
- Metrics: http://localhost:8080/metrics
- Alerts: http://localhost:9093
- Documentation: /docs/
- Runbooks: /docs/runbooks/
