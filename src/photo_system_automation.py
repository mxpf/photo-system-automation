#!/usr/bin/env python3
"""
Local photo system automation runner.

This first version is intentionally conservative: it wraps the existing
read-only intake audit script and does not modify media or the canonical
archive.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config/photo-system.example.json"


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_audit(config: dict, input_path: str) -> int:
    script = Path(config["legacy_automation_root"]) / "photo_intake_audit.py"
    if not script.exists():
        print(f"Missing audit script: {script}", file=sys.stderr)
        return 2
    if not Path(input_path).exists():
        print(f"Missing input folder: {input_path}", file=sys.stderr)
        return 2
    result = subprocess.run(
        ["/usr/bin/python3", str(script), input_path],
        text=True,
        check=False,
    )
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Photo system automation")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--audit",
        choices=["manual", "phone", "both"],
        default="both",
        help="Run read-only audit against one or both intake sources.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    targets = []
    if args.audit in {"manual", "both"}:
        targets.append(("manual", config["manual_inbox"]))
    if args.audit in {"phone", "both"}:
        targets.append(("phone", config["phone_camera_backup"]))

    exit_code = 0
    for label, path in targets:
        print(f"Running read-only {label} audit: {path}")
        status = run_audit(config, path)
        if status != 0:
            exit_code = status
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

