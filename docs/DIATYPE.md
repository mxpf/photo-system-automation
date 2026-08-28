# Diatype / Menu Bar Setup

Use one of these executable files as the menu-bar action:

## Recommended

`/Users/mxpf/Code/photo-system-automation/Photo System Menu.command`

This opens a tiny menu:

1. Audit now
2. Status
3. Install/update interval
4. Stop automation

## Single-purpose actions

Audit now:

`/Users/mxpf/Code/photo-system-automation/Photo System Audit Now.command`

Status:

`/Users/mxpf/Code/photo-system-automation/Photo System Status.command`

Set interval from a launcher that supports arguments:

`/Users/mxpf/Code/photo-system-automation/bin/photo-system-set-interval 6h`

## Notes

The project intentionally lives outside `Documents` because macOS privacy
controls can block background LaunchAgents from reading scripts under
Documents/Desktop.

