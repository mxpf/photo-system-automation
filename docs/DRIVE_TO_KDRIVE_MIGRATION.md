# Google Drive → kDrive migration runbook

This is a staged migration for moving material out of Google Drive and into kDrive while reorganizing along the way.

The rule is simple: copy first, verify second, clean up later.

Do not use the migration itself as the moment where the old house gets demolished. The old Google Drive stays intact until the new kDrive structure has been checked and accepted.

## The model

```text
Google Drive source → local migration workspace → kDrive staging → reviewed kDrive home
```

Google Drive is the source for this migration. kDrive is the destination and future file home. WebDAV is used on the kDrive side. Google Drive itself is best handled through rclone’s Google Drive backend, not WebDAV.

## Why this is the right shape

This gives us three useful powers:

- We can reorganize without touching the old Google Drive.
- We can make durable inventories before and after every batch.
- We can separate “what copied successfully” from “what belongs where.”

The migration becomes a sequence of small, reversible decisions instead of one giant cloud-to-cloud shrug.

## Chunking policy

No migration job should run forever.

Every copy run should have at least one hard boundary:

- a time limit
- a transfer-size limit
- a small, named source folder
- or a single large archive

Default chunk size:

- Time: 60–90 minutes
- Data: 10–25 GB until the path proves boring
- Files: 1,000–5,000 files for mixed folders
- Scope: one human-understandable folder or category

For giant folders, split by subfolder. For giant files, move one at a time. For photos, split by source/date/album and send them through Photo System.

The goal is not maximum throughput. The goal is a migration you can pause, understand, and resume without dread.

## Chunk ledger

Track each chunk in a ledger:

```text
.migration/ledgers/YYYY-MM-DD-drive-to-kdrive-chunks.tsv
```

Columns:

```text
chunk_id	source_path	staging_path	final_home	status	files	bytes	started_at	finished_at	notes
```

Recommended statuses:

```text
planned
copying
copied
verified
promoted
cleanup_approved
skipped
needs_review
```

A chunk is not “done” because a copy process ended. It is done only when the report says the copied files match what we expected.

## Non-negotiables

During migration:

- Do not delete from Google Drive.
- Do not use `sync`.
- Do not use `move`.
- Do not use `purge`.
- Do not overwrite existing kDrive folders.
- Do not merge into final kDrive homes until a batch has an inventory and a clean copy report.

Use `copy` into dated staging folders.

## Destination structure

Use a dated staging area first:

```text
/Private/00 Migration/Google Drive Incoming/YYYY-MM-DD/
```

Inside that, use review buckets:

```text
01 Keep - Ready
02 Needs Review
03 Google Native Exports
04 Photos - Send to Photo System
05 Large Archives
06 Duplicates or Old Copies
99 Skip Candidates
_reports
```

Only after review should files move into their final kDrive homes, such as:

```text
/Private/01 Personal/
/Private/02 Work/
/Private/03 House/
/Private/04 Finance/
/Private/05 Writing/
/Private/06 Archive/
```

## Step 1 — configure remotes

Create two rclone remotes:

```text
gdrive:
kdrive-webdav:
```

`gdrive:` should use rclone’s Google Drive backend.

`kdrive-webdav:` should use kDrive’s WebDAV endpoint.

Keep the rclone config in a migration workspace, not scattered across the machine:

```text
/Users/mxpf/Code/photo-system-automation/.migration/rclone.conf
```

Do not commit that file. It contains credentials.

This repo includes a local helper for the chunked workflow:

```bash
./bin/drive-to-kdrive init
./bin/drive-to-kdrive check
./bin/drive-to-kdrive ledger
```

The helper stores local migration state under:

```text
.migration/
```

That folder is intentionally ignored by git.

Once the remotes are configured, plan a chunk:

```bash
./bin/drive-to-kdrive plan "chunk-001" "My Drive/Folder Name" \
  --bucket "02 Needs Review" \
  --final-home "/Private/01 Personal/Somewhere" \
  --notes "first small test chunk"
```

Preview the capped copy command:

```bash
./bin/drive-to-kdrive command "chunk-001"
```

Dry-run the chunk:

```bash
./bin/drive-to-kdrive copy-chunk "chunk-001"
```

Actually copy the chunk only after the dry-run looks sane:

```bash
./bin/drive-to-kdrive copy-chunk "chunk-001" --run
```

The default copy caps are 90 minutes and 25 GB.

## Step 2 — inventory Google Drive

Before copying anything, list what exists.

Suggested outputs:

```text
.migration/reports/google-drive-lsf.tsv
.migration/reports/google-drive-size.txt
.migration/reports/google-drive-tree.txt
```

The first pass should answer:

- How many files are there?
- How many folders are there?
- How much total data is there?
- What are the giant folders?
- Where are the obvious junk drawers?
- Which folders contain Google-native Docs, Sheets, or Slides?
- Which folders contain photos/videos that should feed the photo pipeline instead of normal documents?

## Step 3 — make a migration map

Create a plain mapping file before each batch:

```text
.migration/maps/YYYY-MM-DD-google-drive-map.tsv
```

Columns:

```text
source_path	destination_bucket	final_home	decision	notes
```

Example:

```text
My Drive/Taxes/2024	01 Keep - Ready	/Private/04 Finance/Taxes/2024	keep	canonical records
My Drive/Camera Uploads	04 Photos - Send to Photo System	/Private/01 Personal/Photos/Inbox/00 New Batches	review	send through Photo System, not directly to archive
My Drive/Old Desktop ZIPs	05 Large Archives	/Private/06 Archive/Old Drive Exports	review	large; inspect before final placement
```

The map is the migration brain. The copy command should follow the map, not improvise.

## Step 4 — copy one batch at a time

For each mapped batch, copy into staging:

```text
/Private/00 Migration/Google Drive Incoming/YYYY-MM-DD/<bucket>/
```

Use copy-only behavior. If a destination already exists, stop and choose a new dated folder rather than merging blindly.

Every copy command should be capped. Use a template like this:

```bash
rclone copy "gdrive:SOURCE/PATH" "kdrive-webdav:00 Migration/Google Drive Incoming/YYYY-MM-DD/CHUNK-ID" \
  --config ".migration/rclone.conf" \
  --immutable \
  --max-duration 90m \
  --cutoff-mode SOFT \
  --max-transfer 25G \
  --transfers 4 \
  --checkers 8 \
  --log-file ".migration/logs/CHUNK-ID-copy.log" \
  --log-level INFO \
  --stats 1m
```

The important parts:

- `copy` means Google Drive is not changed.
- `--immutable` means existing destination files are not overwritten.
- `--max-duration` keeps the run time-boxed.
- `--max-transfer` keeps the batch size bounded.
- `--cutoff-mode SOFT` lets active transfers finish more politely when the cap is reached.

If a capped run stops before the whole source folder is copied, keep the same chunk open and resume it later. Do not start reorganizing the partial result as if it were complete.

Good batch sizes:

- Small documents: a few folders at a time
- Photos/videos: one coherent album/export/source at a time
- Giant archives: one folder at a time

Small batches are not less professional. They are how you keep the room lit.

## Step 4.5 — pause/resume rules

It is safe to pause between chunks.

Before pausing:

1. Let the current capped copy finish, or stop it cleanly.
2. Mark the chunk status as `copied`, `needs_review`, or `copying`.
3. Save the copy log.
4. Do not promote partial chunks.

When resuming:

1. Re-run inventory for the active chunk.
2. Check the prior log.
3. Resume the same source → same staging destination with `copy` and `--immutable`.
4. Verify before promotion.

If anything feels ambiguous, create a new chunk rather than blending two attempts together.

## Step 5 — handle Google-native files deliberately

Google Docs, Sheets, and Slides are not ordinary files in the same way PDFs and JPEGs are ordinary files.

Export them deliberately.

Default choices:

- Docs → `.docx` and optionally `.pdf`
- Sheets → `.xlsx` and optionally `.pdf`
- Slides → `.pptx` and optionally `.pdf`
- Drawings → `.png` or `.pdf`

For important records, keep both editable and archival forms when useful.

Do not assume a Google-native document has been preserved just because a folder copied without obvious errors.

## Step 6 — route photos through Photo System

If Google Drive contains photos or videos, do not drop them directly into the canonical photo archive.

Route them here:

```text
/Users/mxpf/kDrive/01 Personal/Photos/Inbox/00 New Batches
```

Then let Photo System audit them against the canonical archive.

That keeps the photo archive from becoming a dumping ground and preserves the device → kDrive → Ente model.

## Step 7 — verify each batch

Each batch should have:

- source inventory
- destination inventory
- file count comparison
- byte total comparison
- error log
- list of skipped files
- list of Google-native exports

For ordinary binary files, compare hashes where the source and destination backends support it. Where WebDAV cannot provide server-side hashes, use size/path inventories and, for high-value batches, stream files back for local hashing.

## Step 8 — promote only after review

Once a batch is copied and verified, promote it from migration staging into its final kDrive home.

Promotion is a separate decision. It should be boring:

```text
staged folder reviewed → final destination confirmed → move/rename approved
```

Do not combine “copy,” “verify,” and “promote” into one command.

## Step 9 — only then clean Google Drive

Google Drive cleanup comes last.

A folder can be removed from Google Drive only after:

- it exists in kDrive
- its inventory matches expectation
- Google-native exports were handled
- photos were routed through Photo System if needed
- the final kDrive location is accepted
- the migration report says the batch is complete

Until then, Google Drive is the fallback.

## Suggested batch order

1. Low-risk documents
2. Writing and personal projects
3. Finance/taxes/legal records
4. Desktop dumps and old exports
5. Large archives
6. Photos/videos
7. Shared folders and collaborative material
8. Ambiguous leftovers

Photos go late because they already have their own system and deserve a clean intake path.

## Final report per batch

Each batch should end with a short report:

```text
Batch:
Source:
Destination:
Files copied:
Bytes copied:
Google-native exports:
Skipped:
Review needed:
Promoted to:
Safe to remove from Google Drive:
Notes:
```

The goal is not ceremony. The goal is being able to understand the move six months from now.

## References

- [rclone Google Drive backend](https://rclone.org/drive/)
- [rclone WebDAV backend](https://rclone.org/webdav/)
- [Infomaniak kDrive WebDAV](https://www.infomaniak.com/en/support/faq/2409/connect-to-kdrive-via-webdav)
