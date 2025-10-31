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
- **Operator Action:**
  - No action required unless alerts are expected during maintenance.
  - Disable maintenance mode after planned operations to resume alerting.

## General Troubleshooting Steps
- Confirm alert details in Slack or monitoring dashboard.
- Check container and application logs for further context.
- Communicate with the development or infrastructure team as needed.
- Document incident response and resolution steps.

---

_Last updated: {{DATE}}_