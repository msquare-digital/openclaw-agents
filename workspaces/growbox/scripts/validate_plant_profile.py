#!/usr/bin/env python3
"""Validate GrowBox plant profile file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from profile_config import load_and_validate, resolve_profile_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate plant-profile.yaml")
    parser.add_argument("--profile-file", default="", help="Path to profile yaml")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = Path(args.profile_file).expanduser() if args.profile_file else resolve_profile_file()
    profile, report = load_and_validate(path)
    out = {
        "profile_file": str(path),
        "report": report,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    if not report.get("ok", False):
        sys.exit(2)


if __name__ == "__main__":
    main()

