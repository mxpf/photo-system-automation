# Photo System

A small local control room for Max’s photo archive.

The system has one job: keep the photo pipeline legible. New photos arrive, the archive stays canonical, Ente gets fed from clean batches, and nothing quietly rearranges the house while nobody is looking.

## The shape of the system

kDrive is the source of truth.

The canonical archive lives here:

```text
/Users/mxpf/kDrive/01 Personal/Photos/Archive
```

Ente is the beautiful viewing layer. It is allowed to receive carefully prepared imports, but it is not the authority. If Ente loses state, changes an album, has a weird restore/trash behavior, or needs to be rebuilt from scratch, the canonical archive remains intact.

The LaCie archive remains the verified deep backup and migration record. This project does not modify it.

## The daily rhythm

Photos enter through intake folders:

```text
/Users/mxpf/kDrive/01 Personal/Photos/Inbox/00 New Batches
/Users/mxpf/kDrive/01 Personal/Device Backups/Phone/Camera
```

The automation checks those places and writes a report under:

```text
/Users/mxpf/kDrive/01 Personal/Photos/Inbox/_automation/reports
```

If nothing needs attention, it stays quiet. If new or suspicious files appear, it speaks up.

The audit helper is versioned in this repo at:

```text
/Users/mxpf/Code/photo-system-automation/scripts/photo_intake_audit.py
```

There may still be an older copy in the kDrive `_automation` folder for continuity, but the app prefers the repo copy.

## What the automation is allowed to do

By default, this project is intentionally boring:

- scan intake folders
- compare files against the archive manifest
- identify new, duplicate, already-archived, or review-needed files
- write reports
- notify when a human decision is needed

That is it.

## What it will not do by itself

The automation does not:

- delete photos
- rename photos
- move photos into the archive
- deduplicate originals
- modify embedded metadata
- promote anything into the canonical archive
- import anything into Ente
- treat Ente as the source of truth

Those steps require an explicit decision.

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

## The intended long-term loop

1. Phone and desktop photos land in kDrive intake.
2. Photo System audits the intake.
3. New material is reviewed.
4. Clean files are promoted into the canonical kDrive archive.
5. Ente import batches are generated from canonical material.
6. Ente is updated as a derived library.
7. Reports remain behind as a breadcrumb trail.

The important thing is that the archive has a memory. Every batch should be understandable later: where it came from, when it arrived, what was accepted, and what needed judgment.

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

## Project stance

This is not a photo manager. It is a little guardrail system around the photo manager.

The photo archive should remain calm, inspectable, and boring. The apps around it can be replaced. The originals should not care.
