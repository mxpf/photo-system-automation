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

