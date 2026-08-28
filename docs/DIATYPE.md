# Diatype / Menu Bar Font

Diatype is treated as the preferred UI font for the native menu-bar app.

Build the app:

```bash
/Users/mxpf/Code/photo-system-automation/scripts/build-menu-app.sh
```

Open:

`/Users/mxpf/Code/photo-system-automation/dist/Photo System.app`

Because this is a local unsigned app, macOS may require right-click → Open the
first time.

The build script embeds locally installed Diatype font files into:

`dist/Photo System.app/Contents/Resources/Fonts`

It currently looks for local font files matching:

- `~/Library/Fonts/ABCDiatypeTrial-*.otf`
- `~/Library/Fonts/*Diatype*.otf`
- `~/Library/Fonts/*Diatype*.ttf`

The app registers bundled fonts at launch and then tries these font names:

- Diatype
- ABC Diatype
- ABCDiatype
- ABCDiatypeTrial-Regular
- ABCDiatypeTrial-Medium
- ABCDiatypeTrial-Bold
- ABCDiatypeTrial-Heavy
- Diatype-Regular
- Diatype Variable

If none are visible to macOS, the app falls back to the system font.

## App menu items

- Audit now
- Status
- Open latest report
- Set interval: `90m`, `hourly`, `6h`, `12h`, `daily`, `weekly`
- Stop background audit
- Open project folder

## Notes

The project intentionally lives outside `Documents` because macOS privacy
controls can block background LaunchAgents from reading scripts under
Documents/Desktop.
