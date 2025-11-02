#!/usr/bin/env python3
import os
import time
import json
import requests
import re
from collections import deque
from datetime import datetime

class LogWatcher:
    def __init__(self):
        self.webhook_url = os.getenv('SLACK_WEBHOOK_URL', '')
        self.error_threshold = float(os.getenv('ERROR_RATE_THRESHOLD', 2))
        self.window_size = int(os.getenv('WINDOW_SIZE', 200))
        self.cooldown = int(os.getenv('ALERT_COOLDOWN_SEC', 300))
        self.log_file = '/var/log/nginx/access.log'


        self.request_window = deque(maxlen=self.window_size)
        self.last_pool = None
        self.last_alert_time = {}
    

    def parse_log_line(self, line):
        pattern = (
            r'pool="([^"]*)" release="([^"]*)" upstream_status="([^"]*)" '
            r'upstream="([^"]*)" request_time="([^"]*)" upstream_response_time="([^"]*)"'
        )
        match = re.search(pattern, line)
        if match:
            return {
                'pool': match.group(1) if match.group(1) != '-' else None,
                'release': match.group(2) if match.group(2) != '-' else None,
                'upstream_status': match.group(3),
                'upstream': match.group(4),
                'request_time': match.group(5),
                'upstream_response_time': match.group(6)
            }
        return None

    def send_slack_alert(self, alert_data, alert_key):
        if not self.webhook_url:
            print("⚠️ No Slack webhook URL set.")
            return

        now = time.time()
        last_alert_time = self.last_alert_time.get(alert_key, 0)

        if now - last_alert_time < self.cooldown:
            print(f"⏳ Cooldown active for '{alert_key}' ({int(now - last_alert_time)}s elapsed)")
            return

        payload = {
            "text": "🚨 Blue/Green Deployment Alert",
            "attachments": [{
                "color": "danger" if "error" in alert_key else "warning",
                "fields": [
                    {"title": "Alert Type", "value": alert_data["type"], "short": True},
                    {"title": "Timestamp", "value": alert_data["timestamp"], "short": True},
                    {"title": "Details", "value": alert_data["message"], "short": False}
                ],
                "footer": "Blue/Green Monitor",
                "ts": int(now)
            }]
        }

        if "metadata" in alert_data:
            payload["attachments"][0]["fields"].append({
                "title": "Metadata",
                "value": f"```json\n{json.dumps(alert_data['metadata'], indent=2)}\n```",
                "short": False
            })

        try:
            r = requests.post(self.webhook_url, json=payload, timeout=5)
            if r.status_code == 200:
                print(f"✅ Slack alert sent: {alert_data['type']}")
                self.last_alert_time[alert_key] = now
            else:
                print(f"❌ Slack returned status {r.status_code}: {r.text}")
        except Exception as e:
            print(f"❌ Failed to send Slack alert: {e}")

    def check_failover(self, pool, data):
        if pool and self.last_pool and pool != self.last_pool:
            alert_data = {
                "type": "Failover Detected",
                "timestamp": datetime.now().isoformat(),
                "message": f"Pool switched from {self.last_pool} → {pool}",
                "metadata": {
                    "previous_pool": self.last_pool,
                    "current_pool": pool,
                    "upstream": data.get("upstream"),
                    "response_time": data.get("upstream_response_time")
                }
            }
            self.send_slack_alert(alert_data, f"failover_{pool}")

        if pool:
            self.last_pool = pool

    def check_error_rate(self):
        if len(self.request_window) < 10:
            return

        errors = sum(1 for s in self.request_window if s and s.startswith("5"))
        error_rate = (errors / len(self.request_window)) * 100

        if error_rate > self.error_threshold:
            alert_data = {
                "type": "High Error Rate",
                "timestamp": datetime.now().isoformat(),
                "message": f"Error rate {error_rate:.2f}% exceeds threshold {self.error_threshold}%",
                "metadata": {
                    "error_rate": f"{error_rate:.2f}%",
                    "threshold": f"{self.error_threshold}%",
                    "window": len(self.request_window),
                    "total_errors": errors
                }
            }
            self.send_slack_alert(alert_data, "error_rate")

    def tail_log(self):
        """Generator that follows the log file or stream (like tail -F)"""
        with open(self.log_file, 'r') as f:
            if f.seekable():
                f.seek(0, os.SEEK_END)
            else:
                print(f"⚠️ Log file {self.log_file} is not seekable (stream mode). Reading from start...")

            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                yield line.strip()

    def watch_logs(self):
        print("🔍 Starting Blue/Green Alert Watcher...")
        print(f"Webhook: {'Configured' if self.webhook_url else 'Missing'}")
        print(f" access.log: {'opened'  if self.log_file else 'not opened'}")
        print(f"Error threshold: {self.error_threshold}% | Window: {self.window_size} | Cooldown: {self.cooldown}s")

        # Send only once at startup
        if self.webhook_url and not self.last_alert_time.get("startup_sent"):
            startup = {
                "type": "Monitor Started",
                "timestamp": datetime.now().isoformat(),
                "message": "Blue/Green monitor active and watching nginx logs.",
                "metadata": {
                    "error_threshold": self.error_threshold,
                    "window_size": self.window_size,
                    "cooldown": self.cooldown
                }
            }
            self.send_slack_alert(startup, "startup_sent")

        last_size = 0
        while True:
            try:
                if os.path.exists(self.log_file):
                    current_size = os.path.getsize(self.log_file)
                    if current_size > last_size:
                        with open(self.log_file, 'r') as f:
                            f.seek(last_size)
                            new_lines = f.readlines()
                            for line in new_lines:
                                parsed = self.parse_log_line(line.strip())
                                if parsed:
                                    print(f"📄 Log: pool={parsed['pool']}, status={parsed['upstream_status']}")
                                    self.request_window.append(parsed['upstream_status'])
                                    self.check_failover(parsed['pool'], parsed)
                                    self.check_error_rate()
                        last_size = current_size
                else:
                    print("⏳ Waiting for log file...")
                time.sleep(1)
            except Exception as e:
                print(f"❌ Log reading error: {e}")
                time.sleep(2)

if __name__ == "__main__":
    watcher = LogWatcher()
    watcher.watch_logs()