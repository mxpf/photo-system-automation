# Photo System

A small local control room for a device → kDrive → Ente photo pipeline.

Photo System is built around one opinion: preservation and presentation should be separate.

kDrive holds the canonical files. Ente gives those files a humane photo-app surface. This repo sits between them as a quiet auditor, making sure new photos are noticed, compared, reported, and only promoted when the batch makes sense.

## What it does

Photo System watches the kDrive folders where new photos arrive, compares them against the canonical archive, and tells you what needs attention.

In plain terms, it answers:

- Did new photos arrive?
- Are they already in the archive?
- Are there duplicates?
- Are there files that look odd enough to review?
- Where is the latest audit report?

It runs locally on the Mac, can sit in the menu bar, and can also run quiet scheduled checks in the background.

## The pipeline

The intended flow is:

```text
device photos → kDrive intake → audited archive → Ente import/update
```

Each layer has a different job.

1. Devices capture the originals.
   Phones and desktops produce the files. They are not asked to be the archive, the catalog, or the long-term memory.

2. kDrive receives and preserves the originals.
   kDrive is the canonical file layer: ordinary folders, visible paths, syncable storage, and a place where the archive can be inspected without needing a photo app to explain it.

3. Photo System audits the intake.
   It checks what arrived, what is already known, what looks duplicated, and what needs review. It writes a report instead of making silent changes.

4. The archive is promoted deliberately.
   Clean batches can move into the canonical archive only after a human decision.

5. Ente gets updated from the archive.
   Ente is the private photo-library layer: browsing, albums, sharing, memories, and the actual “I want to enjoy my photos” experience. It is downstream from the archive, not above it.

## Why this is a good idea

This architecture keeps the system calm.

- It separates storage truth from app experience.
- It reduces lock-in: if Ente, Google Photos, Apple Photos, or anything else changes, the archive still exists as files.
- It makes kDrive useful as infrastructure instead of pretending it is a full photo brain.
- It lets Ente be good at what Ente is good at: private, polished photo access.
- It creates an audit trail before anything gets promoted.
- It keeps automation on a leash. The script can notice things; it does not get to decide what your archive means.

The point is not to have more software. The point is to keep each piece from becoming responsible for the wrong part of the system.

## Related migration runbooks

- [Google Drive → kDrive migration](docs/DRIVE_TO_KDRIVE_MIGRATION.md)

## Why these apps

### Devices

The phone and desktop are the capture layer. Their job is to produce originals and metadata, then hand them off. They should not be the only place where anything important lives.

### kDrive

kDrive is a strong fit for the canonical layer because it behaves like a file system, not just a photo feed. It can receive automatic mobile photo backups, sync to the Mac, expose ordinary folders, and preserve a path-based archive that can be audited independently.

That makes it a good source of truth: boring, inspectable, and not dependent on one photo app’s database.

Relevant docs:

- [kDrive photo backup on iOS](https://www.infomaniak.com/en/support/faq/2394/import-photos-to-the-kdrive-mobile-app-ios)
- [kDrive photo backup on Android](https://www.infomaniak.com/en/support/faq/2514/import-photos-to-the-kdrive-mobile-app-android)

### Ente

Ente is a strong fit for the photo-app layer because it is designed around end-to-end encrypted photo storage, has apps across desktop, web, and mobile, and supports migration from Google Takeout through the desktop app.

That makes it a good derived library: private, pleasant, and replaceable if needed.

Relevant docs:

- [Ente Photos](https://ente.com/)
- [Import from Google Photos](https://ente.com/help/photos/migration/from-google-photos/)

### Photo System

Photo System is the guardrail between the two. It keeps the kDrive archive from becoming a junk drawer and keeps Ente imports from becoming a mystery ritual.

It does not try to be beautiful. It tries to be trustworthy.

### LaCie

The LaCie archive remains the verified deep backup and migration record. It is the cold, boring safety net: not the daily workflow, but still part of the trust model.

## What it does not do

Photo System does not manage your photo library for you.

It does not:

- delete photos
- rename photos
- move photos into the archive
- deduplicate originals
- modify embedded metadata
- promote anything into the canonical archive
- import anything into Ente
- treat Ente as the source of truth

Those steps require an explicit decision.

## Canonical paths

kDrive is the source of truth.

The canonical archive lives here:

```text
/Users/mxpf/kDrive/01 Personal/Photos/Archive
```

New photos arrive here:

```text
/Users/mxpf/kDrive/01 Personal/Photos/Inbox/00 New Batches
/Users/mxpf/kDrive/01 Personal/Device Backups/Phone/Camera
```

Reports are written under:

```text
/Users/mxpf/kDrive/01 Personal/Photos/Inbox/_automation/reports
```

The audit helper is versioned in this repo at:

```text
/Users/mxpf/Code/photo-system-automation/scripts/photo_intake_audit.py
```

There may still be an older copy in the kDrive `_automation` folder for continuity, but the app prefers the repo copy.

## Menu app

The local Mac app is here:

```text
/Users/mxpf/Code/photo-system-automation/dist/Photo System.app
```

It provides:

- Audit now
- Status
- Open latest report
- Set background audit interval
- Stop background audit
- Open project folder

The Dock icon uses the generated Photo System mark. The menu-bar item uses a flat monochrome icon so it remains legible at tiny sizes.

Because this is a local unsigned app, macOS may require right-click → Open the first time.

## Background audit

The background schedule is installed as a macOS LaunchAgent:

```text
/Users/mxpf/Library/LaunchAgents/com.max.photo-system-audit.plist
```

Common intervals:

- `90m`
- `hourly`
- `6h`
- `12h`
- `daily`
- `weekly`

The minimum interval is 15 minutes. Shorter than that gets noisy and impolite to kDrive.

From Terminal:

```bash
./bin/photo-system status
./bin/photo-system audit --audit both
./bin/photo-system install --interval daily
./bin/photo-system install --interval 90m
./bin/photo-system uninstall
```

## Building the app

```bash
./scripts/build-menu-app.sh
```

The build script:

- compiles the native macOS app
- embeds Diatype if the font is available locally
- copies the app icon into the bundle
- applies local ad-hoc signing

Output:

```text
/Users/mxpf/Code/photo-system-automation/dist/Photo System.app
```
