#!/usr/bin/env python3
"""Chunked Google Drive to kDrive migration helper.

This helper is intentionally conservative:

- it creates local ledgers/log folders;
- it generates capped rclone copy commands;
- it defaults to dry-run for copy execution;
- it never deletes, syncs, moves, purges, or overwrites.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import getpass
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_ROOT = PROJECT_ROOT / ".migration"
RCLONE_CONFIG = MIGRATION_ROOT / "rclone.conf"
LOGS_DIR = MIGRATION_ROOT / "logs"
REPORTS_DIR = MIGRATION_ROOT / "reports"
MAPS_DIR = MIGRATION_ROOT / "maps"
LEDGERS_DIR = MIGRATION_ROOT / "ledgers"
CHUNKS_DIR = MIGRATION_ROOT / "chunks"

LEDGER_FIELDS = [
    "chunk_id",
    "source_path",
    "staging_path",
    "final_home",
    "status",
    "files",
    "bytes",
    "started_at",
    "finished_at",
    "notes",
]

DEFAULT_BUCKET = "02 Needs Review"
DEFAULT_DURATION = "90m"
DEFAULT_MAX_TRANSFER = "25G"
DEFAULT_TRANSFERS = "4"
DEFAULT_CHECKERS = "8"


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d")


def ensure_workspace() -> None:
    for path in [MIGRATION_ROOT, LOGS_DIR, REPORTS_DIR, MAPS_DIR, LEDGERS_DIR, CHUNKS_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def current_ledger_path() -> Path:
    return LEDGERS_DIR / f"{today()}-drive-to-kdrive-chunks.tsv"


def ensure_ledger(path: Path | None = None) -> Path:
    ensure_workspace()
    ledger = path or current_ledger_path()
    if not ledger.exists():
        with ledger.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=LEDGER_FIELDS, delimiter="\t")
            writer.writeheader()
    return ledger


def read_ledger(path: Path | None = None) -> list[dict[str, str]]:
    ledger = ensure_ledger(path)
    with ledger.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_ledger(rows: list[dict[str, str]], path: Path | None = None) -> Path:
    ledger = ensure_ledger(path)
    with ledger.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_FIELDS, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return ledger


def shell_join(parts: Iterable[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def validate_text(value: str, label: str) -> str:
    if not value.strip():
        raise SystemExit(f"{label} cannot be empty.")
    if "\n" in value or "\r" in value:
        raise SystemExit(f"{label} cannot contain line breaks.")
    return value.strip().strip("/")


def staging_remote(chunk_id: str, bucket: str) -> str:
    safe_chunk = validate_text(chunk_id, "chunk_id")
    safe_bucket = validate_text(bucket, "bucket")
    return f"kdrive-webdav:00 Migration/Google Drive Incoming/{today()}/{safe_chunk}/{safe_bucket}"


def source_remote(source_path: str) -> str:
    source = validate_text(source_path, "source_path")
    if source.startswith("gdrive:"):
        return source
    return f"gdrive:{source}"


def rclone_base() -> list[str]:
    return ["rclone", "--config", str(RCLONE_CONFIG)]


def copy_command(
    source_path: str,
    destination: str,
    *,
    duration: str,
    max_transfer: str,
    transfers: str,
    checkers: str,
    log_file: Path,
    dry_run: bool,
) -> list[str]:
    cmd = [
        *rclone_base(),
        "copy",
        source_remote(source_path),
        destination,
        "--immutable",
        "--max-duration",
        duration,
        "--cutoff-mode",
        "SOFT",
        "--max-transfer",
        max_transfer,
        "--transfers",
        transfers,
        "--checkers",
        checkers,
        "--log-file",
        str(log_file),
        "--log-level",
        "INFO",
        "--stats",
        "1m",
    ]
    if dry_run:
        cmd.append("--dry-run")
    return cmd


def init_command(args: argparse.Namespace) -> int:
    ensure_workspace()
    ledger = ensure_ledger()
    sample_map = MAPS_DIR / f"{today()}-google-drive-map.tsv"
    if not sample_map.exists():
        sample_map.write_text(
            "source_path\tdestination_bucket\tfinal_home\tdecision\tnotes\n",
            encoding="utf-8",
        )
    print("Migration workspace is ready.")
    print(f"Config: {RCLONE_CONFIG}")
    print(f"Ledger: {ledger}")
    print(f"Map: {sample_map}")
    print("Next: configure gdrive: and kdrive-webdav: in the migration rclone config.")
    return 0


def check_command(args: argparse.Namespace) -> int:
    ensure_workspace()
    version = subprocess.run(["rclone", "version"], text=True, capture_output=True, check=False)
    if version.returncode != 0:
        print("rclone is not available. Install rclone before starting migration.")
        return version.returncode or 1

    if not RCLONE_CONFIG.exists():
        print("Migration rclone config is missing.")
        print(f"Expected: {RCLONE_CONFIG}")
        print("Run: rclone config --config .migration/rclone.conf")
        return 1

    result = subprocess.run([*rclone_base(), "listremotes"], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        print("Could not read migration rclone remotes.")
        print(result.stderr.strip() or result.stdout.strip())
        return result.returncode

    remotes = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    missing = [remote for remote in ["gdrive:", "kdrive-webdav:"] if remote not in remotes]
    if missing:
        print("Missing remotes: " + ", ".join(missing))
        print(f"Configure them with: rclone config --config {RCLONE_CONFIG}")
        return 1

    print("Migration remotes are configured.")
    print("Found: gdrive:, kdrive-webdav:")
    return 0


def setup_help_command(args: argparse.Namespace) -> int:
    ensure_workspace()
    print("Google Drive remote")
    print("Already configured if `./bin/drive-to-kdrive check` sees gdrive:.")
    print("")
    print("kDrive WebDAV remote")
    print("Create it with:")
    print(
        shell_join(
            [
                "rclone",
                "--config",
                str(RCLONE_CONFIG),
                "config",
                "create",
                "kdrive-webdav",
                "webdav",
                "vendor",
                "other",
                "url",
                "https://YOUR_KDRIVE_ID.connect.kdrive.infomaniak.com",
                "user",
                "YOUR_INFOMANIAK_LOGIN",
            ]
        )
    )
    print("")
    print("Then add the password/app password without showing it on screen:")
    print(
        shell_join(
            [
                "./bin/drive-to-kdrive",
                "set-kdrive-password",
            ]
        )
    )
    print("")
    print("The kDrive ID is the number after /drive/ in the kDrive web app URL.")
    print("The WebDAV URL format is documented by Infomaniak.")
    return 0


def set_kdrive_password_command(args: argparse.Namespace) -> int:
    ensure_workspace()
    password = getpass.getpass("kDrive WebDAV password/app password: ")
    if not password:
        print("No password entered. Nothing changed.")
        return 1

    obscure = subprocess.run(
        ["rclone", "obscure", "-"],
        input=password + "\n",
        text=True,
        capture_output=True,
        check=False,
    )
    if obscure.returncode != 0:
        print("Could not prepare password for rclone.")
        print(obscure.stderr.strip() or obscure.stdout.strip())
        return obscure.returncode

    obscured = obscure.stdout.strip()
    update = subprocess.run(
        [
            *rclone_base(),
            "config",
            "update",
            "kdrive-webdav",
            "pass",
            obscured,
            "--no-obscure",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if update.returncode != 0:
        print("Could not save kDrive WebDAV password.")
        print(update.stderr.strip() or update.stdout.strip())
        return update.returncode

    print("kDrive WebDAV password saved in the local migration rclone config.")
    print("Next: ./bin/drive-to-kdrive check")
    return 0


def ledger_command(args: argparse.Namespace) -> int:
    rows = read_ledger()
    if not rows:
        print("No chunks planned yet.")
        return 0
    for row in rows:
        print(
            f"{row['chunk_id']}: {row['status']} | {row['source_path']} → "
            f"{row['staging_path']} | {row.get('notes', '')}"
        )
    return 0


def plan_command(args: argparse.Namespace) -> int:
    rows = read_ledger()
    if any(row["chunk_id"] == args.chunk_id for row in rows):
        print(f"Chunk already exists: {args.chunk_id}")
        return 1

    destination = args.staging_path or staging_remote(args.chunk_id, args.bucket)
    row = {
        "chunk_id": args.chunk_id,
        "source_path": validate_text(args.source, "source_path"),
        "staging_path": destination,
        "final_home": args.final_home or "",
        "status": "planned",
        "files": "",
        "bytes": "",
        "started_at": "",
        "finished_at": "",
        "notes": args.notes or "",
    }
    rows.append(row)
    ledger = write_ledger(rows)
    print(f"Planned chunk {args.chunk_id}.")
    print(f"Source: {source_remote(args.source)}")
    print(f"Staging: {destination}")
    print(f"Ledger: {ledger}")
    return 0


def set_status(chunk_id: str, status: str, *, started: bool = False, finished: bool = False) -> None:
    rows = read_ledger()
    for row in rows:
        if row["chunk_id"] == chunk_id:
            row["status"] = status
            if started:
                row["started_at"] = stamp()
            if finished:
                row["finished_at"] = stamp()
            write_ledger(rows)
            return
    raise SystemExit(f"Unknown chunk: {chunk_id}")


def find_chunk(chunk_id: str) -> dict[str, str]:
    for row in read_ledger():
        if row["chunk_id"] == chunk_id:
            return row
    raise SystemExit(f"Unknown chunk: {chunk_id}")


def command_command(args: argparse.Namespace) -> int:
    row = find_chunk(args.chunk_id)
    dry_run = not args.run
    log_file = LOGS_DIR / f"{args.chunk_id}-{'copy' if args.run else 'dry-run'}.log"
    cmd = copy_command(
        row["source_path"],
        row["staging_path"],
        duration=args.duration,
        max_transfer=args.max_transfer,
        transfers=args.transfers,
        checkers=args.checkers,
        log_file=log_file,
        dry_run=dry_run,
    )
    print(shell_join(cmd))
    return 0


def copy_chunk_command(args: argparse.Namespace) -> int:
    row = find_chunk(args.chunk_id)
    dry_run = not args.run
    log_file = LOGS_DIR / f"{args.chunk_id}-{'copy' if args.run else 'dry-run'}.log"
    cmd = copy_command(
        row["source_path"],
        row["staging_path"],
        duration=args.duration,
        max_transfer=args.max_transfer,
        transfers=args.transfers,
        checkers=args.checkers,
        log_file=log_file,
        dry_run=dry_run,
    )

    if dry_run:
        print(f"Dry-running chunk {args.chunk_id}. No files will be copied.")
    else:
        print(f"Copying chunk {args.chunk_id} with caps: {args.duration}, {args.max_transfer}.")
        set_status(args.chunk_id, "copying", started=True)

    print(f"Log: {log_file}")
    result = subprocess.run(cmd, text=True, check=False)

    if dry_run:
        return result.returncode

    set_status(args.chunk_id, "copied" if result.returncode == 0 else "needs_review", finished=True)
    if result.returncode == 0:
        print(f"Chunk {args.chunk_id} copy completed. Verify before promotion.")
    else:
        print(f"Chunk {args.chunk_id} needs review. Check the log before resuming.")
    return result.returncode


def inventory_command(args: argparse.Namespace) -> int:
    ensure_workspace()
    label = args.label or args.remote.replace(":", "").replace("/", "-")
    output = REPORTS_DIR / f"{today()}-{label}-inventory.txt"
    cmd = [
        *rclone_base(),
        "lsf",
        args.remote,
        "--recursive",
        "--format",
        "pst",
    ]
    print(f"Writing inventory: {output}")
    with output.open("w", encoding="utf-8") as f:
        result = subprocess.run(cmd, text=True, stdout=f, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        print(result.stderr.strip())
        return result.returncode
    print("Inventory complete.")
    return 0


def add_copy_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--duration", default=DEFAULT_DURATION)
    parser.add_argument("--max-transfer", default=DEFAULT_MAX_TRANSFER)
    parser.add_argument("--transfers", default=DEFAULT_TRANSFERS)
    parser.add_argument("--checkers", default=DEFAULT_CHECKERS)
    parser.add_argument("--run", action="store_true", help="Actually copy files. Default is dry-run.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Chunked Google Drive to kDrive migration helper")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create the local migration workspace.")
    init.set_defaults(func=init_command)

    check = sub.add_parser("check", help="Check rclone and required remotes.")
    check.set_defaults(func=check_command)

    setup_help = sub.add_parser("setup-help", help="Print safe remote setup commands.")
    setup_help.set_defaults(func=setup_help_command)

    set_kdrive_password = sub.add_parser("set-kdrive-password", help="Prompt for and save the kDrive WebDAV password.")
    set_kdrive_password.set_defaults(func=set_kdrive_password_command)

    ledger = sub.add_parser("ledger", help="Show planned chunks.")
    ledger.set_defaults(func=ledger_command)

    plan = sub.add_parser("plan", help="Plan one migration chunk.")
    plan.add_argument("chunk_id")
    plan.add_argument("source")
    plan.add_argument("--bucket", default=DEFAULT_BUCKET)
    plan.add_argument("--staging-path")
    plan.add_argument("--final-home")
    plan.add_argument("--notes")
    plan.set_defaults(func=plan_command)

    command = sub.add_parser("command", help="Print the capped rclone command for a chunk.")
    command.add_argument("chunk_id")
    add_copy_flags(command)
    command.set_defaults(func=command_command)

    copy_chunk = sub.add_parser("copy-chunk", help="Dry-run or run a capped copy for one chunk.")
    copy_chunk.add_argument("chunk_id")
    add_copy_flags(copy_chunk)
    copy_chunk.set_defaults(func=copy_chunk_command)

    inventory = sub.add_parser("inventory", help="Write a recursive inventory for a remote path.")
    inventory.add_argument("remote", help='Example: "gdrive:My Drive" or "kdrive-webdav:00 Migration"')
    inventory.add_argument("--label")
    inventory.set_defaults(func=inventory_command)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
