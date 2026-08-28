# Safety Rules

This project protects the archive by default.

## Never automatic

- Delete originals
- Move originals
- Rename originals
- Deduplicate by deleting files
- Promote files into the canonical archive
- Rewrite canonical metadata catalogs
- Treat Ente deletions as canonical archive deletions

## Allowed automatically

- Read intake folders
- Read canonical metadata
- Hash candidate files
- Detect duplicates
- Detect unsupported files
- Write audit reports
- Notify when review is needed

## Source of truth

kDrive canonical archive:

`/Users/mxpf/kDrive/01 Personal/Photos/Archive`

Ente:

Derived app layer only.

