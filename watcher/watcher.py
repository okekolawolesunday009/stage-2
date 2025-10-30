#!/usr/bin/env python3
"""
Simple log-watcher for Nginx access.log.
Reads lines appended to log file, parses fields, computes rolling 5xx error rate,
and posts alerts to Slack via webhook.
"""
import os
import re
import time
import json
from collections import deque
from datetime import datetime

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
FIELD_RE = re.compile(r'pool:(?P<pool>\S+) release:(?P<release>\S+) upstatus:(?P<upstatus>\S+) upaddr:(?P<upaddr>\S+) req_time:(?P<req_time>\S+) upr_time:(?P<upr_time>\S+)')
STATUS_RE = re.compile(r'"\S+\s+\S+\s+\S+"\s+(?P<status>\d{3})')


def send_slack(message: str, attachments: dict = None):
    global last_alert_ts
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
    # Attempt to parse the status and the custom fields
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
    # Robust tail - follow file growth
    with open(path, 'r') as f:
        f.seek(0, 2)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue
            yield line


def main():
    global last_pool, last_alert_ts, last_error_rate_alert_ts

    if MAINTENANCE_MODE:
        print('MAINTENANCE_MODE is enabled: watcher will start but suppress alerts until mode cleared')

    # wait for file to exist
    while not os.path.exists(WATCH_LOG_PATH):
        print(f'waiting for log file: {WATCH_LOG_PATH}')
        time.sleep(1)

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
            # check cooldown
            if now - last_alert_ts > ALERT_COOLDOWN_SEC:
                msg = f"*Failover detected* — pool changed: {last_pool} → {pool}\nrelease: {parsed['release']}\nupstream: {parsed['upaddr']} upstatus: {parsed['upstatus']}"
                send_slack(msg)
                last_alert_ts = now
        last_pool = pool

        # Check error rate
        rate = check_error_rate()
        if rate is not None and rate >= ERROR_RATE_THRESHOLD and not MAINTENANCE_MODE:
            if now - last_error_rate_alert_ts > ALERT_COOLDOWN_SEC:
                msg = f"*High upstream 5xx rate* — {rate:.2f}% 5xx over last {len(status_window)} requests (threshold {ERROR_RATE_THRESHOLD}%).\nMost recent pool: {last_pool}"
                send_slack(msg)
                last_error_rate_alert_ts = now


if __name__ == '__main__':
    main()
