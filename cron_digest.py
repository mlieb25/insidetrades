#!/usr/bin/env python3
"""Cron runner: Daily digest and weekly summary generator.

Called daily at market close. On Fridays, also generates weekly summary.
Uses native Gmail API via service account for email delivery.
"""
import json
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trade_monitor.main import run_daily_digest, run_weekly_summary
from trade_monitor.gmail_sender import send_digest
from trade_monitor import config
from trade_monitor.logger import log_system, log_error


def main():
    now = datetime.now(timezone.utc)
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"

    log_system(f"Cron digest starting: mode={mode}")
    print(f"[{now.isoformat()}] Generating {mode} report...")

    if mode == "daily":
        digest = run_daily_digest()
        print(digest.get("body_text", ""))

        success = send_digest(digest)
        if success:
            print(f"Daily digest sent to {config.EMAIL}")
        else:
            log_error("Failed to send daily digest email")
            print("Email send failed — check logs")

    elif mode == "weekly":
        summary = run_weekly_summary()
        print(summary.get("body_text", ""))

        success = send_digest(summary)
        if success:
            print(f"Weekly summary sent to {config.EMAIL}")
        else:
            log_error("Failed to send weekly summary email")
            print("Email send failed — check logs")

    print(f"[{datetime.now(timezone.utc).isoformat()}] Done.")


if __name__ == "__main__":
    main()
