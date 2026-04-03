#!/usr/bin/env python3
"""Standalone script to run one poll cycle. Called by cron."""
import json
import sys
import os
import traceback

# Ensure the parent directory is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trade_monitor.main import run_poll_cycle, run_health_check


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "poll"

    try:
        if mode == "poll":
            result = run_poll_cycle()
        elif mode == "health":
            result = run_health_check()
        else:
            result = {"error": f"Unknown mode: {mode}"}

        print(json.dumps(result, indent=2, default=str))

    except Exception as e:
        error_info = {
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
        print(json.dumps(error_info, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
