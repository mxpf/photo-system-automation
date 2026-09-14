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
- Read font intake files and embedded metadata
- Hash incoming font candidates
- Compare incoming fonts with the production catalog
- Write font-intake audit reports

## Font-library safeguards

- Future automation is audit-only.
- New fonts enter through `_Incoming`.
- Production approval requires explicit catalog evidence.
- Restricted and unresolved fonts are preserved under `_Quarantine`; they are not deleted.
- No automated job installs fonts or promotes them into the production collection.

## Source of truth

kDrive canonical archive:

`/Users/mxpf/kDrive/01 Personal/Photos/Archive`

Ente:

Derived app layer only.
