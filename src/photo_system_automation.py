#!/usr/bin/env python3
"""Local photo system automation runner.

This tool is intentionally conservative. The automated path is read-only
against photo/source media: it runs audits, summarizes the newest reports, and
can ask macOS to notify when review is needed.

Archive promotion and Ente import package generation stay manual/explicit.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import plistlib
import subprocess
import sys
from datetime import datetime, timezone
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

    if config.get("font_audit_enabled"):
        font_args = argparse.Namespace(config=args.config, notify=True)
        font_exit = font_audit_command(font_args)
        if font_exit:
            exit_code = exit_code or font_exit

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


FONT_EXTENSIONS = {".otf", ".ttf", ".ttc", ".woff", ".woff2", ".eot"}
APPROVED_FONT_STATUSES = {"open_source", "free_commercial_license"}


def load_font_catalog(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"The font catalog is missing: {path}")
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def font_catalog_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = row.get("status", "provenance_unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def font_status_command(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    rows = load_font_catalog(Path(config["font_catalog"]))
    counts = font_catalog_counts(rows)
    approved = sum(counts.get(status, 0) for status in APPROVED_FONT_STATUSES)
    restricted = counts.get("restricted_or_trial", 0) + counts.get("web_only_restricted", 0)
    review = len(rows) - approved - restricted - counts.get("non_font_admin", 0)
    intake = Path(config["font_intake"])
    intake_files = sum(1 for path in intake.rglob("*") if path.is_file()) if intake.exists() else 0
    print("Font library is organized and monitored.")
    print(f"Approved for production: {approved:,} families")
    print(f"Restricted or web-only: {restricted:,} families")
    print(f"License/provenance review: {review:,} families")
    print(f"New font intake: {intake_files:,} files")
    print("Restricted and unresolved fonts are isolated from the production collection.")
    return 0


def font_metadata(path: Path) -> str:
    tool = "/usr/local/bin/fc-query"
    if not Path(tool).exists():
        return ""
    result = subprocess.run(
        [tool, "--format", "%{family[0]} | %{foundry} | %{fullname[0]}", str(path)],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def font_audit_command(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    root = Path(config["font_library_root"])
    intake = Path(config["font_intake"])
    reports = Path(config["font_reports_root"])
    rows = load_font_catalog(Path(config["font_catalog"]))
    catalog = {row["family"].casefold(): row for row in rows}
    reports.mkdir(parents=True, exist_ok=True)
    intake.mkdir(parents=True, exist_ok=True)

    files = [path for path in intake.rglob("*") if path.is_file()]
    approved_files: dict[tuple[str, int], list[str]] = {}
    reserved = {"Specimens & Licenses", "00 Catalog & Audit", "_Incoming", "_Quarantine"}
    if root.exists():
        for family in root.iterdir():
            if not family.is_dir() or family.name in reserved:
                continue
            for path in family.rglob("*"):
                if path.is_file():
                    try:
                        approved_files.setdefault((path.name.casefold(), path.stat().st_size), []).append(str(path))
                    except OSError:
                        pass

    issues: list[dict[str, str]] = []
    hashes: dict[str, str] = {}
    inspected: list[dict[str, object]] = []
    for path in files:
        relative = str(path.relative_to(intake))
        suffix = path.suffix.lower()
        size = path.stat().st_size
        family = path.relative_to(intake).parts[0] if len(path.relative_to(intake).parts) > 1 else path.stem
        catalog_row = catalog.get(family.casefold())
        record: dict[str, object] = {
            "path": relative,
            "size": size,
            "family": family,
            "catalog_status": catalog_row.get("status") if catalog_row else "new_family",
            "metadata": font_metadata(path) if suffix in FONT_EXTENSIONS else "",
        }
        if size == 0:
            issues.append({"path": relative, "issue": "zero-byte file"})
        if not suffix:
            issues.append({"path": relative, "issue": "missing extension"})
        elif suffix not in FONT_EXTENSIONS and suffix not in {".txt", ".pdf"}:
            issues.append({"path": relative, "issue": f"unsupported extension: {suffix}"})
        if not catalog_row:
            issues.append({"path": relative, "issue": "new family needs license review"})
        elif catalog_row.get("status") not in APPROVED_FONT_STATUSES:
            issues.append({"path": relative, "issue": f"family is not production-approved: {catalog_row.get('status')}"})
        if suffix in FONT_EXTENSIONS and size:
            digest = sha256(path)
            record["sha256"] = digest
            if digest in hashes:
                issues.append({"path": relative, "issue": f"exact duplicate of {hashes[digest]}"})
            else:
                hashes[digest] = relative
            matches = approved_files.get((path.name.casefold(), size), [])
            if matches:
                issues.append({"path": relative, "issue": f"possible archive duplicate: {matches[0]}"})
        inspected.append(record)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {"generated_at": stamp, "intake": str(intake), "file_count": len(files), "issue_count": len(issues), "files": inspected, "issues": issues}
    json_path = reports / f"font-intake-audit-{stamp}.json"
    md_path = reports / f"font-intake-audit-{stamp}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# Font Intake Audit", "", f"- Files: {len(files):,}", f"- Issues: {len(issues):,}", f"- Intake: `{intake}`", ""]
    if issues:
        lines.extend(["## Review queue", ""] + [f"- `{item['path']}` — {item['issue']}" for item in issues])
    else:
        lines.append("Nothing needs review.")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Font intake audit complete: {len(files):,} files, {len(issues):,} issues.")
    print(f"Report: {md_path}")
    if issues and args.notify:
        notify("Font intake needs review", f"{len(issues)} issue{'s' if len(issues) != 1 else ''} found.")
    return 1 if issues else 0


def font_catalog_command(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    path = Path(config["font_catalog"])
    print(path)
    if args.open:
        subprocess.run(["/usr/bin/open", str(path)], check=False)
    return 0


def font_guide_command(args: argparse.Namespace) -> int:
    print("Font use guide")
    print("Production approved: open-source fonts and included freeware licenses that expressly permit commercial work.")
    print("Restricted: trial, test, personal-use, unlicensed, suspect-source, and web-only fonts.")
    print("Web-only: websites only; do not use in desktop layouts, print, PDFs, presentations, logos, or apps.")
    print("Needs license review: keep out of final work until purchase or provenance records are confirmed.")
    print("New fonts: place them in kDrive → Fonts → _Incoming, then run Font intake audit.")
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

    font_audit = sub.add_parser("font-audit", help="Audit the font intake folder without moving files.")
    font_audit.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    font_audit.add_argument("--notify", action="store_true")
    font_audit.set_defaults(func=font_audit_command)

    font_status = sub.add_parser("font-status", help="Show production-font licensing status.")
    font_status.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    font_status.set_defaults(func=font_status_command)

    font_catalog = sub.add_parser("font-catalog", help="Show or open the font license catalog.")
    font_catalog.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    font_catalog.add_argument("--open", action="store_true")
    font_catalog.set_defaults(func=font_catalog_command)

    font_guide = sub.add_parser("font-guide", help="Explain permitted-use categories.")
    font_guide.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    font_guide.set_defaults(func=font_guide_command)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
