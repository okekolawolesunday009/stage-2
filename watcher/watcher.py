import os
import json
import time
import requests
from collections import deque
from datetime import datetime

# ---------------- CONFIG ----------------
SLACK_WEBHOOK = os.getenv('SLACK_WEBHOOK_URL', '')
ERROR_THRESHOLD = float(os.getenv('ERROR_RATE_THRESHOLD', '2'))
WINDOW_SIZE = int(os.getenv('WINDOW_SIZE', '200'))
ALERT_COOLDOWN_SEC = int(os.getenv('ALERT_COOLDOWN_SEC', '300'))
MAINTENANCE_MODE = os.getenv('MAINTENANCE_MODE', 'false').lower() == 'true'
LOG_FILE =  os.getenv('WATCH_LOG_PATH', '/var/log/nginx/access.log')


# ---------------- STATE -----------------
last_pool = None
request_window = deque(maxlen=WINDOW_SIZE)
last_failover_alert = 0
last_error_rate_alert = 0

print(f"[WATCHER] Initialized - Threshold: {ERROR_RATE_THRESHOLD}%, Window: {WINDOW_SIZE}")

# ---------------- FUNCTIONS ----------------
def send_slack_alert(alert_type, message, details=None, from_pool=None, to_pool=None):
    global last_failover_alert, last_error_rate_alert
    now = time.time()
    if MAINTENANCE_MODE:
        print(f"[MAINTENANCE] Alert suppressed: {alert_type}")
        return

    # Cooldown check
    if alert_type == 'failover':
        if now - last_failover_alert < ALERT_COOLDOWN_SEC:
            return
        last_failover_alert = now
    elif alert_type == 'error_rate':
        if now - last_error_rate_alert < ALERT_COOLDOWN_SEC:
            return
        last_error_rate_alert = now

    emoji_map = {'error_rate': ':rotating_light:', 'failover': ':warning:'}
    emoji = emoji_map.get(alert_type, ':information_source:')

    slack_payload = {
        "attachments": [{
            "title": f"{emoji} {alert_type.upper().replace('_', ' ')} Alert",
            "text": message,
            "fields": [
                {"title": "Timestamp", "value": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "short": True},
                {"title": "Alert Type", "value": alert_type, "short": True}
            ],
            "footer": "Blue/Green Monitor",
            "ts": int(now)
        }]
    }

    if details:
        for key, value in details.items():
            slack_payload["attachments"][0]["fields"].append({
                "title": key,
                "value": str(value),
                "short": True
            })

    if SLACK_WEBHOOK_URL:
        try:
            response = requests.post(SLACK_WEBHOOK_URL, json=slack_payload, timeout=5)
            if response.status_code == 200:
                print(f"[SLACK] Alert sent: {alert_type}")
            else:
                print(f"[ERROR] Slack error: {response.status_code}")
        except Exception as e:
            print(f"[ERROR] Failed to send alert: {e}")
    else:
        print(f"[ALERT] {alert_type}: {message}")


def check_failover(pool):
    global last_pool
    if last_pool is None:
        last_pool = pool
        print(f"[INFO] Initial pool: {pool}")
        return
    if pool and pool != last_pool:
        message = f"Failover detected: {last_pool} → {pool}"
        details = {
            "Previous Pool": last_pool,
            "Current Pool": pool,
            "Action Required": "Check primary container health"
        }
        print(f"[FAILOVER] {message}")
        send_slack_alert('failover', message, details, from_pool=last_pool, to_pool=pool)
        last_pool = pool


def check_error_rate():
    if len(request_window) < 20:
        return
    error_count = sum(1 for had_error in request_window if had_error)
    total_count = len(request_window)
    error_rate = (error_count / total_count) * 100
    if error_rate > ERROR_RATE_THRESHOLD:
        message = f"High error rate: {error_rate:.2f}% (threshold: {ERROR_RATE_THRESHOLD}%)"
        details = {
            "Error Rate": f"{error_rate:.2f}%",
            "Threshold": f"{ERROR_RATE_THRESHOLD}%",
            "Requests with Errors": error_count,
            "Total Requests": total_count,
            "Action Required": "Inspect logs, consider pool toggle"
        }
        print(f"[ERROR_RATE] {message}")
        send_slack_alert('error_rate', message, details)


def tail_log():
    print(f"[WATCHER] Starting to tail {LOG_FILE}")
    while not os.path.exists(LOG_FILE):
        print(f"[WATCHER] Waiting for log file...")
        time.sleep(2)
    try:
        with open(LOG_FILE, 'r') as f:
            f.seek(0, 2)
            print("[WATCHER] Ready. Monitoring logs...")
            while True:
                line = f.readline()
                if line:
                    try:
                        log_entry = json.loads(line.strip())
                        pool = log_entry.get('pool', '')
                        upstream_status = log_entry.get('upstream_status', '')
                        had_error = False
                        if upstream_status:
                            print(f"[LOG-upstream] {log_entry}")
                            statuses = str(upstream_status).split(', ')
                            had_error = any(s.startswith('5') for s in statuses if s.strip())
                        request_window.append(had_error)
                        if pool:
                            print(f"[LOG-pool] {pool}")
                            check_failover(pool)
                        check_error_rate()
                    except json.JSONDecodeError:
                        pass
                else:
                    time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n[WATCHER] Shutting down...")
    except Exception as e:
        print(f"[ERROR] {e}")
        raise


# ---------------- ENTRY ----------------
if __name__ == '__main__':
    tail_log()
