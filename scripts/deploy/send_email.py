#!/usr/bin/env python3
"""
Iran Monitor — failure notification email helper.

Reads SMTP config from environment variables (loaded from .env by
deploy.sh) and sends a single email. Used by deploy.sh to notify on
pipeline failures, push failures, etc.

Required env vars:
    SMTP_HOST         (e.g. smtp.gmail.com)
    SMTP_PORT         (e.g. 587)
    SMTP_USER         (the sender address — for Gmail this is the account address)
    SMTP_PASSWORD     (an app password if SMTP_USER is a Gmail account with 2FA)
    ALERT_EMAIL_TO    (recipient address)

Usage:
    python3.11 scripts/deploy/send_email.py \
        --subject "Iran Monitor cron FAILED at 2026-05-04T22:30Z" \
        --body "Pipeline exited 1. See log: /var/log/iran-monitor.log"
"""
from __future__ import annotations

import argparse
import os
import smtplib
import socket
import sys
from email.message import EmailMessage


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--subject", required=True)
    p.add_argument("--body",    required=True)
    args = p.parse_args()

    host = os.environ.get("SMTP_HOST", "").strip()
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "").strip()
    pwd  = os.environ.get("SMTP_PASSWORD", "").strip()
    to   = os.environ.get("ALERT_EMAIL_TO", "").strip()

    missing = [n for n, v in [
        ("SMTP_HOST", host), ("SMTP_USER", user),
        ("SMTP_PASSWORD", pwd), ("ALERT_EMAIL_TO", to),
    ] if not v]
    if missing:
        print(f"send_email: missing env vars {missing}; cannot send", file=sys.stderr)
        return 2

    body = (
        f"{args.body}\n\n"
        f"--\n"
        f"Sent by /opt/iran-monitor/scripts/deploy/send_email.py\n"
        f"Host: {socket.gethostname()}\n"
    )

    msg = EmailMessage()
    msg["From"]    = user
    msg["To"]      = to
    msg["Subject"] = args.subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls()
            s.login(user, pwd)
            s.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        print(f"send_email: SMTP send failed: {e}", file=sys.stderr)
        return 3
    print(f"send_email: sent to {to}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
