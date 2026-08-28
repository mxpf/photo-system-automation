# Photo System Automation

Local automation for Max's photo archive workflow.

## Core model

The canonical photo archive lives in kDrive:

`/Users/mxpf/kDrive/01 Personal/Photos/Archive`

Ente is a derived app layer. It receives import batches generated from the canonical archive, but it is not the source of truth.

## Intended pipeline

1. Devices and desktop exports land in intake folders.
2. This project audits those intake folders.
3. Clean batches get promoted to the canonical kDrive archive only after approval.
4. Ente import batches are generated from newly promoted canonical items.
5. Ente is updated from those batches.

## Safety posture

Default automation is read-only:

- audit inboxes
- write reports
- alert when review is needed

Actions that change the archive must remain explicit:

- promote into canonical archive
- update canonical catalogs
- build/import Ente batches
- delete/trash/quarantine anything

## Desktop/menu-bar use

Use these executables from Finder or Terminal:

- `Photo System Menu.command` — simple interactive menu
- `Photo System Audit Now.command` — run the audit immediately
- `Photo System Status.command` — show local automation status

Direct executable paths:

- `/Users/mxpf/Code/photo-system-automation/bin/photo-system-menu`
- `/Users/mxpf/Code/photo-system-automation/bin/photo-system-audit-now`
- `/Users/mxpf/Code/photo-system-automation/bin/photo-system-status`
- `/Users/mxpf/Code/photo-system-automation/bin/photo-system-set-interval`

Examples:

```bash
/Users/mxpf/Code/photo-system-automation/bin/photo-system-set-interval daily
/Users/mxpf/Code/photo-system-automation/bin/photo-system-set-interval 6h
/Users/mxpf/Code/photo-system-automation/bin/photo-system-set-interval 90m
```

Supported interval examples:

- `hourly`
- `daily`
- `weekly`
- `90m`
- `6h`
- `12h`
- `1d`

Minimum interval is 15 minutes.

## Local scheduled audit

The macOS LaunchAgent lives at:

`/Users/mxpf/Library/LaunchAgents/com.max.photo-system-audit.plist`

Helpful commands:

```bash
./bin/photo-system status
./bin/photo-system install --interval daily
./bin/photo-system install --interval 6h
./bin/photo-system uninstall
```

Logs:

`/Users/mxpf/Code/photo-system-automation/logs`

## Native menu-bar app

Build:

```bash
./scripts/build-menu-app.sh
```

Then open:

`/Users/mxpf/Code/photo-system-automation/dist/Photo System.app`

The app uses Diatype if macOS exposes the font under a standard Diatype family
name, and falls back to the system font otherwise.

Because this is a local unsigned app, macOS may require right-click → Open the
first time.

## Current status

This repo is the local home for the automation code. The existing production scripts still live in:

`/Users/mxpf/kDrive/01 Personal/Photos/Inbox/_automation`

We will migrate or wrap those scripts here carefully, one piece at a time.

## First automation target

Daily read-only audit of:

- `/Users/mxpf/kDrive/01 Personal/Photos/Inbox/00 New Batches`
- `/Users/mxpf/kDrive/01 Personal/Device Backups/Phone/Camera`

Reports should continue to be written under:

`/Users/mxpf/kDrive/01 Personal/Photos/Inbox/_automation/reports`
