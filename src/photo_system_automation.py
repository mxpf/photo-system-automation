#!/usr/bin/env python3
"""Local photo system automation runner.

This tool is intentionally conservative. The automated path is read-only
against photo/source media: it runs audits, summarizes the newest reports, and
can ask macOS to notify when review is needed.

Archive promotion and Ente import package generation stay manual/explicit.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config/photo-system.json"
EXAMPLE_CONFIG = PROJECT_ROOT / "config/photo-system.example.json"
LAUNCH_AGENT_LABEL = "com.max.photo-system-audit"
LAUNCH_AGENTS_DIR = Path.home() / "Library/LaunchAgents"
LAUNCH_AGENT_PATH = LAUNCH_AGENTS_DIR / f"{LAUNCH_AGENT_LABEL}.plist"
LOGS_DIR = PROJECT_ROOT / "logs"


def load_config(path: Path) -> dict:
    if not path.exists() and path == DEFAULT_CONFIG:
        path = EXAMPLE_CONFIG
    return json.loads(path.read_text(encoding="utf-8"))


def latest_summary_for_input(reports_root: Path, input_path: str) -> dict[str, Any] | None:
    summaries: list[tuple[float, dict[str, Any]]] = []
    for summary_path in reports_root.glob("photo-intake-audit-*/summary.json"):
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if summary.get("input") != input_path:
            continue
        try:
            stamp = summary_path.stat().st_mtime
        except OSError:
            stamp = 0
        summaries.append((stamp, summary))
    if not summaries:
        return None
    return sorted(summaries, key=lambda pair: pair[0])[-1][1]


def needs_attention(summary: dict[str, Any]) -> bool:
    file_count = int(summary.get("file_count") or 0)
    already = int(summary.get("already_in_archive_files") or 0)
    review = int(summary.get("review_needed_files") or 0)
    duplicates = int(summary.get("duplicate_files_within_batch") or 0)
    new_or_unaccounted = max(0, file_count - already)
    return bool(file_count and (new_or_unaccounted or review or duplicates))


def friendly_label(label: str) -> str:
    return {
        "manual": "Manual inbox",
        "phone": "Phone camera backup",
        "latest": "Latest report",
    }.get(label, label)


def short_summary(label: str, summary: dict[str, Any] | None) -> str:
    name = friendly_label(label)
    if not summary:
        return f"{name}: no report yet."
    file_count = int(summary.get("file_count") or 0)
    already = int(summary.get("already_in_archive_files") or 0)
    review = int(summary.get("review_needed_files") or 0)
    duplicates = int(summary.get("duplicate_files_within_batch") or 0)
    new_or_unaccounted = max(0, file_count - already)
    report_dir = Path(str(summary.get("report_dir", ""))).name
    bits = [f"{name}: {file_count:,} file{'s' if file_count != 1 else ''} scanned"]
    if new_or_unaccounted:
        bits.append(f"{new_or_unaccounted:,} new/unaccounted")
    elif file_count:
        bits.append("all accounted for")
    if already:
        bits.append(f"{already:,} already in archive")
    if review:
        bits.append(f"{review:,} need review")
    if duplicates:
        bits.append(f"{duplicates:,} duplicates")
    if report_dir:
        bits.append(f"report: {report_dir}")
    return "; ".join(bits) + "."


def first_useful_error(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("Traceback ") or stripped.startswith("File \""):
            continue
        lines.append(stripped)
    return lines[-1] if lines else "See the log/report for details."


def notify(title: str, message: str) -> None:
    # osascript is available on macOS. If notification fails, stdout logs still
    # contain the same information.
    script = 'display notification "{}" with title "{}"'.format(
        message.replace("\\", "\\\\").replace('"', '\\"'),
        title.replace("\\", "\\\\").replace('"', '\\"'),
    )
    subprocess.run(["/usr/bin/osascript", "-e", script], check=False)


def run_audit(config: dict, input_path: str, *, no_hash: bool = False) -> tuple[int, str]:
    script = PROJECT_ROOT / "scripts/photo_intake_audit.py"
    if not script.exists():
        script = Path(config["legacy_automation_root"]) / "photo_intake_audit.py"
    if not script.exists():
        return 2, "The audit helper is missing."
    if not Path(input_path).exists():
        return 2, f"The input folder is missing: {input_path}"
    cmd = ["/usr/bin/python3", str(script), input_path]
    if no_hash:
        cmd.append("--no-hash")
    result = subprocess.run(cmd, text=True, capture_output=True, check=False)
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def audit_command(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    targets = []
    if args.audit in {"manual", "both"}:
        targets.append(("manual", config["manual_inbox"]))
    if args.audit in {"phone", "both"}:
        targets.append(("phone", config["phone_camera_backup"]))

    exit_code = 0
    summaries: list[tuple[str, dict[str, Any] | None]] = []
    for label, path in targets:
        status, output = run_audit(config, path, no_hash=args.no_hash)
        if status != 0:
            exit_code = status
            print(f"{friendly_label(label)} audit needs attention: {first_useful_error(output)}")
        summaries.append((label, latest_summary_for_input(Path(config["reports_root"]), path)))

    attention = [short_summary(label, summary) for label, summary in summaries if needs_attention(summary or {})]
    all_lines = [short_summary(label, summary) for label, summary in summaries]

    print("Photo intake audit complete.")
    for line in all_lines:
        print(f"- {line}")

    if exit_code:
        notify("Photo audit failed", f"Audit exited with status {exit_code}.")
    elif attention:
        message = "New/reviewable photo intake found."
        if not config.get("notify_only_when_action_needed", True) or args.notify:
            notify("Photo intake needs review", message)
        print("Next: review the new/unaccounted files before importing or filing them.")
    else:
        print("Nothing needs attention right now.")

    return exit_code


def interval_to_seconds(value: str) -> int:
    aliases = {
        "hourly": 60 * 60,
        "daily": 24 * 60 * 60,
        "weekly": 7 * 24 * 60 * 60,
        "90m": 90 * 60,
        "6h": 6 * 60 * 60,
        "12h": 12 * 60 * 60,
    }
    value = value.strip().lower()
    if value in aliases:
        return aliases[value]
    match = __import__("re").fullmatch(r"(\d+)(m|h|d)", value)
    if not match:
        raise ValueError("Use an interval like hourly, daily, 90m, 6h, 12h, or 1d.")
    amount = int(match.group(1))
    unit = match.group(2)
    multiplier = {"m": 60, "h": 3600, "d": 86400}[unit]
    seconds = amount * multiplier
    if seconds < 15 * 60:
        raise ValueError("Minimum interval is 15m; below that is too chatty for kDrive.")
    return seconds


def seconds_to_human(seconds: int) -> str:
    if seconds % 86400 == 0:
        days = seconds // 86400
        return f"{days} day{'s' if days != 1 else ''}"
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''}"
    if seconds % 60 == 0:
        minutes = seconds // 60
        return f"{minutes} minutes"
    return f"{seconds} seconds"


def launch_agent_plist(interval_seconds: int, config_path: Path, no_hash: bool) -> dict[str, Any]:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    args = [
        "/usr/bin/python3",
        str(PROJECT_ROOT / "src/photo_system_automation.py"),
        "audit",
        "--config",
        str(config_path),
        "--audit",
        "both",
    ]
    if no_hash:
        args.append("--no-hash")
    return {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": args,
        "StartInterval": interval_seconds,
        "RunAtLoad": True,
        "StandardOutPath": str(LOGS_DIR / "photo-system-audit.out.log"),
        "StandardErrorPath": str(LOGS_DIR / "photo-system-audit.err.log"),
        "WorkingDirectory": str(PROJECT_ROOT),
        "EnvironmentVariables": {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin",
        },
    }


def run_launchctl(*parts: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["/bin/launchctl", *parts], text=True, capture_output=True, check=False)


def install_command(args: argparse.Namespace) -> int:
    seconds = interval_to_seconds(args.interval)
    config_path = args.config.resolve()
    if not config_path.exists():
        raise SystemExit(f"Config file does not exist: {config_path}")

    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    plist = launch_agent_plist(seconds, config_path, args.no_hash)
    with LAUNCH_AGENT_PATH.open("wb") as f:
        plistlib.dump(plist, f, sort_keys=False)

    domain = f"gui/{os.getuid()}"
    run_launchctl("bootout", domain, str(LAUNCH_AGENT_PATH))
    boot = run_launchctl("bootstrap", domain, str(LAUNCH_AGENT_PATH))
    enable = run_launchctl("enable", f"{domain}/{LAUNCH_AGENT_LABEL}")
    kick = run_launchctl("kickstart", "-k", f"{domain}/{LAUNCH_AGENT_LABEL}")

    print(f"Background audit is on: every {seconds_to_human(seconds)}.")
    print("Photo System will check for new intake quietly and only speak up when review is needed.")
    if boot.returncode != 0:
        print(boot.stderr.strip() or boot.stdout.strip(), file=sys.stderr)
        return boot.returncode
    if enable.returncode != 0:
        print(enable.stderr.strip() or enable.stdout.strip(), file=sys.stderr)
    if kick.returncode != 0:
        print(kick.stderr.strip() or kick.stdout.strip(), file=sys.stderr)
    return 0


def uninstall_command(args: argparse.Namespace) -> int:
    domain = f"gui/{os.getuid()}"
    run_launchctl("bootout", domain, str(LAUNCH_AGENT_PATH))
    if args.keep_plist:
        print("Background audit is stopped. The saved schedule file was kept.")
        return 0
    if LAUNCH_AGENT_PATH.exists():
        LAUNCH_AGENT_PATH.unlink()
    print("Background audit is stopped.")
    return 0


def status_command(args: argparse.Namespace) -> int:
    print("Photo System is running.")
    installed = LAUNCH_AGENT_PATH.exists()
    print(f"Background audit: {'On' if installed else 'Off'}")
    if LAUNCH_AGENT_PATH.exists():
        try:
            plist = plistlib.loads(LAUNCH_AGENT_PATH.read_bytes())
            seconds = int(plist.get("StartInterval", 0))
            if seconds:
                print(f"Interval: Every {seconds_to_human(seconds)}")
        except Exception as exc:
            print(f"Interval: Could not read setting ({exc})")
    domain_label = f"gui/{os.getuid()}/{LAUNCH_AGENT_LABEL}"
    proc = run_launchctl("print", domain_label)
    print(f"Scheduler: {'Loaded' if proc.returncode == 0 else 'Not loaded'}")
    err_log = LOGS_DIR / "photo-system-audit.err.log"
    if err_log.exists() and err_log.stat().st_size:
        print("Last run: Needs attention")
    else:
        print("Last run: OK")
    print("Reports: kDrive → 01 Personal → Photos → Inbox → _automation → reports")
    return 0


def latest_report_command(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    reports_root = Path(config["reports_root"])
    summaries: list[tuple[float, dict[str, Any]]] = []
    for summary_path in reports_root.glob("photo-intake-audit-*/summary.json"):
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        try:
            stamp = summary_path.stat().st_mtime
        except OSError:
            stamp = 0
        summaries.append((stamp, summary))

    if not summaries:
        print("No photo intake audit reports found.")
        return 1

    _, summary = sorted(summaries, key=lambda pair: pair[0])[-1]
    report_dir = summary.get("report_dir", "")
    label = "latest"
    print(short_summary(label, summary))
    if args.open and report_dir:
        subprocess.run(["/usr/bin/open", report_dir], check=False)
    return 0


def menu_command(args: argparse.Namespace) -> int:
    """Simple text menu for menu-bar/script-launcher apps."""
    print("Photo System Automation")
    print("")
    print("1. Audit now")
    print("2. Status")
    print("3. Install/update interval")
    print("4. Stop automation")
    print("")
    choice = input("Choose 1-4: ").strip()

    if choice == "1":
        return audit_command(argparse.Namespace(config=args.config, audit="both", no_hash=False, notify=True))
    if choice == "2":
        return status_command(argparse.Namespace(config=args.config))
    if choice == "3":
        interval = input("Interval (daily, hourly, 90m, 6h, 12h, weekly): ").strip() or "daily"
        return install_command(argparse.Namespace(config=args.config, interval=interval, no_hash=False))
    if choice == "4":
        return uninstall_command(argparse.Namespace(keep_plist=False))

    print("No action taken.")
    return 1


def init_config_command(args: argparse.Namespace) -> int:
    if DEFAULT_CONFIG.exists() and not args.force:
        print(f"Config already exists: {DEFAULT_CONFIG}")
        return 0
    DEFAULT_CONFIG.write_text(EXAMPLE_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Wrote config: {DEFAULT_CONFIG}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Photo system automation")
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="Run read-only photo intake audit.")
    audit.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    audit.add_argument("--audit", choices=["manual", "phone", "both"], default="both")
    audit.add_argument("--no-hash", action="store_true", help="Faster audit; skips duplicate/archive hash checks.")
    audit.add_argument("--notify", action="store_true", help="Force a macOS notification when attention is needed.")
    audit.set_defaults(func=audit_command)

    install = sub.add_parser("install", help="Install/update the macOS LaunchAgent.")
    install.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    install.add_argument("--interval", default="daily", help="Interval: hourly, daily, weekly, 90m, 6h, 12h, 1d, etc.")
    install.add_argument("--no-hash", action="store_true", help="Automated run skips hashing.")
    install.set_defaults(func=install_command)

    uninstall = sub.add_parser("uninstall", help="Stop/remove the macOS LaunchAgent.")
    uninstall.add_argument("--keep-plist", action="store_true")
    uninstall.set_defaults(func=uninstall_command)

    status = sub.add_parser("status", help="Show local automation status.")
    status.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    status.set_defaults(func=status_command)

    latest_report = sub.add_parser("latest-report", help="Show/open the newest audit report.")
    latest_report.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    latest_report.add_argument("--open", action="store_true")
    latest_report.set_defaults(func=latest_report_command)

    menu = sub.add_parser("menu", help="Interactive menu for menu bar launchers.")
    menu.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    menu.set_defaults(func=menu_command)

    init_config = sub.add_parser("init-config", help="Create local config from the example.")
    init_config.add_argument("--force", action="store_true")
    init_config.set_defaults(func=init_config_command)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
