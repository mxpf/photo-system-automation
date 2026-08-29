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
import json
import os
import plistlib
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
LAUNCHAGENTS_DIR = MIGRATION_ROOT / "launchagents"

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
    for path in [MIGRATION_ROOT, LOGS_DIR, REPORTS_DIR, MAPS_DIR, LEDGERS_DIR, CHUNKS_DIR, LAUNCHAGENTS_DIR]:
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


def update_chunk(
    chunk_id: str,
    *,
    status: str | None = None,
    files: str | None = None,
    bytes_: str | None = None,
    notes: str | None = None,
    started: bool = False,
    finished: bool = False,
) -> None:
    rows = read_ledger()
    for row in rows:
        if row["chunk_id"] == chunk_id:
            if status is not None:
                row["status"] = status
            if files is not None:
                row["files"] = files
            if bytes_ is not None:
                row["bytes"] = bytes_
            if notes is not None:
                row["notes"] = notes
            if started:
                row["started_at"] = stamp()
            if finished:
                row["finished_at"] = stamp()
            write_ledger(rows)
            return
    raise SystemExit(f"Unknown chunk: {chunk_id}")


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


def run_to_file(cmd: list[str], output: Path) -> subprocess.CompletedProcess[str]:
    ensure_workspace()
    with output.open("w", encoding="utf-8") as f:
        return subprocess.run(cmd, text=True, stdout=f, stderr=subprocess.PIPE, check=False)


def run_json_to_file(cmd: list[str], output: Path) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    result = run_to_file(cmd, output)
    if result.returncode != 0:
        return result, {}
    try:
        return result, json.loads(output.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return result, {}


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line]


def read_path_size(path: Path) -> set[str]:
    return set(read_lines(path))


def read_hashes(path: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for line in read_lines(path):
        digest, sep, relpath = line.partition("  ")
        if sep and relpath:
            hashes[relpath] = digest
    return hashes


def write_review_report(
    chunk_id: str,
    row: dict[str, str],
    *,
    status: str,
    source_size: dict[str, object],
    destination_size: dict[str, object],
    path_size_missing: int,
    path_size_extra: int,
    source_hashes: int | None,
    destination_hashes: int | None,
    hash_missing_or_changed: int | None,
    hash_extra_or_changed: int | None,
    dynamic_exports: list[str],
    note: str,
) -> Path:
    report = REPORTS_DIR / f"{chunk_id}-review.md"
    lines = [
        f"# {chunk_id} review",
        "",
        f"Status: {status}",
        "",
        f"Source: `{source_remote(row['source_path'])}`",
        f"Destination: `{row['staging_path']}`",
        f"Intended final home: `{row.get('final_home', '')}`",
        "",
        "Verification:",
        f"- Source objects: {source_size.get('count', '')}",
        f"- Destination files: {destination_size.get('count', '')}",
        f"- Source reported bytes: {source_size.get('bytes', '')}",
        f"- Destination bytes: {destination_size.get('bytes', '')}",
        f"- Source unknown-size objects: {source_size.get('sizeless', 0)}",
        f"- Missing path+size rows: {path_size_missing}",
        f"- Extra path+size rows: {path_size_extra}",
    ]
    if source_hashes is not None:
        lines.extend(
            [
                f"- Source SHA-256 rows: {source_hashes}",
                f"- Destination SHA-256 rows: {destination_hashes}",
                f"- SHA-256 missing/changed rows: {hash_missing_or_changed}",
                f"- SHA-256 extra/changed rows: {hash_extra_or_changed}",
            ]
        )
    if dynamic_exports:
        lines.extend(["", "Likely dynamic Google-native exports:"])
        lines.extend(f"- `{path}`" for path in dynamic_exports)
    lines.extend(
        [
            "",
            "Decision:",
            f"- {note}",
            "- No promotion or canonical reorganization was performed.",
        ]
    )
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


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
    update_chunk(chunk_id, status=status, started=started, finished=finished)


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


def verify_chunk_command(args: argparse.Namespace) -> int:
    row = find_chunk(args.chunk_id)
    source = source_remote(row["source_path"])
    destination = row["staging_path"]

    print(f"Verifying chunk {args.chunk_id}.")

    source_size_path = REPORTS_DIR / f"{args.chunk_id}-source-size.json"
    destination_size_path = REPORTS_DIR / f"{args.chunk_id}-destination-size.json"
    source_lsf_path = REPORTS_DIR / f"{args.chunk_id}-source-lsf.txt"
    destination_lsf_path = REPORTS_DIR / f"{args.chunk_id}-destination-lsf.txt"
    source_sha_path = REPORTS_DIR / f"{args.chunk_id}-source-sha256.txt"
    destination_sha_path = REPORTS_DIR / f"{args.chunk_id}-destination-sha256.txt"

    checks: list[tuple[str, subprocess.CompletedProcess[str]]] = []
    result, source_size = run_json_to_file([*rclone_base(), "size", source, "--json"], source_size_path)
    checks.append(("source size", result))
    result, destination_size = run_json_to_file([*rclone_base(), "size", destination, "--json"], destination_size_path)
    checks.append(("destination size", result))
    checks.append(
        (
            "source inventory",
            run_to_file(
                [*rclone_base(), "lsf", source, "--recursive", "--files-only", "--format", "ps"],
                source_lsf_path,
            ),
        )
    )
    checks.append(
        (
            "destination inventory",
            run_to_file(
                [*rclone_base(), "lsf", destination, "--recursive", "--files-only", "--format", "ps"],
                destination_lsf_path,
            ),
        )
    )

    failed = [(label, result) for label, result in checks if result.returncode != 0]
    if failed:
        label, result = failed[0]
        note = f"{label} failed; inspect saved reports/logs before continuing"
        update_chunk(args.chunk_id, status="needs_review", notes=note, finished=True)
        print(f"Chunk {args.chunk_id} needs review: {label} failed.")
        print(result.stderr.strip())
        return result.returncode or 1

    source_rows = read_path_size(source_lsf_path)
    destination_rows = read_path_size(destination_lsf_path)
    path_size_missing = len(source_rows - destination_rows)
    path_size_extra = len(destination_rows - source_rows)

    source_hash_count = None
    destination_hash_count = None
    hash_missing_or_changed = None
    hash_extra_or_changed = None
    dynamic_exports: list[str] = []

    if not args.no_hash:
        source_hash_result = run_to_file([*rclone_base(), "hashsum", "SHA256", "--download", source], source_sha_path)
        destination_hash_result = run_to_file(
            [*rclone_base(), "hashsum", "SHA256", "--download", destination],
            destination_sha_path,
        )
        if source_hash_result.returncode != 0 or destination_hash_result.returncode != 0:
            note = "SHA-256 verification command failed; inspect saved hash outputs"
            update_chunk(args.chunk_id, status="needs_review", notes=note, finished=True)
            write_review_report(
                args.chunk_id,
                row,
                status="needs_review",
                source_size=source_size,
                destination_size=destination_size,
                path_size_missing=path_size_missing,
                path_size_extra=path_size_extra,
                source_hashes=None,
                destination_hashes=None,
                hash_missing_or_changed=None,
                hash_extra_or_changed=None,
                dynamic_exports=[],
                note=note,
            )
            print(f"Chunk {args.chunk_id} needs review: SHA-256 verification failed.")
            return source_hash_result.returncode or destination_hash_result.returncode or 1

        source_hashes = read_hashes(source_sha_path)
        destination_hashes = read_hashes(destination_sha_path)
        source_hash_count = len(source_hashes)
        destination_hash_count = len(destination_hashes)
        source_hash_pairs = set(source_hashes.items())
        destination_hash_pairs = set(destination_hashes.items())
        hash_missing_or_changed = len(source_hash_pairs - destination_hash_pairs)
        hash_extra_or_changed = len(destination_hash_pairs - source_hash_pairs)

        if hash_missing_or_changed or hash_extra_or_changed:
            second_source_sha_path = REPORTS_DIR / f"{args.chunk_id}-source-sha256-second-pass.txt"
            second_result = run_to_file(
                [*rclone_base(), "hashsum", "SHA256", "--download", source],
                second_source_sha_path,
            )
            if second_result.returncode == 0:
                second_source_hashes = read_hashes(second_source_sha_path)
                dynamic_exports = sorted(
                    path
                    for path, digest in source_hashes.items()
                    if second_source_hashes.get(path) not in [None, digest]
                )

    verified = (
        int(source_size.get("count", -1)) == int(destination_size.get("count", -2))
        and int(source_size.get("bytes", -1)) == int(destination_size.get("bytes", -2))
        and int(source_size.get("sizeless", 0)) == 0
        and path_size_missing == 0
        and path_size_extra == 0
        and (
            args.no_hash
            or (
                source_hash_count == destination_hash_count == int(source_size.get("count", -1))
                and hash_missing_or_changed == 0
                and hash_extra_or_changed == 0
            )
        )
    )

    status = "verified" if verified else "needs_review"
    if verified:
        note = "copy verified by count, bytes, path+size inventory, and SHA-256; no promotion"
    elif dynamic_exports:
        ordinary_count = int(destination_size.get("count", 0)) - len(dynamic_exports)
        note = (
            f"copied; {ordinary_count} ordinary files appear stable; "
            f"{len(dynamic_exports)} Google-native export(s) have unstable generated hashes and need human review; no promotion"
        )
    else:
        note = "copied but verification found mismatches; inspect review report before continuing; no promotion"

    report = write_review_report(
        args.chunk_id,
        row,
        status=status,
        source_size=source_size,
        destination_size=destination_size,
        path_size_missing=path_size_missing,
        path_size_extra=path_size_extra,
        source_hashes=source_hash_count,
        destination_hashes=destination_hash_count,
        hash_missing_or_changed=hash_missing_or_changed,
        hash_extra_or_changed=hash_extra_or_changed,
        dynamic_exports=dynamic_exports,
        note=note,
    )
    update_chunk(
        args.chunk_id,
        status=status,
        files=str(destination_size.get("count", "")),
        bytes_=str(destination_size.get("bytes", "")),
        notes=note,
        finished=True,
    )
    print(f"Chunk {args.chunk_id}: {status}.")
    print(f"Report: {report}")
    return 0 if verified else 2


def run_chunk_command(args: argparse.Namespace) -> int:
    dry_run_args = argparse.Namespace(
        chunk_id=args.chunk_id,
        duration=args.duration,
        max_transfer=args.max_transfer,
        transfers=args.transfers,
        checkers=args.checkers,
        run=False,
    )
    dry_run_status = copy_chunk_command(dry_run_args)
    if dry_run_status != 0:
        return dry_run_status

    copy_args = argparse.Namespace(
        chunk_id=args.chunk_id,
        duration=args.duration,
        max_transfer=args.max_transfer,
        transfers=args.transfers,
        checkers=args.checkers,
        run=True,
    )
    copy_status = copy_chunk_command(copy_args)
    if copy_status != 0:
        return copy_status

    verify_args = argparse.Namespace(chunk_id=args.chunk_id, no_hash=args.no_hash)
    return verify_chunk_command(verify_args)


def launch_label(chunk_id: str) -> str:
    safe = validate_text(chunk_id, "chunk_id").replace("_", "-")
    return f"com.max.photo-system.drive-to-kdrive.{safe}"


def launchctl_target() -> str:
    return f"gui/{os.getuid()}"


def run_background_command(args: argparse.Namespace) -> int:
    find_chunk(args.chunk_id)
    ensure_workspace()

    label = launch_label(args.chunk_id)
    plist_path = LAUNCHAGENTS_DIR / f"{label}.plist"
    stdout_path = LOGS_DIR / f"{args.chunk_id}-run.out"
    stderr_path = LOGS_DIR / f"{args.chunk_id}-run.err"
    pid_path = CHUNKS_DIR / f"{args.chunk_id}.launchagent"

    program_args = [
        str(PROJECT_ROOT / "bin" / "drive-to-kdrive"),
        "run-chunk",
        args.chunk_id,
        "--duration",
        args.duration,
        "--max-transfer",
        args.max_transfer,
        "--transfers",
        args.transfers,
        "--checkers",
        args.checkers,
    ]
    if args.no_hash:
        program_args.append("--no-hash")

    plist = {
        "Label": label,
        "ProgramArguments": program_args,
        "WorkingDirectory": str(PROJECT_ROOT),
        "RunAtLoad": True,
        "StandardOutPath": str(stdout_path),
        "StandardErrorPath": str(stderr_path),
    }

    if args.replace:
        subprocess.run(["launchctl", "bootout", launchctl_target(), str(plist_path)], check=False)

    with plist_path.open("wb") as f:
        plistlib.dump(plist, f)

    result = subprocess.run(
        ["launchctl", "bootstrap", launchctl_target(), str(plist_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        print("Could not start background chunk runner.")
        print(result.stderr.strip() or result.stdout.strip())
        print(f"If it was already loaded, retry with: ./bin/drive-to-kdrive run-background {args.chunk_id} --replace")
        return result.returncode

    pid_path.write_text(label + "\n", encoding="utf-8")
    update_chunk(args.chunk_id, notes=f"background run started with LaunchAgent {label}; no promotion")
    print(f"Started background chunk runner: {args.chunk_id}")
    print(f"Run output: {stdout_path}")
    print(f"Run errors: {stderr_path}")
    print(f"LaunchAgent: {plist_path}")
    return 0


def background_status_command(args: argparse.Namespace) -> int:
    find_chunk(args.chunk_id)
    label = launch_label(args.chunk_id)
    result = subprocess.run(
        ["launchctl", "print", f"{launchctl_target()}/{label}"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        print(f"{args.chunk_id}: background runner is loaded.")
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith(("state =", "pid =", "last exit code =")):
                print(stripped)
    else:
        print(f"{args.chunk_id}: background runner is not loaded.")
    row = find_chunk(args.chunk_id)
    print(f"ledger: {row['status']} | {row.get('files', '')} files | {row.get('bytes', '')} bytes | {row.get('notes', '')}")
    for path in [LOGS_DIR / f"{args.chunk_id}-run.out", LOGS_DIR / f"{args.chunk_id}-run.err"]:
        if path.exists():
            print(f"{path.name}: {path.stat().st_size} bytes")
    return 0


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
    add_transfer_flags(parser)
    parser.add_argument("--run", action="store_true", help="Actually copy files. Default is dry-run.")


def add_transfer_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--duration", default=DEFAULT_DURATION)
    parser.add_argument("--max-transfer", default=DEFAULT_MAX_TRANSFER)
    parser.add_argument("--transfers", default=DEFAULT_TRANSFERS)
    parser.add_argument("--checkers", default=DEFAULT_CHECKERS)


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

    verify_chunk = sub.add_parser("verify-chunk", help="Verify one copied chunk and write a concise report.")
    verify_chunk.add_argument("chunk_id")
    verify_chunk.add_argument("--no-hash", action="store_true", help="Only compare count, bytes, and path+size.")
    verify_chunk.set_defaults(func=verify_chunk_command)

    run_chunk = sub.add_parser("run-chunk", help="Dry-run, copy, and verify one chunk.")
    run_chunk.add_argument("chunk_id")
    add_transfer_flags(run_chunk)
    run_chunk.add_argument("--no-hash", action="store_true", help="Only compare count, bytes, and path+size.")
    run_chunk.set_defaults(func=run_chunk_command)

    run_background = sub.add_parser("run-background", help="Start a one-shot macOS background runner for a chunk.")
    run_background.add_argument("chunk_id")
    add_transfer_flags(run_background)
    run_background.add_argument("--no-hash", action="store_true", help="Only compare count, bytes, and path+size.")
    run_background.add_argument("--replace", action="store_true", help="Replace this chunk's existing LaunchAgent if loaded.")
    run_background.set_defaults(func=run_background_command)

    background_status = sub.add_parser("background-status", help="Check one chunk's background runner and ledger status.")
    background_status.add_argument("chunk_id")
    background_status.set_defaults(func=background_status_command)

    inventory = sub.add_parser("inventory", help="Write a recursive inventory for a remote path.")
    inventory.add_argument("remote", help='Example: "gdrive:My Drive" or "kdrive-webdav:00 Migration"')
    inventory.add_argument("--label")
    inventory.set_defaults(func=inventory_command)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
