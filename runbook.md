# Alert Watcher Runbook

## Alert Types

### 1. Failover Alert
- **Meaning:** The active pool has changed (e.g., from blue to green or vice versa), indicating a failover event.
- **Operator Action:**
  - Check the primary container for issues.
  - Investigate logs for errors or crashes in the previous pool.
  - Ensure service continuity and notify stakeholders if needed.

### 2. Error Rate Alert
- **Meaning:** The rate of 5xx errors has exceeded the defined threshold (default: 2%) over the monitoring window.
- **Operator Action:**
  - Review recent application and NGINX logs for error spikes.
  - Identify possible causes (e.g., deployment issues, backend failures).
  - Roll back or escalate as appropriate.

### 3. Maintenance Mode
- **Meaning:** Alerts are suppressed due to planned maintenance (maintenance mode enabled).
- **How to Enable:**
  - Set `MAINTENANCE_MODE=true` in your `.env` file or via environment variable for the watcher container.
  - Restart the watcher service to apply the change.
- **Operator Action:**
  - Enable maintenance mode before planned toggles or deployments to suppress alerts.
  - No action required unless alerts are expected during maintenance.
  - Disable maintenance mode (`MAINTENANCE_MODE=false`) after planned operations to resume alerting.

## Event Response Actions

- **Failover Detected:**
  - Check health of the new primary container (use logs, health endpoints).
  - Investigate the previous primary for errors or crashes.
  - Ensure traffic is being served correctly; notify stakeholders if needed.

- **High Error Rate:**
  - Inspect upstream (backend) logs for error spikes.
  - Consider toggling pools if the primary is unhealthy.
  - Escalate if unable to restore normal operation.

- **Recovery:**
  - Confirm the primary is serving traffic again (check logs, health endpoints).
  - Monitor for further anomalies.

## General Troubleshooting Steps
- Confirm alert details in Slack or monitoring dashboard.
- Check container and application logs for further context.
- Communicate with the development or infrastructure team as needed.
- Document incident response and resolution steps.

---

## Support / Escalation

For urgent issues or unresolved incidents, escalate to:
- DevOps Team (devops@example.com)
- Project Maintainer (maintainer@example.com)

_Last updated: 2025-11-02_