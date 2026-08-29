import Cocoa
import CoreText

enum Settings {
    static let projectRoot = "/Users/mxpf/Code/photo-system-automation"
    static let cliPath = "\(projectRoot)/bin/photo-system"
}

func preferredFont(size: CGFloat, weight: NSFont.Weight = .regular) -> NSFont {
    let names = [
        "ABCDiatypeTrial-Regular",
        "ABCDiatypeTrial-Medium",
        "ABCDiatypeTrial-Bold",
        "ABCDiatypeTrial-Heavy",
        "Diatype",
        "ABC Diatype",
        "ABCDiatype",
        "Diatype-Regular",
        "Diatype Variable",
    ]
    for name in names {
        if let font = NSFont(name: name, size: size) {
            return font
        }
    }
    return NSFont.systemFont(ofSize: size, weight: weight)
}

func styled(_ title: String, size: CGFloat = 14, weight: NSFont.Weight = .regular) -> NSAttributedString {
    return NSAttributedString(
        string: title,
        attributes: [
            .font: preferredFont(size: size, weight: weight),
            .foregroundColor: NSColor.labelColor,
        ]
    )
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var mainWindow: NSWindow?

    func applicationDidFinishLaunching(_ notification: Notification) {
        log("applicationDidFinishLaunching")
        registerBundledFonts()
        NSApp.setActivationPolicy(.regular)
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        if let button = statusItem.button {
            button.image = makeMenuBarIcon()
            button.imagePosition = .imageOnly
            button.toolTip = "Photo System Automation"
        }
        rebuildMenu()
        showWindow()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return false
    }

    private func registerBundledFonts() {
        guard let fontsURL = Bundle.main.resourceURL?.appendingPathComponent("Fonts") else {
            log("No bundled Fonts directory found")
            return
        }
        guard let files = try? FileManager.default.contentsOfDirectory(
            at: fontsURL,
            includingPropertiesForKeys: nil
        ) else {
            log("Could not list bundled Fonts directory")
            return
        }

        for url in files where ["otf", "ttf"].contains(url.pathExtension.lowercased()) {
            CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil)
        }
        log("Registered \(files.count) bundled font files")
    }

    private func rebuildMenu() {
        let menu = NSMenu()

        let title = NSMenuItem()
        title.attributedTitle = styled("Photo System", size: 15, weight: .semibold)
        title.isEnabled = false
        menu.addItem(title)
        menu.addItem(.separator())

        menu.addItem(item("Show window", action: #selector(showWindow)))
        menu.addItem(item("Audit now…", action: #selector(auditNow)))
        menu.addItem(item("Status…", action: #selector(showStatus)))
        menu.addItem(item("Open latest report", action: #selector(openLatestReport)))
        menu.addItem(.separator())

        let interval = NSMenuItem(title: "Set interval", action: nil, keyEquivalent: "")
        interval.attributedTitle = styled("Set interval", size: 14, weight: .medium)
        let submenu = NSMenu()
        for value in ["90m", "hourly", "6h", "12h", "daily", "weekly"] {
            let i = NSMenuItem(title: value, action: #selector(setInterval(_:)), keyEquivalent: "")
            i.representedObject = value
            i.target = self
            i.attributedTitle = styled(value)
            submenu.addItem(i)
        }
        interval.submenu = submenu
        menu.addItem(interval)

        menu.addItem(item("Stop background audit", action: #selector(stopAutomation)))
        menu.addItem(.separator())
        menu.addItem(item("Open project folder", action: #selector(openProject)))
        menu.addItem(item("Quit", action: #selector(quit)))

        statusItem.menu = menu
    }

    @objc private func showWindow() {
        log("showWindow")
        if mainWindow == nil {
            mainWindow = makeMainWindow()
        }
        mainWindow?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        log("window visible=\(mainWindow?.isVisible == true)")
    }

    private func makeMainWindow() -> NSWindow {
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 460, height: 340),
            styleMask: [.titled, .closable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Photo System"
        window.center()
        window.isReleasedWhenClosed = false

        let container = NSView(frame: NSRect(x: 0, y: 0, width: 460, height: 340))
        container.wantsLayer = true
        container.layer?.backgroundColor = NSColor.windowBackgroundColor.cgColor

        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 14
        stack.translatesAutoresizingMaskIntoConstraints = false

        let title = NSTextField(labelWithString: "Photo System")
        title.font = preferredFont(size: 28, weight: .bold)

        let subtitle = NSTextField(labelWithString: "Running. Use this window or the small photo icon in the menu bar.")
        subtitle.font = preferredFont(size: 14)
        subtitle.textColor = .secondaryLabelColor
        subtitle.maximumNumberOfLines = 3
        subtitle.lineBreakMode = .byWordWrapping
        subtitle.preferredMaxLayoutWidth = 390

        let status = NSTextField(labelWithString: "Safe defaults: audit-only, no deletes, kDrive remains the source of truth.")
        status.font = preferredFont(size: 13, weight: .medium)
        status.textColor = .secondaryLabelColor
        status.maximumNumberOfLines = 2
        status.preferredMaxLayoutWidth = 390

        let buttonGrid = NSGridView(views: [
            [button("Audit now", #selector(auditNow)), button("Status", #selector(showStatus))],
            [button("Latest report", #selector(openLatestReport)), button("Project folder", #selector(openProject))]
        ])
        buttonGrid.rowSpacing = 10
        buttonGrid.columnSpacing = 10

        let hint = NSTextField(labelWithString: "Tip: if macOS hides the menu-bar item, leave this app open from the Dock.")
        hint.font = preferredFont(size: 12)
        hint.textColor = .tertiaryLabelColor
        hint.maximumNumberOfLines = 2
        hint.preferredMaxLayoutWidth = 390

        stack.addArrangedSubview(title)
        stack.addArrangedSubview(subtitle)
        stack.addArrangedSubview(status)
        stack.addArrangedSubview(buttonGrid)
        stack.addArrangedSubview(hint)

        container.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: container.leadingAnchor, constant: 28),
            stack.trailingAnchor.constraint(lessThanOrEqualTo: container.trailingAnchor, constant: -28),
            stack.topAnchor.constraint(equalTo: container.topAnchor, constant: 28)
        ])

        window.contentView = container
        log("makeMainWindow")
        return window
    }

    private func button(_ title: String, _ action: Selector) -> NSButton {
        let button = NSButton(title: title, target: self, action: action)
        button.font = preferredFont(size: 13, weight: .medium)
        button.bezelStyle = .rounded
        button.setFrameSize(NSSize(width: 160, height: 32))
        return button
    }

    private func makeMenuBarIcon() -> NSImage {
        let size = NSSize(width: 18, height: 18)
        let image = NSImage(size: size)
        image.lockFocus()
        NSColor.black.setStroke()
        NSColor.black.setFill()

        let tray = NSBezierPath(roundedRect: NSRect(x: 3.0, y: 3.0, width: 12.0, height: 5.0), xRadius: 1.4, yRadius: 1.4)
        tray.lineWidth = 1.8
        tray.stroke()

        let circle = NSBezierPath(ovalIn: NSRect(x: 5.0, y: 7.0, width: 8.0, height: 8.0))
        circle.lineWidth = 1.8
        circle.stroke()

        let center = NSPoint(x: 9.0, y: 11.0)
        for angle in stride(from: 0.0, to: 360.0, by: 60.0) {
            let radians = angle * .pi / 180.0
            let inner = NSPoint(x: center.x + CGFloat(cos(radians)) * 1.5, y: center.y + CGFloat(sin(radians)) * 1.5)
            let outer = NSPoint(x: center.x + CGFloat(cos(radians)) * 3.5, y: center.y + CGFloat(sin(radians)) * 3.5)
            let line = NSBezierPath()
            line.move(to: inner)
            line.line(to: outer)
            line.lineWidth = 1.1
            line.stroke()
        }

        image.unlockFocus()
        image.isTemplate = true
        return image
    }

    private func item(_ title: String, action: Selector) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: "")
        item.target = self
        item.attributedTitle = styled(title)
        return item
    }

    private func run(_ args: [String], title: String, notifyOnDone: Bool = false) {
        let taskTitle = title
        DispatchQueue.global(qos: .userInitiated).async {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: Settings.cliPath)
            process.arguments = args
            process.currentDirectoryURL = URL(fileURLWithPath: Settings.projectRoot)

            let pipe = Pipe()
            process.standardOutput = pipe
            process.standardError = pipe

            do {
                try process.run()
                process.waitUntilExit()
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                let output = String(data: data, encoding: .utf8) ?? ""
                DispatchQueue.main.async {
                    if notifyOnDone {
                        self.notify(title: taskTitle, message: process.terminationStatus == 0 ? "Done." : "Needs attention.")
                    }
                    self.alert(title: taskTitle, text: output, ok: process.terminationStatus == 0)
                }
            } catch {
                DispatchQueue.main.async {
                    self.alert(title: taskTitle, text: "\(error)", ok: false)
                }
            }
        }
    }

    private func alert(title: String, text: String, ok: Bool) {
        let alert = NSAlert()
        alert.messageText = title
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        alert.informativeText = ""
        alert.alertStyle = ok ? .informational : .warning
        alert.accessoryView = resultTextView(String(trimmed.prefix(3500)))
        alert.addButton(withTitle: "OK")
        NSApp.activate(ignoringOtherApps: true)
        alert.runModal()
    }

    private func resultTextView(_ text: String) -> NSView {
        let width: CGFloat = 420
        let height: CGFloat = text.count > 900 ? 220 : 140
        let scrollView = NSScrollView(frame: NSRect(x: 0, y: 0, width: width, height: height))
        scrollView.hasVerticalScroller = text.count > 900
        scrollView.borderType = .noBorder
        scrollView.drawsBackground = false

        let textView = NSTextView(frame: scrollView.bounds)
        textView.string = text
        textView.isEditable = false
        textView.isSelectable = true
        textView.drawsBackground = false
        textView.font = preferredFont(size: 13)
        textView.textColor = .labelColor
        textView.textContainerInset = NSSize(width: 0, height: 0)
        textView.textContainer?.lineFragmentPadding = 0
        textView.textContainer?.containerSize = NSSize(width: width, height: .greatestFiniteMagnitude)
        textView.textContainer?.widthTracksTextView = true
        textView.autoresizingMask = [.width]

        scrollView.documentView = textView
        return scrollView
    }

    private func notify(title: String, message: String) {
        let script = "display notification \"\(message)\" with title \"\(title)\""
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        process.arguments = ["-e", script]
        try? process.run()
    }

    @objc private func auditNow() {
        run(["audit", "--audit", "both", "--notify"], title: "Photo audit", notifyOnDone: true)
    }

    @objc private func showStatus() {
        run(["status"], title: "Photo system status")
    }

    @objc private func openLatestReport() {
        run(["latest-report", "--open"], title: "Latest photo report")
    }

    @objc private func setInterval(_ sender: NSMenuItem) {
        guard let value = sender.representedObject as? String else { return }
        run(["install", "--interval", value], title: "Set photo audit interval")
    }

    @objc private func stopAutomation() {
        run(["uninstall"], title: "Stop photo audit automation")
    }

    @objc private func openProject() {
        NSWorkspace.shared.open(URL(fileURLWithPath: Settings.projectRoot))
    }

    @objc private func quit() {
        NSApp.terminate(nil)
    }

    private func log(_ message: String) {
        let url = URL(fileURLWithPath: NSHomeDirectory())
            .appendingPathComponent("Library/Logs/PhotoSystemMenu.log")
        let stamp = ISO8601DateFormatter().string(from: Date())
        let line = "\(stamp) \(message)\n"
        if let data = line.data(using: .utf8) {
            if FileManager.default.fileExists(atPath: url.path) {
                if let handle = try? FileHandle(forWritingTo: url) {
                    _ = try? handle.seekToEnd()
                    try? handle.write(contentsOf: data)
                    try? handle.close()
                }
            } else {
                try? data.write(to: url)
            }
        }
    }
}

@main
enum PhotoSystemMain {
    private static var appDelegate: AppDelegate?

    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        appDelegate = delegate
        app.delegate = delegate
        app.run()
    }
}
