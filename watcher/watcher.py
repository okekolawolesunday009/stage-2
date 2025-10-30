#!/usr/bin/env python3
"""
Robust log-watcher for Nginx access.log.
Tails the log file without using seek (works with Docker-mounted logs).
Parses fields, computes rolling 5xx error rate, and posts alerts to Slack.
"""
import os
import re
import time
from collections import deque
import requests

# Config from env
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')
WATCH_LOG_PATH = os.getenv('WATCH_LOG_PATH', '/var/log/nginx/access.log')
ERROR_RATE_THRESHOLD = float(os.getenv('ERROR_RATE_THRESHOLD', '2'))  # percent
WINDOW_SIZE = int(os.getenv('WINDOW_SIZE', '200'))
ALERT_COOLDOWN_SEC = int(os.getenv('ALERT_COOLDOWN_SEC', '300'))
MAINTENANCE_MODE = os.getenv('MAINTENANCE_MODE', 'false').lower() in ('1', 'true', 'yes')

# Internal state
status_window = deque(maxlen=WINDOW_SIZE)
last_pool = None
last_alert_ts = 0
last_error_rate_alert_ts = 0

# Regex to extract fields written by our nginx.conf.template
FIELD_RE = re.compile(
    r'pool:(?P<pool>\S+) release:(?P<release>\S+) upstatus:(?P<upstatus>\S+) '
    r'upaddr:(?P<upaddr>\S+) req_time:(?P<req_time>\S+) upr_time:(?P<upr_time>\S+)'
)
STATUS_RE = re.compile(r'"\S+\s+\S+\s+\S+"\s+(?P<status>\d{3})')


def send_slack(message: str, attachments: dict = None):
    if not SLACK_WEBHOOK_URL:
        print('SLACK_WEBHOOK_URL not set; skipping Slack alert')
        return
    payload = {"text": message}
    if attachments:
        payload.update({"attachments": [attachments]})
    try:
        r = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=5)
        r.raise_for_status()
        print(f"Sent Slack alert: {message}")
    except Exception as e:
        print(f"Failed sending Slack alert: {e}")


def parse_line(line: str):
    m_fields = FIELD_RE.search(line)
    m_status = STATUS_RE.search(line)
    if not m_fields or not m_status:
        return None
    try:
        return {
            'pool': m_fields.group('pool'),
            'release': m_fields.group('release'),
            'upstatus': m_fields.group('upstatus'),
            'upaddr': m_fields.group('upaddr'),
            'req_time': float(m_fields.group('req_time')),
            'upr_time': float(m_fields.group('upr_time')),
            'status': int(m_status.group('status'))
        }
    except Exception:
        return None


def check_error_rate():
    if len(status_window) < 10:
        return None
    total = len(status_window)
    errors = sum(1 for s in status_window if 500 <= s < 600)
    rate = (errors / total) * 100
    return rate


def tail_f(path):
    """
    Tail a file without using seek (safe for Docker-mounted logs).
    Strategy:
      - Wait until the path exists.
      - Open and read lines in a loop; if none, sleep briefly and continue.
      - If the file rotates/recreates, reopen automatically.
    """
    last_inode = None
    while True:
        # wait for file to appear
        while not os.path.exists(path):
            print(f"Waiting for log file: {path}")
            time.sleep(1)

        try:
            with open(path, 'r', errors='ignore') as f:
                print(f"Opened log file: {path}")
                while True:
                    line = f.readline()
                    if line:
                        yield line
                    else:
                        # detect rotation/recreation: if inode changed, break to reopen
                        try:
                            stat = os.stat(path)
                            inode = (stat.st_ino, stat.st_dev)
                            if last_inode is None:
                                last_inode = inode
                            elif inode != last_inode:
                                print("Log file was rotated/recreated — reopening.")
                                last_inode = inode
                                break
                        except FileNotFoundError:
                            # file disappeared, reopen loop
                            print("Log file disappeared — will wait and reopen.")
                            break
                        time.sleep(0.5)
        except Exception as e:
            print(f"Error opening/reading log file: {e}. Retrying in 1s.")
            time.sleep(1)


def main():
    global last_pool, last_alert_ts, last_error_rate_alert_ts

    if MAINTENANCE_MODE:
        print('MAINTENANCE_MODE is enabled: watcher will start but suppress alerts until mode cleared')

    for line in tail_f(WATCH_LOG_PATH):
        parsed = parse_line(line)
        if not parsed:
            # Could not parse; skip
            continue

        status_window.append(parsed['status'])

        # Detect pool flip
        pool = parsed['pool']
        now = time.time()
        if last_pool and pool != last_pool and not MAINTENANCE_MODE:
            if now - last_alert_ts > ALERT_COOLDOWN_SEC:
                msg = (
                    f"*Failover detected* — pool changed: {last_pool} → {pool}\n"
                    f"release: {parsed['release']}\n"
                    f"upstream: {parsed['upaddr']} upstatus: {parsed['upstatus']}"
                )
                send_slack(msg)
                last_alert_ts = now
        last_pool = pool

        # Check error rate
        rate = check_error_rate()
        if rate is not None and rate >= ERROR_RATE_THRESHOLD and not MAINTENANCE_MODE:
            if now - last_error_rate_alert_ts > ALERT_COOLDOWN_SEC:
                msg = (
                    f"*High upstream 5xx rate* — {rate:.2f}% 5xx over last {len(status_window)} requests "
                    f"(threshold {ERROR_RATE_THRESHOLD}%).\nMost recent pool: {last_pool}"
                )
                send_slack(msg)
                last_error_rate_alert_ts = now


if __name__ == '__main__':
    main()
