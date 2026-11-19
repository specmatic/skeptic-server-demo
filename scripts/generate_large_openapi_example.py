#!/usr/bin/env python3
"""Wrap checked-in large OpenAPI specs as Specmatic HTTP examples."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / ".demo-state" / "specmatic-examples"
SPECS = (
    ("large-openapi-at-limit.json", "/large-openapi-at-limit.yaml", "large-openapi-5mb.yaml"),
    ("large-openapi-over-limit.json", "/large-openapi-over-limit.yaml", "large-openapi-5_5mb.yaml"),
)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "large-openapi.json").unlink(missing_ok=True)
    for filename, path, spec_filename in SPECS:
        spec = (ROOT / "specs" / spec_filename).read_text()
        example = {
            "http-request": {"method": "GET", "path": path},
            "http-response": {
                "status": 200,
                "headers": {"Content-Type": "application/yaml"},
                "body": spec,
            },
        }
        (OUTPUT_DIR / filename).write_text(json.dumps(example) + "\n")
        print(f"Generated {path} ({len(spec):,} Unicode code points)")


if __name__ == "__main__":
    main()
