#!/usr/bin/env python3
"""Poll only /status until a config snapshot SHA is fresh."""

import argparse
import json
from pathlib import Path
import ssl
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".demo-state"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True, help="Expected full config commit SHA")
    parser.add_argument("--timeout", type=int, default=360, help="Maximum wait seconds (default: 360)")
    parser.add_argument("--interval", type=float, default=5, help="Poll interval seconds (default: 5)")
    args = parser.parse_args()
    if args.timeout <= 0 or args.interval <= 0:
        parser.error("--timeout and --interval must be positive")

    url = (STATE / "server-url").read_text().strip() + "/status"
    ca_file = (STATE / "server-ca").read_text().strip() if (STATE / "server-ca").exists() else None
    context = ssl.create_default_context(cafile=ca_file) if url.startswith("https:") else None
    deadline = time.monotonic() + args.timeout
    while True:
        try:
            with urllib.request.urlopen(url, context=context, timeout=10) as response:
                status = json.loads(response.read())
            for config in status.get("configs", []):
                if config.get("commitSha") == args.sha and config.get("stale") is False:
                    print(f"PASS: config refreshed to {args.sha} (stale=false).")
                    return 0
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            last_error = type(error).__name__
        else:
            last_error = "target commit not fresh yet"
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print(f"FAIL: {last_error}; expected {args.sha} within {args.timeout}s.")
            return 1
        time.sleep(min(args.interval, remaining))


if __name__ == "__main__":
    raise SystemExit(main())
