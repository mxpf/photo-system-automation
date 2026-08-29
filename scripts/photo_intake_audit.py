#!/usr/bin/env python3
"""
Photo inbox intake audit.

Default behavior is read-only against the photo archive and inbox media.
It creates reports in:

  /Users/mxpf/kDrive/01 Personal/Photos/Inbox/_automation/reports

It does not move, delete, rename, deduplicate, or modify source media.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


PHOTOS_ROOT = Path("/Users/mxpf/kDrive/01 Personal/Photos")
INBOX_ROOT = PHOTOS_ROOT / "Inbox"
DEFAULT_INPUT = INBOX_ROOT / "00 New Batches"
PHONE_BACKUP_INPUT = Path("/Users/mxpf/kDrive/01 Personal/Device Backups/Phone/Camera")
REPORTS_ROOT = INBOX_ROOT / "_automation" / "reports"
ARCHIVE_MANIFEST = PHOTOS_ROOT / "Archive" / "metadata" / "manifests" / "archive-sha256.tsv"

MEDIA_EXTENSIONS = {
    ".jpg", ".jpeg", ".jpe", ".png", ".heic", ".heif", ".gif", ".webp", ".tif", ".tiff",
    ".dng", ".arw", ".cr2", ".nef", ".rw2", ".orf", ".raf",
    ".mp4", ".mov", ".m4v", ".avi", ".3gp", ".3gpp", ".mts", ".m2ts", ".mpg", ".mpeg",
}
SIDECAR_EXTENSIONS = {".json", ".xmp", ".aae"}
ARCHIVE_EXTENSIONS = {".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".dmg", ".pkg", ".iso"}
DOCUMENT_EXTENSIONS = {".pdf", ".txt", ".md", ".rtf", ".doc", ".docx", ".csv", ".tsv"}

DATE_PATTERNS = [
    re.compile(r"(?P<y>20\d{2}|19\d{2})[-_. ]?(?P<m>0[1-9]|1[0-2])[-_. ]?(?P<d>0[1-9]|[12]\d|3[01])"),
    re.compile(r"(?P<y>20\d{2}|19\d{2})(?P<m>0[1-9]|1[0-2])(?P<d>0[1-9]|[12]\d|3[01])"),
]


def utc_now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")


def next_report_dir(reports_root: Path, stamp: str) -> Path:
    base = reports_root / f"photo-intake-audit-{stamp}"
    if not base.exists():
        return base
    for index in range(2, 1000):
        candidate = reports_root / f"photo-intake-audit-{stamp}-{index:02d}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not create a unique report folder for {stamp}")


def safe_rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_files(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in {".DS_Store", "__MACOSX"} and not d.startswith(".")
        ]
        for filename in filenames:
            if filename == ".DS_Store":
                continue
            yield Path(dirpath) / filename


def classify(path: Path, size: int) -> str:
    suffix = path.suffix.lower()
    if size == 0:
        return "zero_byte"
    if suffix in MEDIA_EXTENSIONS:
        return "media"
    if suffix in SIDECAR_EXTENSIONS:
        return "sidecar"
    if suffix in ARCHIVE_EXTENSIONS:
        return "archive_or_installer"
    if suffix in DOCUMENT_EXTENSIONS:
        return "document"
    if suffix == "":
        return "no_extension_review"
    return "unsupported_review"


def infer_date_from_filename(path: Path) -> str:
    text = path.name
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        try:
            found = dt.date(int(match.group("y")), int(match.group("m")), int(match.group("d")))
            return found.isoformat()
        except ValueError:
            continue
    return ""


def load_archive_hashes(path: Path) -> dict[str, list[str]]:
    by_hash: dict[str, list[str]] = defaultdict(list)
    if not path.exists():
        return by_hash
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            digest = row.get("sha256", "")
            rel = row.get("relative_path", "")
            if digest:
                by_hash[digest].append(rel)
    return by_hash


def write_tsv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def human_bytes(num: int) -> str:
    value = float(num)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{num} B"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit new photo inbox batches without changing source files.")
    parser.add_argument("input", nargs="?", default=str(DEFAULT_INPUT), help="Batch folder or inbox folder to audit.")
    parser.add_argument("--no-hash", action="store_true", help="Skip SHA-256 hashing. Faster, but cannot detect duplicate content.")
    parser.add_argument("--reports-root", default=str(REPORTS_ROOT), help="Where to write reports.")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser()
    reports_root = Path(args.reports_root).expanduser()

    if not input_path.exists():
        print(f"Input path does not exist: {input_path}", file=sys.stderr)
        return 2
    if not input_path.is_dir():
        print(f"Input path is not a folder: {input_path}", file=sys.stderr)
        return 2

    stamp = utc_now_stamp()
    report_dir = next_report_dir(reports_root, stamp)
    report_dir.mkdir(parents=True, exist_ok=False)

    archive_by_hash = {} if args.no_hash else load_archive_hashes(ARCHIVE_MANIFEST)
    rows: list[dict] = []
    hash_to_rows: dict[str, list[int]] = defaultdict(list)

    for path in sorted(iter_files(input_path), key=lambda p: p.as_posix().lower()):
        try:
            stat = path.stat()
        except OSError as exc:
            rows.append({
                "relative_path": safe_rel(path, input_path),
                "absolute_path": path.as_posix(),
                "category": "unreadable_review",
                "size_bytes": "",
                "size_human": "",
                "sha256": "",
                "duplicate_within_batch": "",
                "already_in_archive": "",
                "archive_matches": "",
                "filename_date_guess": "",
                "modified_time": "",
                "note": str(exc),
            })
            continue

        category = classify(path, stat.st_size)
        digest = ""
        archive_matches = []
        if not args.no_hash and stat.st_size > 0:
            try:
                digest = sha256_file(path)
                archive_matches = archive_by_hash.get(digest, [])
            except OSError as exc:
                category = "unreadable_review"
                digest = ""
                archive_matches = []
                note = str(exc)
            else:
                note = ""
        else:
            note = "hash skipped" if args.no_hash else ""

        row = {
            "relative_path": safe_rel(path, input_path),
            "absolute_path": path.as_posix(),
            "category": category,
            "size_bytes": stat.st_size,
            "size_human": human_bytes(stat.st_size),
            "sha256": digest,
            "duplicate_within_batch": "",
            "already_in_archive": "yes" if archive_matches else "no",
            "archive_matches": "; ".join(archive_matches[:10]),
            "filename_date_guess": infer_date_from_filename(path),
            "modified_time": dt.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            "note": note,
        }
        rows.append(row)
        if digest:
            hash_to_rows[digest].append(len(rows) - 1)

    for digest, indexes in hash_to_rows.items():
        if len(indexes) > 1:
            for index in indexes:
                rows[index]["duplicate_within_batch"] = "yes"

    fields = [
        "relative_path",
        "category",
        "size_bytes",
        "size_human",
        "sha256",
        "duplicate_within_batch",
        "already_in_archive",
        "archive_matches",
        "filename_date_guess",
        "modified_time",
        "note",
        "absolute_path",
    ]
    write_tsv(report_dir / "file-manifest.tsv", rows, fields)

    counts = Counter(row["category"] for row in rows)
    bytes_by_category = Counter()
    for row in rows:
        if isinstance(row["size_bytes"], int):
            bytes_by_category[row["category"]] += row["size_bytes"]

    duplicate_files = sum(1 for row in rows if row["duplicate_within_batch"] == "yes")
    already_in_archive = sum(1 for row in rows if row["already_in_archive"] == "yes")
    zero_byte = counts.get("zero_byte", 0)
    review_needed = sum(counts.get(c, 0) for c in ["zero_byte", "archive_or_installer", "no_extension_review", "unsupported_review", "unreadable_review"])
    total_bytes = sum(row["size_bytes"] for row in rows if isinstance(row["size_bytes"], int))

    summary = {
        "created_at_utc": stamp,
        "input": input_path.as_posix(),
        "recognized_intake_sources": {
            "manual_batches": DEFAULT_INPUT.as_posix(),
            "kdrive_phone_backup_camera": PHONE_BACKUP_INPUT.as_posix(),
        },
        "report_dir": report_dir.as_posix(),
        "archive_manifest": ARCHIVE_MANIFEST.as_posix(),
        "hashed": not args.no_hash,
        "file_count": len(rows),
        "total_bytes": total_bytes,
        "total_size_human": human_bytes(total_bytes),
        "category_counts": dict(counts),
        "category_bytes": dict(bytes_by_category),
        "duplicate_files_within_batch": duplicate_files,
        "already_in_archive_files": already_in_archive,
        "zero_byte_files": zero_byte,
        "review_needed_files": review_needed,
    }
    (report_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    markdown = [
        "# Photo Intake Audit",
        "",
        f"Created: {stamp} UTC",
        "",
        f"Input: `{input_path}`",
        f"Report folder: `{report_dir}`",
        "",
        "Recognized intake sources:",
        "",
        f"- Manual batches: `{DEFAULT_INPUT}`",
        f"- kDrive phone camera backup: `{PHONE_BACKUP_INPUT}`",
        "",
        "## Summary",
        "",
        f"- Files scanned: {len(rows):,}",
        f"- Total size: {human_bytes(total_bytes)}",
        f"- Hash comparison: {'enabled' if not args.no_hash else 'skipped'}",
        f"- Files already in canonical archive: {already_in_archive:,}",
        f"- Duplicate files within this intake: {duplicate_files:,}",
        f"- Zero-byte files: {zero_byte:,}",
        f"- Files needing review: {review_needed:,}",
        "",
        "## Categories",
        "",
        "| Category | Files | Size |",
        "|---|---:|---:|",
    ]
    for category, count in sorted(counts.items()):
        markdown.append(f"| {category} | {count:,} | {human_bytes(bytes_by_category[category])} |")
    markdown.extend([
        "",
        "## What this script did",
        "",
        "- Read the input folder.",
        "- Classified files by type.",
        "- Calculated SHA-256 hashes unless `--no-hash` was used.",
        "- Compared hashes against the canonical archive manifest when available.",
        "- Wrote a manifest and summary report.",
        "",
        "## What this script did not do",
        "",
        "- It did not move files.",
        "- It did not rename files.",
        "- It did not delete files.",
        "- It did not modify embedded metadata.",
        "- It did not add anything to the canonical archive.",
        "",
        "## Next decision",
        "",
        "Review `file-manifest.tsv`. If the batch looks clean, move or copy the batch into `10 Ready to Canonicalize` and run the future canonicalization/promote step.",
        "",
    ])
    (report_dir / "README.md").write_text("\n".join(markdown), encoding="utf-8")

    print(f"Photo intake audit complete.")
    print(f"Files scanned: {len(rows):,}")
    print(f"Total size: {human_bytes(total_bytes)}")
    print(f"Already in archive: {already_in_archive:,}")
    print(f"Duplicates within intake: {duplicate_files:,}")
    print(f"Review needed: {review_needed:,}")
    print(f"Report: {report_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
