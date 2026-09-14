# App Typography

The native menu-bar app uses Geist, an open-source family approved by the font catalog.

Build the app:

```bash
/Users/mxpf/Code/photo-system-automation/scripts/build-menu-app.sh
```

The build embeds these locally installed files when available:

- `~/Library/Fonts/Geist-VariableFont_wght.ttf`
- `~/Library/Fonts/Geist-Italic-VariableFont_wght.ttf`

The app registers the bundled files at launch and falls back to the macOS system font if Geist is unavailable.

Diatype is no longer embedded because the available files are trial builds and are not approved for production use.

The built app is located at:

```text
/Users/mxpf/Code/photo-system-automation/dist/Photo System.app
```

Because this is a local unsigned app, macOS may require right-click → Open the first time.
